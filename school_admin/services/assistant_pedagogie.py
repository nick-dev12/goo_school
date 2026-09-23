"""
Vague 3 — tools pédagogie pour l’assistant directeur.

Lecture : notes de classe, moyennes, bulletin, justifications, coefficients,
élèves en difficulté, évaluations.
Écriture : brouillon + confirmation (justification, coefficient, moyenne annuelle).
"""
from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation

from django.db.models import Q
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from school_admin.services.assistant_actions import (
    ActionSpec,
    _err,
    _find_classe,
    _find_eleve,
    _incomplete,
    _ok,
    _pending,
    register_action,
)
from school_admin.services.assistant_search import CLASSE_PARAM_DESCRIPTION

logger = logging.getLogger(__name__)

NOTES_LIMIT = 40
ELEVES_LIMIT = 24


def _reverse(route, args=None):
    try:
        return reverse(route, args=args or [])
    except NoReverseMatch:
        return None


def _safe(value):
    if value is None:
        return None
    return float(value)


def _find_periode(ctx, query=None):
    from school_admin.services.assistant_pilotage import _find_periode as finder

    return finder(ctx, query)


def _find_matiere(ctx, query):
    from school_admin.services.assistant_staff import _find_matiere as finder

    return finder(ctx, query)


def _seuil_passage(ctx):
    from school_admin.services.assistant_pilotage import _seuil_passage as finder

    return finder(ctx)


def _parse_coef(raw):
    text = str(raw or '').strip().replace(',', '.')
    if not text:
        return None
    try:
        value = Decimal(text)
    except (InvalidOperation, ValueError):
        return None
    if value < 0 or value > 10:
        return None
    return value.quantize(Decimal('0.1'))


def _eleves_classe(ctx, classe):
    from school_admin.services.assistant_tools import _eleves_qs

    return _eleves_qs(ctx).filter(classe=classe).select_related('classe')


# ---------------------------------------------------------------------------
# Lecture
# ---------------------------------------------------------------------------

def tool_notes_classe(ctx, args):
    args = args if isinstance(args, dict) else {}
    classe = _find_classe(ctx, args.get('classe') or args.get('query') or '')
    if not classe:
        return {'erreur': 'Indique la classe dont tu veux les notes.'}
    matiere = _find_matiere(ctx, args.get('matiere') or '') if args.get('matiere') else None
    periode = _find_periode(ctx, args.get('periode'))
    items = []
    if ctx.est_primaire:
        from school_admin.model.note_primaire_model import NotePrimaire

        qs = NotePrimaire.objects.filter(
            eleve__classe=classe,
            statut_publication=NotePrimaire.STATUT_PUBLIEE,
        ).select_related('eleve', 'evaluation_primaire', 'evaluation_primaire__matiere')
        if ctx.annee_scolaire:
            qs = qs.filter(
                Q(annee_scolaire=ctx.annee_scolaire) | Q(annee_scolaire__isnull=True)
            )
        if matiere:
            qs = qs.filter(evaluation_primaire__matiere=matiere)
        if periode:
            qs = qs.filter(evaluation_primaire__periode_scolaire=periode)
        for note in qs.order_by('eleve__nom', '-id')[:NOTES_LIMIT]:
            evaluation = note.evaluation_primaire
            items.append({
                'eleve': note.eleve.nom_complet,
                'matiere': evaluation.matiere.nom if evaluation and evaluation.matiere_id else None,
                'evaluation': evaluation.titre if evaluation else None,
                'note': _safe(note.note),
                'bareme': _safe(evaluation.bareme) if evaluation else 20,
            })
    else:
        from school_admin.model.evaluation_model import Note

        qs = Note.objects.filter(
            evaluation__classe=classe,
            statut_publication=Note.STATUT_PUBLIEE,
        ).select_related('eleve', 'evaluation', 'evaluation__matiere', 'matiere')
        if ctx.annee_scolaire:
            qs = qs.filter(
                Q(evaluation__annee_scolaire=ctx.annee_scolaire)
                | Q(evaluation__annee_scolaire__isnull=True)
            )
        if matiere:
            qs = qs.filter(Q(matiere=matiere) | Q(evaluation__matiere=matiere))
        if periode:
            qs = qs.filter(evaluation__periode_scolaire=periode)
        for note in qs.order_by('eleve__nom', '-id')[:NOTES_LIMIT]:
            evaluation = note.evaluation
            mat = note.matiere or (evaluation.matiere if evaluation else None)
            items.append({
                'eleve': note.eleve.nom_complet,
                'matiere': mat.nom if mat else None,
                'evaluation': evaluation.titre if evaluation else None,
                'note': _safe(note.note),
                'bareme': _safe(evaluation.bareme) if evaluation else 20,
            })
    return {
        'classe': classe.nom,
        'periode': periode.nom_periode if periode else None,
        'matiere': matiere.nom if matiere else None,
        'nb': len(items),
        'notes': items,
        'message': None if items else 'Aucune note publiée pour ce périmètre.',
    }


