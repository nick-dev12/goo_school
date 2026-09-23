"""
Vague 5 — tools RH pour l’assistant directeur.

Lecture : dossier employé, volume horaire (semaine / mois / année),
absences professeur, fiche de paie vacataire existante.
Écriture : brouillon + confirmation (dossier, suppression d’absence).
Pas de bulletins de paie permanents. Pas de tools CG.
"""
from __future__ import annotations

import logging
import re
from datetime import date as date_cls
from decimal import Decimal, InvalidOperation

from django.db.models import Q
from django.urls import NoReverseMatch, reverse

from school_admin.model.employe_dossier_model import TYPE_CONTRAT_CHOICES
from school_admin.services.assistant_actions import (
    ActionSpec,
    _err,
    _incomplete,
    _ok,
    _parse_date,
    _pending,
    register_action,
)

logger = logging.getLogger(__name__)

ABSENCES_LIMIT = 24
LIGNES_LIMIT = 24

_STR = {'type': 'string'}
CONTRAT_CODES = {code for code, _label in TYPE_CONTRAT_CHOICES}
CONTRAT_ALIASES = {
    'cdi': 'cdi',
    'cdd': 'cdd',
    'vacataire': 'vacataire',
    'vacat': 'vacataire',
    'heure': 'vacataire',
    'stage': 'stage',
    'alternance': 'stage',
    'convention': 'convention',
    'prestation': 'prestation',
    'freelance': 'prestation',
    'autre': 'autre',
}


def _reverse(route, args=None):
    try:
        return reverse(route, args=args or [])
    except NoReverseMatch:
        return None


def _safe(value):
    if value is None:
        return None
    return float(value)


def _parse_money(raw):
    if raw is None or raw == '':
        return None
    text = str(raw).strip().replace(' ', '').replace(',', '.')
    if not text:
        return None
    try:
        value = Decimal(text)
    except (InvalidOperation, ValueError, TypeError):
        return None
    if value < 0:
        return None
    return value.quantize(Decimal('0.01'))


def _normalize_contrat(raw):
    text = (raw or '').strip().lower()
    if not text:
        return None
    if text in CONTRAT_CODES:
        return text
    for alias, code in CONTRAT_ALIASES.items():
        if alias in text:
            return code
    return None


def _find_professeur(ctx, query):
    from school_admin.services.assistant_staff import _find_professeur as finder

    found = finder(ctx, query)
    if found:
        return found
    cleaned = _clean_query(query)
    if cleaned and cleaned != (query or '').strip():
        return finder(ctx, cleaned)
    return None


def _find_personnel(ctx, query):
    from school_admin.services.assistant_staff import _find_personnel as finder

    return finder(ctx, query)


_QUERY_NOISE = re.compile(
    r'\b(dossier|employe|employé|employée|professeur|enseignant|personnel|'
    r'cnss|rib|contrat|salaire|base|tarif|horaire|de|du|des|la|le|les|'
    r'quel|quelle|quels|quelles)\b',
    re.IGNORECASE,
)


def _clean_query(query):
    cleaned = _QUERY_NOISE.sub(' ', query or '')
    return re.sub(r'\s+', ' ', cleaned).strip()


def _resolve_employe(ctx, args):
    query = (
        (args.get('query') or args.get('nom') or args.get('professeur')
         or args.get('personnel') or args.get('employe') or '')
    ).strip()
    if not query:
        return None, None
    role = (args.get('role') or args.get('type') or '').strip().lower()
    candidates = [query, _clean_query(query)]
    if role in ('personnel', 'admin', 'administratif', 'caissier', 'secretaire'):
        for text in candidates:
            personnel = _find_personnel(ctx, text)
            if personnel:
                return 'personnel', personnel
    for text in candidates:
        prof = _find_professeur(ctx, text)
        if prof:
            return 'professeur', prof
    for text in candidates:
        personnel = _find_personnel(ctx, text)
        if personnel:
            return 'personnel', personnel
    return None, None


