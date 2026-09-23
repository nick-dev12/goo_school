"""
Actions mutantes de l’assistant vocal directeur.

Chaque outil prépare un brouillon (rien n’est écrit). L’écriture n’a lieu
qu’après confirmation explicite, via les mêmes contrôleurs / modèles que
les vues Django de l’espace directeur.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Callable

from django.db import transaction
from django.db.models import Q
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from school_admin.utils.frais_annexes import (
    extraire_frais_annexes_depuis_args,
    frais_annexes_actifs,
)

logger = logging.getLogger(__name__)

GUIDED_ACTIONS = {
    'creer_publier_annonce',
    'annonce_guidee',
    'creer_emploi_du_temps',
    'ajouter_creneau_emploi',
}

CONFIRM_CHOICES = [
    {'label': 'Oui, c’est bon', 'value': 'Oui, c’est bon.', 'intent': 'confirm'},
    {'label': 'Annuler', 'value': 'Annuler.', 'intent': 'cancel'},
]
DESTRUCTIVE_CHOICES = [
    {'label': 'Oui, confirmer', 'value': 'Oui, je confirme.', 'intent': 'confirm'},
    {'label': 'Annuler', 'value': 'Annuler.', 'intent': 'cancel'},
]


@dataclass(frozen=True)
class ActionSpec:
    name: str
    description: str
    properties: dict
    required: tuple = ()
    destructive: bool = False
    prepare: Callable = None
    apply: Callable = None
    choices: Callable = None


ACTION_SPECS: dict[str, ActionSpec] = {}


def register_action(spec: ActionSpec):
    ACTION_SPECS[spec.name] = spec
    return spec


def is_write_action(name):
    return name in ACTION_SPECS or name in GUIDED_ACTIONS


def get_action(name):
    return ACTION_SPECS.get(name)


def build_tool_schemas():
    schemas = []
    for spec in ACTION_SPECS.values():
        extra = ' Confirmation obligatoire avant toute écriture.'
        if spec.destructive:
            extra = ' Action destructive : confirmation obligatoire.'
        schemas.append({
            'type': 'function',
            'function': {
                'name': spec.name,
                'description': spec.description + extra,
                'parameters': {
                    'type': 'object',
                    'properties': spec.properties,
                    'required': list(spec.required),
                },
            },
        })
    return schemas


def _reverse(route, args=None):
    try:
        return reverse(route, args=args or [])
    except NoReverseMatch:
        return None


def _pending(action, resume, **extra):
    payload = {
        'statut': 'en_attente_confirmation',
        'action': action,
        'resume': resume,
        'message': 'Rien n’a encore été enregistré. Demande une confirmation explicite.',
    }
    payload.update(extra)
    return payload


def _incomplete(action, manquants, message, **extra):
    payload = {
        'statut': 'incomplet',
        'action': action,
        'manquants': list(manquants),
        'message': message,
    }
    payload.update(extra)
    return payload


def _ok(message, **extra):
    payload = {'statut': 'ok', 'message': message}
    payload.update(extra)
    return payload


def _emit(ctx, event_type, item=None, **extra):
    """Diffuse un événement Channels vers les pages directeur ouvertes."""
    from school_admin.services.realtime_helpers import emit_live

    etablissement = getattr(ctx, 'etablissement', None)
    if not etablissement:
        return
    payload = {'event': event_type}
    if item is not None:
        payload['item'] = item
    payload.update(extra)
    try:
        emit_live(etablissement.id, event_type, payload)
    except Exception:
        logger.exception('Émission temps réel assistant [%s]', event_type)
    return payload


def _err(message, **extra):
    payload = {'erreur': message}
    payload.update(extra)
    return payload


def _parse_date(raw):
    text = re.sub(r'\s+', ' ', (raw or '').strip())
    if not text:
        return None
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y', '%d %m %Y', '%d/%m/%y', '%d-%m-%y'):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    digits = re.fullmatch(r'(\d{1,2})\D+(\d{1,2})\D+(\d{2,4})', text)
    if digits:
        day, month, year = digits.groups()
        if len(year) == 2:
            year = '20' + year
        try:
            return datetime(int(year), int(month), int(day)).date()
        except ValueError:
            return None
    return None


def _parse_money(raw):
    text = str(raw or '').strip().replace(' ', '').replace(',', '.')
    if not text:
        return None
    try:
        value = Decimal(text)
    except (InvalidOperation, ValueError):
        return None
    if value <= 0:
        return None
    return value


def _find_eleve(ctx, query):
    from school_admin.services.assistant_tools import _find_eleve as finder

    return finder(ctx, query)


def _find_classe(ctx, query):
    from school_admin.services.assistant_tools import _find_classe as finder

    return finder(ctx, query)


def _find_annee(ctx, query):
    from school_admin.model.annee_scolaire_model import AnneeScolaire

    qs = AnneeScolaire.objects.filter(etablissement=ctx.etablissement)
    raw = (query or '').strip()
    if not raw:
        return qs.filter(est_active=True).first() or qs.order_by('-annee_debut').first()
    found = qs.filter(Q(libelle__icontains=raw) | Q(annee_debut__iexact=raw)).first()
    if found:
        return found
    digits = re.sub(r'\D', '', raw)
    if len(digits) == 4:
        return qs.filter(annee_debut=int(digits)).first()
    return None


def _find_periode(ctx, query):
    from school_admin.model.periode_model import PeriodeScolaire

    qs = PeriodeScolaire.objects.filter(etablissement=ctx.etablissement)
    if ctx.annee_scolaire:
        qs = qs.filter(
            Q(annee_scolaire_fk=ctx.annee_scolaire)
            | Q(annee_scolaire=ctx.annee_scolaire.libelle)
        )
    raw = (query or '').strip()
    if not raw:
        return PeriodeScolaire.get_periode_active(ctx.etablissement) or qs.order_by('date_debut').first()
    return qs.filter(
        Q(nom_periode__icontains=raw) | Q(type_periode__icontains=raw)
    ).first()


def _find_annonce(ctx, query):
    from school_admin.model.annonce_model import Annonce

    qs = Annonce.objects.filter(etablissement=ctx.etablissement, actif=True)
    raw = (query or '').strip()
    if not raw:
        return qs.order_by('-date_creation').first()
    if raw.isdigit():
        return qs.filter(pk=int(raw)).first()
    return qs.filter(titre__icontains=raw).order_by('-date_creation').first()


def _find_liaison(ctx, query):
    from school_admin.model.demande_liaison_model import DemandeLiaisonParent

    qs = DemandeLiaisonParent.objects.filter(
        Q(etablissement=ctx.etablissement)
        | Q(eleve_valide__etablissement=ctx.etablissement)
    ).select_related('parent_demandeur', 'eleve_valide')
    raw = (query or '').strip()
    if raw.isdigit():
        return qs.filter(pk=int(raw)).first()
    if raw:
        return qs.filter(
            Q(matricule_eleve__icontains=raw)
            | Q(nom_eleve__icontains=raw)
            | Q(prenom_eleve__icontains=raw)
            | Q(parent_demandeur__nom__icontains=raw)
            | Q(parent_demandeur__prenom__icontains=raw)
        ).order_by('-date_demande').first()
    return qs.filter(statut='en_attente').order_by('-date_demande').first()


def _find_preinscription(ctx, query):
    from school_admin.model.preinscription_model import PreinscriptionEleve

    qs = PreinscriptionEleve.objects.filter(etablissement=ctx.etablissement)
    raw = (query or '').strip()
    if raw.isdigit():
        return qs.filter(pk=int(raw)).first()
    if raw:
        return qs.filter(Q(nom__icontains=raw) | Q(prenom__icontains=raw)).order_by('-id').first()
    return qs.filter(statut='en_attente').order_by('-id').first()


def _find_absence(ctx, query):
    from school_admin.model.presence_model import Presence

    qs = Presence.objects.filter(
        etablissement=ctx.etablissement,
        statut='absent',
    ).select_related('eleve', 'classe')
    raw = (query or '').strip()
    if raw.isdigit():
        return qs.filter(pk=int(raw)).first()
    eleve = _find_eleve(ctx, raw) if raw else None
    if eleve:
        return qs.filter(eleve=eleve).order_by('-date').first()
    return qs.order_by('-date').first()


def _find_session_examen(ctx, query):
    from school_admin.model.session_examen_model import SessionExamen

    qs = SessionExamen.objects.filter(etablissement=ctx.etablissement)
    raw = (query or '').strip()
    if raw.isdigit():
        return qs.filter(pk=int(raw)).first()
    if raw:
        return qs.filter(nom_examen__icontains=raw).order_by('-date_creation').first()
    return qs.order_by('-date_creation').first()


def _find_salle(ctx, query):
    from school_admin.services.assistant_emploi import _find_salle as finder

    return finder(ctx, query)


def _find_matiere(ctx, query, classe=None):
    from school_admin.services.assistant_emploi import _find_matiere as finder

    return finder(ctx, query, classe=classe)


def _find_creneau(ctx, query, classe=None):
    from school_admin.model.emploi_du_temps_model import CreneauEmploiDuTemps

    raw = (query or '').strip()
    qs = CreneauEmploiDuTemps.objects.filter(
        emploi_du_temps__classe__etablissement=ctx.etablissement,
        emploi_du_temps__est_actif=True,
    ).select_related('emploi_du_temps', 'matiere', 'emploi_du_temps__classe')
    if classe:
        qs = qs.filter(emploi_du_temps__classe=classe)
    if raw.isdigit():
        return qs.filter(pk=int(raw)).first()
    if raw:
        return qs.filter(
            Q(matiere__nom__icontains=raw) | Q(jour__icontains=raw)
        ).first()
    return None


def _annonce_url(annonce_id):
    return _reverse('directeur:apercu_annonce', args=[annonce_id])


def default_choices(draft):
    if (draft or {}).get('statut') != 'en_attente_confirmation':
        return []
    if (draft or {}).get('destructive'):
        return list(DESTRUCTIVE_CHOICES)
    return list(CONFIRM_CHOICES)


def default_prompt(draft):
    data = draft or {}
    if data.get('statut') == 'incomplet':
        return data.get('message') or 'Il me manque encore des informations.'
    resume = data.get('resume') or 'cette action'
    return f"Je {resume}. C’est bon ?"


def is_action_ready(draft):
    return (draft or {}).get('statut') == 'en_attente_confirmation'


def next_action_prompt(name, draft):
    spec = get_action(name)
    if spec and getattr(spec, 'next_prompt', None):
        return spec.next_prompt(draft)
    return default_prompt(draft)


def choices_for_action(name, draft):
    spec = get_action(name)
    if spec and getattr(spec, 'choices', None):
        return spec.choices(draft)
    return default_choices(draft)


# ---------------------------------------------------------------------------
# Annonces (hors création guidée déjà existante)
# ---------------------------------------------------------------------------

def prepare_publier_annonce(ctx, args):
    annonce = _find_annonce(ctx, args.get('query') or args.get('titre'))
    if not annonce:
        return _incomplete('publier_annonce', ['query'], 'Quelle annonce dois-je publier ?')
    if annonce.statut == 'publiee':
        return _ok(
            f'L’annonce « {annonce.titre} » est déjà publiée.',
            id=annonce.id,
            url=_annonce_url(annonce.id),
        )
    return _pending(
        'publier_annonce',
        f'publie l’annonce « {annonce.titre} »',
        id=annonce.id,
        titre=annonce.titre,
        url=_annonce_url(annonce.id),
    )


def apply_publier_annonce(ctx, draft):
    from school_admin.model.annonce_model import Annonce

    annonce = Annonce.objects.filter(
        pk=draft.get('id'), etablissement=ctx.etablissement, actif=True
    ).first()
    if not annonce:
        return _err('Annonce introuvable.')
    if annonce.statut != 'brouillon':
        return _ok(f'L’annonce « {annonce.titre} » n’est pas un brouillon.', id=annonce.id)
    annonce.publier()
    _emit(ctx, 'annonce.mise_a_jour', {'id': annonce.id, 'action': 'publiee'})
    return _ok(
        f'Annonce publiée : {annonce.titre}.',
        id=annonce.id,
        url=_annonce_url(annonce.id),
    )


def prepare_archiver_annonce(ctx, args):
    annonce = _find_annonce(ctx, args.get('query') or args.get('titre'))
    if not annonce:
        return _incomplete('archiver_annonce', ['query'], 'Quelle annonce dois-je archiver ?')
    return _pending(
        'archiver_annonce',
        f'archive l’annonce « {annonce.titre} »',
        id=annonce.id,
        titre=annonce.titre,
        url=_annonce_url(annonce.id),
        destructive=True,
    )


def apply_archiver_annonce(ctx, draft):
    from school_admin.model.annonce_model import Annonce

    annonce = Annonce.objects.filter(
        pk=draft.get('id'), etablissement=ctx.etablissement, actif=True
    ).first()
    if not annonce:
        return _err('Annonce introuvable.')
    annonce.archiver()
    _emit(ctx, 'annonce.mise_a_jour', {'id': annonce.id, 'action': 'archivee'})
    return _ok(f'Annonce archivée : {annonce.titre}.', id=annonce.id, url=_annonce_url(annonce.id))


def prepare_supprimer_annonce(ctx, args):
    annonce = _find_annonce(ctx, args.get('query') or args.get('titre'))
    if not annonce:
        return _incomplete('supprimer_annonce', ['query'], 'Quelle annonce dois-je supprimer ?')
    return _pending(
        'supprimer_annonce',
        f'supprime définitivement l’annonce « {annonce.titre} »',
        id=annonce.id,
        titre=annonce.titre,
        destructive=True,
    )


def apply_supprimer_annonce(ctx, draft):
    from school_admin.model.annonce_model import Annonce

    annonce = Annonce.objects.filter(
        pk=draft.get('id'), etablissement=ctx.etablissement, actif=True
    ).first()
    if not annonce:
        return _err('Annonce introuvable.')
    titre = annonce.titre
    annonce_id = annonce.id
    if annonce.fichier_joint:
        annonce.fichier_joint.delete(save=False)
    annonce.actif = False
    annonce.save(update_fields=['actif'])
    _emit(ctx, 'annonce.mise_a_jour', {'id': annonce_id, 'action': 'supprimee'})
    return _ok(f'Annonce supprimée : {titre}.')


def prepare_modifier_annonce(ctx, args):
    annonce = _find_annonce(ctx, args.get('query') or args.get('titre'))
    if not annonce:
        return _incomplete('modifier_annonce', ['query'], 'Quelle annonce dois-je modifier ?')
    titre = (args.get('nouveau_titre') or '').strip() or annonce.titre
    contenu = (args.get('contenu') or '').strip() or annonce.contenu
    return _pending(
        'modifier_annonce',
        f'modifie l’annonce « {annonce.titre} »',
        id=annonce.id,
        titre=titre,
        contenu=contenu,
        url=_annonce_url(annonce.id),
    )


def apply_modifier_annonce(ctx, draft):
    from school_admin.model.annonce_model import Annonce

    annonce = Annonce.objects.filter(
        pk=draft.get('id'), etablissement=ctx.etablissement, actif=True
    ).first()
    if not annonce:
        return _err('Annonce introuvable.')
    annonce.titre = (draft.get('titre') or annonce.titre)[:255]
    annonce.contenu = draft.get('contenu') or annonce.contenu
    annonce.save(update_fields=['titre', 'contenu'])
    _emit(ctx, 'annonce.mise_a_jour', {'id': annonce.id, 'action': 'modifiee'})
    return _ok(
        f'Annonce mise à jour : {annonce.titre}.',
        id=annonce.id,
        url=_annonce_url(annonce.id),
    )


# ---------------------------------------------------------------------------
# Années scolaires
# ---------------------------------------------------------------------------

def prepare_creer_annee_scolaire(ctx, args):
    from school_admin.controllers.annee_scolaire_controller import AnneeScolaireController

    suggestions = AnneeScolaireController.get_annee_scolaire_suivante(ctx.etablissement)
    date_debut = _parse_date(args.get('date_debut')) or suggestions['date_debut']
    date_fin = _parse_date(args.get('date_fin')) or suggestions['date_fin']
    annee_debut = int(args.get('annee_debut') or date_debut.year)
    annee_fin = int(args.get('annee_fin') or (annee_debut + 1))
    libelle = (args.get('libelle') or '').strip() or AnneeScolaireController.generer_libelle_annee(annee_debut)
    return _pending(
        'creer_annee_scolaire',
        f'crée l’année scolaire {libelle}',
        libelle=libelle,
        annee_debut=annee_debut,
        annee_fin=annee_fin,
        date_debut=date_debut.isoformat(),
        date_fin=date_fin.isoformat(),
        est_ouverte=bool(args.get('est_ouverte', True)),
        url=_reverse('directeur:liste_annees_scolaires'),
    )


def apply_creer_annee_scolaire(ctx, draft):
    from school_admin.controllers.annee_scolaire_controller import AnneeScolaireController

    from school_admin.services.live_serializers import serialize_annee_scolaire_item

    annee = AnneeScolaireController.creer_annee_scolaire(
        etablissement=ctx.etablissement,
        libelle=draft['libelle'],
        annee_debut=int(draft['annee_debut']),
        annee_fin=int(draft['annee_fin']),
        date_debut=_parse_date(draft['date_debut']),
        date_fin=_parse_date(draft['date_fin']),
        est_ouverte=bool(draft.get('est_ouverte', True)),
    )
    _emit(ctx, 'annee_scolaire.creee', serialize_annee_scolaire_item(annee))
    return _ok(
        f'Année scolaire {annee.libelle} créée.',
        id=annee.id,
        url=_reverse('directeur:detail_annee_scolaire', args=[annee.id]),
    )


def prepare_activer_annee_scolaire(ctx, args):
    annee = _find_annee(ctx, args.get('query') or args.get('libelle'))
    if not annee:
        return _incomplete('activer_annee_scolaire', ['query'], 'Quelle année scolaire dois-je activer ?')
    if annee.est_active:
        return _ok(f'L’année {annee.libelle} est déjà active.', id=annee.id)
    return _pending(
        'activer_annee_scolaire',
        f'active l’année scolaire {annee.libelle} et initialise les structures',
        id=annee.id,
        libelle=annee.libelle,
        url=_reverse('directeur:detail_annee_scolaire', args=[annee.id]),
    )


def apply_activer_annee_scolaire(ctx, draft):
    from school_admin.controllers.annee_scolaire_controller import AnneeScolaireController
    from school_admin.model.annee_scolaire_model import AnneeScolaire

    annee = AnneeScolaire.objects.filter(
        pk=draft.get('id'), etablissement=ctx.etablissement
    ).first()
    if not annee:
        return _err('Année scolaire introuvable.')
    annee, stats = AnneeScolaireController.activer_annee_scolaire(
        ctx.etablissement, annee, initialiser=True
    )
    extra = ''
    if stats:
        extra = (
            f" Initialisation : {stats.get('classes_copiees', 0)} classes, "
            f"{stats.get('matieres_copiees', 0)} matières."
        )
    _emit(ctx, 'annee_scolaire.modifiee', {'id': annee.id, 'action': 'activee'})
    return _ok(
        f'Année scolaire {annee.libelle} activée.{extra}',
        id=annee.id,
        url=_reverse('directeur:dashboard_directeur'),
    )


def prepare_desactiver_annee_scolaire(ctx, args):
    annee = _find_annee(ctx, args.get('query') or args.get('libelle'))
    if not annee:
        return _incomplete('desactiver_annee_scolaire', ['query'], 'Quelle année dois-je désactiver ?')
    return _pending(
        'desactiver_annee_scolaire',
        f'désactive l’année scolaire {annee.libelle}',
        id=annee.id,
        libelle=annee.libelle,
        destructive=True,
    )


def apply_desactiver_annee_scolaire(ctx, draft):
    from school_admin.model.annee_scolaire_model import AnneeScolaire

    annee = AnneeScolaire.objects.filter(
        pk=draft.get('id'), etablissement=ctx.etablissement
    ).first()
    if not annee:
        return _err('Année scolaire introuvable.')
    annee.est_active = False
    annee.save(update_fields=['est_active'])
    _emit(ctx, 'annee_scolaire.modifiee', {'id': annee.id, 'action': 'desactivee'})
    return _ok(f'Année scolaire {annee.libelle} désactivée.', id=annee.id)


# ---------------------------------------------------------------------------
# Périodes
# ---------------------------------------------------------------------------

def prepare_creer_periode(ctx, args):
    if not ctx.annee_scolaire:
        return _err('Aucune année scolaire active. Créez et activez une année d’abord.')
    nom = (args.get('nom') or args.get('nom_periode') or '').strip()
    type_periode = (args.get('type_periode') or 'trimestre').strip()
    date_debut = _parse_date(args.get('date_debut'))
    date_fin = _parse_date(args.get('date_fin'))
    missing = []
    if not nom:
        missing.append('nom')
    if not date_debut:
        missing.append('date_debut')
    if not date_fin:
        missing.append('date_fin')
    if missing:
        return _incomplete(
            'creer_periode',
            missing,
            'Il me faut le nom de la période et les dates de début et de fin.',
            nom=nom,
            type_periode=type_periode,
        )
    return _pending(
        'creer_periode',
        f'crée la période {nom}',
        nom=nom,
        type_periode=type_periode,
        date_debut=date_debut.isoformat(),
        date_fin=date_fin.isoformat(),
        est_active=bool(args.get('est_active', True)),
        url=_reverse('directeur:gestion_periodes_scolaires'),
    )


def apply_creer_periode(ctx, draft):
    from school_admin.model.periode_model import PeriodeScolaire

    if not ctx.annee_scolaire:
        return _err('Aucune année scolaire active.')
    type_periode = draft.get('type_periode') or 'trimestre'
    if type_periode not in dict(PeriodeScolaire.TYPE_PERIODE_CHOICES):
        type_periode = 'trimestre'
    from school_admin.services.live_serializers import serialize_periode_item

    periode = PeriodeScolaire.objects.create(
        etablissement=ctx.etablissement,
        nom_periode=draft['nom'],
        type_periode=type_periode,
        date_debut=_parse_date(draft['date_debut']),
        date_fin=_parse_date(draft['date_fin']),
        annee_scolaire=ctx.annee_scolaire.libelle,
        annee_scolaire_fk=ctx.annee_scolaire,
        est_active=bool(draft.get('est_active', True)),
    )
    _emit(ctx, 'periode.creee', serialize_periode_item(periode))
    return _ok(
        f'Période « {periode.nom_periode} » créée pour {ctx.annee_scolaire.libelle}.',
        id=periode.id,
        url=_reverse('directeur:gestion_periodes_scolaires'),
    )


def prepare_activer_periode(ctx, args):
    periode = _find_periode(ctx, args.get('query') or args.get('nom'))
    if not periode:
        return _incomplete('activer_periode', ['query'], 'Quelle période dois-je activer ?')
    return _pending(
        'activer_periode',
        f'active la période {periode.nom_periode}',
        id=periode.id,
        nom=periode.nom_periode,
    )


def apply_activer_periode(ctx, draft):
    from school_admin.model.periode_model import PeriodeScolaire

    periode = PeriodeScolaire.objects.filter(
        pk=draft.get('id'), etablissement=ctx.etablissement
    ).first()
    if not periode:
        return _err('Période introuvable.')
    PeriodeScolaire.objects.filter(etablissement=ctx.etablissement).exclude(pk=periode.pk).update(
        est_active=False
    )
    from school_admin.services.live_serializers import serialize_periode_item

    periode.est_active = True
    periode.save(update_fields=['est_active'])
    _emit(ctx, 'periode.modifiee', serialize_periode_item(periode))
    return _ok(f'Période « {periode.nom_periode} » activée.', id=periode.id)


def prepare_supprimer_periode(ctx, args):
    periode = _find_periode(ctx, args.get('query') or args.get('nom'))
    if not periode:
        return _incomplete('supprimer_periode', ['query'], 'Quelle période dois-je supprimer ?')
    return _pending(
        'supprimer_periode',
        f'supprime la période {periode.nom_periode}',
        id=periode.id,
        nom=periode.nom_periode,
        destructive=True,
    )


def apply_supprimer_periode(ctx, draft):
    from school_admin.model.periode_model import PeriodeScolaire

    periode = PeriodeScolaire.objects.filter(
        pk=draft.get('id'), etablissement=ctx.etablissement
    ).first()
    if not periode:
        return _err('Période introuvable.')
    nom = periode.nom_periode
    periode_id = periode.id
    periode.delete()
    _emit(ctx, 'periode.supprimee', {'id': periode_id})
    return _ok(f'Période « {nom} » supprimée.')


# ---------------------------------------------------------------------------
# Présences
# ---------------------------------------------------------------------------

def prepare_justifier_absence(ctx, args):
    presence = _find_absence(ctx, args.get('query') or args.get('eleve'))
    if not presence:
        return _incomplete(
            'justifier_absence',
            ['query'],
            'Pour quel élève dois-je justifier une absence ?',
        )
    date_str = presence.date.strftime('%d/%m/%Y') if presence.date else ''
    return _pending(
        'justifier_absence',
        f'justifie l’absence de {presence.eleve.nom_complet} du {date_str}',
        id=presence.id,
        eleve=presence.eleve.nom_complet,
        date=date_str,
        url=_reverse('directeur:suivi_presence'),
    )


def apply_justifier_absence(ctx, draft):
    from school_admin.model.presence_model import Presence

    presence = Presence.objects.select_related('eleve', 'classe').filter(
        pk=draft.get('id'),
        etablissement=ctx.etablissement,
    ).first()
    if not presence:
        return _err('Absence introuvable.')
    if presence.statut != 'absent':
        return _err('Seules les absences non justifiées peuvent être converties.')
    presence.statut = 'present'
    presence.type_justificatif = None
    presence.justificatif_valide = True
    presence.date_justification = timezone.now()
    presence.save(update_fields=[
        'statut', 'type_justificatif', 'justificatif_valide',
        'date_justification', 'date_modification',
    ])
    date_str = presence.date.strftime('%d/%m/%Y') if presence.date else ''
    _emit(ctx, 'presence.mise_a_jour', {
        'id': presence.id,
        'eleve_id': presence.eleve_id,
        'classe_id': presence.classe_id,
        'action': 'justifiee',
    })
    return _ok(
        f'Absence du {date_str} justifiée pour {presence.eleve.nom_complet}.',
        id=presence.id,
        url=_reverse('directeur:suivi_presence'),
    )


# ---------------------------------------------------------------------------
# Liaisons parent-élève
# ---------------------------------------------------------------------------

def _liaison_resume(demande):
    parent = getattr(demande.parent_demandeur, 'nom_complet', '') if demande.parent_demandeur_id else ''
    eleve = ''
    if demande.eleve_valide_id:
        eleve = demande.eleve_valide.nom_complet
    else:
        eleve = f'{demande.prenom_eleve} {demande.nom_eleve}'.strip()
    return parent, eleve


def prepare_approuver_liaison(ctx, args):
    demande = _find_liaison(ctx, args.get('query'))
    if not demande:
        return _incomplete('approuver_liaison', ['query'], 'Quelle demande de liaison dois-je approuver ?')
    parent, eleve = _liaison_resume(demande)
    return _pending(
        'approuver_liaison',
        f'approuve la liaison entre {parent} et {eleve}',
        id=demande.id,
        url=_reverse('directeur:demandes_liaison_liste'),
    )


def apply_approuver_liaison(ctx, draft):
    from school_admin.model.demande_liaison_model import DemandeLiaisonParent
    from school_admin.model.lien_familial_model import LienFamilial

    demande = DemandeLiaisonParent.objects.select_related(
        'parent_demandeur', 'eleve_valide'
    ).filter(pk=draft.get('id')).first()
    if not demande or (
        demande.etablissement_id not in (None, ctx.etablissement.id)
        and getattr(demande.eleve_valide, 'etablissement_id', None) != ctx.etablissement.id
    ):
        if not demande:
            return _err('Demande de liaison introuvable.')
    parent, eleve = _liaison_resume(demande)
    if demande.eleve_valide_id:
        lien = LienFamilial.objects.filter(
            parent=demande.parent_demandeur,
            eleve=demande.eleve_valide,
        ).first()
        if lien:
            lien.actif = True
            lien.statut = 'valide'
            lien.save()
        else:
            demande.approuver(traite_par=None)
    demande.statut = 'approuvee'
    demande.date_traitement = timezone.now()
    demande.save()
    _emit(ctx, 'liaison.mise_a_jour', {'id': demande.id, 'action': 'approuvee'})
    return _ok(
        f'Liaison approuvée entre {parent} et {eleve}.',
        id=demande.id,
        url=_reverse('directeur:demandes_liaison_liste'),
    )


def prepare_rejeter_liaison(ctx, args):
    demande = _find_liaison(ctx, args.get('query'))
    if not demande:
        return _incomplete('rejeter_liaison', ['query'], 'Quelle demande de liaison dois-je rejeter ?')
    parent, eleve = _liaison_resume(demande)
    return _pending(
        'rejeter_liaison',
        f'rejette la liaison entre {parent} et {eleve}',
        id=demande.id,
        motif=(args.get('motif') or 'Demande refusée par l’établissement').strip(),
        destructive=True,
    )


def apply_rejeter_liaison(ctx, draft):
    from school_admin.model.demande_liaison_model import DemandeLiaisonParent

    demande = DemandeLiaisonParent.objects.select_related(
        'parent_demandeur', 'eleve_valide'
    ).filter(pk=draft.get('id')).first()
    if not demande:
        return _err('Demande de liaison introuvable.')
    motif = draft.get('motif') or 'Demande refusée par l’établissement'
    demande.refuser(traite_par=None, motif=motif)
    demande.statut = 'refusee'
    demande.motif_refus = motif
    demande.save()
    parent, eleve = _liaison_resume(demande)
    _emit(ctx, 'liaison.mise_a_jour', {'id': demande.id, 'action': 'rejetee'})
    return _ok(f'Demande de liaison rejetée ({parent} / {eleve}).', id=demande.id)


def prepare_desapprouver_liaison(ctx, args):
    demande = _find_liaison(ctx, args.get('query'))
    if not demande:
        return _incomplete(
            'desapprouver_liaison',
            ['query'],
            'Quelle liaison approuvée dois-je retirer ?',
        )
    parent, eleve = _liaison_resume(demande)
    return _pending(
        'desapprouver_liaison',
        f'retire la liaison entre {parent} et {eleve}',
        id=demande.id,
        destructive=True,
    )


def apply_desapprouver_liaison(ctx, draft):
    from school_admin.model.demande_liaison_model import DemandeLiaisonParent
    from school_admin.model.lien_familial_model import LienFamilial

    demande = DemandeLiaisonParent.objects.select_related(
        'parent_demandeur', 'eleve_valide'
    ).filter(pk=draft.get('id')).first()
    if not demande:
        return _err('Demande de liaison introuvable.')
    if demande.statut not in ('reussie', 'approuvee'):
        return _err('Cette demande n’a pas été approuvée.')
    if demande.eleve_valide_id:
        LienFamilial.objects.filter(
            parent=demande.parent_demandeur,
            eleve=demande.eleve_valide,
            actif=True,
        ).update(actif=False)
    demande.statut = 'en_attente'
    demande.date_traitement = None
    demande.save()
    parent, eleve = _liaison_resume(demande)
    _emit(ctx, 'liaison.mise_a_jour', {'id': demande.id, 'action': 'retiree'})
    return _ok(f'Liaison retirée entre {parent} et {eleve}.', id=demande.id)


# ---------------------------------------------------------------------------
# Préinscriptions
# ---------------------------------------------------------------------------

def prepare_valider_preinscription(ctx, args):
    dossier = _find_preinscription(ctx, args.get('query'))
    if not dossier:
        return _incomplete(
            'valider_preinscription',
            ['query'],
            'Quelle préinscription dois-je valider ?',
        )
    classe = dossier.classe_souhaitee
    classe_nom = args.get('classe')
    if classe_nom:
        found = _find_classe(ctx, classe_nom)
        if found:
            classe = found
    if not classe:
        return _incomplete(
            'valider_preinscription',
            ['classe'],
            'Dans quelle classe dois-je inscrire ce candidat ?',
            id=dossier.id,
            nom=f'{dossier.prenom} {dossier.nom}',
        )
    return _pending(
        'valider_preinscription',
        f'valide la préinscription de {dossier.prenom} {dossier.nom} en {classe.nom}',
        id=dossier.id,
        classe_id=classe.id,
        classe=classe.nom,
        url=_reverse('directeur:detail_preinscription', args=[dossier.id]),
    )


def apply_valider_preinscription(ctx, draft):
    from school_admin.model.classe_model import Classe
    from school_admin.model.preinscription_model import PreinscriptionEleve

    dossier = PreinscriptionEleve.objects.filter(
        pk=draft.get('id'), etablissement=ctx.etablissement
    ).first()
    if not dossier:
        return _err('Préinscription introuvable.')
    if dossier.statut != 'en_attente':
        return _err('Cette préinscription a déjà été traitée.')
    classe = Classe.objects.filter(
        pk=draft.get('classe_id'), etablissement=ctx.etablissement
    ).first() or dossier.classe_souhaitee
    if not classe:
        return _err('Classe d’affectation manquante.')
    eleve, _parent = dossier.valider(
        ctx.etablissement,
        commentaires='',
        documents={},
        classe=classe,
        statut_inscription=dossier.statut_inscription or 'nouvelle',
    )
    url = _reverse('secretaire:reçu_inscription_eleve', args=[eleve.id])
    _emit(ctx, 'preinscription.mise_a_jour', {
        'id': dossier.id,
        'eleve_id': eleve.id,
        'action': 'validee',
    })
    _emit(ctx, 'eleve.inscrit', {'id': eleve.id, 'classe_id': classe.id})
    return _ok(
        f'Préinscription validée. {eleve.nom_complet} est inscrit en {classe.nom}.',
        id=dossier.id,
        eleve_id=eleve.id,
        url=url,
    )


def prepare_rejeter_preinscription(ctx, args):
    dossier = _find_preinscription(ctx, args.get('query'))
    if not dossier:
        return _incomplete('rejeter_preinscription', ['query'], 'Quelle préinscription dois-je rejeter ?')
    return _pending(
        'rejeter_preinscription',
        f'rejette la préinscription de {dossier.prenom} {dossier.nom}',
        id=dossier.id,
        commentaires=(args.get('motif') or '').strip(),
        destructive=True,
    )


def apply_rejeter_preinscription(ctx, draft):
    from school_admin.model.preinscription_model import PreinscriptionEleve

    dossier = PreinscriptionEleve.objects.filter(
        pk=draft.get('id'), etablissement=ctx.etablissement
    ).first()
    if not dossier:
        return _err('Préinscription introuvable.')
    dossier.rejeter(ctx.etablissement, draft.get('commentaires') or '')
    _emit(ctx, 'preinscription.mise_a_jour', {'id': dossier.id, 'action': 'rejetee'})
    return _ok(f'Préinscription de {dossier.prenom} {dossier.nom} rejetée.', id=dossier.id)


def prepare_toggle_lien_preinscription(ctx, args):
    from school_admin.model.preinscription_model import LienPreinscription

    lien = LienPreinscription.objects.filter(etablissement=ctx.etablissement).order_by('-id').first()
    if not lien:
        return _err('Aucun lien de préinscription. Ouvrez la page des liens pour en créer un.')
    verbe = 'désactive' if lien.actif else 'active'
    return _pending(
        'toggle_lien_preinscription',
        f'{verbe} le lien de préinscription',
        id=lien.id,
        actif=not lien.actif,
        url=_reverse('directeur:gerer_liens_preinscription'),
    )


def apply_toggle_lien_preinscription(ctx, draft):
    from school_admin.model.preinscription_model import LienPreinscription

    lien = LienPreinscription.objects.filter(
        pk=draft.get('id'), etablissement=ctx.etablissement
    ).first()
    if not lien:
        return _err('Lien de préinscription introuvable.')
    lien.actif = bool(draft.get('actif'))
    lien.save(update_fields=['actif'])
    etat = 'activé' if lien.actif else 'désactivé'
    _emit(ctx, 'preinscription.mise_a_jour', {'id': lien.id, 'action': 'lien', 'actif': lien.actif})
    return _ok(f'Lien de préinscription {etat}.', id=lien.id)


# ---------------------------------------------------------------------------
# Bulletins
# ---------------------------------------------------------------------------

def prepare_publier_bulletins(ctx, args):
    classe = _find_classe(ctx, args.get('classe') or args.get('query'))
    if not classe:
        return _incomplete('publier_bulletins', ['classe'], 'Pour quelle classe dois-je publier les bulletins ?')
    periode = _find_periode(ctx, args.get('periode'))
    if not periode:
        return _err('Aucune période scolaire active.')
    return _pending(
        'publier_bulletins',
        f'publie les bulletins de {classe.nom} pour {periode.nom_periode}',
        classe_id=classe.id,
        classe=classe.nom,
        periode_id=periode.id,
        periode=periode.nom_periode,
        url=_reverse('directeur:bulletins_notes'),
    )


def apply_publier_bulletins(ctx, draft):
    from school_admin.model.moyenne_periode_model import MoyennePeriode

    qs = MoyennePeriode.objects.filter(
        etablissement=ctx.etablissement,
        periode_id=draft.get('periode_id'),
        est_moyenne_generale=True,
        eleve__classe_id=draft.get('classe_id'),
    )
    if ctx.annee_scolaire:
        qs = qs.filter(annee_scolaire=ctx.annee_scolaire)
    if not qs.exists():
        return _err(
            'Aucune moyenne générale calculée pour cette classe. '
            'Calculez d’abord les moyennes.'
        )
    publies = qs.update(est_publie=True, date_publication=timezone.now())
    _emit(ctx, 'bulletin.mise_a_jour', {
        'classe_id': draft.get('classe_id'),
        'periode_id': draft.get('periode_id'),
        'action': 'publie',
    })
    return _ok(
        f'{publies} bulletin(s) publié(s) pour {draft.get("classe")} ({draft.get("periode")}).',
        url=_reverse('directeur:bulletins_notes'),
    )


def prepare_calculer_moyennes_classe(ctx, args):
    classe = _find_classe(ctx, args.get('classe') or args.get('query'))
    if not classe:
        return _incomplete(
            'calculer_moyennes_classe',
            ['classe'],
            'Pour quelle classe dois-je calculer les moyennes ?',
        )
    periode = _find_periode(ctx, args.get('periode'))
    url = _reverse('directeur:calculer_moyennes_periode', args=[classe.id])
    if periode and url:
        url = f'{url}?periode={periode.id}'
    return _pending(
        'calculer_moyennes_classe',
        f'lance le calcul des moyennes de {classe.nom}',
        classe_id=classe.id,
        classe=classe.nom,
        periode_id=periode.id if periode else None,
        url=url,
        ouvrir=True,
    )


def apply_calculer_moyennes_classe(ctx, draft):
    """Ouvre la même action que le bouton directeur (calcul côté vue)."""
    url = _reverse('directeur:calculer_moyennes_periode', args=[draft.get('classe_id')])
    if draft.get('periode_id') and url:
        url = f'{url}?periode={draft["periode_id"]}'
    return _ok(
        f'J’ouvre le calcul des moyennes pour {draft.get("classe")}.',
        url=url,
        ouvrir=True,
    )


# ---------------------------------------------------------------------------
# Comptabilité
# ---------------------------------------------------------------------------

def prepare_enregistrer_paiement(ctx, args):
    from school_admin.model.comptabilite_eleve_model import FraisAnnexe, FraisInscription, Mensualite

    eleve = _find_eleve(ctx, args.get('query') or args.get('eleve'))
    if not eleve:
        return _incomplete('enregistrer_paiement', ['query'], 'Pour quel élève dois-je enregistrer un paiement ?')
    montant = _parse_money(args.get('montant'))
    type_paiement = (args.get('type_paiement') or args.get('type') or 'mensualite').strip()
    aliases = {
        'inscription': 'frais_inscription',
        'frais_inscription': 'frais_inscription',
        'mensualite': 'mensualite',
        'mensualité': 'mensualite',
        'annexe': 'frais_annexe',
        'frais_annexe': 'frais_annexe',
        'tenue': 'frais_annexe',
        'carte': 'frais_annexe',
        'assurance': 'frais_annexe',
        'dossier': 'frais_annexe',
        'examen': 'frais_annexe',
        'transport': 'frais_annexe',
        'cantine': 'frais_annexe',
        'apport': 'frais_annexe',
    }
    type_paiement = aliases.get(type_paiement.lower(), type_paiement or 'mensualite')
    mode = (args.get('mode_paiement') or 'especes').strip()
    extra = {}
    libelle = type_paiement
    if type_paiement == 'frais_annexe':
        code = (args.get('frais_annexe_code') or args.get('code') or args.get('frais') or type_paiement).strip()
        qs = FraisAnnexe.objects.filter(
            eleve=eleve,
            etablissement=ctx.etablissement,
            annee_scolaire=ctx.annee_scolaire,
        )
        frais = None
        if args.get('frais_annexe_id'):
            frais = qs.filter(pk=args['frais_annexe_id']).first()
        if frais is None and code and code not in ('frais_annexe', 'annexe'):
            frais = qs.filter(code__iexact=code).first() or qs.filter(libelle__icontains=code).first()
        if frais is None:
            frais = qs.exclude(statut='paye').order_by('libelle').first()
        if not frais:
            return _err('Aucun frais annexe à payer pour cet élève. Configure-les d’abord dans les paramètres.')
        extra['frais_annexe_id'] = frais.id
        extra['frais_annexe_code'] = frais.code
        libelle = frais.libelle
    elif type_paiement == 'frais_inscription':
        frais = FraisInscription.objects.filter(
            eleve=eleve, etablissement=ctx.etablissement, annee_scolaire=ctx.annee_scolaire,
        ).first()
        if frais:
            extra['frais_inscription_id'] = frais.id
            libelle = 'frais d’inscription'
    elif type_paiement == 'mensualite':
        periode = (args.get('periode') or args.get('mois') or '').strip()
        qs = Mensualite.objects.filter(
            eleve=eleve, etablissement=ctx.etablissement, annee_scolaire=ctx.annee_scolaire,
        )
        mensualite = qs.filter(periode__icontains=periode).first() if periode else None
        if mensualite is None:
            mensualite = qs.exclude(statut='paye').order_by('annee', 'mois').first()
        if mensualite:
            extra['mensualite_id'] = mensualite.id
            libelle = mensualite.periode
    if not montant:
        return _incomplete(
            'enregistrer_paiement',
            ['montant'],
            f'Quel montant dois-je enregistrer pour {eleve.nom_complet} ?',
            query=eleve.nom_complet,
            eleve_id=eleve.id,
            type_paiement=type_paiement,
            mode_paiement=mode,
            **extra,
        )
    return _pending(
        'enregistrer_paiement',
        f'enregistre un paiement de {montant} ({libelle}) pour {eleve.nom_complet}',
        eleve_id=eleve.id,
        eleve=eleve.nom_complet,
        montant=str(montant),
        type_paiement=type_paiement,
        mode_paiement=mode,
        url=_reverse('directeur:details_comptabilite_eleve_directeur', args=[eleve.id]),
        **extra,
    )


def apply_enregistrer_paiement(ctx, draft):
    from school_admin.model.comptabilite_eleve_model import (
        ComptabiliteEleve,
        FraisAnnexe,
        FraisInscription,
        Mensualite,
        PaiementEleve,
    )
    from school_admin.model.eleve_model import Eleve

    if not ctx.annee_scolaire:
        return _err('Aucune année scolaire active.')
    eleve = Eleve.objects.filter(
        pk=draft.get('eleve_id'), etablissement=ctx.etablissement, actif=True
    ).first()
    if not eleve:
        return _err('Élève introuvable.')
    montant = _parse_money(draft.get('montant'))
    if not montant:
        return _err('Montant invalide.')
    type_paiement = draft.get('type_paiement') or 'mensualite'
    mode = draft.get('mode_paiement') or 'especes'
    fiche = ComptabiliteEleve.objects.filter(
        eleve=eleve,
        etablissement=ctx.etablissement,
        annee_scolaire=ctx.annee_scolaire,
    ).first()
    frais = None
    mensualite = None
    frais_annexe = None
    if type_paiement == 'frais_annexe':
        qs = FraisAnnexe.objects.filter(
            eleve=eleve, etablissement=ctx.etablissement, annee_scolaire=ctx.annee_scolaire,
        )
        if draft.get('frais_annexe_id'):
            frais_annexe = qs.filter(pk=draft['frais_annexe_id']).first()
        if frais_annexe is None:
            frais_annexe = qs.exclude(statut='paye').order_by('libelle').first()
        if not frais_annexe:
            return _err('Aucun frais annexe à payer pour cet élève.')
        reste = frais_annexe.get_reste_a_payer()
        if montant > reste:
            return _err(f'Le montant dépasse le reste à payer ({reste}).')
        frais_annexe.ajouter_paiement(montant)
        type_paiement = 'frais_annexe'
    elif type_paiement == 'frais_inscription' and fiche:
        frais = FraisInscription.objects.filter(
            comptabilite_eleve=fiche,
            annee_scolaire=ctx.annee_scolaire,
            statut__in=['en_attente', 'en_retard'],
        ).order_by('date_echeance').first()
        if draft.get('frais_inscription_id'):
            frais = FraisInscription.objects.filter(
                pk=draft['frais_inscription_id'], eleve=eleve, etablissement=ctx.etablissement,
            ).first() or frais
        if frais:
            reste = frais.get_reste_a_payer()
            if montant > reste:
                return _err(f'Le montant dépasse le reste à payer ({reste}).')
            frais.ajouter_paiement(montant)
    elif fiche:
        mensualite = Mensualite.objects.filter(
            comptabilite_eleve=fiche,
            annee_scolaire=ctx.annee_scolaire,
            statut__in=['en_attente', 'en_retard', 'impaye'],
        ).order_by('date_echeance').first()
        if draft.get('mensualite_id'):
            mensualite = Mensualite.objects.filter(
                pk=draft['mensualite_id'], eleve=eleve, etablissement=ctx.etablissement,
            ).first() or mensualite
        if mensualite:
            reste = mensualite.get_reste_a_payer()
            if montant > reste:
                return _err(f'Le montant dépasse le reste à payer ({reste}).')
            mensualite.ajouter_paiement(montant)
            type_paiement = 'mensualite'
    with transaction.atomic():
        PaiementEleve.objects.create(
            eleve=eleve,
            etablissement=ctx.etablissement,
            annee_scolaire=ctx.annee_scolaire,
            type_paiement=type_paiement,
            frais_inscription=frais,
            mensualite=mensualite,
            frais_annexe=frais_annexe,
            montant=montant,
            mode_paiement=mode,
            notes='Enregistré par l’assistante vocale Aria',
        )
        if fiche:
            fiche.verifier_statut_paiement()
    from school_admin.services.live_serializers import (
        serialize_comptabilite_eleve_snapshot,
        serialize_comptabilite_paiement_result,
    )

    message = f'Paiement de {montant} enregistré pour {eleve.nom_complet}.'
    devise = getattr(ctx.etablissement, 'devise_monnaie', None) or 'FCFA'
    snapshot = serialize_comptabilite_eleve_snapshot(
        eleve.id, ctx.etablissement, ctx.annee_scolaire, devise
    )
    live_item = serialize_comptabilite_paiement_result(eleve.id, message, snapshot=snapshot)
    _emit(ctx, 'comptabilite.mise_a_jour', live_item)
    return _ok(
        message,
        eleve_id=eleve.id,
        url=_reverse('directeur:details_comptabilite_eleve_directeur', args=[eleve.id]),
    )


def _parse_groupes_classes(raw):
    if raw is None:
        return []
    if isinstance(raw, (list, tuple)):
        return [str(item).strip() for item in raw if str(item).strip()]
    text = str(raw).strip()
    if not text:
        return []
    return [part.strip() for part in re.split(r'[,;/]| et ', text) if part.strip()]


def _serialize_parametre_groupe(parametre):
    actifs = frais_annexes_actifs(getattr(parametre, 'frais_annexes', None))
    return {
        'id': parametre.id,
        'nom': parametre.nom,
        'groupes': list(parametre.groupes_classes or []),
        'type_facturation': parametre.type_facturation,
        'montant_frais_inscription': str(parametre.montant_frais_inscription or '0'),
        'montant_mensualite': str(parametre.montant_mensualite or '0'),
        'montant_frais_reinscription': str(parametre.montant_frais_reinscription or '0'),
        'jour_versement': parametre.jour_versement,
        'frais_annexes': [
            {
                'code': item['code'],
                'libelle': item['libelle'],
                'montant': item['montant'],
                'actif': item['actif'],
                'periodicite': item['periodicite'],
                'periodicite_display': item['periodicite_display'],
            }
            for item in actifs
        ],
        'url': _reverse('directeur:parametres_comptabilite_directeur'),
    }


def prepare_creer_parametres_comptabilite(ctx, args):
    from school_admin.model.parametres_comptabilite_groupe_classe_model import (
        ParametresComptabiliteGroupeClasse,
    )

    if not ctx.etablissement.module_comptabilite:
        return _err('Le module comptabilité n’est pas activé pour cet établissement.')
    nom = (args.get('nom') or '').strip()
    groupes = _parse_groupes_classes(args.get('groupes_classes') or args.get('groupes') or args.get('classe'))
    disponibles = ParametresComptabiliteGroupeClasse.get_groupes_disponibles(ctx.etablissement)
    deja = set(ParametresComptabiliteGroupeClasse.get_groupes_deja_assignes(ctx.etablissement))
    if not nom:
        return _incomplete(
            'creer_parametres_comptabilite',
            ['nom'],
            'Quel nom dois-je donner à ces paramètres de comptabilité ?',
            groupes_disponibles=disponibles,
            groupes_deja_assignes=sorted(deja),
        )
    if not groupes:
        return _incomplete(
            'creer_parametres_comptabilite',
            ['groupes_classes'],
            'Quels groupes de classes dois-je paramétrer ? '
            f'Disponibles : {", ".join(disponibles) or "aucun"}.',
            nom=nom,
            groupes_disponibles=disponibles,
            groupes_deja_assignes=sorted(deja),
        )
    inconnus = [g for g in groupes if g not in disponibles]
    if inconnus:
        return _incomplete(
            'creer_parametres_comptabilite',
            ['groupes_classes'],
            f'Groupe(s) inconnu(s) : {", ".join(inconnus)}. '
            f'Disponibles : {", ".join(disponibles)}.',
            nom=nom,
            groupes_disponibles=disponibles,
        )
    conflits = [g for g in groupes if g in deja]
    if conflits:
        return _err(
            f'Ces groupes ont déjà des paramètres : {", ".join(conflits)}.',
            groupes_deja_assignes=sorted(deja),
        )
    inscription = _parse_money(args.get('montant_frais_inscription')) or Decimal('0.00')
    mensualite = _parse_money(args.get('montant_mensualite')) or Decimal('0.00')
    reinscription = _parse_money(args.get('montant_frais_reinscription')) or Decimal('0.00')
    type_facturation = (args.get('type_facturation') or 'mensuel').strip()
    if type_facturation not in ('mensuel', 'annuel'):
        type_facturation = 'mensuel'
    jour_versement = int(args.get('jour_versement') or 5)
    frais_annexes = extraire_frais_annexes_depuis_args(args, None)
    return _pending(
        'creer_parametres_comptabilite',
        f'crée les paramètres « {nom} » pour {", ".join(groupes)}',
        nom=nom,
        groupes_classes=groupes,
        montant_frais_inscription=str(inscription),
        montant_mensualite=str(mensualite),
        montant_frais_reinscription=str(reinscription),
        type_facturation=type_facturation,
        jour_versement=jour_versement,
        frais_annexes=frais_annexes,
        url=_reverse('directeur:parametres_comptabilite_directeur'),
    )


def apply_creer_parametres_comptabilite(ctx, draft):
    from school_admin.model.parametres_comptabilite_groupe_classe_model import (
        ParametresComptabiliteGroupeClasse,
    )

    if not ctx.etablissement.module_comptabilite:
        return _err('Le module comptabilité n’est pas activé pour cet établissement.')
    nom = (draft.get('nom') or '').strip()
    groupes = _parse_groupes_classes(draft.get('groupes_classes'))
    if not nom or not groupes:
        return _err('Nom et groupes de classes sont obligatoires.')
    deja = set(ParametresComptabiliteGroupeClasse.get_groupes_deja_assignes(ctx.etablissement))
    if set(groupes) & deja:
        return _err(f'Groupes déjà paramétrés : {", ".join(sorted(set(groupes) & deja))}.')
    parametre = ParametresComptabiliteGroupeClasse.objects.create(
        etablissement=ctx.etablissement,
        nom=nom,
        groupes_classes=groupes,
        montant_frais_inscription=Decimal(draft.get('montant_frais_inscription') or '0'),
        montant_frais_reinscription=Decimal(draft.get('montant_frais_reinscription') or '0'),
        montant_mensualite=Decimal(draft.get('montant_mensualite') or '0'),
        montant_facturation_annuelle=Decimal(draft.get('montant_facturation_annuelle') or '0'),
        type_facturation=draft.get('type_facturation') or 'mensuel',
        jour_versement=int(draft.get('jour_versement') or 5),
        paiement_en_avance=bool(draft.get('paiement_en_avance')),
        autoriser_retards=True,
        autoriser_paiements_partiels=True,
        delai_tolerance_retard=15,
        envoyer_rappels_automatiques=True,
        mois_debut_facturation=9,
        mois_fin_facturation=6,
        frais_annexes=draft.get('frais_annexes') or extraire_frais_annexes_depuis_args(draft, None),
    )
    try:
        parametre.mettre_a_jour_systeme_comptabilite()
    except Exception as exc:
        logger.warning('Mise à jour comptabilité après création paramètres : %s', exc)
    from school_admin.services.live_serializers import serialize_parametres_groupe_classe

    _emit(
        ctx,
        'comptabilite.parametres',
        serialize_parametres_groupe_classe(parametre, ctx.etablissement, action='created'),
    )
    return _ok(
        f'Paramètres « {parametre.nom} » créés pour {", ".join(groupes)}.',
        **_serialize_parametre_groupe(parametre),
    )


def _find_parametre_groupe(ctx, query):
    from school_admin.model.parametres_comptabilite_groupe_classe_model import (
        ParametresComptabiliteGroupeClasse,
    )

    text = (query or '').strip()
    qs = ParametresComptabiliteGroupeClasse.objects.filter(etablissement=ctx.etablissement)
    if not text:
        return qs.first() if qs.count() == 1 else None
    lowered = text.lower()
    if lowered in ('premier', 'premiere', 'première', '1', '1er', '1ère', 'first'):
        return qs.order_by('pk').first()
    if lowered in ('dernier', 'derniere', 'dernière', 'last'):
        return qs.order_by('-pk').first()
    if text.isdigit():
        found = qs.filter(pk=int(text)).first()
        if found:
            return found
    found = qs.filter(nom__iexact=text).first()
    if found:
        return found
    found = qs.filter(nom__icontains=text).first()
    if found:
        return found
    for parametre in qs:
        if text in (parametre.groupes_classes or []):
            return parametre
    return None


def prepare_modifier_parametres_comptabilite(ctx, args):
    parametre = _find_parametre_groupe(ctx, args.get('query') or args.get('nom'))
    if not parametre:
        return _incomplete(
            'modifier_parametres_comptabilite',
            ['query'],
            'Quels paramètres de comptabilité dois-je modifier (nom ou groupe) ?',
        )
    groupes = _parse_groupes_classes(args.get('groupes_classes') or args.get('groupes')) or list(
        parametre.groupes_classes or []
    )
    return _pending(
        'modifier_parametres_comptabilite',
        f'modifie les paramètres « {parametre.nom} »',
        id=parametre.id,
        nom=(args.get('nouveau_nom') or args.get('nom') or parametre.nom).strip(),
        groupes_classes=groupes,
        montant_frais_inscription=str(
            _parse_money(args.get('montant_frais_inscription')) or parametre.montant_frais_inscription or Decimal('0')
        ),
        montant_mensualite=str(
            _parse_money(args.get('montant_mensualite')) or parametre.montant_mensualite or Decimal('0')
        ),
        montant_frais_reinscription=str(
            _parse_money(args.get('montant_frais_reinscription'))
            or parametre.montant_frais_reinscription
            or Decimal('0')
        ),
        type_facturation=args.get('type_facturation') or parametre.type_facturation,
        jour_versement=int(args.get('jour_versement') or parametre.jour_versement or 5),
        frais_annexes=extraire_frais_annexes_depuis_args(args, getattr(parametre, 'frais_annexes', None)),
        url=_reverse('directeur:modifier_parametres_groupe_directeur', args=[parametre.id]),
    )


def apply_modifier_parametres_comptabilite(ctx, draft):
    from school_admin.model.parametres_comptabilite_groupe_classe_model import (
        ParametresComptabiliteGroupeClasse,
    )

    parametre = ParametresComptabiliteGroupeClasse.objects.filter(
        pk=draft.get('id'), etablissement=ctx.etablissement
    ).first()
    if not parametre:
        return _err('Paramètres introuvables.')
    parametre.nom = (draft.get('nom') or parametre.nom).strip()
    groupes = _parse_groupes_classes(draft.get('groupes_classes'))
    if groupes:
        parametre.groupes_classes = groupes
    if draft.get('montant_frais_inscription') is not None:
        parametre.montant_frais_inscription = Decimal(draft['montant_frais_inscription'])
    if draft.get('montant_mensualite') is not None:
        parametre.montant_mensualite = Decimal(draft['montant_mensualite'])
    if draft.get('montant_frais_reinscription') is not None:
        parametre.montant_frais_reinscription = Decimal(draft['montant_frais_reinscription'])
    if draft.get('type_facturation'):
        parametre.type_facturation = draft['type_facturation']
    if draft.get('jour_versement'):
        parametre.jour_versement = int(draft['jour_versement'])
    if draft.get('frais_annexes') is not None:
        parametre.frais_annexes = draft['frais_annexes']
    parametre.save()
    try:
        parametre.mettre_a_jour_systeme_comptabilite()
    except Exception as exc:
        logger.warning('Mise à jour comptabilité après modification paramètres : %s', exc)
    from school_admin.services.live_serializers import serialize_parametres_groupe_classe

    _emit(
        ctx,
        'comptabilite.parametres',
        serialize_parametres_groupe_classe(parametre, ctx.etablissement, action='updated'),
    )
    return _ok(
        f'Paramètres « {parametre.nom} » mis à jour.',
        **_serialize_parametre_groupe(parametre),
    )


def prepare_supprimer_parametres_comptabilite(ctx, args):
    parametre = _find_parametre_groupe(ctx, args.get('query') or args.get('nom'))
    if not parametre:
        return _incomplete(
            'supprimer_parametres_comptabilite',
            ['query'],
            'Quels paramètres de comptabilité dois-je supprimer ?',
        )
    return _pending(
        'supprimer_parametres_comptabilite',
        f'supprime les paramètres « {parametre.nom} »',
        id=parametre.id,
        nom=parametre.nom,
        url=_reverse('directeur:parametres_comptabilite_directeur'),
        destructive=True,
    )


def apply_supprimer_parametres_comptabilite(ctx, draft):
    from school_admin.model.parametres_comptabilite_groupe_classe_model import (
        ParametresComptabiliteGroupeClasse,
    )

    parametre = ParametresComptabiliteGroupeClasse.objects.filter(
        pk=draft.get('id'), etablissement=ctx.etablissement
    ).first()
    if not parametre:
        return _err('Paramètres introuvables.')
    nom = parametre.nom
    deleted_id = parametre.id
    parametre.delete()
    from school_admin.services.live_serializers import serialize_parametres_groupe_deleted

    _emit(
        ctx,
        'comptabilite.parametres',
        serialize_parametres_groupe_deleted(deleted_id, ctx.etablissement),
    )
    return _ok(
        f'Paramètres « {nom} » supprimés.',
        url=_reverse('directeur:parametres_comptabilite_directeur'),
    )


# ---------------------------------------------------------------------------
# Examens
# ---------------------------------------------------------------------------

def prepare_creer_session_examen(ctx, args):
    if not ctx.annee_scolaire:
        return _err('Aucune année scolaire active.')
    nom = (args.get('nom') or args.get('nom_examen') or '').strip()
    periode = _find_periode(ctx, args.get('periode'))
    date_debut = _parse_date(args.get('date_debut'))
    date_fin = _parse_date(args.get('date_fin'))
    missing = []
    if not nom:
        missing.append('nom')
    if not periode:
        missing.append('periode')
    if not date_debut:
        missing.append('date_debut')
    if not date_fin:
        missing.append('date_fin')
    if missing:
        return _incomplete(
            'creer_session_examen',
            missing,
            'Il me faut le nom, la période et les dates de la session d’examen.',
            nom=nom,
        )
    return _pending(
        'creer_session_examen',
        f'crée la session d’examen « {nom} »',
        nom=nom,
        periode_id=periode.id,
        periode=periode.nom_periode,
        date_debut=date_debut.isoformat(),
        date_fin=date_fin.isoformat(),
        description=(args.get('description') or '').strip(),
        url=_reverse('directeur:gestion_examens'),
    )


def apply_creer_session_examen(ctx, draft):
    from school_admin.model.periode_model import PeriodeScolaire
    from school_admin.model.session_examen_model import SessionExamen

    periode = PeriodeScolaire.objects.filter(
        pk=draft.get('periode_id'), etablissement=ctx.etablissement
    ).first()
    if not periode:
        return _err('Période introuvable.')
    session = SessionExamen.objects.create(
        nom_examen=draft['nom'],
        etablissement=ctx.etablissement,
        periode=periode,
        date_debut=_parse_date(draft['date_debut']),
        date_fin=_parse_date(draft['date_fin']),
        description=draft.get('description') or None,
        annee_scolaire=ctx.annee_scolaire,
    )
    _emit(ctx, 'examen.mise_a_jour', {'id': session.id, 'action': 'creee'})
    return _ok(
        f'Session d’examen « {session.nom_examen} » créée.',
        id=session.id,
        url=_reverse('directeur:gestion_examens'),
    )


def prepare_supprimer_session_examen(ctx, args):
    session = _find_session_examen(ctx, args.get('query') or args.get('nom'))
    if not session:
        return _incomplete('supprimer_session_examen', ['query'], 'Quelle session d’examen dois-je supprimer ?')
    return _pending(
        'supprimer_session_examen',
        f'supprime la session « {session.nom_examen} » et ses créneaux',
        id=session.id,
        nom=session.nom_examen,
        destructive=True,
    )


def apply_supprimer_session_examen(ctx, draft):
    from school_admin.model.session_examen_model import SessionExamen

    session = SessionExamen.objects.filter(
        pk=draft.get('id'), etablissement=ctx.etablissement
    ).first()
    if not session:
        return _err('Session d’examen introuvable.')
    nom = session.nom_examen
    session_id = session.id
    nb = session.creneaux.count()
    session.delete()
    _emit(ctx, 'examen.mise_a_jour', {'id': session_id, 'action': 'supprimee'})
    return _ok(f'Session « {nom} » et {nb} créneau(x) supprimé(s).')


# ---------------------------------------------------------------------------
# Classes / salles / matières
# ---------------------------------------------------------------------------

def prepare_creer_classe(ctx, args):
    from school_admin.services.assistant_schema import resolve_niveau_classe

    nom = (args.get('nom') or args.get('query') or '').strip()
    niveau = resolve_niveau_classe(ctx, args)
    if not nom:
        return _incomplete('creer_classe', ['nom'], 'Quel nom pour la nouvelle classe ?')
    if not niveau:
        return _incomplete(
            'creer_classe',
            ['cycle'],
            'Cette classe est-elle de collège ou de lycée ?',
            nom=nom,
            capacite=args.get('capacite') or args.get('capacite_max') or 30,
        )
    capacite = int(args.get('capacite') or args.get('capacite_max') or 30)
    return _pending(
        'creer_classe',
        f'crée la classe {nom}',
        nom=nom,
        niveau=niveau,
        cycle=niveau,
        capacite_max=capacite,
        url=_reverse('administrateur_etablissement:liste_classes'),
    )


def apply_creer_classe(ctx, draft):
    from school_admin.controllers.classe_controller import ClasseController
    from school_admin.model.classe_model import Classe

    from school_admin.services.assistant_schema import normalize_cycle

    nom = (draft.get('nom') or '').strip()
    niveau = normalize_cycle(draft.get('niveau') or draft.get('cycle'))
    if not niveau:
        return _err('Indiquez le cycle de la classe (collège ou lycée).')
    if Classe.objects.filter(nom=nom, etablissement=ctx.etablissement, niveau=niveau).exists():
        return _err(f'Une classe « {nom} » existe déjà.')
    code = ClasseController.generate_code_classe(nom, niveau, ctx.etablissement)
    classe = Classe.objects.create(
        nom=nom,
        niveau=niveau,
        code_classe=code,
        capacite_max=int(draft.get('capacite_max') or 30),
        etablissement=ctx.etablissement,
    )
    est_superieur = ctx.etablissement.type_etablissement == 'superieur'
    item = ClasseController._serialize_classe_liste_item(classe, est_superieur, 0)
    ClasseController._emit_classe_realtime(
        ctx.etablissement.id,
        'classe.creee',
        {'event': 'classe.creee', 'item': item},
    )
    return _ok(
        f'Classe {classe.nom} créée.',
        id=classe.id,
        url=_reverse('administrateur_etablissement:detail_classe', args=[classe.id]),
    )


def prepare_desactiver_classe(ctx, args):
    classe = _find_classe(ctx, args.get('query') or args.get('classe'))
    if not classe:
        return _incomplete('desactiver_classe', ['query'], 'Quelle classe dois-je activer ou désactiver ?')
    verbe = 'désactive' if classe.actif else 'réactive'
    return _pending(
        'desactiver_classe',
        f'{verbe} la classe {classe.nom}',
        id=classe.id,
        nom=classe.nom,
        actif=not classe.actif,
    )


def apply_desactiver_classe(ctx, draft):
    from school_admin.model.classe_model import Classe

    classe = Classe.objects.filter(
        pk=draft.get('id'), etablissement=ctx.etablissement
    ).first()
    if not classe:
        return _err('Classe introuvable.')
    from school_admin.controllers.classe_controller import ClasseController

    classe.actif = bool(draft.get('actif'))
    classe.save(update_fields=['actif'])
    etat = 'activée' if classe.actif else 'désactivée'
    est_superieur = ctx.etablissement.type_etablissement == 'superieur'
    item = ClasseController._serialize_classe_liste_item(classe, est_superieur, 0)
    ClasseController._emit_classe_realtime(
        ctx.etablissement.id,
        'classe.modifiee',
        {'event': 'classe.modifiee', 'item': item},
    )
    return _ok(f'Classe {classe.nom} {etat}.', id=classe.id)


def prepare_supprimer_classe(ctx, args):
    classe = _find_classe(ctx, args.get('query') or args.get('classe'))
    if not classe:
        return _incomplete('supprimer_classe', ['query'], 'Quelle classe dois-je supprimer ?')
    return _pending(
        'supprimer_classe',
        f'supprime la classe {classe.nom}',
        id=classe.id,
        nom=classe.nom,
        destructive=True,
    )


def apply_supprimer_classe(ctx, draft):
    from school_admin.model.classe_model import Classe

    classe = Classe.objects.filter(
        pk=draft.get('id'), etablissement=ctx.etablissement
    ).first()
    if not classe:
        return _err('Classe introuvable.')
    from school_admin.controllers.classe_controller import ClasseController

    nom = classe.nom
    classe_id = classe.id
    classe.delete()
    ClasseController._emit_classe_realtime(
        ctx.etablissement.id,
        'classe.supprimee',
        {'event': 'classe.supprimee', 'item': {'id': classe_id}},
    )
    return _ok(f'Classe {nom} supprimée.')


def prepare_creer_salle(ctx, args):
    nom = (args.get('nom') or args.get('query') or '').strip()
    numero = (args.get('numero') or nom or '').strip()
    if not nom or not numero:
        return _incomplete('creer_salle', ['nom', 'numero'], 'Quel nom et quel numéro pour la salle ?')
    return _pending(
        'creer_salle',
        f'crée la salle {nom} ({numero})',
        nom=nom,
        numero=numero,
        type_salle=(args.get('type_salle') or 'classe').strip(),
        capacite_max=int(args.get('capacite') or 30),
        url=_reverse('salle:liste_salles'),
    )


def apply_creer_salle(ctx, draft):
    from school_admin.model.salle_model import Salle

    if Salle.objects.filter(etablissement=ctx.etablissement, numero=draft['numero']).exists():
        return _err(f'Une salle numéro {draft["numero"]} existe déjà.')
    type_salle = draft.get('type_salle') or 'classe'
    if type_salle not in dict(Salle.TYPE_SALLE_CHOICES):
        type_salle = 'classe'
    from school_admin.controllers.salle_controller import SalleController

    salle = Salle.objects.create(
        nom=draft['nom'],
        numero=draft['numero'],
        type_salle=type_salle,
        capacite_max=int(draft.get('capacite_max') or 30),
        etablissement=ctx.etablissement,
    )
    _emit(ctx, 'salle.creee', SalleController._serialize_salle_item(salle))
    return _ok(f'Salle {salle.nom} créée.', id=salle.id, url=_reverse('salle:liste_salles'))


def prepare_desactiver_salle(ctx, args):
    salle = _find_salle(ctx, args.get('query') or args.get('nom'))
    if not salle:
        return _incomplete('desactiver_salle', ['query'], 'Quelle salle dois-je activer ou désactiver ?')
    verbe = 'désactive' if salle.actif else 'réactive'
    return _pending(
        'desactiver_salle',
        f'{verbe} la salle {salle.nom}',
        id=salle.id,
        nom=salle.nom,
        actif=not salle.actif,
    )


def apply_desactiver_salle(ctx, draft):
    from school_admin.model.salle_model import Salle

    salle = Salle.objects.filter(pk=draft.get('id'), etablissement=ctx.etablissement).first()
    if not salle:
        return _err('Salle introuvable.')
    from school_admin.controllers.salle_controller import SalleController

    salle.actif = bool(draft.get('actif'))
    salle.save(update_fields=['actif'])
    etat = 'activée' if salle.actif else 'désactivée'
    _emit(ctx, 'salle.modifiee', SalleController._serialize_salle_item(salle))
    return _ok(f'Salle {salle.nom} {etat}.', id=salle.id)


def prepare_creer_matiere(ctx, args):
    nom = (args.get('nom') or args.get('query') or '').strip()
    if not nom:
        return _incomplete('creer_matiere', ['nom'], 'Quel nom pour la matière ?')
    return _pending(
        'creer_matiere',
        f'crée la matière {nom}',
        nom=nom,
        code=(args.get('code') or nom[:3]).upper(),
        url=_reverse('matiere:liste_matieres'),
    )


def apply_creer_matiere(ctx, draft):
    from school_admin.model.matiere_model import Matiere

    nom = draft['nom']
    code = (draft.get('code') or nom[:3]).upper()
    if Matiere.objects.filter(etablissement=ctx.etablissement, nom__iexact=nom).exists():
        return _err(f'La matière {nom} existe déjà.')
    extras = {}
    if hasattr(Matiere, 'etablissement'):
        extras['etablissement'] = ctx.etablissement
    try:
        matiere = Matiere.objects.create(nom=nom, code=code, **extras)
    except Exception:
        logger.exception('Création matière Aria')
        matiere = Matiere(nom=nom, code=code)
        if hasattr(matiere, 'etablissement_id'):
            matiere.etablissement = ctx.etablissement
        matiere.save()
    try:
        from school_admin.services.live_serializers import serialize_matiere_item
        item = serialize_matiere_item(matiere)
    except Exception:
        item = {'id': matiere.id, 'nom': matiere.nom}
    _emit(ctx, 'matiere.creee', item)
    return _ok(f'Matière {matiere.nom} créée.', id=matiere.id, url=_reverse('matiere:liste_matieres'))


def prepare_desactiver_matiere(ctx, args):
    matiere = _find_matiere(ctx, args.get('query') or args.get('nom'))
    if not matiere:
        return _incomplete('desactiver_matiere', ['query'], 'Quelle matière dois-je activer ou désactiver ?')
    verbe = 'désactive' if getattr(matiere, 'actif', True) else 'réactive'
    return _pending(
        'desactiver_matiere',
        f'{verbe} la matière {matiere.nom}',
        id=matiere.id,
        nom=matiere.nom,
        actif=not getattr(matiere, 'actif', True),
    )


def apply_desactiver_matiere(ctx, draft):
    from school_admin.model.matiere_model import Matiere

    matiere = Matiere.objects.filter(pk=draft.get('id')).first()
    if not matiere:
        return _err('Matière introuvable.')
    if hasattr(matiere, 'etablissement_id') and matiere.etablissement_id != ctx.etablissement.id:
        return _err('Matière introuvable.')
    matiere.actif = bool(draft.get('actif'))
    matiere.save(update_fields=['actif'])
    etat = 'activée' if matiere.actif else 'désactivée'
    try:
        from school_admin.services.live_serializers import serialize_matiere_item
        item = serialize_matiere_item(matiere)
    except Exception:
        item = {'id': matiere.id, 'nom': matiere.nom, 'actif': matiere.actif}
    _emit(ctx, 'matiere.modifiee', item)
    return _ok(f'Matière {matiere.nom} {etat}.', id=matiere.id)


# ---------------------------------------------------------------------------
# Emploi du temps (compléments)
# ---------------------------------------------------------------------------

def prepare_publier_emploi_du_temps(ctx, args):
    from school_admin.services.assistant_emploi import _emploi_actif, emploi_detail_url

    classe = _find_classe(ctx, args.get('classe') or args.get('query'))
    if not classe:
        return _incomplete('publier_emploi_du_temps', ['classe'], 'Pour quelle classe dois-je publier l’emploi du temps ?')
    emploi = _emploi_actif(ctx, classe)
    if not emploi:
        return _err(f'Aucun emploi du temps actif pour {classe.nom}.')
    return _pending(
        'publier_emploi_du_temps',
        f'publie l’emploi du temps de {classe.nom}',
        id=emploi.id,
        classe_id=classe.id,
        classe=classe.nom,
        url=emploi_detail_url(classe.id),
    )


def apply_publier_emploi_du_temps(ctx, draft):
    from school_admin.model.emploi_du_temps_model import EmploiDuTemps
    from school_admin.services.assistant_emploi import emploi_detail_url

    emploi = EmploiDuTemps.objects.filter(pk=draft.get('id')).first()
    if not emploi or emploi.classe.etablissement_id != ctx.etablissement.id:
        return _err('Emploi du temps introuvable.')
    if hasattr(emploi, 'publier'):
        emploi.publier()
    else:
        emploi.statut_publication = 'publie'
        emploi.save()
    from school_admin.services.live_serializers import serialize_emploi_refresh_item

    _emit(ctx, 'emploi.mise_a_jour', serialize_emploi_refresh_item(emploi.classe_id, emploi.id))
    return _ok(
        f'Emploi du temps de {draft.get("classe")} publié.',
        url=emploi_detail_url(emploi.classe_id),
    )


def prepare_supprimer_creneau_emploi(ctx, args):
    from school_admin.services.assistant_emploi import emploi_detail_url

    classe = _find_classe(ctx, args.get('classe') or '')
    creneau = _find_creneau(ctx, args.get('query') or args.get('matiere'), classe=classe)
    if not creneau:
        return _incomplete(
            'supprimer_creneau_emploi',
            ['query'],
            'Quel créneau dois-je supprimer (classe, matière, jour) ?',
        )
    classe_nom = creneau.emploi_du_temps.classe.nom
    matiere = creneau.matiere.nom if creneau.matiere_id else 'sans matière'
    return _pending(
        'supprimer_creneau_emploi',
        f'supprime le créneau {matiere} ({creneau.jour}) de {classe_nom}',
        id=creneau.id,
        classe=classe_nom,
        url=emploi_detail_url(creneau.emploi_du_temps.classe_id),
        destructive=True,
    )


def apply_supprimer_creneau_emploi(ctx, draft):
    from school_admin.model.emploi_du_temps_model import CreneauEmploiDuTemps
    from school_admin.services.assistant_emploi import emploi_detail_url

    creneau = CreneauEmploiDuTemps.objects.select_related(
        'emploi_du_temps', 'emploi_du_temps__classe'
    ).filter(pk=draft.get('id')).first()
    if not creneau or creneau.emploi_du_temps.classe.etablissement_id != ctx.etablissement.id:
        return _err('Créneau introuvable.')
    from school_admin.services.live_serializers import serialize_emploi_refresh_item

    classe_id = creneau.emploi_du_temps.classe_id
    emploi_id = creneau.emploi_du_temps_id
    creneau.delete()
    _emit(ctx, 'emploi.mise_a_jour', serialize_emploi_refresh_item(classe_id, emploi_id))
    return _ok('Créneau supprimé.', url=emploi_detail_url(classe_id))


# ---------------------------------------------------------------------------
# Documents administratifs
# ---------------------------------------------------------------------------

DOCUMENT_ROUTES = {
    'certificat_scolarite': ('directeur:generer_certificat_scolarite', 'certificat de scolarité'),
    'attestation_reussite': ('directeur:generer_attestation_reussite', 'attestation de réussite'),
    'attestation_conduite': ('directeur:generer_attestation_conduite', 'attestation de conduite'),
    'fiche_inscription': ('directeur:generer_fiche_inscription', 'fiche d’inscription'),
    'certificat_radiation': ('directeur:generer_certificat_radiation', 'certificat de radiation'),
    'convocation': ('directeur:generer_convocation', 'convocation'),
}


def prepare_generer_document(ctx, args):
    kind = (args.get('type') or args.get('document') or '').strip().lower()
    aliases = {
        'certificat': 'certificat_scolarite',
        'scolarite': 'certificat_scolarite',
        'réussite': 'attestation_reussite',
        'reussite': 'attestation_reussite',
        'conduite': 'attestation_conduite',
        'fiche': 'fiche_inscription',
        'radiation': 'certificat_radiation',
        'transfert': 'certificat_radiation',
        'convocation': 'convocation',
    }
    kind = aliases.get(kind, kind)
    if kind not in DOCUMENT_ROUTES:
        return _incomplete(
            'generer_document',
            ['type'],
            'Quel document : certificat, attestation de réussite, conduite, fiche, radiation ou convocation ?',
        )
    eleve = _find_eleve(ctx, args.get('query') or args.get('eleve'))
    if not eleve:
        return _incomplete('generer_document', ['query'], 'Pour quel élève dois-je générer ce document ?', type=kind)
    route, label = DOCUMENT_ROUTES[kind]
    url = _reverse(route, args=[eleve.id])
    return _pending(
        'generer_document',
        f'génère le {label} de {eleve.nom_complet}',
        type=kind,
        eleve_id=eleve.id,
        eleve=eleve.nom_complet,
        url=url,
        ouvrir=True,
    )


def apply_generer_document(ctx, draft):
    kind = draft.get('type')
    if kind not in DOCUMENT_ROUTES:
        return _err('Type de document inconnu.')
    route, label = DOCUMENT_ROUTES[kind]
    url = _reverse(route, args=[draft.get('eleve_id')])
    return _ok(
        f'J’ouvre le {label} de {draft.get("eleve")}.',
        url=url,
        ouvrir=True,
    )


# ---------------------------------------------------------------------------
# Session consultée
# ---------------------------------------------------------------------------

def prepare_changer_session(ctx, args):
    annee = _find_annee(ctx, args.get('query') or args.get('libelle'))
    if not annee:
        return _incomplete('changer_session', ['query'], 'Quelle année scolaire dois-je consulter ?')
    return _pending(
        'changer_session',
        f'passe la consultation sur {annee.libelle}',
        id=annee.id,
        libelle=annee.libelle,
    )


def apply_changer_session(ctx, draft):
    return _ok(
        f'Session consultée : {draft.get("libelle")}. Relancez la page pour l’appliquer.',
        id=draft.get('id'),
        session_id=draft.get('id'),
        url=_reverse('directeur:liste_annees_scolaires'),
    )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_QUERY = {'type': 'string', 'description': 'Nom, titre, matricule ou identifiant'}
_CLASSE = {'type': 'string', 'description': 'Nom de la classe'}

_ACTIONS = (
    ActionSpec(
        'publier_annonce',
        'Publie une annonce déjà rédigée (brouillon).',
        {'query': _QUERY, 'titre': {'type': 'string'}},
        prepare=prepare_publier_annonce,
        apply=apply_publier_annonce,
    ),
    ActionSpec(
        'archiver_annonce',
        'Archive une annonce publiée.',
        {'query': _QUERY, 'titre': {'type': 'string'}},
        destructive=True,
        prepare=prepare_archiver_annonce,
        apply=apply_archiver_annonce,
    ),
    ActionSpec(
        'supprimer_annonce',
        'Supprime une annonce (soft delete).',
        {'query': _QUERY, 'titre': {'type': 'string'}},
        destructive=True,
        prepare=prepare_supprimer_annonce,
        apply=apply_supprimer_annonce,
    ),
    ActionSpec(
        'modifier_annonce',
        'Modifie le titre ou le contenu d’une annonce existante.',
        {
            'query': _QUERY,
            'nouveau_titre': {'type': 'string'},
            'contenu': {'type': 'string'},
        },
        prepare=prepare_modifier_annonce,
        apply=apply_modifier_annonce,
    ),
    ActionSpec(
        'creer_annee_scolaire',
        'Crée une année scolaire. Dates optionnelles : suggestion automatique.',
        {
            'libelle': {'type': 'string'},
            'annee_debut': {'type': 'integer'},
            'date_debut': {'type': 'string'},
            'date_fin': {'type': 'string'},
            'est_ouverte': {'type': 'boolean'},
        },
        prepare=prepare_creer_annee_scolaire,
        apply=apply_creer_annee_scolaire,
    ),
    ActionSpec(
        'activer_annee_scolaire',
        'Active une année scolaire et initialise les structures (contrôleur AnneeScolaire).',
        {'query': _QUERY, 'libelle': {'type': 'string'}},
        prepare=prepare_activer_annee_scolaire,
        apply=apply_activer_annee_scolaire,
    ),
    ActionSpec(
        'desactiver_annee_scolaire',
        'Désactive une année scolaire.',
        {'query': _QUERY, 'libelle': {'type': 'string'}},
        destructive=True,
        prepare=prepare_desactiver_annee_scolaire,
        apply=apply_desactiver_annee_scolaire,
    ),
    ActionSpec(
        'creer_periode',
        'Crée une période scolaire (trimestre / semestre) sur l’année active.',
        {
            'nom': {'type': 'string'},
            'type_periode': {'type': 'string', 'enum': ['trimestre', 'semestre', 'annee']},
            'date_debut': {'type': 'string'},
            'date_fin': {'type': 'string'},
            'est_active': {'type': 'boolean'},
        },
        required=('nom', 'date_debut', 'date_fin'),
        prepare=prepare_creer_periode,
        apply=apply_creer_periode,
    ),
    ActionSpec(
        'activer_periode',
        'Active une période scolaire (désactive les autres).',
        {'query': _QUERY, 'nom': {'type': 'string'}},
        prepare=prepare_activer_periode,
        apply=apply_activer_periode,
    ),
    ActionSpec(
        'supprimer_periode',
        'Supprime une période scolaire.',
        {'query': _QUERY, 'nom': {'type': 'string'}},
        destructive=True,
        prepare=prepare_supprimer_periode,
        apply=apply_supprimer_periode,
    ),
    ActionSpec(
        'justifier_absence',
        'Justifie une absence (la marque présente), comme le bouton directeur.',
        {'query': _QUERY, 'eleve': {'type': 'string'}},
        prepare=prepare_justifier_absence,
        apply=apply_justifier_absence,
    ),
    ActionSpec(
        'approuver_liaison',
        'Approuve une demande de liaison parent-élève.',
        {'query': _QUERY},
        prepare=prepare_approuver_liaison,
        apply=apply_approuver_liaison,
    ),
    ActionSpec(
        'rejeter_liaison',
        'Rejette une demande de liaison parent-élève.',
        {'query': _QUERY, 'motif': {'type': 'string'}},
        destructive=True,
        prepare=prepare_rejeter_liaison,
        apply=apply_rejeter_liaison,
    ),
    ActionSpec(
        'desapprouver_liaison',
        'Retire une liaison parent-élève déjà approuvée.',
        {'query': _QUERY},
        destructive=True,
        prepare=prepare_desapprouver_liaison,
        apply=apply_desapprouver_liaison,
    ),
    ActionSpec(
        'valider_preinscription',
        'Valide une préinscription et inscrit l’élève (même logique que le contrôleur).',
        {'query': _QUERY, 'classe': _CLASSE},
        prepare=prepare_valider_preinscription,
        apply=apply_valider_preinscription,
    ),
    ActionSpec(
        'rejeter_preinscription',
        'Rejette une préinscription.',
        {'query': _QUERY, 'motif': {'type': 'string'}},
        destructive=True,
        prepare=prepare_rejeter_preinscription,
        apply=apply_rejeter_preinscription,
    ),
    ActionSpec(
        'toggle_lien_preinscription',
        'Active ou désactive le lien public de préinscription.',
        {},
        prepare=prepare_toggle_lien_preinscription,
        apply=apply_toggle_lien_preinscription,
    ),
    ActionSpec(
        'publier_bulletins',
        'Publie les bulletins d’une classe pour une période.',
        {'classe': _CLASSE, 'periode': {'type': 'string'}},
        required=('classe',),
        prepare=prepare_publier_bulletins,
        apply=apply_publier_bulletins,
    ),
    ActionSpec(
        'calculer_moyennes_classe',
        'Lance le calcul des moyennes d’une classe (ouvre l’action directeur).',
        {'classe': _CLASSE, 'periode': {'type': 'string'}},
        required=('classe',),
        prepare=prepare_calculer_moyennes_classe,
        apply=apply_calculer_moyennes_classe,
    ),
    ActionSpec(
        'creer_parametres_comptabilite',
        'Crée un jeu de paramètres de scolarité (inscription, mensualité, tenue, carte, etc.).',
        {
            'nom': {'type': 'string', 'description': 'Nom du jeu de paramètres'},
            'groupes_classes': {
                'type': 'string',
                'description': 'Groupes concernés, ex. 2nde, 1ère, Terminale',
            },
            'montant_frais_inscription': {'type': 'string'},
            'montant_mensualite': {'type': 'string'},
            'montant_frais_reinscription': {'type': 'string'},
            'type_facturation': {'type': 'string', 'enum': ['mensuel', 'annuel']},
            'jour_versement': {'type': 'integer'},
            'frais_annexes': {
                'type': 'array',
                'description': (
                    'Frais annexes : code (tenue, carte_scolaire, dossier, assurance, '
                    'examen, transport, cantine, apport, autre), montant, actif, '
                    'periodicite (inscription|annuel|ponctuel), libelle.'
                ),
                'items': {'type': 'object'},
            },
        },
        prepare=prepare_creer_parametres_comptabilite,
        apply=apply_creer_parametres_comptabilite,
    ),
    ActionSpec(
        'modifier_parametres_comptabilite',
        'Modifie un jeu de paramètres de comptabilité existant.',
        {
            'query': _QUERY,
            'nom': {'type': 'string'},
            'nouveau_nom': {'type': 'string'},
            'groupes_classes': {'type': 'string'},
            'montant_frais_inscription': {'type': 'string'},
            'montant_mensualite': {'type': 'string'},
            'frais_annexes': {
                'type': 'array',
                'description': 'Frais annexes à activer ou modifier (tenue, carte, etc.).',
                'items': {'type': 'object'},
            },
        },
        prepare=prepare_modifier_parametres_comptabilite,
        apply=apply_modifier_parametres_comptabilite,
    ),
    ActionSpec(
        'supprimer_parametres_comptabilite',
        'Supprime un jeu de paramètres de comptabilité.',
        {'query': _QUERY, 'nom': {'type': 'string'}},
        destructive=True,
        prepare=prepare_supprimer_parametres_comptabilite,
        apply=apply_supprimer_parametres_comptabilite,
    ),
    ActionSpec(
        'enregistrer_paiement',
        'Enregistre un paiement élève (inscription, mensualité ou frais annexe : tenue, carte…).',
        {
            'query': _QUERY,
            'montant': {'type': 'string'},
            'type_paiement': {
                'type': 'string',
                'enum': ['frais_inscription', 'mensualite', 'frais_annexe'],
            },
            'frais': {'type': 'string', 'description': 'Code ou libellé du frais annexe (tenue, carte…)'},
            'mode_paiement': {'type': 'string'},
        },
        prepare=prepare_enregistrer_paiement,
        apply=apply_enregistrer_paiement,
    ),
    ActionSpec(
        'creer_session_examen',
        'Crée une session d’examen (nom, période, dates).',
        {
            'nom': {'type': 'string'},
            'periode': {'type': 'string'},
            'date_debut': {'type': 'string'},
            'date_fin': {'type': 'string'},
            'description': {'type': 'string'},
        },
        prepare=prepare_creer_session_examen,
        apply=apply_creer_session_examen,
    ),
    ActionSpec(
        'supprimer_session_examen',
        'Supprime une session d’examen et ses créneaux.',
        {'query': _QUERY, 'nom': {'type': 'string'}},
        destructive=True,
        prepare=prepare_supprimer_session_examen,
        apply=apply_supprimer_session_examen,
    ),
    ActionSpec(
        'creer_classe',
        'Crée une classe (code généré par ClasseController).',
        {
            'nom': {'type': 'string'},
            'niveau': {'type': 'string'},
            'cycle': {
                'type': 'string',
                'description': (
                    'Cycle : college ou lycee. Obligatoire pour un établissement '
                    'collège+lycée ou mixte.'
                ),
            },
            'capacite': {'type': 'integer'},
        },
        required=('nom',),
        prepare=prepare_creer_classe,
        apply=apply_creer_classe,
    ),
    ActionSpec(
        'desactiver_classe',
        'Active ou désactive une classe.',
        {'query': _QUERY, 'classe': _CLASSE},
        prepare=prepare_desactiver_classe,
        apply=apply_desactiver_classe,
    ),
    ActionSpec(
        'supprimer_classe',
        'Supprime une classe.',
        {'query': _QUERY, 'classe': _CLASSE},
        destructive=True,
        prepare=prepare_supprimer_classe,
        apply=apply_supprimer_classe,
    ),
    ActionSpec(
        'creer_salle',
        'Crée une salle.',
        {
            'nom': {'type': 'string'},
            'numero': {'type': 'string'},
            'type_salle': {'type': 'string'},
            'capacite': {'type': 'integer'},
        },
        prepare=prepare_creer_salle,
        apply=apply_creer_salle,
    ),
    ActionSpec(
        'desactiver_salle',
        'Active ou désactive une salle.',
        {'query': _QUERY, 'nom': {'type': 'string'}},
        prepare=prepare_desactiver_salle,
        apply=apply_desactiver_salle,
    ),
    ActionSpec(
        'creer_matiere',
        'Crée une matière.',
        {'nom': {'type': 'string'}, 'code': {'type': 'string'}},
        required=('nom',),
        prepare=prepare_creer_matiere,
        apply=apply_creer_matiere,
    ),
    ActionSpec(
        'desactiver_matiere',
        'Active ou désactive une matière.',
        {'query': _QUERY, 'nom': {'type': 'string'}},
        prepare=prepare_desactiver_matiere,
        apply=apply_desactiver_matiere,
    ),
    ActionSpec(
        'publier_emploi_du_temps',
        'Publie l’emploi du temps actif d’une classe.',
        {'classe': _CLASSE},
        required=('classe',),
        prepare=prepare_publier_emploi_du_temps,
        apply=apply_publier_emploi_du_temps,
    ),
    ActionSpec(
        'supprimer_creneau_emploi',
        'Supprime un créneau d’emploi du temps.',
        {'classe': _CLASSE, 'query': _QUERY, 'matiere': {'type': 'string'}},
        destructive=True,
        prepare=prepare_supprimer_creneau_emploi,
        apply=apply_supprimer_creneau_emploi,
    ),
    ActionSpec(
        'generer_document',
        'Prépare un document administratif (certificat, attestation, fiche, convocation).',
        {
            'type': {
                'type': 'string',
                'enum': list(DOCUMENT_ROUTES.keys()),
            },
            'query': _QUERY,
            'eleve': {'type': 'string'},
        },
        required=('type',),
        prepare=prepare_generer_document,
        apply=apply_generer_document,
    ),
    ActionSpec(
        'changer_session',
        'Change l’année scolaire consultée.',
        {'query': _QUERY, 'libelle': {'type': 'string'}},
        prepare=prepare_changer_session,
        apply=apply_changer_session,
    ),
)

for _spec in _ACTIONS:
    register_action(_spec)

# Élèves, professeurs, personnel, caisse, paie, filières.
import school_admin.services.assistant_staff  # noqa: E402,F401
# Fiches longues : dossier, réinscription, moratoire, moyennes, affectations.
import school_admin.services.assistant_dossiers  # noqa: E402,F401
# Vague 2 : remises fratrie + recalcul des statuts de paiement.
import school_admin.services.assistant_pilotage  # noqa: E402,F401
# Vague 3 : justifications, coefficients, moyenne annuelle.
import school_admin.services.assistant_pedagogie  # noqa: E402,F401