def tool_moyennes_classe(ctx, args):
    from school_admin.model.moyenne_periode_model import MoyennePeriode

    args = args if isinstance(args, dict) else {}
    classe = _find_classe(ctx, args.get('classe') or args.get('query') or '')
    if not classe:
        return {'erreur': 'Indique la classe dont tu veux les moyennes.'}
    periode = _find_periode(ctx, args.get('periode'))
    if not periode:
        return {'erreur': 'Aucune période scolaire trouvée.'}
    qs = MoyennePeriode.objects.filter(
        etablissement=ctx.etablissement,
        periode=periode,
        eleve__classe=classe,
    ).select_related('eleve', 'matiere')
    if ctx.annee_scolaire:
        qs = qs.filter(Q(annee_scolaire=ctx.annee_scolaire) | Q(annee_scolaire__isnull=True))
    generales = []
    for row in qs.filter(est_moyenne_generale=True, moyenne_generale__isnull=False).order_by(
        'rang', 'eleve__nom'
    )[:ELEVES_LIMIT]:
        item = {
            'eleve': row.eleve.nom_complet,
            'moyenne': _safe(row.moyenne_generale),
            'rang': row.rang,
            'publie': row.est_publie,
        }
        if ctx.est_superieur:
            credits_qs = qs.filter(
                eleve=row.eleve,
                est_moyenne_generale=False,
                credits__isnull=False,
            )
            inscrits = sum((c.credits or 0) for c in credits_qs)
            seuil = _seuil_passage(ctx)
            valides = sum(
                (c.credits or 0)
                for c in credits_qs
                if c.moyenne_matiere is not None and c.moyenne_matiere >= seuil
            )
            if inscrits:
                item['credits_inscrits'] = _safe(inscrits)
                item['credits_valides'] = _safe(valides)
        generales.append(item)
    matieres = []
    for row in qs.filter(est_moyenne_generale=False, matiere__isnull=False).order_by(
        'matiere__nom', 'eleve__nom'
    )[:NOTES_LIMIT]:
        matieres.append({
            'eleve': row.eleve.nom_complet,
            'matiere': row.matiere.nom,
            'moyenne': _safe(row.moyenne_matiere),
            'coefficient': _safe(row.coefficient),
            'credits': _safe(row.credits) if ctx.est_superieur else None,
        })
    return {
        'classe': classe.nom,
        'periode': periode.nom_periode,
        'seuil': _safe(_seuil_passage(ctx)),
        'nb': len(generales),
        'moyennes': generales,
        'par_matiere': matieres,
        'message': None if generales else 'Aucune moyenne calculée pour cette classe et cette période.',
    }


