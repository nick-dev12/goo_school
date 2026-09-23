"""
Vague 6 — tools examens pour l’assistant directeur.

Lecture : sessions enrichies, emploi des examens, notes d’examen.
Écriture : brouillon + confirmation (modifier session, ajouter / supprimer créneau).
Créneaux et notes : collège / lycée / mixte / supérieur — masqués en primaire.
Pas de tools CG.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Q
from django.urls import NoReverseMatch, reverse

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

SEARCH_LIMIT = 24
NOTES_LIMIT = 40

_STR = {'type': 'string'}

_SESSION_NOISE = re.compile(
    r'\b(session|examen|examens|emploi|cr[ée]neau|creneau|cr[ée]neaux|'
    r'notes?|de|du|des|la|le|les|quel|quelle|quels|quelles|'
    r'ouvre|montre|affiche|liste|donne)\b',
    re.IGNORECASE,
)
_ELEVE_NOISE = re.compile(
    r'\b(notes?|examen|examens|session|de|du|des|la|le|les|'
    r'quel|quelle|élève|eleve|étudiant|etudiant)\b',
    re.IGNORECASE,
)


def _clean_query(query, noise):
    cleaned = noise.sub(' ', query or '')
    return re.sub(r'\s+', ' ', cleaned).strip()


def _reverse(route, args=None):
    try:
        return reverse(route, args=args or [])
    except NoReverseMatch:
        return None


def _validation_message(exc):
    if hasattr(exc, 'message_dict'):
        parts = []
        for messages in exc.message_dict.values():
            if isinstance(messages, (list, tuple)):
                parts.extend(str(item) for item in messages)
            else:
                parts.append(str(messages))
        return ' '.join(parts) or str(exc)
    return str(exc)


def _parse_time(raw):
    from school_admin.services.assistant_emploi import _time_obj

    return _time_obj(raw)


def _find_session(ctx, query):
    from school_admin.services.assistant_actions import _find_session_examen

    found = _find_session_examen(ctx, query)
    if found:
        return found
    cleaned = _clean_query(query, _SESSION_NOISE)
    if cleaned and cleaned != (query or '').strip():
        return _find_session_examen(ctx, cleaned)
    return None


def _find_matiere(ctx, query):
    from school_admin.services.assistant_emploi import _find_matiere as finder

    return finder(ctx, query)


def _find_salle(ctx, query):
    from school_admin.services.assistant_emploi import _find_salle as finder

    return finder(ctx, query)


def _find_professeur(ctx, query):
    from school_admin.services.assistant_emploi import _find_professeur as finder

    return finder(ctx, query)


def _find_classe(ctx, query):
    from school_admin.services.assistant_actions import _find_classe as finder

    return finder(ctx, query)


def _find_eleve(ctx, query):
    from school_admin.services.assistant_actions import _find_eleve as finder

    return finder(ctx, query)


def _find_periode(ctx, query):
    from school_admin.services.assistant_actions import _find_periode as finder

    return finder(ctx, query)


def _sessions_qs(ctx):
    from school_admin.model.session_examen_model import SessionExamen

    qs = SessionExamen.objects.filter(etablissement=ctx.etablissement)
    if ctx.annee_scolaire:
        qs = qs.filter(Q(annee_scolaire=ctx.annee_scolaire) | Q(annee_scolaire__isnull=True))
    return qs


def _session_item(session):
    classes = list(session.classes.all())
    return {
        'id': session.id,
        'nom': session.nom_examen,
        'periode': session.periode.nom_periode if session.periode_id else None,
        'debut': session.date_debut.isoformat() if session.date_debut else None,
        'fin': session.date_fin.isoformat() if session.date_fin else None,
        'nb_creneaux': getattr(session, 'nb_creneaux', None),
        'classes': [classe.nom for classe in classes],
        'nb_classes': len(classes),
    }


def tool_examens(ctx, args):
    """Sessions d’examen + nombre de créneaux et classes concernées."""
    args = args if isinstance(args, dict) else {}
    qs = _sessions_qs(ctx).select_related('periode').prefetch_related('classes')
    query = (args.get('query') or args.get('nom') or '').strip()
    if query:
        qs = qs.filter(nom_examen__icontains=query)
    qs = qs.annotate(
        nb_creneaux=Count('creneaux', filter=Q(creneaux__actif=True)),
    ).order_by('-date_creation')[:SEARCH_LIMIT]
    items = [_session_item(session) for session in qs]
    return {'nb': len(items), 'sessions': items}


def _creneau_item(creneau):
    return {
        'id': creneau.id,
        'session': creneau.session_examen.nom_examen if creneau.session_examen_id else None,
        'session_id': creneau.session_examen_id,
        'matiere': creneau.matiere.nom if creneau.matiere_id else None,
        'date': creneau.date_examen.isoformat() if creneau.date_examen else None,
        'heure_debut': creneau.heure_debut.strftime('%H:%M') if creneau.heure_debut else None,
        'heure_fin': creneau.heure_fin.strftime('%H:%M') if creneau.heure_fin else None,
        'salle': creneau.salle.nom if creneau.salle_id else None,
        'surveillant': creneau.surveillant.nom_complet if creneau.surveillant_id else None,
        'annule': creneau.est_annule,
    }


def tool_emploi_examens(ctx, args):
    from school_admin.model.creneau_examen_model import CreneauExamen

    args = args if isinstance(args, dict) else {}
    query = (args.get('query') or args.get('session') or args.get('nom') or '').strip()
    session = _find_session(ctx, query) if query else None
    if query and not session:
        return {'erreur': f'Aucune session d’examen « {query} ».'}

    qs = CreneauExamen.objects.filter(
        session_examen__etablissement=ctx.etablissement,
        actif=True,
    ).select_related('session_examen', 'matiere', 'salle', 'surveillant')
    if ctx.annee_scolaire:
        qs = qs.filter(
            Q(annee_scolaire=ctx.annee_scolaire)
            | Q(annee_scolaire__isnull=True)
            | Q(session_examen__annee_scolaire=ctx.annee_scolaire)
            | Q(session_examen__annee_scolaire__isnull=True)
        )
    if session:
        qs = qs.filter(session_examen=session)
    items = [
        _creneau_item(creneau)
        for creneau in qs.order_by('date_examen', 'heure_debut')[:SEARCH_LIMIT]
    ]
    payload = {
        'nb': len(items),
        'creneaux': items,
        'url': _reverse('directeur:emploi_du_temps_examens'),
    }
    if session:
        payload['session'] = session.nom_examen
        payload['session_id'] = session.id
        payload['classes'] = [classe.nom for classe in session.classes.all()]
    return payload


def _note_item(note):
    return {
        'id': note.id,
        'eleve': note.eleve.nom_complet if note.eleve_id else None,
        'session': note.session_examen.nom_examen if note.session_examen_id else None,
        'matiere': note.matiere.nom if note.matiere_id else None,
        'classe': note.classe.nom if note.classe_id else None,
        'note': float(note.note) if note.note is not None else None,
        'bareme': float(note.bareme) if note.bareme is not None else None,
        'note_sur_20': float(note.note_sur_20) if note.note_sur_20 is not None else None,
        'absent': note.absent,
        'statut_publication': note.statut_publication,
        'format': note.note_format,
    }


def tool_notes_examen(ctx, args):
    from school_admin.model.note_examen_model import NoteExamen

    args = args if isinstance(args, dict) else {}
    session_query = (args.get('session') or args.get('nom_session') or '').strip()
    eleve_query = (args.get('eleve') or '').strip()
    raw_query = (args.get('query') or '').strip()
    classe_query = (args.get('classe') or '').strip()
    matiere_query = (args.get('matiere') or '').strip()

    session = _find_session(ctx, session_query) if session_query else None
    if not session and raw_query:
        session = _find_session(ctx, raw_query)
    if session_query and not session:
        return {'erreur': f'Aucune session d’examen « {session_query} ».'}

    eleve = None
    if eleve_query:
        eleve = _find_eleve(ctx, eleve_query)
    if not eleve and raw_query and not session:
        eleve = _find_eleve(ctx, raw_query) or _find_eleve(
            ctx, _clean_query(raw_query, _ELEVE_NOISE)
        )
    if raw_query and not session and not eleve and not classe_query and not session_query:
        return {'erreur': f'Aucun élève ni session « {raw_query} ». N’invente aucune note.'}

    classe = _find_classe(ctx, classe_query) if classe_query else None
    matiere = _find_matiere(ctx, matiere_query) if matiere_query else None

    qs = NoteExamen.objects.filter(
        session_examen__etablissement=ctx.etablissement,
        actif=True,
    ).select_related('eleve', 'session_examen', 'matiere', 'classe', 'professeur')
    if session:
        qs = qs.filter(session_examen=session)
    if eleve:
        qs = qs.filter(eleve=eleve)
    if classe:
        qs = qs.filter(classe=classe)
    if matiere:
        qs = qs.filter(matiere=matiere)
    if ctx.annee_scolaire:
        qs = qs.filter(
            Q(annee_scolaire=ctx.annee_scolaire) | Q(annee_scolaire__isnull=True)
        )

    items = [_note_item(note) for note in qs.order_by('eleve__nom', 'matiere__nom')[:NOTES_LIMIT]]
    return {
        'nb': qs.count(),
        'notes': items,
        'session': session.nom_examen if session else None,
        'eleve': eleve.nom_complet if eleve else None,
        'classe': classe.nom if classe else None,
        'matiere': matiere.nom if matiere else None,
        'message': (
            None
            if items
            else 'Aucune note d’examen enregistrée pour ce filtre. N’invente aucun chiffre.'
        ),
    }


def _find_creneau(ctx, args, session=None):
    from school_admin.model.creneau_examen_model import CreneauExamen

    qs = CreneauExamen.objects.filter(
        session_examen__etablissement=ctx.etablissement,
        actif=True,
    ).select_related('session_examen', 'matiere', 'salle', 'surveillant')
    raw_id = args.get('id') or args.get('creneau_id')
    if raw_id and str(raw_id).isdigit():
        found = qs.filter(pk=int(raw_id)).first()
        if found:
            return found
    if session:
        qs = qs.filter(session_examen=session)
    date_examen = _parse_date(args.get('date') or args.get('date_examen'))
    if date_examen:
        qs = qs.filter(date_examen=date_examen)
    matiere_query = (args.get('matiere') or '').strip()
    if matiere_query:
        matiere = _find_matiere(ctx, matiere_query)
        if matiere:
            qs = qs.filter(matiere=matiere)
        else:
            qs = qs.filter(matiere__nom__icontains=matiere_query)
    return qs.order_by('date_examen', 'heure_debut').first()


def prepare_modifier_session_examen(ctx, args):
    args = args if isinstance(args, dict) else {}
    session = _find_session(ctx, args.get('query') or args.get('nom') or args.get('session'))
    if not session:
        return _incomplete(
            'modifier_session_examen',
            ['query'],
            'Quelle session d’examen dois-je modifier ?',
        )
    nom = (args.get('nouveau_nom') or args.get('nom_examen') or '').strip()
    if nom and nom.lower() == (session.nom_examen or '').lower() and not args.get('nouveau_nom'):
        # « modifier la session BEPC » avec nom = nom actuel : pas un nouveau nom
        nom = ''
    periode = None
    if args.get('periode'):
        periode = _find_periode(ctx, args.get('periode'))
        if not periode:
            return _incomplete(
                'modifier_session_examen',
                ['periode'],
                'Quelle période scolaire ?',
                query=session.nom_examen,
            )
    date_debut = _parse_date(args.get('date_debut'))
    date_fin = _parse_date(args.get('date_fin'))
    if not any((nom, periode, date_debut, date_fin, args.get('description') is not None)):
        return _incomplete(
            'modifier_session_examen',
            ['nom_examen', 'date_debut', 'date_fin', 'periode'],
            f'Que modifier pour la session « {session.nom_examen} » : nom, dates ou période ?',
            query=session.nom_examen,
        )
    new_nom = nom or session.nom_examen
    new_debut = date_debut or session.date_debut
    new_fin = date_fin or session.date_fin
    new_periode = periode or session.periode
    return _pending(
        'modifier_session_examen',
        (
            f'modifie la session « {session.nom_examen} » '
            f'({new_nom}, {new_debut.isoformat()} → {new_fin.isoformat()}, '
            f'{new_periode.nom_periode if new_periode else "—"})'
        ),
        id=session.id,
        nom=new_nom,
        periode_id=new_periode.id if new_periode else None,
        periode=new_periode.nom_periode if new_periode else None,
        date_debut=new_debut.isoformat() if new_debut else None,
        date_fin=new_fin.isoformat() if new_fin else None,
        description=(
            args.get('description')
            if args.get('description') is not None
            else session.description
        ),
        url=_reverse('directeur:gestion_examens'),
    )


def apply_modifier_session_examen(ctx, draft):
    from school_admin.model.periode_model import PeriodeScolaire
    from school_admin.model.session_examen_model import SessionExamen

    session = SessionExamen.objects.filter(
        pk=draft.get('id'), etablissement=ctx.etablissement
    ).first()
    if not session:
        return _err('Session d’examen introuvable.')
    periode = PeriodeScolaire.objects.filter(
        pk=draft.get('periode_id'), etablissement=ctx.etablissement
    ).first()
    if not periode:
        return _err('Période introuvable.')
    session.nom_examen = draft['nom']
    session.periode = periode
    session.date_debut = _parse_date(draft['date_debut'])
    session.date_fin = _parse_date(draft['date_fin'])
    if 'description' in draft:
        session.description = draft.get('description') or None
    try:
        session.full_clean()
        session.save()
    except ValidationError as exc:
        return _err(_validation_message(exc))
    from school_admin.services.assistant_actions import _emit

    _emit(ctx, 'examen.mise_a_jour', {'id': session.id, 'action': 'modifiee'})
    return _ok(
        f'Session d’examen « {session.nom_examen} » mise à jour.',
        id=session.id,
        url=_reverse('directeur:gestion_examens'),
    )


def prepare_ajouter_creneau_examen(ctx, args):
    args = args if isinstance(args, dict) else {}
    session = _find_session(ctx, args.get('session') or args.get('query') or args.get('nom'))
    if not session:
        return _incomplete(
            'ajouter_creneau_examen',
            ['session'],
            'Pour quelle session d’examen dois-je ajouter un créneau ?',
        )
    matiere = _find_matiere(ctx, args.get('matiere'))
    if not matiere:
        return _incomplete(
            'ajouter_creneau_examen',
            ['matiere'],
            'Quelle matière pour ce créneau d’examen ?',
            session=session.nom_examen,
        )
    date_examen = _parse_date(args.get('date') or args.get('date_examen'))
    if not date_examen:
        return _incomplete(
            'ajouter_creneau_examen',
            ['date'],
            'Quel jour pour ce créneau d’examen ?',
            session=session.nom_examen,
            matiere=matiere.nom,
        )
    heure_debut = _parse_time(args.get('heure_debut'))
    heure_fin = _parse_time(args.get('heure_fin'))
    if not heure_debut or not heure_fin:
        return _incomplete(
            'ajouter_creneau_examen',
            ['heure_debut', 'heure_fin'],
            'Quelles heures de début et de fin ?',
            session=session.nom_examen,
            matiere=matiere.nom,
            date=date_examen.isoformat(),
        )
    if heure_fin <= heure_debut:
        return _err('L’heure de fin doit être après l’heure de début.')
    if date_examen < session.date_debut or date_examen > session.date_fin:
        return _err(
            f'La date doit être entre le {session.date_debut} et le {session.date_fin} '
            f'(session « {session.nom_examen} »).'
        )
    salle = _find_salle(ctx, args.get('salle')) if args.get('salle') else None
    if args.get('salle') and not salle:
        return _incomplete(
            'ajouter_creneau_examen',
            ['salle'],
            f'Quelle salle ? Je ne trouve pas « {args.get("salle")} ».',
            session=session.nom_examen,
            matiere=matiere.nom,
        )
    surveillant = (
        _find_professeur(ctx, args.get('surveillant') or args.get('professeur'))
        if (args.get('surveillant') or args.get('professeur'))
        else None
    )
    if (args.get('surveillant') or args.get('professeur')) and not surveillant:
        return _incomplete(
            'ajouter_creneau_examen',
            ['surveillant'],
            'Quel surveillant ? Je ne trouve pas ce professeur.',
            session=session.nom_examen,
            matiere=matiere.nom,
        )
    return _pending(
        'ajouter_creneau_examen',
        (
            f'ajoute le créneau {matiere.nom} le {date_examen.isoformat()} '
            f'de {heure_debut.strftime("%H:%M")} à {heure_fin.strftime("%H:%M")} '
            f'sur la session « {session.nom_examen} »'
            + (f' en {salle.nom}' if salle else '')
            + (f', surveillant {surveillant.nom_complet}' if surveillant else '')
        ),
        session_id=session.id,
        session=session.nom_examen,
        matiere_id=matiere.id,
        matiere=matiere.nom,
        date=date_examen.isoformat(),
        heure_debut=heure_debut.strftime('%H:%M'),
        heure_fin=heure_fin.strftime('%H:%M'),
        salle_id=salle.id if salle else None,
        salle=salle.nom if salle else None,
        surveillant_id=surveillant.id if surveillant else None,
        surveillant=surveillant.nom_complet if surveillant else None,
        consignes=(args.get('consignes') or args.get('consignes_specifiques') or '').strip(),
        url=_reverse('directeur:emploi_du_temps_examens'),
    )


def apply_ajouter_creneau_examen(ctx, draft):
    from school_admin.model.creneau_examen_model import CreneauExamen
    from school_admin.model.matiere_model import Matiere
    from school_admin.model.professeur_model import Professeur
    from school_admin.model.salle_model import Salle
    from school_admin.model.session_examen_model import SessionExamen
    from school_admin.services.assistant_actions import _emit

    session = SessionExamen.objects.filter(
        pk=draft.get('session_id'), etablissement=ctx.etablissement
    ).first()
    if not session:
        return _err('Session d’examen introuvable.')
    matiere = Matiere.objects.filter(
        pk=draft.get('matiere_id'), etablissement=ctx.etablissement
    ).first()
    if not matiere:
        return _err('Matière introuvable.')
    salle = None
    if draft.get('salle_id'):
        salle = Salle.objects.filter(
            pk=draft['salle_id'], etablissement=ctx.etablissement
        ).first()
    surveillant = None
    if draft.get('surveillant_id'):
        surveillant = Professeur.objects.filter(
            pk=draft['surveillant_id'], etablissement=ctx.etablissement
        ).first()
    heure_debut = datetime.strptime(draft['heure_debut'], '%H:%M').time()
    heure_fin = datetime.strptime(draft['heure_fin'], '%H:%M').time()
    date_examen = _parse_date(draft['date'])
    try:
        with transaction.atomic():
            if not session.matieres.filter(pk=matiere.id).exists():
                session.matieres.add(matiere)
            creneau = CreneauExamen(
                session_examen=session,
                matiere=matiere,
                date_examen=date_examen,
                heure_debut=heure_debut,
                heure_fin=heure_fin,
                surveillant=surveillant,
                salle=salle,
                consignes_specifiques=draft.get('consignes') or None,
                annee_scolaire=ctx.annee_scolaire,
            )
            creneau.save()
    except ValidationError as exc:
        return _err(_validation_message(exc))
    _emit(ctx, 'examen.mise_a_jour', {'id': session.id, 'action': 'creneau_ajoute'})
    return _ok(
        (
            f'Créneau {matiere.nom} ajouté le {date_examen.isoformat()} '
            f'de {draft["heure_debut"]} à {draft["heure_fin"]}.'
        ),
        id=creneau.id,
        url=_reverse('directeur:emploi_du_temps_examens'),
    )


def prepare_supprimer_creneau_examen(ctx, args):
    args = args if isinstance(args, dict) else {}
    session = _find_session(ctx, args.get('session') or args.get('query') or args.get('nom'))
    creneau = _find_creneau(ctx, args, session=session)
    if not creneau:
        return _incomplete(
            'supprimer_creneau_examen',
            ['session', 'matiere', 'date'],
            'Quel créneau d’examen dois-je supprimer (session, matière, date) ?',
        )
    return _pending(
        'supprimer_creneau_examen',
        (
            f'supprime le créneau {creneau.matiere.nom} du '
            f'{creneau.date_examen.isoformat()} '
            f'({creneau.session_examen.nom_examen})'
        ),
        id=creneau.id,
        session_id=creneau.session_examen_id,
        matiere=creneau.matiere.nom,
        date=creneau.date_examen.isoformat(),
        destructive=True,
        url=_reverse('directeur:emploi_du_temps_examens'),
    )


def apply_supprimer_creneau_examen(ctx, draft):
    from school_admin.model.creneau_examen_model import CreneauExamen
    from school_admin.services.assistant_actions import _emit

    creneau = CreneauExamen.objects.filter(
        pk=draft.get('id'),
        session_examen__etablissement=ctx.etablissement,
    ).select_related('session_examen', 'matiere').first()
    if not creneau:
        return _err('Créneau d’examen introuvable.')
    nom = creneau.matiere.nom
    jour = creneau.date_examen.isoformat()
    session_id = creneau.session_examen_id
    creneau.delete()
    _emit(ctx, 'examen.mise_a_jour', {'id': session_id, 'action': 'creneau_supprime'})
    return _ok(f'Créneau {nom} du {jour} supprimé.')


register_action(ActionSpec(
    'modifier_session_examen',
    'Modifie le nom, les dates ou la période d’une session d’examen.',
    {
        'query': _STR,
        'session': _STR,
        'nom': _STR,
        'nouveau_nom': _STR,
        'nom_examen': _STR,
        'periode': _STR,
        'date_debut': {'type': 'string', 'description': 'YYYY-MM-DD'},
        'date_fin': {'type': 'string', 'description': 'YYYY-MM-DD'},
        'description': _STR,
    },
    prepare=prepare_modifier_session_examen,
    apply=apply_modifier_session_examen,
))

register_action(ActionSpec(
    'ajouter_creneau_examen',
    'Ajoute un créneau d’examen (matière, date, heures, salle, surveillant). '
    'Signale les conflits de salle ou de surveillant.',
    {
        'session': _STR,
        'query': _STR,
        'nom': _STR,
        'matiere': _STR,
        'date': {'type': 'string', 'description': 'Date YYYY-MM-DD'},
        'date_examen': _STR,
        'heure_debut': {'type': 'string', 'description': 'HH:MM ou 8h'},
        'heure_fin': {'type': 'string'},
        'salle': _STR,
        'surveillant': _STR,
        'professeur': _STR,
        'consignes': _STR,
    },
    prepare=prepare_ajouter_creneau_examen,
    apply=apply_ajouter_creneau_examen,
))

register_action(ActionSpec(
    'supprimer_creneau_examen',
    'Supprime un créneau d’examen.',
    {
        'query': _STR,
        'session': _STR,
        'nom': _STR,
        'matiere': _STR,
        'date': _STR,
        'id': _STR,
    },
    destructive=True,
    prepare=prepare_supprimer_creneau_examen,
    apply=apply_supprimer_creneau_examen,
))


VAGUE6_READ_SCHEMA = [
    {
        'type': 'function',
        'function': {
            'name': 'get_emploi_examens',
            'description': (
                'Emploi des examens : créneaux d’une session (matière, date, '
                'heures, salle, surveillant). Collège / lycée / supérieur.'
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'query': {'type': 'string', 'description': 'Nom de la session'},
                    'session': _STR,
                    'nom': _STR,
                },
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'get_notes_examen',
            'description': (
                'Notes d’examen déjà saisies (NoteExamen) pour un élève, '
                'une session, une classe ou une matière. N’invente aucun chiffre.'
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'query': {'type': 'string', 'description': 'Nom de l’élève'},
                    'eleve': _STR,
                    'session': {'type': 'string', 'description': 'Nom de la session'},
                    'classe': _STR,
                    'matiere': _STR,
                },
            },
        },
    },
]

VAGUE6_READ_HANDLERS = {
    'get_examens': tool_examens,
    'get_emploi_examens': tool_emploi_examens,
    'get_notes_examen': tool_notes_examen,
}
