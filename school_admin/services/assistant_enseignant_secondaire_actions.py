"""
Actions mutantes de l'assistant vocal enseignant primaire.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Callable

from django.db import transaction
from django.urls import NoReverseMatch, reverse
from django.utils import timezone
from django.utils.dateparse import parse_date

from school_admin.services.assistant_actions import CONFIRM_CHOICES, _incomplete, _ok, _pending
from school_admin.services.assistant_enseignant_scope import (
    ensure_classe_access,
    ensure_eleve_access,
    ensure_matiere_in_classe,
    find_classe_prof,
    find_eleve_prof,
)

logger = logging.getLogger(__name__)


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


ENSEIGNANT_SECONDAIRE_ACTION_SPECS: dict[str, ActionSpec] = {}


def register_enseignant_secondaire_action(spec: ActionSpec):
    ENSEIGNANT_SECONDAIRE_ACTION_SPECS[spec.name] = spec
    return spec


def get_enseignant_secondaire_action(name):
    return ENSEIGNANT_SECONDAIRE_ACTION_SPECS.get(name)


def build_enseignant_secondaire_action_tool_schemas():
    schemas = []
    for spec in ENSEIGNANT_SECONDAIRE_ACTION_SPECS.values():
        extra = ' Confirmation obligatoire avant toute écriture.'
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


def choices_for_enseignant_secondaire_action(name, draft):
    spec = ENSEIGNANT_SECONDAIRE_ACTION_SPECS.get(name)
    if spec and spec.choices:
        return spec.choices(draft)
    return CONFIRM_CHOICES


def _reverse(route, args=None):
    try:
        return reverse(route, args=args or [])
    except NoReverseMatch:
        return None


def _parse_note(raw):
    if raw is None or raw == '':
        return None
    try:
        return Decimal(str(raw).replace(',', '.'))
    except (InvalidOperation, ValueError):
        return None


def _resolve_periode(ctx, args, classe=None):
    from django.db.models import Q

    from school_admin.model.periode_model import PeriodeScolaire

    if getattr(ctx, 'est_superieur', False):
        from school_admin.services.assistant_superieur import (
            _find_periode,
            normalize_niveau_lmd,
        )

        niveau = normalize_niveau_lmd(args.get('niveau_lmd')) or (
            getattr(classe, 'niveau_lmd', None) if classe else None
        )
        nom = (args.get('periode') or args.get('semestre') or '').strip()
        if not nom and not niveau:
            active = PeriodeScolaire.get_periode_active(ctx.etablissement)
            if active and (not ctx.annee_scolaire or active.annee_scolaire_fk_id == ctx.annee_scolaire.id):
                return active
        return _find_periode(ctx, nom or None, niveau_lmd=niveau)

    periode_id = args.get('periode_id')
    if periode_id:
        qs = PeriodeScolaire.objects.filter(
            etablissement=ctx.etablissement,
            pk=periode_id,
        )
        if ctx.annee_scolaire:
            qs = qs.filter(annee_scolaire_fk=ctx.annee_scolaire)
        return qs.first()
    nom = (args.get('periode') or '').strip()
    qs = PeriodeScolaire.objects.filter(
        etablissement=ctx.etablissement,
        est_active=True,
    )
    if ctx.annee_scolaire:
        qs = qs.filter(annee_scolaire_fk=ctx.annee_scolaire)
    if nom:
        return qs.filter(nom_periode__icontains=nom).first()
    return qs.order_by('date_debut').filter(est_active=True).first() or qs.first()


def _resolve_matiere(ctx, classe, args):
    from school_admin.model.matiere_model import Matiere

    matiere_id = args.get('matiere_id')
    if matiere_id:
        matiere = Matiere.objects.filter(pk=matiere_id).first()
    else:
        q = (args.get('matiere') or '').strip()
        matiere = None
        if q:
            for m in Matiere.objects.filter(nom__icontains=q):
                if ensure_matiere_in_classe(ctx, classe, m) is None:
                    matiere = m
                    break
    if not matiere:
        return None, ['matiere']
    if ensure_matiere_in_classe(ctx, classe, matiere):
        return None, ['matiere']
    return matiere, []


def prepare_enregistrer_note(ctx, args):
    from school_admin.model.evaluation_model import Evaluation

    classe = find_classe_prof(ctx, args.get('classe') or '')
    if not classe:
        return _incomplete('enregistrer_note', ['classe'], 'Quelle classe ?')
    if err := ensure_classe_access(ctx, classe):
        return err
    eleve = find_eleve_prof(ctx, args.get('eleve') or args.get('query') or '', classe)
    if not eleve:
        return _incomplete('enregistrer_note', ['eleve'], 'Quel élève ?')
    eval_id = args.get('evaluation_id')
    eval_q = (args.get('evaluation') or args.get('titre') or '').strip()
    evaluation = None
    if eval_id:
        evaluation = Evaluation.objects.filter(
            pk=eval_id,
            classe=classe,
            professeur=ctx.professeur,
            actif=True,
        ).first()
    elif eval_q:
        evaluation = Evaluation.objects.filter(
            classe=classe,
            professeur=ctx.professeur,
            actif=True,
            titre__icontains=eval_q,
        ).first()
    if not evaluation:
        return _incomplete('enregistrer_note', ['evaluation'], 'Quelle évaluation ?')
    note_val = _parse_note(args.get('note'))
    if note_val is None:
        return _incomplete('enregistrer_note', ['note'], 'Quelle note ?')
    if note_val < 0 or note_val > evaluation.bareme:
        return {'erreur': f'Note invalide (barème {evaluation.bareme}).'}
    draft = {
        'classe_id': classe.id,
        'classe': classe.nom,
        'eleve_id': eleve.id,
        'eleve': eleve.nom_complet,
        'evaluation_id': evaluation.id,
        'evaluation': evaluation.titre,
        'note': str(note_val),
        'manquants': [],
    }
    return _pending(
        'enregistrer_note',
        f"Note {note_val} pour {eleve.nom_complet} en {evaluation.titre} ({classe.nom}).",
        **draft,
    )


def apply_enregistrer_note(ctx, draft):
    from school_admin.model.evaluation_model import Evaluation, Note
    from school_admin.model.releve_notes_model import ReleveNotes

    evaluation = Evaluation.objects.filter(
        pk=draft.get('evaluation_id'),
        professeur=ctx.professeur,
    ).select_related('classe', 'matiere', 'periode_scolaire').first()
    if not evaluation:
        return {'erreur': 'Évaluation introuvable.'}
    if err := ensure_classe_access(ctx, evaluation.classe):
        return err
    from school_admin.model.eleve_model import Eleve

    eleve = Eleve.objects.filter(pk=draft.get('eleve_id')).first()
    if err := ensure_eleve_access(ctx, eleve):
        return err
    note_val = _parse_note(draft.get('note'))
    if evaluation.matiere_id and evaluation.periode_scolaire_id:
        releve_qs = ReleveNotes.objects.filter(
            classe=evaluation.classe,
            professeur=ctx.professeur,
            matiere=evaluation.matiere,
            periode_scolaire=evaluation.periode_scolaire,
            soumis=True,
        )
        if ctx.annee_scolaire:
            releve_qs = releve_qs.filter(annee_scolaire=ctx.annee_scolaire)
        if releve_qs.exists():
            return {'erreur': 'Le relevé de cette matière est déjà soumis.'}
    note_obj, _created = Note.objects.get_or_create(
        eleve=eleve,
        evaluation=evaluation,
        defaults={
            'matiere': evaluation.matiere,
            'annee_scolaire': ctx.annee_scolaire,
            'absent': False,
        },
    )
    note_obj.note = note_val
    note_obj.absent = False
    if note_obj.note_publiee is None:
        note_obj.statut_publication = Note.STATUT_BROUILLON
    elif note_obj.note_publiee != note_val:
        note_obj.statut_publication = Note.STATUT_MODIFIEE
    note_obj.save(update_fields=['note', 'absent', 'statut_publication'])
    url = _reverse('enseignant:noter_eleves', [evaluation.classe_id])
    return _ok(
        f"Note {note_val} enregistrée pour {eleve.nom_complet}.",
        url=url,
    )


def prepare_creer_evaluation(ctx, args):
    classe = find_classe_prof(ctx, args.get('classe') or '')
    if not classe:
        return _incomplete('creer_evaluation', ['classe'], 'Pour quelle classe ?')
    if err := ensure_classe_access(ctx, classe):
        return err
    manquants = []
    titre = (args.get('titre') or '').strip()
    if not titre:
        manquants.append('titre')
    matiere, m_missing = _resolve_matiere(ctx, classe, args)
    if m_missing:
        manquants.extend(m_missing)
    periode = _resolve_periode(ctx, args, classe=classe)
    if not periode:
        if getattr(ctx, 'est_superieur', False):
            manquants.extend(['periode', 'niveau_lmd'])
        else:
            manquants.append('periode')
    date_eval = parse_date((args.get('date_evaluation') or '')[:10])
    if not date_eval:
        manquants.append('date_evaluation')
    bareme = args.get('bareme') or 20
    if manquants:
        return _incomplete(
            'creer_evaluation',
            manquants,
            'Il manque des informations pour créer l’évaluation.',
            classe_id=classe.id,
            classe=classe.nom,
            titre=titre,
            matiere_id=getattr(matiere, 'id', None),
            matiere=getattr(matiere, 'nom', None),
            periode_id=getattr(periode, 'id', None),
            periode=getattr(periode, 'nom_periode', None),
            date_evaluation=date_eval.isoformat() if date_eval else None,
            bareme=str(bareme),
        )
    draft = {
        'classe_id': classe.id,
        'titre': titre,
        'matiere_id': matiere.id,
        'periode_id': periode.id,
        'date_evaluation': date_eval.isoformat(),
        'bareme': str(bareme),
        'description': (args.get('description') or '')[:2000],
        'manquants': [],
    }
    return _pending(
        'creer_evaluation',
        f"Créer l’évaluation « {titre} » en {matiere.nom} pour {classe.nom}.",
        **draft,
    )


def apply_creer_evaluation(ctx, draft):
    from school_admin.model.classe_model import Classe
    from school_admin.model.evaluation_model import Evaluation
    from school_admin.model.matiere_model import Matiere
    from school_admin.model.periode_model import PeriodeScolaire

    classe = Classe.objects.filter(pk=draft.get('classe_id')).first()
    if err := ensure_classe_access(ctx, classe):
        return err
    matiere = Matiere.objects.filter(pk=draft.get('matiere_id')).first()
    if err := ensure_matiere_in_classe(ctx, classe, matiere):
        return err
    periode = PeriodeScolaire.objects.filter(pk=draft.get('periode_id')).first()
    date_eval = parse_date(draft.get('date_evaluation') or '')
    evaluation = Evaluation.objects.create(
        titre=draft.get('titre'),
        description=draft.get('description') or '',
        classe=classe,
        professeur=ctx.professeur,
        matiere=matiere,
        periode_scolaire=periode,
        date_evaluation=date_eval,
        bareme=Decimal(str(draft.get('bareme') or 20)),
        annee_scolaire=ctx.annee_scolaire,
        actif=True,
    )
    url = _reverse('enseignant:noter_eleves', [classe.id])
    return _ok(
        f"Évaluation « {evaluation.titre} » créée.",
        url=url,
        id=evaluation.id,
    )


def prepare_creer_exercice_maison(ctx, args):
    classe = find_classe_prof(ctx, args.get('classe') or '')
    if not classe:
        return _incomplete('creer_exercice_maison', ['classe'], 'Pour quelle classe ?')
    titre = (args.get('titre') or '').strip()
    if not titre:
        return _incomplete('creer_exercice_maison', ['titre'], 'Quel titre pour l’exercice ?')
    matiere, m_missing = _resolve_matiere(ctx, classe, args)
    if m_missing:
        return _incomplete('creer_exercice_maison', ['matiere'], 'Quelle matière ?')
    date_rendu = parse_date((args.get('date_rendu') or '')[:10])
    if not date_rendu:
        return _incomplete('creer_exercice_maison', ['date_rendu'], 'Quelle date de rendu ?')
    periode = _resolve_periode(ctx, args)
    draft = {
        'classe_id': classe.id,
        'titre': titre,
        'matiere_id': matiere.id,
        'date_rendu': date_rendu.isoformat(),
        'periode_id': periode.id if periode else None,
        'description': (args.get('description') or '')[:4000],
        'manquants': [],
    }
    return _pending(
        'creer_exercice_maison',
        f"Programmer « {titre} » pour {classe.nom}, rendu le {date_rendu.strftime('%d/%m/%Y')}.",
        **draft,
    )


def apply_creer_exercice_maison(ctx, draft):
    from school_admin.model.classe_model import Classe
    from school_admin.model.exercice_maison_model import ExerciceMaison
    from school_admin.model.matiere_model import Matiere
    from school_admin.model.periode_model import PeriodeScolaire

    classe = Classe.objects.filter(pk=draft.get('classe_id')).first()
    if err := ensure_classe_access(ctx, classe):
        return err
    matiere = Matiere.objects.filter(pk=draft.get('matiere_id')).first()
    if err := ensure_matiere_in_classe(ctx, classe, matiere):
        return err
    periode = None
    if draft.get('periode_id'):
        periode = PeriodeScolaire.objects.filter(pk=draft['periode_id']).first()
    date_rendu = parse_date(draft.get('date_rendu') or '')
    exercice = ExerciceMaison.objects.create(
        professeur=ctx.professeur,
        etablissement=ctx.etablissement,
        classe=classe,
        matiere=matiere,
        periode=periode,
        titre=draft.get('titre'),
        description=draft.get('description') or '',
        date_rendu=date_rendu,
        annee_scolaire=ctx.annee_scolaire,
        actif=True,
    )
    url = _reverse('enseignant:exercices_maison')
    return _ok(f"Exercice « {exercice.titre} » programmé.", url=url, id=exercice.id)


def prepare_enregistrer_presences(ctx, args):
    classe = find_classe_prof(ctx, args.get('classe') or '')
    if not classe:
        return _incomplete('enregistrer_presences', ['classe'], 'Pour quelle classe ?')
    eleve = find_eleve_prof(ctx, args.get('eleve') or args.get('query') or '', classe)
    statut = (args.get('statut') or 'present').strip().lower()
    if statut not in ('present', 'absent', 'retard', 'absent_justifie'):
        statut = 'present'
    if not eleve:
        return _incomplete(
            'enregistrer_presences',
            ['eleve'],
            'Quel élève et quel statut (présent, absent, retard) ?',
            classe_id=classe.id,
        )
    draft = {
        'classe_id': classe.id,
        'presences': [{'eleve_id': eleve.id, 'statut': statut}],
        'eleve': eleve.nom_complet,
        'statut': statut,
        'manquants': [],
    }
    return _pending(
        'enregistrer_presences',
        f"Marquer {eleve.nom_complet} comme {statut} pour {classe.nom}.",
        **draft,
    )


def apply_enregistrer_presences(ctx, draft):
    from school_admin.services.presence_sync_service import (
        PresenceSyncError,
        enregistrer_liste_presence,
    )

    try:
        result = enregistrer_liste_presence(ctx.professeur, {
            'classe_id': draft.get('classe_id'),
            'numero_appel': draft.get('numero_appel') or 1,
            'niveau': 'secondaire',
            'presences': draft.get('presences') or [],
        })
    except PresenceSyncError as exc:
        return {'erreur': exc.message}
    url = _reverse('enseignant:liste_presence', [draft.get('classe_id')])
    return _ok(result.get('message') or 'Présences enregistrées.', url=url)


def prepare_soumettre_sanction(ctx, args):
    classe = find_classe_prof(ctx, args.get('classe') or '')
    eleve = find_eleve_prof(ctx, args.get('eleve') or args.get('query') or '', classe)
    type_sanction = (args.get('type_sanction') or args.get('type') or '').strip()
    raison = (args.get('raison') or args.get('motif') or '').strip()
    manquants = []
    if not eleve:
        manquants.append('eleve')
    if not type_sanction:
        manquants.append('type_sanction')
    if not raison:
        manquants.append('raison')
    if manquants:
        return _incomplete('soumettre_sanction', manquants, 'Informations manquantes pour la sanction.')
    if not classe and eleve:
        from school_admin.services.assistant_enseignant_scope import classe_eleve_active

        classe = classe_eleve_active(ctx, eleve)
    if err := ensure_classe_access(ctx, classe):
        return err
    date_sanction = parse_date((args.get('date_sanction') or timezone.now().date().isoformat())[:10])
    draft = {
        'eleve_id': eleve.id,
        'classe_id': classe.id,
        'type_sanction': type_sanction,
        'raison': raison,
        'gravite': args.get('gravite') or 'moyenne',
        'description': (args.get('description') or '')[:2000],
        'date_sanction': date_sanction.isoformat(),
        'manquants': [],
    }
    return _pending(
        'soumettre_sanction',
        f"Sanction {type_sanction} pour {eleve.nom_complet} : {raison}.",
        **draft,
    )


def apply_soumettre_sanction(ctx, draft):
    from school_admin.model.classe_model import Classe
    from school_admin.model.eleve_model import Eleve
    from school_admin.model.sanction_model import Sanction

    eleve = Eleve.objects.filter(pk=draft.get('eleve_id')).first()
    classe = Classe.objects.filter(pk=draft.get('classe_id')).first()
    if err := ensure_eleve_access(ctx, eleve):
        return err
    if err := ensure_classe_access(ctx, classe):
        return err
    date_sanction = parse_date(draft.get('date_sanction') or '')
    sanction = Sanction.objects.create(
        eleve=eleve,
        classe=classe,
        professeur=ctx.professeur,
        etablissement=ctx.etablissement,
        type_sanction=draft.get('type_sanction'),
        raison=draft.get('raison'),
        gravite=draft.get('gravite') or 'moyenne',
        description=draft.get('description') or '',
        date_sanction=date_sanction,
        annee_scolaire=ctx.annee_scolaire,
    )
    url = _reverse('enseignant:gestion_eleves')
    return _ok(f"Sanction enregistrée pour {eleve.nom_complet}.", url=url, id=sanction.id)


def prepare_soumettre_releve_notes(ctx, args):
    classe = find_classe_prof(ctx, args.get('classe') or '')
    if not classe:
        return _incomplete('soumettre_releve_notes', ['classe'], 'Quelle classe ?')
    matiere, m_missing = _resolve_matiere(ctx, classe, args)
    if m_missing:
        return _incomplete('soumettre_releve_notes', ['matiere'], 'Quelle matière ?')
    periode = _resolve_periode(ctx, args)
    if not periode:
        return _incomplete('soumettre_releve_notes', ['periode'], 'Quelle période ?')
    draft = {
        'classe_id': classe.id,
        'matiere_id': matiere.id,
        'periode_id': periode.id,
        'manquants': [],
    }
    return _pending(
        'soumettre_releve_notes',
        f"Soumettre le relevé {matiere.nom} pour {classe.nom} ({periode.nom_periode}).",
        **draft,
    )


def apply_soumettre_releve_notes(ctx, draft):
    from school_admin.model.classe_model import Classe
    from school_admin.model.matiere_model import Matiere
    from school_admin.model.moyenne_model import Moyenne
    from school_admin.model.periode_model import PeriodeScolaire
    from school_admin.model.releve_notes_model import ReleveNotes

    classe = Classe.objects.filter(pk=draft.get('classe_id')).first()
    matiere = Matiere.objects.filter(pk=draft.get('matiere_id')).first()
    periode = PeriodeScolaire.objects.filter(pk=draft.get('periode_id')).first()
    if not (classe and matiere and periode):
        return {'erreur': 'Classe, matière ou période introuvable.'}
    if err := ensure_matiere_in_classe(ctx, classe, matiere):
        return err
    releve, _created = ReleveNotes.objects.get_or_create(
        classe=classe,
        professeur=ctx.professeur,
        matiere=matiere,
        etablissement=ctx.etablissement,
        periode_scolaire=periode,
        defaults={
            'annee_scolaire': ctx.annee_scolaire,
            'soumis': False,
            'actif': True,
        },
    )
    if releve.soumis:
        return {'erreur': 'Ce relevé est déjà soumis.'}
    releve.soumettre()
    Moyenne.objects.filter(
        classe=classe,
        professeur=ctx.professeur,
        matiere=matiere,
        periode=str(periode.id),
        actif=True,
    ).update(soumis=True)
    url = _reverse('enseignant:noter_eleves', [classe.id])
    return _ok('Relevé de notes soumis.', url=url)


def prepare_calculer_moyennes_matiere(ctx, args):
    classe = find_classe_prof(ctx, args.get('classe') or '')
    if not classe:
        return _incomplete('calculer_moyennes_matiere', ['classe'], 'Quelle classe ?')
    matiere, m_missing = _resolve_matiere(ctx, classe, args)
    if m_missing:
        return _incomplete('calculer_moyennes_matiere', ['matiere'], 'Quelle matière ?')
    periode = _resolve_periode(ctx, args)
    if not periode:
        return _incomplete('calculer_moyennes_matiere', ['periode'], 'Quelle période ?')
    draft = {
        'classe_id': classe.id,
        'matiere_id': matiere.id,
        'periode_id': periode.id,
        'mode_calcul': args.get('mode_calcul') or 'toutes',
        'ponderation': args.get('ponderation') or '50_50',
        'manquants': [],
    }
    return _pending(
        'calculer_moyennes_matiere',
        f"Calculer les moyennes {matiere.nom} pour {classe.nom}.",
        **draft,
    )


def apply_calculer_moyennes_matiere(ctx, draft):
    from school_admin.model.classe_model import Classe
    from school_admin.model.matiere_model import Matiere
    from school_admin.model.periode_model import PeriodeScolaire

    classe = Classe.objects.filter(pk=draft.get('classe_id')).first()
    matiere = Matiere.objects.filter(pk=draft.get('matiere_id')).first()
    periode = PeriodeScolaire.objects.filter(pk=draft.get('periode_id')).first()
    if not (classe and matiere and periode):
        return {'erreur': 'Classe, matière ou période introuvable.'}
    if err := ensure_matiere_in_classe(ctx, classe, matiere):
        return err
    url = _reverse('enseignant:calculer_moyennes', [classe.id])
    return _ok(
        f"J’ouvre le calcul des moyennes pour {classe.nom}. Validez sur la page.",
        url=url,
    )


register_enseignant_secondaire_action(ActionSpec(
    name='enregistrer_note',
    description='Enregistre une note pour un élève sur une évaluation.',
    properties={
        'classe': {'type': 'string'},
        'eleve': {'type': 'string'},
        'evaluation': {'type': 'string'},
        'evaluation_id': {'type': 'integer'},
        'note': {'type': 'string'},
    },
    required=('eleve', 'note'),
    prepare=prepare_enregistrer_note,
    apply=apply_enregistrer_note,
))

register_enseignant_secondaire_action(ActionSpec(
    name='creer_evaluation',
    description=(
        'Crée une nouvelle évaluation pour une classe et une matière enseignées. '
        'En supérieur LMD : indiquer le semestre (ex. Semestre 1) et le niveau LMD si besoin.'
    ),
    properties={
        'classe': {'type': 'string'},
        'titre': {'type': 'string'},
        'matiere': {'type': 'string'},
        'date_evaluation': {'type': 'string'},
        'bareme': {'type': 'number'},
        'periode': {'type': 'string', 'description': 'Semestre ou période (ex. Semestre 1).'},
        'semestre': {'type': 'string'},
        'niveau_lmd': {'type': 'string', 'description': 'L1, L2, M1… en supérieur.'},
        'description': {'type': 'string'},
    },
    required=('classe', 'titre', 'matiere', 'date_evaluation'),
    prepare=prepare_creer_evaluation,
    apply=apply_creer_evaluation,
))

register_enseignant_secondaire_action(ActionSpec(
    name='creer_exercice_maison',
    description='Programme un exercice à la maison.',
    properties={
        'classe': {'type': 'string'},
        'matiere': {'type': 'string'},
        'titre': {'type': 'string'},
        'date_rendu': {'type': 'string'},
        'description': {'type': 'string'},
        'periode': {'type': 'string'},
    },
    required=('classe', 'titre', 'matiere', 'date_rendu'),
    prepare=prepare_creer_exercice_maison,
    apply=apply_creer_exercice_maison,
))

register_enseignant_secondaire_action(ActionSpec(
    name='enregistrer_presences',
    description='Enregistre la présence d’un élève (présent, absent, retard).',
    properties={
        'classe': {'type': 'string'},
        'eleve': {'type': 'string'},
        'statut': {'type': 'string'},
    },
    required=('classe', 'eleve'),
    prepare=prepare_enregistrer_presences,
    apply=apply_enregistrer_presences,
))

register_enseignant_secondaire_action(ActionSpec(
    name='valider_presence_classe',
    description='Valide la liste de présence du jour pour une classe.',
    properties={
        'classe': {'type': 'string'},
        'numero_appel': {'type': 'integer'},
    },
    required=('classe',),
    prepare=prepare_enregistrer_presences,
    apply=apply_enregistrer_presences,
))

register_enseignant_secondaire_action(ActionSpec(
    name='soumettre_sanction',
    description='Soumet une sanction disciplinaire pour un élève.',
    properties={
        'eleve': {'type': 'string'},
        'classe': {'type': 'string'},
        'type_sanction': {'type': 'string'},
        'raison': {'type': 'string'},
        'date_sanction': {'type': 'string'},
        'gravite': {'type': 'string'},
        'description': {'type': 'string'},
    },
    required=('eleve', 'type_sanction', 'raison'),
    prepare=prepare_soumettre_sanction,
    apply=apply_soumettre_sanction,
))

register_enseignant_secondaire_action(ActionSpec(
    name='soumettre_releve_notes',
    description='Soumet le relevé de notes pour une matière (bloque les modifications).',
    properties={
        'classe': {'type': 'string'},
        'matiere': {'type': 'string'},
        'periode': {'type': 'string'},
    },
    required=('classe', 'matiere', 'periode'),
    prepare=prepare_soumettre_releve_notes,
    apply=apply_soumettre_releve_notes,
))

register_enseignant_secondaire_action(ActionSpec(
    name='calculer_moyennes_matiere',
    description='Calcule les moyennes d’une matière pour une classe et une période.',
    properties={
        'classe': {'type': 'string'},
        'matiere': {'type': 'string'},
        'periode': {'type': 'string'},
        'mode_calcul': {'type': 'string'},
        'ponderation': {'type': 'string'},
    },
    required=('classe', 'matiere', 'periode'),
    prepare=prepare_calculer_moyennes_matiere,
    apply=apply_calculer_moyennes_matiere,
))

from school_admin.services import assistant_enseignant_examens_actions  # noqa: F401