def tool_bulletin_eleve(ctx, args):
    args = args if isinstance(args, dict) else {}
    query = (args.get('query') or args.get('eleve') or '').strip()
    eleve = _find_eleve(ctx, query)
    if not eleve:
        return {'erreur': f'Aucun {ctx.libelle_eleve} trouvé pour « {query} ».'}
    if not eleve.classe_id:
        return {'erreur': f'{eleve.nom_complet} n’est pas affecté à une classe.'}
    periode = _find_periode(ctx, args.get('periode'))
    from school_admin.model.moyenne_periode_model import MoyennePeriode

    moy = None
    if periode:
        moy_qs = MoyennePeriode.objects.filter(
            eleve=eleve,
            etablissement=ctx.etablissement,
            periode=periode,
            est_moyenne_generale=True,
        )
        if ctx.annee_scolaire:
            moy_qs = moy_qs.filter(
                Q(annee_scolaire=ctx.annee_scolaire) | Q(annee_scolaire__isnull=True)
            )
        moy = moy_qs.first()
    ouvrir = args.get('ouvrir')
    if ouvrir is None:
        ouvrir = True
    url = _reverse('directeur:voir_bulletin_eleve', args=[eleve.classe_id, eleve.id])
    impression = _reverse('directeur:imprimer_bulletin_eleve', args=[eleve.classe_id, eleve.id])
    return {
        'eleve': eleve.nom_complet,
        'classe': eleve.classe.nom,
        'periode': periode.nom_periode if periode else None,
        'moyenne': _safe(moy.moyenne_generale) if moy else None,
        'rang': moy.rang if moy else None,
        'publie': moy.est_publie if moy else False,
        'url': url,
        'url_impression': impression,
        'ouvrir': bool(ouvrir),
        'titre': f'Bulletin de {eleve.nom_complet}',
        'message': None if moy else 'Aucune moyenne de période : le bulletin peut être vide.',
    }


def tool_imprimer_bulletins_classe(ctx, args):
    args = args if isinstance(args, dict) else {}
    classe = _find_classe(ctx, args.get('classe') or args.get('query') or '')
    if not classe:
        return {'erreur': 'Indique la classe dont tu veux imprimer les bulletins.'}
    ouvrir = args.get('ouvrir')
    if ouvrir is None:
        ouvrir = True
    url = _reverse('directeur:imprimer_bulletins_classe', args=[classe.id])
    return {
        'classe': classe.nom,
        'url': url,
        'ouvrir': bool(ouvrir),
        'titre': f'Impression des bulletins — {classe.nom}',
        'message': 'J’ouvre la page d’impression déjà existante. Aucun PDF n’est généré ici.',
    }


def tool_eleves_difficulte(ctx, args):
    from school_admin.model.moyenne_periode_model import MoyennePeriode

    args = args if isinstance(args, dict) else {}
    periode = _find_periode(ctx, args.get('periode'))
    if not periode:
        return {'erreur': 'Aucune période scolaire trouvée.'}
    classe = _find_classe(ctx, args.get('classe') or '') if args.get('classe') else None
    seuil = _seuil_passage(ctx)
    qs = MoyennePeriode.objects.filter(
        etablissement=ctx.etablissement,
        periode=periode,
        est_moyenne_generale=True,
        moyenne_generale__lt=seuil,
    ).select_related('eleve', 'eleve__classe')
    if ctx.annee_scolaire:
        qs = qs.filter(Q(annee_scolaire=ctx.annee_scolaire) | Q(annee_scolaire__isnull=True))
    if classe:
        qs = qs.filter(eleve__classe=classe)
    items = []
    for row in qs.order_by('moyenne_generale', 'eleve__nom')[:ELEVES_LIMIT]:
        item = {
            'eleve': row.eleve.nom_complet,
            'classe': row.eleve.classe.nom if row.eleve.classe_id else None,
            'moyenne': _safe(row.moyenne_generale),
            'rang': row.rang,
            'motif': 'sous_seuil',
        }
        if ctx.est_superieur:
            credits_qs = MoyennePeriode.objects.filter(
                eleve=row.eleve,
                etablissement=ctx.etablissement,
                periode=periode,
                est_moyenne_generale=False,
                credits__isnull=False,
            )
            inscrits = sum((c.credits or 0) for c in credits_qs)
            valides = sum(
                (c.credits or 0)
                for c in credits_qs
                if c.moyenne_matiere is not None and c.moyenne_matiere >= seuil
            )
            if inscrits:
                item['credits_inscrits'] = _safe(inscrits)
                item['credits_valides'] = _safe(valides)
                if valides < inscrits:
                    item['motif'] = 'credits_insuffisants'
        items.append(item)
    return {
        'periode': periode.nom_periode,
        'seuil': _safe(seuil),
        'perimetre': classe.nom if classe else 'etablissement',
        'nb': len(items),
        'eleves': items,
        'message': None if items else 'Aucun élève sous le seuil de passage pour cette période.',
    }


