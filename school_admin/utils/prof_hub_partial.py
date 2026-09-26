"""Réponses fragment HTML pour navigation hub professeur (hub_partial)."""
from __future__ import annotations

from django.shortcuts import render


HUB_PARTIAL_VALUES = frozenset({'hub', 'chrome', 'panel'})


def wants_prof_hub_partial(request) -> str | None:
    """Retourne hub_partial si requête XHR fragment, sinon None."""
    partial = (request.GET.get('hub_partial') or '').strip()
    if partial not in HUB_PARTIAL_VALUES:
        return None
    if request.headers.get('X-Requested-With') != 'XMLHttpRequest':
        return None
    return partial


def render_prof_hub_partial(request, context, swap_template: str):
    """
    Rend le template swap (contient #prof-hub-chrome et #prof-hub-panel).
    context reçoit hub_partial_mode pour templates optionnels.
    """
    partial = wants_prof_hub_partial(request)
    if not partial:
        return None
    ctx = dict(context)
    ctx['hub_partial_mode'] = partial
    return render(request, swap_template, ctx)
