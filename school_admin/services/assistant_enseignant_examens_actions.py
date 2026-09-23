"""
Action confirmee : enregistrer une note d'examen (college / lycee).
"""
from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.urls import NoReverseMatch, reverse

from school_admin.services.assistant_actions import CONFIRM_CHOICES, _incomplete, _ok, _pending
from school_admin.services.assistant_enseignant_examens_tools import _find_session_prof
from school_admin.services.assistant_enseignant_scope import (
    ensure_classe_access,
    ensure_eleve_access,
    find_classe_prof,
    find_eleve_prof,
)
from school_admin.services.assistant_enseignant_secondaire_actions import (
    ActionSpec,
    _parse_note,
    _resolve_matiere,
    register_enseignant_secondaire_action,
)

logger = logging.getLogger(__name__)


def _reverse(route, args=None):
    try:
        return reverse(route, args=args or [])
    except NoReverseMatch:
        return None


def _session_covers(session, classe, matiere):
    if not session.classes.filter(pk=classe.id).exists():
        return False
    return session.matieres.filter(pk=matiere.id).exists()


def prepare_enregistrer_note_examen(ctx, args):
    from school_admin.services.assistant_enseignant_examens_tools import _examens_allowed

    if not _examens_allowed(ctx):
        return {'erreur': 'Action examen indisponible pour ce profil.'}

    classe = find_classe_prof(ctx, args.get('classe') or '')
    if not classe:
        return _incomplete('enregistrer_note_examen', ['classe'], 'Pour quelle classe ?')
    if err := ensure_classe_access(ctx, classe):
        return err

    session = _find_session_prof(
        ctx,
        args.get('session') or args.get('nom_session') or args.get('nom') or '',
    )
    if not session:
        return _incomplete(
            'enregistrer_note_examen',
            ['session'],
            'Quelle session d\'examen ?',
            classe_id=classe.id,
            classe=classe.nom,
        )

    eleve = find_eleve_prof(ctx, args.get('eleve') or args.get('query') or '')
    if not eleve:
        return _incomplete(
            'enregistrer_note_examen',
            ['eleve'],
            'Quel eleve ?',
            classe_id=classe.id,
            session_id=session.id,
        )
    if err := ensure_eleve_access(ctx, eleve):
        return err

    matiere, m_missing = _resolve_matiere(ctx, classe, args)
    if m_missing:
        return _incomplete(
            'enregistrer_note_examen',
            m_missing,
            'Quelle matiere ?',
            classe_id=classe.id,
            session_id=session.id,
            eleve_id=eleve.id,
        )

    if not _session_covers(session, classe, matiere):
        return {
            'erreur': 'Cette session ne couvre pas la classe ou la matiere indiquee.',
        }

    absent = bool(args.get('absent'))
    note_val = None if absent else _parse_note(args.get('note'))
    if not absent and note_val is None:
        return _incomplete(
            'enregistrer_note_examen',
            ['note'],
            'Quelle note (ou absent) ?',
            classe_id=classe.id,
            session_id=session.id,
            eleve_id=eleve.id,
            matiere_id=matiere.id,
        )

    bareme = _parse_note(args.get('bareme')) or Decimal('20')

    from school_admin.model.note_examen_model import NoteExamen

    existing = NoteExamen.objects.filter(
        eleve=eleve,
        session_examen=session,
        matiere=matiere,
        actif=True,
    ).first()
    if existing and existing.soumis:
        return {'erreur': 'Les notes de cette session sont deja soumises et verrouillees.'}

    label_note = 'Absent' if absent else str(note_val)
    return _pending(
        'enregistrer_note_examen',
        (
            f"Note d'examen {label_note} pour {eleve.nom_complet}, "
            f"{matiere.nom}, session « {session.nom_examen} »."
        ),
        classe_id=classe.id,
        session_id=session.id,
        eleve_id=eleve.id,
        matiere_id=matiere.id,
        note=str(note_val) if note_val is not None else None,
        absent=absent,
        bareme=str(bareme),
    )


def apply_enregistrer_note_examen(ctx, draft):
    from school_admin.model.classe_model import Classe
    from school_admin.model.eleve_model import Eleve
    from school_admin.model.matiere_model import Matiere
    from school_admin.model.note_examen_model import NoteExamen
    from school_admin.model.session_examen_model import SessionExamen

    classe = Classe.objects.filter(pk=draft.get('classe_id')).first()
    session = SessionExamen.objects.filter(pk=draft.get('session_id')).first()
    eleve = Eleve.objects.filter(pk=draft.get('eleve_id')).first()
    matiere = Matiere.objects.filter(pk=draft.get('matiere_id')).first()
    if not (classe and session and eleve and matiere):
        return {'erreur': 'Donnees incompletes pour la note d\'examen.'}
    if err := ensure_classe_access(ctx, classe):
        return err
    if err := ensure_eleve_access(ctx, eleve):
        return err
    if not _session_covers(session, classe, matiere):
        return {'erreur': 'Session, classe ou matiere invalides.'}

    absent = bool(draft.get('absent'))
    bareme = Decimal(str(draft.get('bareme') or '20'))
    note_raw = draft.get('note')
    note_val = None if absent else Decimal(str(note_raw))

    with transaction.atomic():
        note_obj, _created = NoteExamen.objects.get_or_create(
            eleve=eleve,
            session_examen=session,
            matiere=matiere,
            defaults={
                'professeur': ctx.professeur,
                'classe': classe,
                'bareme': bareme,
                'annee_scolaire': ctx.annee_scolaire,
            },
        )
        if note_obj.soumis:
            return {'erreur': 'Note deja soumise, modification impossible.'}
        note_obj.professeur = ctx.professeur
        note_obj.classe = classe
        note_obj.bareme = bareme
        note_obj.absent = absent
        if absent:
            note_obj.note = None
        else:
            note_obj.note = note_val
        if note_obj.statut_publication == NoteExamen.STATUT_PUBLIEE and note_obj.note_publiee != note_val:
            note_obj.statut_publication = NoteExamen.STATUT_MODIFIEE
        elif not note_obj.note_publiee:
            note_obj.statut_publication = NoteExamen.STATUT_BROUILLON
        note_obj.save()

    url = _reverse(
        'enseignant:noter_examen_session',
        [classe.id, session.id],
    )
    return _ok(
        f"Note d'examen enregistree pour {eleve.nom_complet}.",
        url=url,
    )


register_enseignant_secondaire_action(
    ActionSpec(
        name='enregistrer_note_examen',
        description=(
            'Enregistre ou met a jour une note d\'examen (session, eleve, matiere). '
            'College / lycee uniquement.'
        ),
        properties={
            'classe': {'type': 'string'},
            'session': {'type': 'string'},
            'nom_session': {'type': 'string'},
            'eleve': {'type': 'string'},
            'matiere': {'type': 'string'},
            'note': {'type': 'string'},
            'bareme': {'type': 'number'},
            'absent': {'type': 'boolean'},
        },
        required=('classe', 'session', 'eleve'),
        prepare=prepare_enregistrer_note_examen,
        apply=apply_enregistrer_note_examen,
    )
)
