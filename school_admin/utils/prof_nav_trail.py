"""Fil d'Ariane professeur — un niveau parent sémantique (P3)."""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlencode

from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from school_admin.model.professeur_model import Professeur

_DASHBOARD_URL_NAMES = frozenset({
    'dashboard_enseignant',
    'dashboard',
})

_NOTES_QUERY = ('periode', 'classe', 'matiere', 'vue')
_CLASSE_QUERY = ('classe',)
_CLASSE_FROM_PATH = (('classe', 'classe_id'),)


@dataclass(frozen=True)
class TrailRule:
    parent_name: str
    parent_label: str
    current_label: str
    query_keys: tuple[str, ...] = ()
    parent_kwargs: tuple[str, ...] = ()
    query_from_kwargs: tuple[tuple[str, str], ...] = ()


def set_prof_breadcrumb_current_label(request, label: str) -> None:
    """Les vues peuvent affiner le libellé courant (nom d'élève, de classe…)."""
    request.prof_breadcrumb_current_label = label


def _notes(current: str) -> TrailRule:
    return TrailRule('gestion_notes', _('Notes'), current, _NOTES_QUERY, (), _CLASSE_FROM_PATH)


def _eleves(current: str) -> TrailRule:
    return TrailRule('gestion_eleves', _('Élèves'), current, _CLASSE_QUERY, (), _CLASSE_FROM_PATH)


def _classes(current: str) -> TrailRule:
    return TrailRule('gestion_classes', _('Classes'), current, _CLASSE_QUERY, (), _CLASSE_FROM_PATH)


def _presence(current: str) -> TrailRule:
    return TrailRule(
        'gestion_presence', _('Présence'), current, _CLASSE_QUERY, (), _CLASSE_FROM_PATH,
    )


def _eleve_detail(current: str) -> TrailRule:
    return TrailRule('detail_eleve', _('Élève'), current, (), ('eleve_id',))


_SHARED_RULES: dict[str, TrailRule] = {
    'liste_presence': _presence(_('Appel')),
    'noter_eleves': _notes(_('Saisie des notes')),
    'voir_releve': _notes(_('Relevé')),
    'creer_evaluation': _notes(_('Nouvelle évaluation')),
    'liste_evaluations': _notes(_('Évaluations')),
    'modifier_evaluation': TrailRule(
        'liste_evaluations', _('Évaluations'), _('Modifier l\'évaluation'), _CLASSE_QUERY,
    ),
    'detail_eleve': _eleves(_('Élève')),
    'detail_classe': _classes(_('Classe')),
    'historique_presence': _eleve_detail(_('Historique des présences')),
    'historique_sanctions': _eleve_detail(_('Historique des sanctions')),
    'liste_sanctions_classe': _eleves(_('Sanctions')),
    'historique_annees': TrailRule(
        'parametres_profil', _('Profil'), _('Années scolaires'),
    ),
    'historique_annee_detail': TrailRule(
        'historique_annees', _('Années scolaires'), _('Année archivée'),
    ),
}

_EXTRA_RULES: dict[tuple[str, str], TrailRule] = {
    ('enseignant', 'noter_examen'): _notes(_('Notes d\'examen')),
    ('enseignant', 'noter_examen_session'): _notes(_('Notes d\'examen')),
    ('enseignant_primaire', 'evaluations_classe'): TrailRule(
        'liste_evaluations', _('Évaluations'), _('Évaluations de la classe'),
        _CLASSE_QUERY, (), _CLASSE_FROM_PATH,
    ),
}


def _trail_rules() -> dict[tuple[str, str], TrailRule]:
    rules: dict[tuple[str, str], TrailRule] = {}
    for ns in ('enseignant', 'enseignant_primaire'):
        for url_name, rule in _SHARED_RULES.items():
            rules[(ns, url_name)] = rule
    rules.update(_EXTRA_RULES)
    return rules


_TRAIL_RULES = _trail_rules()


def _copy_query(request, keys: tuple[str, ...], from_kwargs: tuple[tuple[str, str], ...]) -> dict[str, str]:
    q: dict[str, str] = {}
    match = getattr(request, 'resolver_match', None)
    kwargs = getattr(match, 'kwargs', None) or {}
    for dest, src in from_kwargs:
        val = kwargs.get(src)
        if val not in (None, ''):
            q[dest] = str(val)
    for key in keys:
        val = (request.GET.get(key) or '').strip()
        if val:
            q[key] = val
    return q


def resolve_prof_nav_trail(request) -> dict | None:
    user = getattr(request, 'user', None)
    if not isinstance(user, Professeur):
        return None
    match = getattr(request, 'resolver_match', None)
    if not match or not match.url_name:
        return None
    if match.url_name in _DASHBOARD_URL_NAMES:
        return None

    ns = match.namespace or ''
    # Les URLs secondaire/LMD sont aussi enregistrées sous school_admin (include historique).
    if ns == 'school_admin':
        ns = 'enseignant'
    rule = _TRAIL_RULES.get((ns, match.url_name))
    if not rule:
        return None

    reverse_kwargs: dict[str, object] = {}
    match_kwargs = getattr(match, 'kwargs', None) or {}
    for key in rule.parent_kwargs:
        val = match_kwargs.get(key)
        if val in (None, ''):
            return None
        reverse_kwargs[key] = val

    try:
        if reverse_kwargs:
            parent_url = reverse(f'{ns}:{rule.parent_name}', kwargs=reverse_kwargs)
        else:
            parent_url = reverse(f'{ns}:{rule.parent_name}')
    except Exception:
        return None

    q = _copy_query(request, rule.query_keys, rule.query_from_kwargs)
    if q:
        parent_url = parent_url + '?' + urlencode(q)

    current_label = rule.current_label
    override = getattr(request, 'prof_breadcrumb_current_label', None)
    if override:
        current_label = override

    return {
        'parent_url': parent_url,
        'parent_label': rule.parent_label,
        'current_label': current_label,
    }
