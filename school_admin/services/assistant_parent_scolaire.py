"""
Lecture scolaire parent — alignée sur les vues eleve (Par4).
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

READ_LIMIT = 15
DEVOIR_LIMIT = 12
EMPLOI_LIMIT = 25


def _dec(value):
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _annee_classe(eleve, ctx):
    from school_admin.model.annee_scolaire_model import AnneeScolaire
    from school_admin.personal_views.eleve_view import get_classe_eleve_active

    etab = eleve.etablissement
    annee = ctx.annee_scolaire
    if not annee and etab:
        annee = AnneeScolaire.get_session_active(etab)
    classe = get_classe_eleve_active(eleve, annee, etab) if eleve else None
    return annee, classe, etab


def _est_primaire_etab(etab):
    return getattr(etab, 'type_etablissement', None) == 'primary'


def _est_superieur_etab(etab):
    from school_admin.services.assistant_schema import classify_etablissement

    if not etab:
        return False
    return classify_etablissement(etab).get('est_superieur', False)


def read_notes_enfant(eleve, ctx):
    from school_admin.model.periode_model import PeriodeScolaire

    annee, classe, etab = _annee_classe(eleve, ctx)
    if not etab:
        return {'erreur': 'Établissement introuvable pour cet enfant.'}

    periode = None
    if annee:
        periode = (
            PeriodeScolaire.objects.filter(
                etablissement=etab,
                est_active=True,
                annee_scolaire_fk=annee,
            )
            .order_by('-date_debut')
            .first()
        )
    moyennes = []
    notes_detail = []
    moyenne_generale = None

    if _est_primaire_etab(etab):
        from school_admin.model.note_primaire_model import NotePrimaire, MoyenneMatierePrimaire

        if periode:
            mm_qs = MoyenneMatierePrimaire.objects.filter(
                eleve=eleve,
                periode_scolaire=periode,
            ).select_related('matiere')
            if annee:
                mm_qs = mm_qs.filter(annee_scolaire=annee)
            for m in mm_qs.exclude(moyenne__isnull=True)[:READ_LIMIT]:
                moyennes.append({
                    'matiere': m.matiere.nom if m.matiere_id else None,
                    'moyenne': _dec(m.moyenne),
                })
        n_qs = NotePrimaire.objects.filter(
            eleve=eleve,
            statut_publication='publiee',
        ).select_related('evaluation_primaire', 'evaluation_primaire__matiere')
        if annee:
            n_qs = n_qs.filter(
                Q(annee_scolaire=annee) | Q(annee_scolaire__isnull=True)
            )
        for n in n_qs.order_by('-id')[:READ_LIMIT]:
            notes_detail.append({
                'matiere': (
                    n.evaluation_primaire.matiere.nom
                    if n.evaluation_primaire_id and n.evaluation_primaire.matiere_id
                    else None
                ),
                'evaluation': n.evaluation_primaire.titre if n.evaluation_primaire_id else None,
                'note': _dec(n.note_publiee or n.note),
            })
    else:
        from school_admin.model.evaluation_model import Note
        from school_admin.model.moyenne_model import Moyenne

        if periode:
            m_qs = Moyenne.objects.filter(
                eleve=eleve,
                periode=str(periode.id),
                actif=True,
            ).select_related('matiere')
            if annee:
                m_qs = m_qs.filter(annee_scolaire=annee)
            for m in m_qs.exclude(moyenne__isnull=True)[:READ_LIMIT]:
                moyennes.append({
                    'matiere': m.matiere.nom if m.matiere_id else None,
                    'moyenne': _dec(m.moyenne),
                })
        n_qs = Note.objects.filter(
            eleve=eleve,
            statut_publication='publiee',
        ).select_related('evaluation', 'evaluation__matiere')
        if annee:
            n_qs = n_qs.filter(
                Q(evaluation__annee_scolaire=annee)
                | Q(evaluation__annee_scolaire__isnull=True)
            )
        for n in n_qs.order_by('-id')[:READ_LIMIT]:
            notes_detail.append({
                'matiere': (
                    n.evaluation.matiere.nom
                    if n.evaluation_id and n.evaluation.matiere_id
                    else None
                ),
                'evaluation': n.evaluation.titre if n.evaluation_id else None,
                'note': _dec(n.note),
            })

        from school_admin.model.moyenne_periode_model import MoyennePeriode

        mgp = MoyennePeriode.objects.filter(
            eleve=eleve,
            etablissement=etab,
            est_moyenne_generale=True,
            afficher_bulletin=True,
        )
        if annee:
            mgp = mgp.filter(annee_scolaire=annee)
        rec = mgp.order_by('-updated_at').first()
        if rec and rec.moyenne_generale is not None:
            moyenne_generale = _dec(rec.moyenne_generale)

    libelle = 'étudiant' if _est_superieur_etab(etab) else 'élève'
    msg_parts = [f"Notes de {eleve.prenom} ({libelle})."]
    if moyenne_generale is not None:
        msg_parts.append(f"Moyenne générale publiée : {moyenne_generale}.")
    if moyennes:
        msg_parts.append(f"{len(moyennes)} moyenne(s) par matière sur la période courante.")
    elif notes_detail:
        msg_parts.append(f"{len(notes_detail)} note(s) publiée(s) récente(s).")
    else:
        msg_parts.append('Aucune note publiée visible pour le moment.')

    return {
        'eleve_id': eleve.id,
        'nom': getattr(eleve, 'nom_complet', None) or f'{eleve.prenom} {eleve.nom}',
        'classe': classe.nom if classe else None,
        'type_etablissement': getattr(etab, 'type_etablissement', None),
        'periode': periode.nom_periode if periode else None,
        'moyenne_generale': moyenne_generale,
        'moyennes_matieres': moyennes,
        'notes_recentes': notes_detail,
        'url_notes': reverse('eleve:notes_evaluations'),
        'message': ' '.join(msg_parts),
    }


def read_bulletin_enfant(eleve, ctx):
    from school_admin.model.moyenne_periode_model import MoyennePeriode
    from school_admin.model.periode_model import PeriodeScolaire

    annee, classe, etab = _annee_classe(eleve, ctx)
    if not etab:
        return {'erreur': 'Établissement introuvable.'}
    if not classe:
        return {
            'erreur': 'Aucune classe active : bulletin indisponible.',
            'statut': 'classe_requise',
        }

    qs = MoyennePeriode.objects.filter(
        eleve=eleve,
        etablissement=etab,
        est_moyenne_generale=True,
        afficher_bulletin=True,
        moyenne_generale__isnull=False,
    ).select_related('periode')
    if annee:
        qs = qs.filter(annee_scolaire=annee)
    rec = qs.order_by('-updated_at').first()
    if not rec:
        return {
            'eleve_id': eleve.id,
            'publie': False,
            'message': f"Le bulletin de {eleve.prenom} n'est pas encore publié.",
            'url_bulletin': reverse('eleve:bulletin_eleve'),
        }

    periode_nom = rec.periode.nom_periode if rec.periode_id else None
    return {
        'eleve_id': eleve.id,
        'publie': True,
        'periode': periode_nom,
        'moyenne_generale': _dec(rec.moyenne_generale),
        'type_etablissement': getattr(etab, 'type_etablissement', None),
        'format': 'LMD' if _est_superieur_etab(etab) else 'standard',
        'url_bulletin': reverse('eleve:bulletin_eleve'),
        'message': (
            f"Bulletin publié pour {eleve.prenom}"
            + (f" — {periode_nom}" if periode_nom else '')
            + f", moyenne générale {_dec(rec.moyenne_generale)}."
        ),
    }


def read_devoirs_enfant(eleve, ctx, periode='semaine'):
    from school_admin.model.exercice_maison_model import ExerciceMaison
    from school_admin.model.evaluation_model import Evaluation
    from school_admin.model.evaluation_primaire_model import EvaluationPrimaire

    annee, classe, etab = _annee_classe(eleve, ctx)
    if not classe:
        return {'erreur': 'Classe active introuvable.', 'devoirs': [], 'evaluations': []}

    today = timezone.now().date()
    horizon = today + timedelta(days=14)
    if (periode or '').strip().lower() == 'semaine':
        horizon = today + timedelta(days=7)

    exercices = []
    ex_qs = ExerciceMaison.objects.filter(classe=classe, actif=True)
    if etab:
        ex_qs = ex_qs.filter(etablissement=etab)
    if annee:
        ex_qs = ex_qs.filter(annee_scolaire=annee)
    ex_qs = ex_qs.filter(date_rendu__gte=today, date_rendu__lte=horizon).select_related('matiere')
    for ex in ex_qs.order_by('date_rendu')[:DEVOIR_LIMIT]:
        exercices.append({
            'titre': ex.titre,
            'matiere': ex.matiere.nom if ex.matiere_id else None,
            'date_rendu': ex.date_rendu.isoformat() if ex.date_rendu else None,
        })

    evaluations = []
    if _est_primaire_etab(etab):
        ev_qs = EvaluationPrimaire.objects.filter(classe=classe, actif=True)
    else:
        ev_qs = Evaluation.objects.filter(classe=classe, actif=True)
    if annee:
        ev_qs = ev_qs.filter(annee_scolaire=annee)
    ev_qs = ev_qs.filter(date_evaluation__gte=today, date_evaluation__lte=horizon).select_related(
        'matiere'
    )
    for ev in ev_qs.order_by('date_evaluation')[:DEVOIR_LIMIT]:
        evaluations.append({
            'titre': ev.titre,
            'matiere': ev.matiere.nom if ev.matiere_id else None,
            'date': ev.date_evaluation.isoformat() if ev.date_evaluation else None,
        })

    return {
        'eleve_id': eleve.id,
        'exercices_maison': exercices,
        'evaluations_a_venir': evaluations,
        'nb_exercices': len(exercices),
        'nb_evaluations': len(evaluations),
        'url_devoirs': reverse('eleve:devoirs_eleve'),
        'message': (
            f"Pour {eleve.prenom} : {len(exercices)} exercice(s) à rendre "
            f"et {len(evaluations)} évaluation(s) à venir."
        ),
    }


def read_absences_enfant(eleve, ctx):
    from school_admin.model.presence_model import Presence

    annee, _classe, etab = _annee_classe(eleve, ctx)
    qs = Presence.objects.filter(eleve=eleve)
    if annee:
        qs = qs.filter(annee_scolaire=annee)
    total_abs = qs.filter(Q(statut='absent') | Q(statut='absent_justifie')).count()
    total_ret = qs.filter(statut='retard').count()
    recent = []
    for p in qs.filter(
        Q(statut='absent') | Q(statut='absent_justifie') | Q(statut='retard')
    ).order_by('-date')[:READ_LIMIT]:
        recent.append({
            'date': p.date.isoformat() if p.date else None,
            'statut': p.statut,
            'justifie': p.statut == 'absent_justifie',
        })
    return {
        'eleve_id': eleve.id,
        'total_absences': total_abs,
        'total_retards': total_ret,
        'derniers_evenements': recent,
        'url_absences': reverse('eleve:absences_retards'),
        'message': (
            f"Absences de {eleve.prenom} : {total_abs} absence(s), "
            f"{total_ret} retard(s) sur l'année en cours."
        ),
    }


def read_sanctions_enfant(eleve, ctx):
    from school_admin.model.sanction_model import Sanction

    annee, _classe, _etab = _annee_classe(eleve, ctx)
    qs = Sanction.objects.filter(eleve=eleve)
    if annee:
        qs = qs.filter(annee_scolaire=annee)
    items = []
    for s in qs.order_by('-date_sanction')[:READ_LIMIT]:
        items.append({
            'date': s.date_sanction.isoformat() if s.date_sanction else None,
            'type': s.get_type_sanction_display() if hasattr(s, 'get_type_sanction_display') else s.type_sanction,
            'gravite': getattr(s, 'gravite', None),
            'motif': (s.motif or '')[:160],
        })
    return {
        'eleve_id': eleve.id,
        'nb': len(items),
        'sanctions': items,
        'url_sanctions': reverse('eleve:sanctions_eleve'),
        'message': (
            f"{len(items)} sanction(s) récente(s) pour {eleve.prenom}."
            if items
            else f"Aucune sanction enregistrée pour {eleve.prenom}."
        ),
    }


def read_convocations_enfant(eleve, ctx, a_venir=True):
    from school_admin.model.convocation_model import Convocation

    annee, _classe, _etab = _annee_classe(eleve, ctx)
    today = timezone.now().date()
    qs = Convocation.objects.filter(eleve=eleve, actif=True)
    if annee:
        qs = qs.filter(annee_scolaire=annee)
    if a_venir:
        qs = qs.filter(date_convocation__gte=today)
    items = []
    for c in qs.order_by('date_convocation', 'heure_convocation')[:READ_LIMIT]:
        items.append({
            'date': c.date_convocation.isoformat() if c.date_convocation else None,
            'heure': str(c.heure_convocation) if c.heure_convocation else None,
            'motif': (c.motif or c.objet or '')[:160],
            'statut': c.statut,
            'lieu': getattr(c, 'lieu', None),
        })
    return {
        'eleve_id': eleve.id,
        'nb': len(items),
        'convocations': items,
        'url_convocations': reverse('eleve:convocations_eleve'),
        'message': (
            f"{len(items)} convocation(s) à venir pour {eleve.prenom}."
            if a_venir and items
            else f"{len(items)} convocation(s) listée(s) pour {eleve.prenom}."
        ),
    }


def read_convocations_famille(parent, ctx):
    from school_admin.model.convocation_model import Convocation
    from school_admin.services.assistant_parent_scope import liens_valides_qs

    eleve_ids = list(
        liens_valides_qs(parent).filter(eleve__actif=True).values_list('eleve_id', flat=True)
    )
    if not eleve_ids:
        return {'nb': 0, 'convocations': [], 'message': 'Aucun enfant lié.'}

    today = timezone.now().date()
    qs = Convocation.objects.filter(eleve_id__in=eleve_ids, actif=True)
    if ctx.annee_scolaire:
        qs = qs.filter(annee_scolaire=ctx.annee_scolaire)
    qs = qs.filter(date_convocation__gte=today).select_related('eleve', 'etablissement')
    items = []
    for c in qs.order_by('date_convocation', 'heure_convocation')[:READ_LIMIT]:
        items.append({
            'enfant': c.eleve.nom_complet if c.eleve_id else None,
            'etablissement': c.etablissement.nom if c.etablissement_id else None,
            'date': c.date_convocation.isoformat() if c.date_convocation else None,
            'heure': str(c.heure_convocation) if c.heure_convocation else None,
            'motif': (c.motif or c.objet or '')[:120],
            'statut': c.statut,
        })
    return {
        'nb': len(items),
        'convocations': items,
        'url_convocations_parent': reverse('school_admin:convocations_parent'),
        'message': f"{len(items)} convocation(s) à venir pour vos enfants.",
    }


def read_emploi_enfant(eleve, ctx):
    from school_admin.model.emploi_du_temps_model import CreneauEmploiDuTemps, EmploiDuTemps

    annee, classe, etab = _annee_classe(eleve, ctx)
    if not classe or not etab:
        return {'erreur': 'Classe ou établissement manquant pour l’emploi du temps.'}

    emplois = EmploiDuTemps.objects.filter(
        classe=classe,
        est_actif=True,
    )
    if annee:
        emplois = emplois.filter(annee_scolaire_fk=annee)
    emploi = emplois.filter(statut_publication='publie').order_by('-date_publication').first()
    if not emploi:
        return {
            'eleve_id': eleve.id,
            'publie': False,
            'creneaux': [],
            'url_edt': reverse('eleve:emploi_du_temps'),
            'message': f"L’emploi du temps de {eleve.prenom} n’est pas encore publié.",
        }

    creneaux = []
    c_qs = CreneauEmploiDuTemps.objects.filter(emploi_du_temps=emploi).select_related('matiere')
    for cr in c_qs.order_by('jour', 'heure_debut')[:EMPLOI_LIMIT]:
        creneaux.append({
            'jour': cr.jour,
            'debut': str(cr.heure_debut) if cr.heure_debut else None,
            'fin': str(cr.heure_fin) if cr.heure_fin else None,
            'matiere': cr.matiere.nom if cr.matiere_id else None,
        })
    return {
        'eleve_id': eleve.id,
        'publie': True,
        'creneaux': creneaux,
        'nb': len(creneaux),
        'url_edt': reverse('eleve:emploi_du_temps'),
        'message': f"Emploi du temps de {eleve.prenom} : {len(creneaux)} créneau(x) publié(s).",
    }