def _periode_volume(ctx, args):
    from school_admin.utils.volume_horaire import resoudre_periode

    args = args if isinstance(args, dict) else {}
    kind = (args.get('periode') or args.get('kind') or 'mois').strip().lower()
    if kind in ('semaine', 'week', 'hebdo'):
        kind = 'semaine'
    elif kind in ('annee', 'année', 'year', 'annuel'):
        kind = 'annee'
    else:
        kind = 'mois'
    reference = date_cls.today()
    mois = (args.get('mois') or '').strip()
    if mois:
        try:
            parsed = date_cls.fromisoformat(mois + '-01') if len(mois) == 7 else date_cls.fromisoformat(mois)
            reference = parsed
        except ValueError:
            pass
    jour = _parse_date(args.get('date') or args.get('semaine_du'))
    if jour:
        reference = jour
    try:
        return resoudre_periode(
            kind,
            reference=reference,
            annee_scolaire=ctx.annee_scolaire,
        )
    except ValueError:
        return resoudre_periode(
            'mois',
            reference=date_cls.today(),
            annee_scolaire=ctx.annee_scolaire,
        )


def _query_periode(periode):
    from school_admin.controllers.volume_horaire_controller import VolumeHoraireController

    return VolumeHoraireController._query_periode(periode)


def _get_dossier(employe):
    from school_admin.model.employe_dossier_model import DossierEmployeComplementaire

    try:
        return employe.dossier_complementaire
    except DossierEmployeComplementaire.DoesNotExist:
        return None


def _serialize_dossier(kind, employe):
    dossier = _get_dossier(employe)
    if kind == 'professeur':
        url = _reverse('professeur:detail_professeur', args=[employe.id])
        role_label = 'professeur'
        fonction = None
        if getattr(employe, 'matiere_principale', None):
            fonction = employe.matiere_principale.nom
    else:
        url = _reverse('personnel:detail_personnel', args=[employe.id])
        role_label = 'personnel'
        fonction = employe.get_fonction_display() if hasattr(employe, 'get_fonction_display') else employe.fonction
    return {
        'role': role_label,
        'nom': employe.nom_complet,
        'telephone': employe.telephone or None,
        'email': employe.email or None,
        'numero_employe': getattr(employe, 'numero_employe', None) or None,
        'fonction': fonction,
        'date_embauche': (
            employe.date_embauche.isoformat()
            if getattr(employe, 'date_embauche', None) else None
        ),
        'tarif_horaire': _safe(getattr(employe, 'prix_volume_horaire', None)),
        'type_contrat': (dossier.type_contrat or None) if dossier else None,
        'type_contrat_libelle': (
            dossier.get_type_contrat_display_label()
            if dossier and dossier.type_contrat else None
        ),
        'date_fin_contrat': (
            dossier.date_fin_contrat.isoformat()
            if dossier and dossier.date_fin_contrat else None
        ),
        'salaire_base': _safe(dossier.salaire_base) if dossier else None,
        'numero_cnss': (dossier.numero_cnss or None) if dossier else None,
        'banque': (dossier.banque or None) if dossier else None,
        'rib': (dossier.numero_compte_bancaire or None) if dossier else None,
        'charges_sociales': None,
        'url': url,
    }


# ---------------------------------------------------------------------------
# Lecture
# ---------------------------------------------------------------------------

def tool_volume_horaire(ctx, args):
    from school_admin.controllers.volume_horaire_controller import VolumeHoraireController
    from school_admin.model.professeur_model import Professeur

    args = args if isinstance(args, dict) else {}
    periode = _periode_volume(ctx, args)
    query = (args.get('query') or args.get('professeur') or '').strip()
    qs = Professeur.objects.filter(etablissement=ctx.etablissement, actif=True)
    if query:
        qs = qs.filter(
            Q(nom__icontains=query) | Q(prenom__icontains=query) | Q(numero_employe__icontains=query)
        )
    lignes = []
    for prof in qs.order_by('nom', 'prenom')[:LIGNES_LIMIT]:
        creneaux = list(
            VolumeHoraireController._creneaux_publies(
                ctx.etablissement, ctx.annee_scolaire, professeur=prof
            )
        )
        resultat, _abs, _rempl = VolumeHoraireController._resultat_avec_absences(
            creneaux, periode, prof, ctx.etablissement
        )
        paie = VolumeHoraireController._paie_periode(prof, periode)
        lignes.append({
            'professeur': prof.nom_complet,
            'heures': str(resultat.heures),
            'montant': str(resultat.montant) if resultat.montant is not None else None,
            'tarif_horaire': _safe(prof.prix_volume_horaire),
            'paye': bool(paie),
        })
    return {
        'periode': periode.label,
        'periode_kind': periode.kind,
        'debut': periode.date_debut.isoformat(),
        'fin': periode.date_fin.isoformat(),
        'lignes': lignes,
    }


def tool_dossier_employe(ctx, args):
    args = args if isinstance(args, dict) else {}
    kind, employe = _resolve_employe(ctx, args)
    if not employe:
        return {'erreur': 'Indique le professeur ou le personnel dont tu veux le dossier.'}
    payload = _serialize_dossier(kind, employe)
    payload['invente'] = False
    return payload


