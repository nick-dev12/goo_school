"""
Aria et le cahier de texte : consulter les entrées d'une classe, et rédiger une entrée à la
place de l'enseignant (avec confirmation avant enregistrement).
"""
from __future__ import annotations

import hashlib
from datetime import date

from django.urls import NoReverseMatch, reverse
from django.utils import timezone
from django.utils.dateparse import parse_date

from school_admin.services.assistant_actions import _incomplete, _ok, _pending
from school_admin.services.assistant_enseignant_scope import (
    ensure_classe_access,
    ensure_matiere_in_classe,
    find_classe_prof,
    matiere_ids_for_prof,
)

DESCRIPTION_REDIGER = (
    "Rédige intelligemment l'entrée du cahier de texte d'un cours (leçon, objectifs, déroulement, "
    "travail à faire) à la place de l'enseignant, à partir de ce qu'il a fait ou de ses notes, en tenant "
    "compte du niveau de la classe et des leçons précédentes. Montre le texte proposé puis enregistre "
    "après confirmation. Deux possibilités à proposer à l'enseignant : brouillon (modifiable) ou "
    "validation (envoyée à la direction, définitive : plus aucune modification possible, sauf demande "
    "explicite à la direction). Avant de valider, préviens-le clairement de ce caractère définitif."
)
PROPRIETES_REDIGER = {
    'classe': {'type': 'string', 'description': 'Nom de la classe.'},
    'matiere': {'type': 'string', 'description': 'Matière (facultatif si une seule).'},
    'date': {'type': 'string', 'description': "Date du cours AAAA-MM-JJ (aujourd'hui par défaut)."},
    'notes': {'type': 'string', 'description': "Ce que l'enseignant a fait ou veut noter (chapitre, exercices…)."},
    'travail_a_faire': {'type': 'string', 'description': 'Travail donné, si précisé.'},
    'valider': {'type': 'boolean', 'description': (
        "True seulement si l'enseignant demande explicitement de valider. Une entrée validée est envoyée à "
        "la direction et ne peut plus être modifiée ; sinon l'entrée est enregistrée en brouillon.")},
}
SCHEMA_LECTURE = {
    'type': 'function',
    'function': {
        'name': 'get_cahier_texte',
        'description': "Lit les dernières entrées du cahier de texte d'une de vos classes (leçons faites, travail donné).",
        'parameters': {'type': 'object', 'properties': {
            'classe': {'type': 'string'}, 'matiere': {'type': 'string'}, 'nb': {'type': 'integer'},
        }},
    },
}


def _ns(ctx):
    from school_admin.services.assistant_enseignant_scope import _persona_primaire

    return 'enseignant_primaire' if _persona_primaire(ctx) else 'enseignant'


def _url(ctx):
    try:
        return reverse(f'{_ns(ctx)}:cahier_texte')
    except NoReverseMatch:
        return None


def _matiere(ctx, classe, args):
    from school_admin.model.matiere_model import Matiere

    ids = matiere_ids_for_prof(ctx, classe)
    candidates = list(Matiere.objects.filter(pk__in=ids)) if ids else []
    q = (args.get('matiere') or '').strip().lower()
    if q:
        for m in candidates or Matiere.objects.filter(nom__icontains=q):
            if q in m.nom.lower() and ensure_matiere_in_classe(ctx, classe, m) is None:
                return m, False
        return None, True
    if len(candidates) == 1:
        return candidates[0], False
    if getattr(ctx.professeur, 'matiere_principale_id', None) in ids:
        return ctx.professeur.matiere_principale, False
    return None, bool(candidates)


def ct_regle():
    from school_admin.services.cahier_texte import AIDE_VALIDATION

    return AIDE_VALIDATION


def tool_get_cahier_texte(ctx, args):
    from school_admin.model.cahier_texte_model import CahierTexte

    qs = CahierTexte.objects.filter(professeur=ctx.professeur).select_related('classe', 'matiere')
    classe = find_classe_prof(ctx, args.get('classe') or '') if args.get('classe') else None
    if classe:
        qs = qs.filter(classe=classe)
    nb = max(1, min(int(args.get('nb') or 5), 15))
    items = [{
        'date': e.date.isoformat(), 'classe': e.classe.nom, 'matiere': getattr(e.matiere, 'nom', ''),
        'titre': e.titre, 'travail_a_faire': e.travail_a_faire[:200], 'statut': e.get_statut_display(),
        'modifiable': e.modifiable, 'demande_modification': e.get_demande_statut_display() if e.demande_statut else '',
    } for e in qs.order_by('-date', '-heure_debut')[:nb]]
    if not items:
        return {'entrees': [], 'nb': 0, 'message': "Aucune entrée dans votre cahier de texte pour l'instant.",
                'url': _url(ctx)}
    return {'entrees': items, 'nb': len(items), 'url': _url(ctx), 'regle': ct_regle(),
            'message': f"Dernière leçon : « {items[0]['titre']} » ({items[0]['classe']}, {items[0]['date']})."}