def tool_justifications_notes(ctx, args):
    from school_admin.model.justification_note_model import JustificationNote

    args = args if isinstance(args, dict) else {}
    qs = JustificationNote.objects.filter(
        etablissement=ctx.etablissement,
    ).select_related('eleve', 'classe', 'matiere', 'professeur', 'evaluation', 'evaluation_primaire')
    if ctx.annee_scolaire:
        qs = qs.filter(annee_scolaire=ctx.annee_scolaire)
    statut = (args.get('statut') or JustificationNote.STATUT_EN_ATTENTE).strip()
    if statut:
        qs = qs.filter(statut=statut)
    if args.get('classe'):
        classe = _find_classe(ctx, args.get('classe'))
        if classe:
            qs = qs.filter(classe=classe)
    query = (args.get('query') or args.get('eleve') or '').strip()
    if query:
        eleve = _find_eleve(ctx, query)
        if eleve:
            qs = qs.filter(eleve=eleve)
    items = []
    for just in qs.order_by('-date_creation')[:ELEVES_LIMIT]:
        items.append({
            'id': just.id,
            'eleve': just.eleve.nom_complet,
            'classe': just.classe.nom if just.classe_id else None,
            'matiere': just.matiere.nom if just.matiere_id else None,
            'ancienne_note': _safe(just.ancienne_note),
            'nouvelle_note': _safe(just.nouvelle_note),
            'motif': just.motif,
            'statut': just.get_statut_display(),
            'professeur': (
                f'{just.professeur.prenom} {just.professeur.nom}'
                if just.professeur_id else None
            ),
        })
    return {
        'statut': statut,
        'nb': qs.count(),
        'justifications': items,
        'url': _reverse('directeur:justifications_notes'),
    }


def tool_coefficients(ctx, args):
    from school_admin.model.matiere_model import Matiere

    args = args if isinstance(args, dict) else {}
    qs = Matiere.objects.filter(etablissement=ctx.etablissement, actif=True)
    query = (args.get('query') or args.get('matiere') or '').strip()
    if query:
        qs = qs.filter(Q(nom__icontains=query) | Q(code__icontains=query))
    items = []
    est_lycee_groupes = getattr(ctx, 'est_lycee', False) or getattr(ctx, 'est_college_lycee', False)
    groupes = {}
    if est_lycee_groupes:
        from school_admin.model.coefficient_matiere_groupe_model import CoefficientMatiereGroupe

        for coeff in CoefficientMatiereGroupe.objects.filter(
            etablissement=ctx.etablissement,
            matiere__in=qs,
        ).select_related('matiere'):
            groupes.setdefault(coeff.matiere_id, []).append({
                'groupe': coeff.nom_groupe,
                'coefficient': _safe(coeff.coefficient),
            })
    for matiere in qs.order_by('nom')[:NOTES_LIMIT]:
        item = {
            'nom': matiere.nom,
            'code': matiere.code,
            'coefficient': _safe(matiere.coefficient),
        }
        if ctx.est_superieur:
            item['credits'] = _safe(matiere.credits)
        if est_lycee_groupes:
            item['groupes'] = groupes.get(matiere.id, [])
        items.append(item)
    return {
        'nb': qs.count(),
        'matieres': items,
        'url': _reverse('matiere:liste_matieres'),
    }