def tool_absences_professeur(ctx, args):
    from school_admin.model.caisse_etablissement_model import AbsenceEnseignant

    args = args if isinstance(args, dict) else {}
    prof = _find_professeur(ctx, args.get('query') or args.get('professeur') or '')
    if not prof:
        return {'erreur': 'Indique le professeur dont tu veux les absences.'}
    qs = AbsenceEnseignant.objects.filter(
        etablissement=ctx.etablissement,
        professeur=prof,
    ).select_related('remplacant')
    periode = None
    if args.get('periode') or args.get('mois') or args.get('date'):
        periode = _periode_volume(ctx, args)
        qs = qs.filter(date__gte=periode.date_debut, date__lte=periode.date_fin)
    items = []
    minutes_total = 0
    for absence in qs.order_by('-date')[:ABSENCES_LIMIT]:
        minutes_total += absence.minutes or 0
        items.append({
            'id': absence.id,
            'date': absence.date.isoformat(),
            'minutes': absence.minutes,
            'heures': round((absence.minutes or 0) / 60.0, 2),
            'remplacant': absence.remplacant.nom_complet if absence.remplacant_id else None,
        })
    return {
        'professeur': prof.nom_complet,
        'periode': periode.label if periode else None,
        'nb': len(items),
        'minutes_totales': minutes_total,
        'heures_totales': round(minutes_total / 60.0, 2),
        'absences': items,
        'url': _reverse('directeur:detail_volume_horaire', args=[prof.id]),
    }


def tool_ouvrir_fiche_paie(ctx, args):
    from school_admin.controllers.volume_horaire_controller import VolumeHoraireController

    args = args if isinstance(args, dict) else {}
    prof = _find_professeur(ctx, args.get('query') or args.get('professeur') or '')
    if not prof:
        return {'erreur': 'Indique le professeur dont tu veux la fiche de paie.'}
    periode = _periode_volume(ctx, args)
    paie = VolumeHoraireController._paie_periode(prof, periode)
    if paie is None:
        return {
            'erreur': (
                f'Aucune paie marquée pour {prof.nom_complet} '
                f'({periode.label}). Marque d’abord la période comme payée '
                '(marquer_paie). Pas de bulletin permanent.'
            ),
            'professeur': prof.nom_complet,
            'periode': periode.label,
        }
    url = _reverse('directeur:fiche_paie_directeur', args=[prof.id])
    if url:
        url = url + _query_periode(periode)
    return {
        'ouvrir': True,
        'url': url,
        'professeur': prof.nom_complet,
        'periode': periode.label,
        'heures': _safe(paie.heures),
        'montant_net': _safe(paie.montant_net),
        'date_paiement': paie.date_paiement.date().isoformat() if paie.date_paiement else None,
        'message': (
            f'Fiche de paie vacataire de {prof.nom_complet} '
            f'({periode.label}) : {paie.montant_net} FCFA.'
        ),
    }


# ---------------------------------------------------------------------------
# Écriture
# ---------------------------------------------------------------------------

def prepare_modifier_dossier_employe(ctx, args):
    args = args if isinstance(args, dict) else {}
    kind, employe = _resolve_employe(ctx, args)
    if not employe:
        return _incomplete(
            'modifier_dossier_employe',
            ['query'],
            'Quel employé dois-je mettre à jour ?',
        )
    changes = {}
    contrat = _normalize_contrat(args.get('type_contrat') or args.get('contrat'))
    if args.get('type_contrat') or args.get('contrat'):
        if not contrat:
            autorises = ', '.join(sorted(CONTRAT_CODES))
            return _err(f'Type de contrat inconnu. Utilise : {autorises}.')
        changes['type_contrat'] = contrat
    if args.get('salaire_base') not in (None, ''):
        salaire = _parse_money(args.get('salaire_base'))
        if salaire is None:
            return _err('Salaire de base invalide.')
        changes['salaire_base'] = str(salaire)
    if args.get('numero_cnss') or args.get('cnss'):
        changes['numero_cnss'] = (args.get('numero_cnss') or args.get('cnss') or '').strip()
    if args.get('rib') or args.get('numero_compte_bancaire'):
        changes['numero_compte_bancaire'] = (
            args.get('rib') or args.get('numero_compte_bancaire') or ''
        ).strip()
    if args.get('banque'):
        changes['banque'] = (args.get('banque') or '').strip()
    if args.get('date_fin_contrat'):
        fin = _parse_date(args.get('date_fin_contrat'))
        if not fin:
            return _err('Date de fin de contrat invalide.')
        changes['date_fin_contrat'] = fin.isoformat()
    tarif = args.get('tarif_horaire') or args.get('prix_horaire') or args.get('prix_volume_horaire')
    if tarif not in (None, ''):
        parsed = _parse_money(tarif)
        if parsed is None:
            return _err('Tarif horaire invalide.')
        changes['prix_volume_horaire'] = str(parsed)
    if not changes:
        return _incomplete(
            'modifier_dossier_employe',
            ['champs'],
            (
                f'Que modifier pour {employe.nom_complet} ? '
                'Contrat, salaire, CNSS, RIB ou tarif horaire.'
            ),
            query=employe.nom_complet,
        )
    resume_parts = [f'{key}={value}' for key, value in changes.items()]
    return _pending(
        'modifier_dossier_employe',
        f'met à jour le dossier de {employe.nom_complet} ({", ".join(resume_parts)})',
        employe_id=employe.id,
        role=kind,
        nom=employe.nom_complet,
        changes=changes,
    )


