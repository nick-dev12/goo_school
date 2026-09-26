"""Fil d'Ariane professeur — un niveau parent sémantique (R4)."""
from __future__ import annotations

from django.urls import reverse
from urllib.parse import urlencode

from school_admin.model.professeur_model import Professeur

_DASHBOARD_URL_NAMES = frozenset({
    'dashboard_enseignant',
    'dashboard',
})

# (namespace, url_name) -> (parent_url_name, parent_label, query_param_names)
_TRAIL_RULES: dict[tuple[str, str], tuple[str, str, tuple[str, ...]]] = {
    ('enseignant', 'liste_presence'): ('gestion_presence', 'Présence', ('classe',)),
    ('enseignant_primaire', 'liste_presence'): ('gestion_presence', 'Présence', ('classe',)),
    ('enseignant', 'noter_eleves'): ('gestion_notes', 'Notes', ('periode', 'classe')),
    ('enseignant_primaire', 'noter_eleves'): ('gestion_notes', 'Notes', ('periode', 'classe', 'matiere')),
    ('enseignant', 'detail_eleve'): ('gestion_eleves', 'Élèves', ('classe',)),
    ('enseignant_primaire', 'detail_eleve'): ('gestion_eleves', 'Élèves', ('classe',)),
    ('enseignant_primaire', 'voir_releve'): ('gestion_notes', 'Notes', ('periode', 'classe', 'matiere')),
}


def _copy_query(request, keys: tuple[str, ...]) -> dict[str, str]:
    q: dict[str, str] = {}
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
    rule = _TRAIL_RULES.get((ns, match.url_name))
    if not rule:
        return None

    parent_name, parent_label, query_keys = rule
    try:
        parent_url = reverse(f'{ns}:{parent_name}')
    except Exception:
        return None

    q = _copy_query(request, query_keys)
    if q:
        parent_url = parent_url + '?' + urlencode(q)

    current_label = (getattr(match, 'view_name', None) or match.url_name or '').replace('_', ' ').title()
    if hasattr(request, 'prof_breadcrumb_current_label') and request.prof_breadcrumb_current_label:
        current_label = request.prof_breadcrumb_current_label

    return {
        'parent_url': parent_url,
        'parent_label': parent_label,
        'current_label': current_label,
    }