def tool_evaluations(ctx, args):
    args = args if isinstance(args, dict) else {}
    classe = _find_classe(ctx, args.get('classe') or args.get('query') or '')
    if not classe:
        return {'erreur': 'Indique la classe dont tu veux les évaluations.'}
    matiere = _find_matiere(ctx, args.get('matiere') or '') if args.get('matiere') else None
    periode = _find_periode(ctx, args.get('periode'))
    items = []
    if ctx.est_primaire:
        from school_admin.model.evaluation_primaire_model import EvaluationPrimaire

        qs = EvaluationPrimaire.objects.filter(classe=classe, actif=True).select_related(
            'matiere', 'periode_scolaire'
        )
        if ctx.annee_scolaire:
            qs = qs.filter(
                Q(annee_scolaire=ctx.annee_scolaire) | Q(annee_scolaire__isnull=True)
            )
        if matiere:
            qs = qs.filter(matiere=matiere)
        if periode:
            qs = qs.filter(periode_scolaire=periode)
        for ev in qs.order_by('-date_evaluation')[:ELEVES_LIMIT]:
            items.append({
                'titre': ev.titre,
                'matiere': ev.matiere.nom if ev.matiere_id else None,
                'date': ev.date_evaluation.isoformat() if ev.date_evaluation else None,
                'bareme': _safe(ev.bareme),
                'periode': ev.periode_scolaire.nom_periode if ev.periode_scolaire_id else None,
            })
    else:
        from school_admin.model.evaluation_model import Evaluation

        qs = Evaluation.objects.filter(classe=classe, actif=True).select_related(
            'matiere', 'periode_scolaire'
        )
        if ctx.annee_scolaire:
            qs = qs.filter(Q(annee_scolaire=ctx.annee_scolaire) | Q(annee_scolaire__isnull=True))
        if matiere:
            qs = qs.filter(matiere=matiere)
        if periode:
            qs = qs.filter(periode_scolaire=periode)
        for ev in qs.order_by('-date_evaluation')[:ELEVES_LIMIT]:
            items.append({
                'titre': ev.titre,
                'matiere': ev.matiere.nom if ev.matiere_id else None,
                'date': ev.date_evaluation.isoformat() if ev.date_evaluation else None,
                'bareme': _safe(ev.bareme),
                'periode': ev.periode_scolaire.nom_periode if ev.periode_scolaire_id else None,
            })
    return {
        'classe': classe.nom,
        'periode': periode.nom_periode if periode else None,
        'matiere': matiere.nom if matiere else None,
        'nb': len(items),
        'evaluations': items,
    }


# ---------------------------------------------------------------------------
# Écriture
# ---------------------------------------------------------------------------

def _find_justification(ctx, args):
    from school_admin.model.justification_note_model import JustificationNote

    qs = JustificationNote.objects.filter(etablissement=ctx.etablissement)
    if ctx.annee_scolaire:
        qs = qs.filter(annee_scolaire=ctx.annee_scolaire)
    raw_id = args.get('id') or args.get('justification_id')
    if raw_id:
        try:
            found = qs.filter(pk=int(raw_id)).first()
            if found:
                return found
        except (TypeError, ValueError):
            pass
    query = (args.get('query') or args.get('eleve') or '').strip()
    if query:
        eleve = _find_eleve(ctx, query)
        if eleve:
            pending = qs.filter(
                eleve=eleve,
                statut=JustificationNote.STATUT_EN_ATTENTE,
            )
            matiere = _find_matiere(ctx, args.get('matiere') or '') if args.get('matiere') else None
            if matiere:
                pending = pending.filter(matiere=matiere)
            return pending.order_by('-date_creation').first()
    return qs.filter(statut=JustificationNote.STATUT_EN_ATTENTE).order_by('-date_creation').first() if not query else None