def apply_modifier_dossier_employe(ctx, draft):
    from school_admin.model.personnel_administratif_model import PersonnelAdministratif
    from school_admin.model.professeur_model import Professeur
    from school_admin.utils.employe_dossier_utils import (
        get_or_create_dossier,
        parse_optional_date,
        parse_optional_decimal,
    )

    role = draft.get('role')
    changes = draft.get('changes') or {}
    if role == 'professeur':
        employe = Professeur.objects.filter(
            pk=draft.get('employe_id'), etablissement=ctx.etablissement
        ).first()
        dossier = get_or_create_dossier(professeur=employe) if employe else None
    else:
        employe = PersonnelAdministratif.objects.filter(
            pk=draft.get('employe_id'), etablissement=ctx.etablissement
        ).first()
        dossier = get_or_create_dossier(personnel=employe) if employe else None
    if not employe or not dossier:
        return _err('Employé introuvable.')
    dossier_fields = []
    if 'type_contrat' in changes:
        dossier.type_contrat = changes['type_contrat']
        dossier_fields.append('type_contrat')
    if 'salaire_base' in changes:
        dossier.salaire_base = parse_optional_decimal(changes['salaire_base'])
        dossier_fields.append('salaire_base')
    if 'numero_cnss' in changes:
        dossier.numero_cnss = changes['numero_cnss']
        dossier_fields.append('numero_cnss')
    if 'numero_compte_bancaire' in changes:
        dossier.numero_compte_bancaire = changes['numero_compte_bancaire']
        dossier_fields.append('numero_compte_bancaire')
    if 'banque' in changes:
        dossier.banque = changes['banque']
        dossier_fields.append('banque')
    if 'date_fin_contrat' in changes:
        dossier.date_fin_contrat = parse_optional_date(changes['date_fin_contrat'])
        dossier_fields.append('date_fin_contrat')
    if dossier_fields:
        dossier.save(update_fields=dossier_fields + ['date_modification'])
    if 'prix_volume_horaire' in changes:
        employe.prix_volume_horaire = parse_optional_decimal(changes['prix_volume_horaire'])
        employe.save(update_fields=['prix_volume_horaire'])
    return _ok(f'Dossier de {employe.nom_complet} mis à jour.')


def prepare_supprimer_absence_professeur(ctx, args):
    from school_admin.model.caisse_etablissement_model import AbsenceEnseignant

    args = args if isinstance(args, dict) else {}
    prof = _find_professeur(ctx, args.get('query') or args.get('professeur') or '')
    if not prof:
        return _incomplete(
            'supprimer_absence_professeur',
            ['query'],
            'De quel professeur dois-je retirer une absence ?',
        )
    jour = _parse_date(args.get('date'))
    absence = None
    if args.get('id') and str(args.get('id')).isdigit():
        absence = AbsenceEnseignant.objects.filter(
            pk=int(args['id']),
            professeur=prof,
            etablissement=ctx.etablissement,
        ).first()
    if absence is None and jour:
        absence = AbsenceEnseignant.objects.filter(
            professeur=prof,
            etablissement=ctx.etablissement,
            date=jour,
        ).first()
    if absence is None:
        return _incomplete(
            'supprimer_absence_professeur',
            ['date'],
            f'Quelle date d’absence supprimer pour {prof.nom_complet} ?',
            query=prof.nom_complet,
        )
    return _pending(
        'supprimer_absence_professeur',
        f'supprime l’absence de {prof.nom_complet} le {absence.date.isoformat()}',
        id=absence.id,
        professeur_id=prof.id,
        nom=prof.nom_complet,
        date=absence.date.isoformat(),
        url=_reverse('directeur:detail_volume_horaire', args=[prof.id]),
    )