def prepare_rediger_cahier_texte(ctx, args):
    from school_admin.services import cahier_texte as ct

    nom = 'rediger_cahier_texte'
    classe = find_classe_prof(ctx, args.get('classe') or '')
    if not classe:
        return _incomplete(nom, ['classe'], 'Pour quelle classe dois-je rédiger le cahier de texte ?')
    matiere, manque = _matiere(ctx, classe, args)
    if manque:
        return _incomplete(nom, ['matiere'], f'Pour quelle matière en {classe.nom} ?')
    jour = parse_date((args.get('date') or '')[:10]) or timezone.localdate()
    if jour > timezone.localdate():
        return _incomplete(nom, ['date'], "Le cahier de texte se remplit pour un cours déjà fait ou d'aujourd'hui.")
    cours = [c for c in ct.cours_du_professeur(ctx.professeur, jour, jour, ctx.annee_scolaire)
             if c['classe'].id == classe.id and (matiere is None or c['matiere'] is None
                                                 or c['matiere'].id == matiere.id)]
    cours.sort(key=lambda c: c['debut'])
    debut = cours[0]['debut'] if cours else None
    fin = cours[0]['fin'] if cours else None
    duree = None
    if debut and fin:
        duree = (fin.hour * 60 + fin.minute) - (debut.hour * 60 + debut.minute)
    notes = (args.get('notes') or '').strip()
    if args.get('travail_a_faire'):
        notes += f"\nTravail à faire indiqué : {args['travail_a_faire']}"
    # Même demande rejouée (par ex. « valide-le ») : on réutilise le texte déjà proposé.
    from django.core.cache import cache

    cle = f"ct-ia:{ctx.professeur.id}:{classe.id}:{getattr(matiere, 'id', 0)}:{jour}:{hashlib.md5(notes.encode()).hexdigest()}"
    brouillon = cache.get(cle)
    if brouillon is None:
        try:
            brouillon = ct.rediger(ctx.professeur, classe, matiere, jour, notes, duree)
        except ValueError as exc:
            return {'erreur': str(exc)}
        cache.set(cle, brouillon, 1800)
    resume = (f"propose pour le cahier de texte de {classe.nom}{' (' + matiere.nom + ')' if matiere else ''} "
              f"du {jour:%d/%m/%Y} la leçon « {brouillon['titre']} ».")
    if brouillon['travail_a_faire']:
        resume += f" Travail : {brouillon['travail_a_faire'][:120]}."
    valider = bool(args.get('valider'))
    if valider:
        resume += (" Je vais la VALIDER : elle sera envoyée à la direction et ne pourra plus être modifiée, "
                   "sauf demande de modification à la direction.")
    else:
        resume += (" Je l'enregistre en brouillon (modifiable). Vous pouvez aussi la valider pour l'envoyer à la "
                   "direction : attention, ce sera définitif.")
    return _pending(
        nom, resume,
        classe_id=classe.id, matiere_id=getattr(matiere, 'id', None), date=jour.isoformat(),
        heure_debut=debut.strftime('%H:%M') if debut else None, heure_fin=fin.strftime('%H:%M') if fin else None,
        valider=valider, proposition=brouillon, manquants=[],
    )


def apply_rediger_cahier_texte(ctx, draft):
    from datetime import time

    from school_admin.model.classe_model import Classe
    from school_admin.model.matiere_model import Matiere
    from school_admin.services import cahier_texte as ct

    classe = Classe.objects.filter(pk=draft.get('classe_id')).first()
    if err := ensure_classe_access(ctx, classe):
        return err
    matiere = Matiere.objects.filter(pk=draft.get('matiere_id')).first() if draft.get('matiere_id') else None

    def _t(v):
        return time.fromisoformat(v) if v else None

    donnees = dict(draft.get('proposition') or {})
    mode = draft.get('mode') or ('valider' if draft.get('valider') else 'brouillon')
    donnees['statut'] = 'valide' if mode == 'valider' else 'brouillon'
    try:
        entree = ct.enregistrer(ctx.professeur, classe, date.fromisoformat(draft['date']), donnees, matiere=matiere,
                                debut=_t(draft.get('heure_debut')), fin=_t(draft.get('heure_fin')),
                                annee_scolaire=ctx.annee_scolaire, redige_par_ia=True)
    except ValueError as exc:
        return {'erreur': str(exc)}
    etat = ('enregistrée en brouillon (modifiable)' if entree.statut == 'brouillon'
            else 'validée et envoyée à la direction (elle ne peut plus être modifiée)')
    return _ok(f"Entrée « {entree.titre} » {etat} dans le cahier de texte de {classe.nom}.",
               url=_url(ctx), id=entree.id)


def choix_rediger(draft):
    """Boutons proposés : brouillon, validation définitive, annulation."""
    if (draft or {}).get('valider'):
        return [
            {'label': 'Oui, valider définitivement', 'value': 'Oui, je valide.', 'intent': 'confirm', 'mode': 'valider'},
            {'label': 'Plutôt en brouillon', 'value': 'Enregistre en brouillon.', 'intent': 'confirm', 'mode': 'brouillon'},
            {'label': 'Annuler', 'value': 'Annuler.', 'intent': 'cancel'},
        ]
    return [
        {'label': 'Enregistrer en brouillon', 'value': 'Enregistre en brouillon.', 'intent': 'confirm', 'mode': 'brouillon'},
        {'label': 'Valider et envoyer (définitif)', 'value': 'Valide et envoie à la direction.', 'intent': 'confirm',
         'mode': 'valider'},
        {'label': 'Annuler', 'value': 'Annuler.', 'intent': 'cancel'},
    ]


def enregistrer_dans(register, spec_cls, handlers=None, schema=None):
    """Ajoute l'action d'écriture, l'outil de lecture et son schéma à un registre de persona."""
    register(spec_cls(
        name='rediger_cahier_texte', description=DESCRIPTION_REDIGER, properties=PROPRIETES_REDIGER,
        required=('classe',), prepare=prepare_rediger_cahier_texte, apply=apply_rediger_cahier_texte,
        choices=choix_rediger,
    ))
    if handlers is not None:
        handlers['get_cahier_texte'] = tool_get_cahier_texte
    if schema is not None and not any(s.get('function', {}).get('name') == 'get_cahier_texte' for s in schema):
        schema.append(SCHEMA_LECTURE)