def prepare_traiter_justification(ctx, args):
    args = args if isinstance(args, dict) else {}
    just = _find_justification(ctx, args)
    if not just:
        return _incomplete(
            'traiter_justification',
            ['query'],
            'Quelle justification dois-je traiter ? Donne l’élève ou l’identifiant.',
        )
    from school_admin.model.justification_note_model import JustificationNote

    if just.statut != JustificationNote.STATUT_EN_ATTENTE:
        return _err('Cette justification a déjà été traitée.')
    decision = (args.get('decision') or args.get('action') or '').strip().lower()
    aliases = {
        'valider': 'valider',
        'accepter': 'valider',
        'approuver': 'valider',
        'oui': 'valider',
        'rejeter': 'rejeter',
        'refuser': 'rejeter',
        'non': 'rejeter',
    }
    decision = aliases.get(decision)
    if not decision:
        return _incomplete(
            'traiter_justification',
            ['decision'],
            (
                f'Accepter ou refuser la justification de {just.eleve.nom_complet} '
                f'({just.ancienne_note} → {just.nouvelle_note}) ?'
            ),
            justification_id=just.id,
            eleve=just.eleve.nom_complet,
        )
    commentaire = (args.get('commentaire') or args.get('motif') or '').strip()
    verbe = 'accepte' if decision == 'valider' else 'refuse'
    return _pending(
        'traiter_justification',
        (
            f'{verbe} la justification de {just.eleve.nom_complet} '
            f'({just.ancienne_note} → {just.nouvelle_note})'
        ),
        justification_id=just.id,
        decision=decision,
        commentaire=commentaire,
        eleve=just.eleve.nom_complet,
    )


def apply_traiter_justification(ctx, draft):
    from school_admin.model.justification_note_model import JustificationNote

    just = JustificationNote.objects.filter(
        pk=draft.get('justification_id'),
        etablissement=ctx.etablissement,
    ).select_related(
        'note', 'note_primaire', 'note_examen',
        'evaluation', 'evaluation_primaire', 'eleve',
    ).first()
    if not just:
        return _err('Justification introuvable.')
    if just.statut != JustificationNote.STATUT_EN_ATTENTE:
        return _err('Cette justification a déjà été traitée.')
    commentaire = draft.get('commentaire') or ''
    if draft.get('decision') == 'valider':
        note_obj = just.note or just.note_primaire or just.note_examen
        if not note_obj:
            return _err('Impossible de mettre à jour la note ciblée.')
        note_obj.note = just.nouvelle_note
        if hasattr(note_obj, 'absent'):
            note_obj.absent = False
        note_obj.save()
        just.statut = JustificationNote.STATUT_VALIDEE
        message = f'Note de {just.eleve.nom_complet} mise à jour ({just.nouvelle_note}).'
    else:
        just.statut = JustificationNote.STATUT_REFUSEE
        message = f'Justification de {just.eleve.nom_complet} refusée.'
    just.commentaire_direction = commentaire
    just.valide_par = ctx.etablissement
    just.date_validation = timezone.now()
    just.save()
    return _ok(
        message,
        id=just.id,
        url=_reverse('directeur:justifications_notes'),
    )


def prepare_configurer_coefficient(ctx, args):
    args = args if isinstance(args, dict) else {}
    matiere = _find_matiere(ctx, args.get('matiere') or args.get('query') or '')
    if not matiere:
        return _incomplete(
            'configurer_coefficient',
            ['matiere'],
            'Pour quelle matière dois-je changer le coefficient ?',
        )
    coefficient = _parse_coef(args.get('coefficient') or args.get('valeur'))
    if coefficient is None:
        return _incomplete(
            'configurer_coefficient',
            ['coefficient'],
            f'Quel coefficient pour {matiere.nom} (entre 0 et 10) ?',
            matiere=matiere.nom,
            matiere_id=matiere.id,
        )
    groupe = (args.get('groupe') or '').strip()
    if (getattr(ctx, 'est_lycee', False) or getattr(ctx, 'est_college_lycee', False)) and not groupe:
        classe = _find_classe(ctx, args.get('classe') or '') if args.get('classe') else None
        if classe:
            import re

            match = re.match(r'^(.+?)\s+([A-Z0-9]+)$', classe.nom)
            groupe = match.group(1).strip() if match else classe.nom
    resume = f'passe le coefficient de {matiere.nom} à {coefficient}'
    if groupe:
        resume += f' pour le groupe {groupe}'
    return _pending(
        'configurer_coefficient',
        resume,
        matiere_id=matiere.id,
        matiere=matiere.nom,
        coefficient=str(coefficient),
        groupe=groupe or None,
    )