def apply_supprimer_absence_professeur(ctx, draft):
    from school_admin.model.caisse_etablissement_model import AbsenceEnseignant

    absence = AbsenceEnseignant.objects.filter(
        pk=draft.get('id'),
        professeur_id=draft.get('professeur_id'),
        etablissement=ctx.etablissement,
    ).first()
    if not absence:
        return _err('Absence introuvable.')
    jour = absence.date.isoformat()
    nom = draft.get('nom') or ''
    absence.delete()
    return _ok(f'Absence de {nom} le {jour} supprimée.')


register_action(ActionSpec(
    'modifier_dossier_employe',
    'Met à jour le dossier complémentaire d’un employé (contrat, salaire, CNSS, RIB, tarif). '
    'Ne saisit pas de charges CSS/IPRES.',
    {
        'query': _STR,
        'nom': _STR,
        'professeur': _STR,
        'personnel': _STR,
        'employe': _STR,
        'role': {'type': 'string', 'enum': ['professeur', 'personnel']},
        'type_contrat': {
            'type': 'string',
            'enum': sorted(CONTRAT_CODES),
            'description': 'cdi, cdd, vacataire, stage, convention, prestation, autre',
        },
        'contrat': _STR,
        'salaire_base': {'type': 'string', 'description': 'Salaire de base en FCFA'},
        'numero_cnss': _STR,
        'cnss': _STR,
        'rib': _STR,
        'numero_compte_bancaire': _STR,
        'banque': _STR,
        'date_fin_contrat': {'type': 'string'},
        'tarif_horaire': {'type': 'string', 'description': 'FCFA / heure (vacataire)'},
        'prix_horaire': _STR,
    },
    prepare=prepare_modifier_dossier_employe,
    apply=apply_modifier_dossier_employe,
))

register_action(ActionSpec(
    'supprimer_absence_professeur',
    'Supprime une absence professeur déjà enregistrée.',
    {
        'query': _STR,
        'professeur': _STR,
        'date': {'type': 'string', 'description': 'Date YYYY-MM-DD'},
        'id': {'type': 'string'},
    },
    destructive=True,
    prepare=prepare_supprimer_absence_professeur,
    apply=apply_supprimer_absence_professeur,
))


VAGUE5_READ_SCHEMA = [
    {
        'type': 'function',
        'function': {
            'name': 'get_dossier_employe',
            'description': (
                'Dossier RH d’un professeur ou du personnel : contrat, salaire de base, '
                'N° CNSS, RIB, tarif horaire. N’invente aucune charge sociale.'
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'query': {'type': 'string', 'description': 'Nom de l’employé'},
                    'professeur': _STR,
                    'personnel': _STR,
                    'role': {'type': 'string', 'enum': ['professeur', 'personnel']},
                },
                'required': ['query'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'get_absences_professeur',
            'description': (
                'Absences d’un professeur : dates, minutes perdues, remplaçant. '
                'Filtre optionnel semaine / mois.'
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'query': {'type': 'string', 'description': 'Nom du professeur'},
                    'professeur': _STR,
                    'periode': {
                        'type': 'string',
                        'enum': ['semaine', 'mois', 'annee'],
                    },
                    'mois': {'type': 'string', 'description': 'YYYY-MM'},
                    'date': _STR,
                },
                'required': ['query'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'ouvrir_fiche_paie',
            'description': (
                'Ouvre la fiche de paie vacataire déjà marquée payée '
                '(URL existante, pas de bulletin permanent).'
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'query': {'type': 'string', 'description': 'Nom du professeur'},
                    'professeur': _STR,
                    'periode': {
                        'type': 'string',
                        'enum': ['semaine', 'mois', 'annee'],
                    },
                    'mois': {'type': 'string'},
                    'ouvrir': {'type': 'boolean'},
                },
                'required': ['query'],
            },
        },
    },
]

VAGUE5_READ_HANDLERS = {
    'get_dossier_employe': tool_dossier_employe,
    'get_absences_professeur': tool_absences_professeur,
    'ouvrir_fiche_paie': tool_ouvrir_fiche_paie,
    'get_volume_horaire': tool_volume_horaire,
}
