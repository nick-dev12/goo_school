"""
Cache explicite Gemini : prompt Aria + schéma des outils.

Le contexte établissement n'est pas mis en cache (il change par école).
"""
import hashlib
import json
import logging
import threading

from django.conf import settings

from school_admin.services.assistant_tools import TOOLS_SCHEMA

logger = logging.getLogger(__name__)

CACHE_DISPLAY_NAME = 'aria-directeur-tools-v2'
DEFAULT_TTL_SECONDS = 7200

_lock = threading.Lock()
_cache_name = None
_cache_model = None
_cache_fingerprint = None
_cache_token_count = None


def cache_enabled():
    if (getattr(settings, 'ASSISTANT_LLM_PROVIDER', 'gemini') or 'gemini') == 'deepseek':
        return False
    raw = getattr(settings, 'GEMINI_CONTEXT_CACHE', True)
    if isinstance(raw, str):
        return raw.strip().lower() in ('1', 'true', 'yes', 'on')
    return bool(raw)


def _ttl_seconds():
    try:
        return int(getattr(settings, 'GEMINI_CACHE_TTL_SECONDS', DEFAULT_TTL_SECONDS) or DEFAULT_TTL_SECONDS)
    except (TypeError, ValueError):
        return DEFAULT_TTL_SECONDS


def tools_fingerprint(system_prompt, model):
    payload = {
        'model': model,
        'prompt': system_prompt,
        'tools': [
            (item.get('function') or {}).get('name')
            for item in TOOLS_SCHEMA
        ],
        'count': len(TOOLS_SCHEMA),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]


def openai_tools_to_gemini():
    from google.genai import types

    declarations = []
    for item in TOOLS_SCHEMA:
        function = item.get('function') or {}
        name = function.get('name')
        if not name:
            continue
        schema = function.get('parameters') or {'type': 'object', 'properties': {}}
        declarations.append(
            types.FunctionDeclaration(
                name=name,
                description=function.get('description') or '',
                parameters_json_schema=schema,
            )
        )
    return [types.Tool(function_declarations=declarations)]


def _get_native_client():
    from google import genai

    api_key = getattr(settings, 'GEMINI_API_KEY', '') or ''
    if not api_key:
        raise RuntimeError('Clé API Gemini manquante. Configurez GEMINI_API_KEY.')
    return genai.Client(api_key=api_key)


def get_cache_stats():
    return {
        'enabled': cache_enabled(),
        'name': _cache_name,
        'model': _cache_model,
        'fingerprint': _cache_fingerprint,
        'cached_tokens': _cache_token_count,
        'tools': len(TOOLS_SCHEMA),
    }


def _reuse_or_create_cache(system_prompt, model):
    global _cache_name, _cache_model, _cache_fingerprint, _cache_token_count

    from google.genai import types

    fingerprint = tools_fingerprint(system_prompt, model)
    ttl = f'{_ttl_seconds()}s'
    with _lock:
        if _cache_name and _cache_fingerprint == fingerprint and _cache_model == model:
            return _cache_name, _cache_model, _cache_token_count

        client = _get_native_client()
        existing = None
        try:
            for item in client.caches.list():
                if getattr(item, 'display_name', None) == CACHE_DISPLAY_NAME:
                    existing = item
                    break
        except Exception:
            logger.debug('Liste des caches Gemini indisponible.', exc_info=True)

        if existing and getattr(existing, 'name', None):
            try:
                client.caches.update(
                    name=existing.name,
                    config=types.UpdateCachedContentConfig(ttl=ttl),
                )
                usage = getattr(existing, 'usage_metadata', None)
                tokens = getattr(usage, 'total_token_count', None) if usage else None
                _cache_name = existing.name
                _cache_model = model
                _cache_fingerprint = fingerprint
                _cache_token_count = tokens
                logger.info(
                    'Cache Gemini réutilisé %s (%s outils, %s tokens).',
                    existing.name,
                    len(TOOLS_SCHEMA),
                    tokens,
                )
                return _cache_name, _cache_model, _cache_token_count
            except Exception:
                logger.warning('Impossible de prolonger le cache Gemini, recréation.', exc_info=True)
                try:
                    client.caches.delete(name=existing.name)
                except Exception:
                    pass

        created = client.caches.create(
            model=model,
            config=types.CreateCachedContentConfig(
                display_name=CACHE_DISPLAY_NAME,
                system_instruction=system_prompt,
                tools=openai_tools_to_gemini(),
                ttl=ttl,
            ),
        )
        usage = getattr(created, 'usage_metadata', None)
        tokens = getattr(usage, 'total_token_count', None) if usage else None
        _cache_name = created.name
        _cache_model = model
        _cache_fingerprint = fingerprint
        _cache_token_count = tokens
        logger.info(
            'Cache Gemini créé %s (%s outils, %s tokens, ttl=%s).',
            created.name,
            len(TOOLS_SCHEMA),
            tokens,
            ttl,
        )
        return _cache_name, _cache_model, _cache_token_count


def reset_cache_state():
    global _cache_name, _cache_model, _cache_fingerprint, _cache_token_count
    with _lock:
        _cache_name = None
        _cache_model = None
        _cache_fingerprint = None
        _cache_token_count = None


def ensure_tools_cache(system_prompt, model):
    """
    Crée ou réutilise le cache prompt + outils.
    Retourne (name, model, token_count) ou None si indisponible.
    """
    if not cache_enabled():
        return None
    try:
        return _reuse_or_create_cache(system_prompt, model)
    except Exception:
        logger.exception('Impossible de créer le cache Gemini, repli sans cache.')
        reset_cache_state()
        return None