def apply_configurer_coefficient(ctx, draft):
    from school_admin.model.matiere_model import Matiere

    matiere = Matiere.objects.filter(
        pk=draft.get('matiere_id'),
        etablissement=ctx.etablissement,
    ).first()
    if not matiere:
        return _err('Matière introuvable.')
    coefficient = _parse_coef(draft.get('coefficient'))
    if coefficient is None:
        return _err('Coefficient invalide.')
    groupe = draft.get('groupe')
    if groupe and (getattr(ctx, 'est_lycee', False) or getattr(ctx, 'est_college_lycee', False)):
        from school_admin.model.coefficient_matiere_groupe_model import CoefficientMatiereGroupe

        obj, _created = CoefficientMatiereGroupe.objects.update_or_create(
            matiere=matiere,
            etablissement=ctx.etablissement,
            nom_groupe=groupe,
            defaults={'coefficient': coefficient},
        )
        return _ok(
            f'Coefficient de {matiere.nom} ({groupe}) : {obj.coefficient}.',
            url=_reverse('matiere:liste_matieres'),
        )
    matiere.coefficient = coefficient
    matiere.save(update_fields=['coefficient', 'date_modification'])
    return _ok(
        f'Coefficient de {matiere.nom} : {matiere.coefficient}.',
        url=_reverse('matiere:liste_matieres'),
    )


def prepare_calculer_moyenne_annuelle(ctx, args):
    args = args if isinstance(args, dict) else {}
    classe = _find_classe(ctx, args.get('classe') or args.get('query') or '')
    if not classe:
        return _incomplete(
            'calculer_moyenne_annuelle',
            ['classe'],
            'Pour quelle classe dois-je calculer la moyenne annuelle ?',
        )
    periode = _find_periode(ctx, args.get('periode'))
    url = _reverse('directeur:calculer_moyenne_annuelle', args=[classe.id])
    if periode and url:
        url = f'{url}?periode={periode.id}'
    return _pending(
        'calculer_moyenne_annuelle',
        f'lance le calcul de la moyenne annuelle de {classe.nom}',
        classe_id=classe.id,
        classe=classe.nom,
        periode_id=periode.id if periode else None,
        url=url,
        ouvrir=True,
    )


def apply_calculer_moyenne_annuelle(ctx, draft):
    url = _reverse('directeur:calculer_moyenne_annuelle', args=[draft.get('classe_id')])
    if draft.get('periode_id') and url:
        url = f'{url}?periode={draft["periode_id"]}'
    return _ok(
        f'J’ouvre le calcul de la moyenne annuelle pour {draft.get("classe")}.',
        url=url,
        ouvrir=True,
    )


_STR = {'type': 'string'}
_CLASSE = {'type': 'string', 'description': CLASSE_PARAM_DESCRIPTION}

