"""Suppression de sessions, commune à l’interface et à l’assistant."""
from django.db import transaction
from django.db.models import Q

from django.db.models import Subquery

from school_admin.model.classe_model import Classe
from school_admin.model.note_examen_model import NoteExamen
from school_admin.model.session_examen_model import SessionExamen


class SessionProtegee(Exception):
    pass


def verrouiller_classes_session(session_id, etablissement):
    """Verrouille les classes dans l’ordre utilisé par le jury et la saisie des notes."""
    ids = SessionExamen.objects.filter(pk=session_id, etablissement=etablissement).values_list('classes__pk', flat=True)
    list(Classe.objects.select_for_update().filter(pk__in=ids).order_by('pk').values_list('pk', flat=True))


def notes_session(session):
    return NoteExamen.objects.filter(Q(session_examen=session) | Q(creneau_examen__session_examen=session))


def notes_protegees(notes):
    return notes.filter(
        Q(note__isnull=False) | Q(note_sur_20__isnull=False) | Q(absent=True) |
        Q(absence_justifiee=True) | Q(soumis=True) | Q(date_soumission__isnull=False) |
        Q(note_publiee__isnull=False) | Q(date_publication__isnull=False) |
        ~Q(statut_publication='brouillon') |
        (Q(commentaire__isnull=False) & ~Q(commentaire=''))
    )


@transaction.atomic
def supprimer_session_sans_resultats(etablissement, session_id, annee=None):
    verrouiller_classes_session(session_id, etablissement)
    sessions = SessionExamen.objects.select_for_update().filter(etablissement=etablissement)
    if annee is not None:
        sessions = sessions.filter(annee_scolaire=annee)
    session = sessions.get(pk=session_id)
    note_ids = notes_session(session).order_by().values('pk')
    notes = NoteExamen.objects.filter(pk__in=Subquery(note_ids)).select_for_update().order_by('pk')
    list(notes.values_list('pk', flat=True))
    if notes_protegees(notes).exists():
        raise SessionProtegee(
            "Suppression interdite : cette session contient des notes, absences, soumissions ou publications."
        )
    nom, nb = session.nom_examen, session.creneaux.count()
    session.delete()
    return nom, nb
