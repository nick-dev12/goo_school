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


def _err(message, **extra):
    payload = {'erreur': message}
    payload.update(extra)
    return payload


def _parse_date(raw):
    text = (raw or '').strip()
    if not text:
        return None
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y'):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
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
    if annonce.fichier_joint:
        annonce.fichier_joint.delete(save=False)
    annonce.actif = False
    annonce.save(update_fields=['actif'])
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

    annee = AnneeScolaireController.creer_annee_scolaire(
        etablissement=ctx.etablissement,
        libelle=draft['libelle'],
        annee_debut=int(draft['annee_debut']),
        annee_fin=int(draft['annee_fin']),
        date_debut=_parse_date(draft['date_debut']),
        date_fin=_parse_date(draft['date_fin']),
        est_ouverte=bool(draft.get('est_ouverte', True)),
    )
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
    periode.est_active = True
    periode.save(update_fields=['est_active'])
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
    periode.delete()
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
    eleve = _find_eleve(ctx, args.get('query') or args.get('eleve'))
    if not eleve:
        return _incomplete('enregistrer_paiement', ['query'], 'Pour quel élève dois-je enregistrer un paiement ?')
    montant = _parse_money(args.get('montant'))
    type_paiement = (args.get('type_paiement') or 'mensualite').strip()
    mode = (args.get('mode_paiement') or 'especes').strip()
    if not montant:
        return _incomplete(
            'enregistrer_paiement',
            ['montant'],
            f'Quel montant dois-je enregistrer pour {eleve.nom_complet} ?',
            query=eleve.nom_complet,
            eleve_id=eleve.id,
            type_paiement=type_paiement,
            mode_paiement=mode,
        )
    return _pending(
        'enregistrer_paiement',
        f'enregistre un paiement de {montant} pour {eleve.nom_complet}',
        eleve_id=eleve.id,
        eleve=eleve.nom_complet,
        montant=str(montant),
        type_paiement=type_paiement,
        mode_paiement=mode,
        url=_reverse('directeur:details_comptabilite_eleve_directeur', args=[eleve.id]),
    )


def apply_enregistrer_paiement(ctx, draft):
    from school_admin.model.comptabilite_eleve_model import (
        ComptabiliteEleve,
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
    if type_paiement == 'frais_inscription' and fiche:
        frais = FraisInscription.objects.filter(
            comptabilite_eleve=fiche,
            annee_scolaire=ctx.annee_scolaire,
            statut__in=['en_attente', 'en_retard'],
        ).order_by('date_echeance').first()
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
            montant=montant,
            mode_paiement=mode,
            notes='Enregistré par l’assistante vocale Aria',
        )
        if fiche:
            fiche.verifier_statut_paiement()
    return _ok(
        f'Paiement de {montant} enregistré pour {eleve.nom_complet}.',
        eleve_id=eleve.id,
        url=_reverse('directeur:details_comptabilite_eleve_directeur', args=[eleve.id]),
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
    nb = session.creneaux.count()
    session.delete()
    return _ok(f'Session « {nom} » et {nb} créneau(x) supprimé(s).')


# ---------------------------------------------------------------------------
# Classes / salles / matières
# ---------------------------------------------------------------------------

def prepare_creer_classe(ctx, args):
    nom = (args.get('nom') or args.get('query') or '').strip()
    niveau = (args.get('niveau') or '').strip()
    if ctx.etablissement.type_etablissement == 'primary':
        niveau = niveau or 'primaire'
    elif ctx.etablissement.type_etablissement == 'collège':
        niveau = niveau or 'college'
    elif ctx.etablissement.type_etablissement == 'lycée':
        niveau = niveau or 'lycee'
    elif ctx.etablissement.type_etablissement == 'superieur':
        niveau = niveau or 'superieur'
    else:
        niveau = niveau or 'lycee'
    if not nom:
        return _incomplete('creer_classe', ['nom'], 'Quel nom pour la nouvelle classe ?')
    capacite = int(args.get('capacite') or args.get('capacite_max') or 30)
    return _pending(
        'creer_classe',
        f'crée la classe {nom}',
        nom=nom,
        niveau=niveau,
        capacite_max=capacite,
        url=_reverse('administrateur_etablissement:liste_classes'),
    )


def apply_creer_classe(ctx, draft):
    from school_admin.controllers.classe_controller import ClasseController
    from school_admin.model.classe_model import Classe

    nom = (draft.get('nom') or '').strip()
    niveau = draft.get('niveau') or 'lycee'
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
    classe.actif = bool(draft.get('actif'))
    classe.save(update_fields=['actif'])
    etat = 'activée' if classe.actif else 'désactivée'
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
    nom = classe.nom
    classe.delete()
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
    salle = Salle.objects.create(
        nom=draft['nom'],
        numero=draft['numero'],
        type_salle=type_salle,
        capacite_max=int(draft.get('capacite_max') or 30),
        etablissement=ctx.etablissement,
    )
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
    salle.actif = bool(draft.get('actif'))
    salle.save(update_fields=['actif'])
    etat = 'activée' if salle.actif else 'désactivée'
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
    classe_id = creneau.emploi_du_temps.classe_id
    creneau.delete()
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
        'enregistrer_paiement',
        'Enregistre un paiement élève (frais ou mensualité) via PaiementEleve.',
        {
            'query': _QUERY,
            'montant': {'type': 'string'},
            'type_paiement': {'type': 'string', 'enum': ['frais_inscription', 'mensualite']},
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