register_action(ActionSpec(
    'traiter_justification',
    'Accepte ou refuse une justification de note en attente (met à jour la note si acceptée).',
    {
        'query': {'type': 'string', 'description': 'Nom de l’élève'},
        'id': {'type': 'string', 'description': 'Identifiant de la justification'},
        'decision': {'type': 'string', 'enum': ['valider', 'rejeter']},
        'commentaire': _STR,
        'matiere': _STR,
    },
    prepare=prepare_traiter_justification,
    apply=apply_traiter_justification,
))
register_action(ActionSpec(
    'configurer_coefficient',
    'Modifie le coefficient d’une matière (0 à 10). En lycée, précise le groupe de classes.',
    {
        'matiere': _STR,
        'coefficient': _STR,
        'groupe': {'type': 'string', 'description': 'Groupe de classes (ex. 1ère, Terminale)'},
        'classe': _CLASSE,
    },
    prepare=prepare_configurer_coefficient,
    apply=apply_configurer_coefficient,
))
register_action(ActionSpec(
    'calculer_moyenne_annuelle',
    'Ouvre le calcul de la moyenne annuelle d’une classe (même route que le bouton directeur).',
    {'classe': _CLASSE, 'periode': _STR},
    prepare=prepare_calculer_moyenne_annuelle,
    apply=apply_calculer_moyenne_annuelle,
))


VAGUE3_READ_SCHEMA = [
    {
        'type': 'function',
        'function': {
            'name': 'get_notes_classe',
            'description': (
                'Notes publiées d’une classe, éventuellement filtrées par matière ou période. '
                'Primaire : NotePrimaire. Autres : Note + barème. Synthèse élève × évaluation.'
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'classe': _CLASSE,
                    'matiere': _STR,
                    'periode': _STR,
                },
                'required': ['classe'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'get_moyennes_classe',
            'description': (
                'Moyennes de période d’une classe (MoyennePeriode) : générale, rang, '
                'détail par matière. En supérieur, ajoute les crédits s’ils sont déjà calculés.'
            ),
            'parameters': {
                'type': 'object',
                'properties': {'classe': _CLASSE, 'periode': _STR},
                'required': ['classe'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'get_bulletin_eleve',
            'description': (
                'Résume et ouvre le bulletin d’un élève (URL existante, pas de PDF magique).'
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'query': {'type': 'string', 'description': 'Nom ou matricule'},
                    'periode': _STR,
                    'ouvrir': {'type': 'boolean'},
                },
                'required': ['query'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'imprimer_bulletins_classe',
            'description': 'Ouvre la page d’impression des bulletins d’une classe.',
            'parameters': {
                'type': 'object',
                'properties': {'classe': _CLASSE, 'ouvrir': {'type': 'boolean'}},
                'required': ['classe'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'get_eleves_difficulte',
            'description': (
                'Élèves sous le seuil de passage pour une période. '
                'En supérieur : crédits insuffisants s’ils sont calculés. '
                'Optionnellement une classe.'
            ),
            'parameters': {
                'type': 'object',
                'properties': {'classe': _CLASSE, 'periode': _STR},
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'get_justifications_notes',
            'description': (
                'Justifications de notes. Défaut : en attente. '
                'Filtres classe, élève, statut (en_attente, validee, refusee).'
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'classe': _CLASSE,
                    'query': _STR,
                    'statut': {
                        'type': 'string',
                        'enum': ['en_attente', 'validee', 'refusee'],
                    },
                },
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'get_coefficients',
            'description': (
                'Coefficients des matières. Lycée / mixte : coefficients par groupe. '
                'Supérieur : crédits matière s’ils existent, sans inventer d’ECTS.'
            ),
            'parameters': {
                'type': 'object',
                'properties': {'query': _STR, 'matiere': _STR},
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'get_evaluations',
            'description': 'Liste les évaluations d’une classe, éventuellement matière / période.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'classe': _CLASSE,
                    'matiere': _STR,
                    'periode': _STR,
                },
                'required': ['classe'],
            },
        },
    },
]

VAGUE3_READ_HANDLERS = {
    'get_notes_classe': tool_notes_classe,
    'get_moyennes_classe': tool_moyennes_classe,
    'get_bulletin_eleve': tool_bulletin_eleve,
    'imprimer_bulletins_classe': tool_imprimer_bulletins_classe,
    'get_eleves_difficulte': tool_eleves_difficulte,
    'get_justifications_notes': tool_justifications_notes,
    'get_coefficients': tool_coefficients,
    'get_evaluations': tool_evaluations,
}
