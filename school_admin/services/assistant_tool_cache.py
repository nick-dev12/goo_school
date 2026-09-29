"""Cache Redis (django cache) pour les outils assistant lourds en lecture."""
from __future__ import annotations

import hashlib
import json
import logging
from functools import wraps
from typing import Any, Callable

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

DEFAULT_ASSISTANT_TOOL_TTL = int(
    getattr(settings, 'ASSISTANT_TOOL_CACHE_TTL', 900) or 900
)

CACHEABLE_ASSISTANT_TOOLS = frozenset({
    'get_bilan_scolarite',
    'get_statistiques_pilotage',
    'get_impayes',
    'get_taux_reussite',
    'get_taux_presence',
    'get_comparatif_periodes',
    'get_repartition_cycles',
    'get_fiche_scolarite',
    'get_moratoires',
})


def _stable_args_hash(arguments: dict | None) -> str:
    payload = arguments if isinstance(arguments, dict) else {}
    raw = json.dumps(payload, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()[:20]


def _actor_scope(ctx) -> str:
    for attr in ('personnel', 'professeur', 'parent', 'eleve'):
        obj = getattr(ctx, attr, None)
        if obj is not None:
            return f'{attr}:{getattr(obj, "pk", "")}'
    etab = getattr(ctx, 'etablissement', None)
    return f'etab:{getattr(etab, "pk", "")}'


def assistant_tool_cache_key(ctx, tool_name: str, arguments: dict | None) -> str:
    etab_id = getattr(getattr(ctx, 'etablissement', None), 'pk', '') or ''
    persona = getattr(ctx, 'persona', 'directeur') or 'directeur'
    annee_id = getattr(getattr(ctx, 'annee_scolaire', None), 'pk', '') or ''
    args_hash = _stable_args_hash(arguments)
    actor = _actor_scope(ctx)
    return (
        f'aria:assistant-tool:v1:{persona}:{etab_id}:{annee_id}:'
        f'{actor}:{tool_name}:{args_hash}'
    )


def _cache_get(key: str):
    try:
        return cache.get(key), True
    except Exception:
        logger.debug('Cache assistant indisponible (lecture), exécution directe.')
        return None, False


def _cache_set(key: str, value: Any, ttl: int):
    try:
        cache.set(key, value, timeout=ttl)
    except Exception:
        logger.debug('Cache assistant indisponible (écriture), résultat non mis en cache.')


def cached_assistant_tool(
    ttl: int | None = None,
    tool_name: str | None = None,
) -> Callable:
    """
    Décorateur pour handlers `(ctx, args) -> dict`.
    Si Redis/cache indisponible : exécution directe, sans erreur visible.
    """

    def decorator(handler: Callable):
        name = tool_name or handler.__name__

        @wraps(handler)
        def wrapper(ctx, arguments=None):
            if name not in CACHEABLE_ASSISTANT_TOOLS:
                return handler(ctx, arguments)
            key = assistant_tool_cache_key(ctx, name, arguments)
            hit, _ok = _cache_get(key)
            if hit is not None:
                logger.info('assistant.tool_cache hit %s', name)
                return hit
            result = handler(ctx, arguments)
            _cache_set(key, result, ttl or DEFAULT_ASSISTANT_TOOL_TTL)
            logger.info('assistant.tool_cache miss %s', name)
            return result

        return wrapper

    return decorator


def wrap_cacheable_tool_handlers(handlers: dict) -> dict:
    """Applique le cache aux handlers lourds connus (clé schéma, pas __name__)."""
    wrapped = {}
    for name, handler in handlers.items():
        if name in CACHEABLE_ASSISTANT_TOOLS:
            wrapped[name] = cached_assistant_tool(tool_name=name)(handler)
        else:
            wrapped[name] = handler
    return wrapped
