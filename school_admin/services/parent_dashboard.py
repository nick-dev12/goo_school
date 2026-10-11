"""
Accueil parent (V3) : résumé clair de chaque enfant et des nouvelles importantes.

Règle : le parent ne voit que ce qui a été publié par l'établissement
(notes au statut « publiée », bulletins publiés).
"""
from __future__ import annotations

from django.db.models import Count, Q


def _sur20(note, bareme):
    try:
        note = float(note)
        bareme = float(bareme or 20) or 20.0
    except (TypeError, ValueError):
        return None
    return round(note / bareme * 20, 2)


def _dernieres_notes(eleve, annee, limit=3):
    from school_admin.model.evaluation_model import Note
    from school_admin.model.note_primaire_model import NotePrimaire

    notes = []
    qs = Note.objects.filter(eleve=eleve, statut_publication=Note.STATUT_PUBLIEE, absent=False)
    if annee:
        qs = qs.filter(annee_scolaire=annee)
    for n in qs.select_related('evaluation', 'matiere').order_by('-date_publication', '-date_saisie')[:limit]:
        valeur = n.note_publiee if n.note_publiee is not None else n.note
        notes.append({
            'matiere': getattr(n.matiere, 'nom', '') or getattr(n.evaluation.matiere, 'nom', ''),
            'titre': n.evaluation.titre,
            'valeur': valeur,
            'bareme': n.evaluation.bareme,
            'sur20': _sur20(valeur, n.evaluation.bareme),
            'date': n.date_publication or n.date_saisie,
        })
    if len(notes) < limit:
        qs_p = NotePrimaire.objects.filter(eleve=eleve, statut_publication='publiee', absent=False)
        if annee:
            qs_p = qs_p.filter(annee_scolaire=annee)
        for n in qs_p.select_related('evaluation_primaire__matiere').order_by('-date_publication', '-date_saisie')[: limit - len(notes)]:
            ev = n.evaluation_primaire
            valeur = n.note_publiee if n.note_publiee is not None else n.note
            notes.append({
                'matiere': getattr(ev.matiere, 'nom', ''),
                'titre': ev.titre,
                'valeur': valeur,
                'bareme': ev.bareme,
                'sur20': _sur20(valeur, ev.bareme),
                'date': n.date_publication or n.date_saisie,
            })
    return notes


def enrichir_enfants(enfants, request):
    """Ajoute à chaque entrée : moyenne publiée, assiduité, dernières notes, prochaine convocation."""
    from school_admin.model.convocation_model import Convocation
    from school_admin.model.moyenne_periode_model import MoyennePeriode
    from school_admin.model.presence_model import Presence
    from school_admin.utils.session_utils import get_session_active
    from django.utils import timezone

    today = timezone.localdate()
    for entry in enfants:
        eleve = entry['eleve']
        annee = get_session_active(request, eleve.etablissement) if eleve.etablissement else None

        presences = Presence.objects.filter(eleve=eleve)
        if annee:
            presences = presences.filter(annee_scolaire=annee)
        agg = presences.aggregate(
            total=Count('id'),
            absents=Count('id', filter=Q(statut__in=('absent', 'absent_justifie'))),
            retards=Count('id', filter=Q(statut='retard')),
        )
        # Assiduité : part des appels où l'enfant n'était pas absent (un retard compte comme présent).
        entry['assiduite'] = round((agg['total'] - agg['absents']) / agg['total'] * 100) if agg['total'] else None
        entry['retards'] = agg['retards'] or 0

        moyenne = (
            MoyennePeriode.objects.filter(eleve=eleve, est_moyenne_generale=True, est_publie=True,
                                          moyenne_generale__isnull=False)
            .select_related('periode').order_by('-periode__date_debut').first()
        )
        entry['moyenne'] = moyenne.moyenne_generale if moyenne else None
        entry['moyenne_periode'] = moyenne.periode.nom_periode if moyenne and moyenne.periode_id else ''

        entry['dernieres_notes'] = _dernieres_notes(eleve, annee)

        convocation = (
            Convocation.objects.filter(eleve=eleve, actif=True, date_convocation__gte=today)
            .order_by('date_convocation', 'heure_convocation').first()
        )
        entry['convocation'] = convocation
    return enfants


def nouvelles_parent(parent, enfants, annee):
    """Annonces récentes et convocations à venir, pour le bloc « À savoir »."""
    from school_admin.model.annonce_model import Annonce
    from school_admin.model.convocation_model import Convocation
    from django.db import NotSupportedError
    from django.utils import timezone

    today = timezone.localdate()
    annonces = []
    if parent.etablissement:
        base = Annonce.objects.filter(etablissement=parent.etablissement, statut='publiee', actif=True)
        if annee:
            base = base.filter(annee_scolaire=annee)
        base = base.order_by('-date_publication')
        try:
            annonces = list(
                base.filter(Q(destinataires__contains=['tous']) | Q(destinataires__contains=['parents']))[:3]
            )
        except NotSupportedError:
            annonces = [a for a in base[:20] if {'tous', 'parents'} & set(a.destinataires or [])][:3]

    eleve_ids = [e['eleve'].id for e in enfants]
    convocations = list(
        Convocation.objects.filter(eleve_id__in=eleve_ids, actif=True, date_convocation__gte=today)
        .select_related('eleve').order_by('date_convocation', 'heure_convocation')[:3]
    )
    return {'annonces': annonces, 'convocations': convocations}
