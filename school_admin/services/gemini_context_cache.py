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

CACHE_DISPLAY_NAME = 'aria-directeur-tools-v14'
CACHE_DISPLAY_NAME_ENSEIGNANT = 'aria-enseignant-primaire-tools-v2'
DEFAULT_TTL_SECONDS = 7200

_lock = threading.Lock()
_cache_name = None
_cache_model = None
_cache_fingerprint = None
_cache_token_count = None

_enseignant_lock = threading.Lock()
_enseignant_cache_name = None
_enseignant_cache_model = None
_enseignant_cache_fingerprint = None
_enseignant_cache_token_count = None


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


def tools_fingerprint(system_prompt, model, tools_schema=None):
    schema = tools_schema if tools_schema is not None else TOOLS_SCHEMA
    payload = {
        'model': model,
        'prompt': system_prompt,
        'tools': [
            (item.get('function') or {}).get('name')
            for item in schema
        ],
        'count': len(schema),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]


def openai_tools_to_gemini(tools_schema=None):
    from google.genai import types

    schema = tools_schema if tools_schema is not None else TOOLS_SCHEMA
    declarations = []
    for item in schema:
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


def _reuse_or_create_cache(
    system_prompt,
    model,
    *,
    display_name,
    tools_schema,
    state,
    lock,
):
    from google.genai import types

    fingerprint = tools_fingerprint(system_prompt, model, tools_schema)
    ttl = f'{_ttl_seconds()}s'
    with lock:
        if (
            state['name']
            and state['fingerprint'] == fingerprint
            and state['model'] == model
        ):
            return state['name'], state['model'], state['token_count']

        client = _get_native_client()
        existing = None
        try:
            for item in client.caches.list():
                if getattr(item, 'display_name', None) == display_name:
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
                state['name'] = existing.name
                state['model'] = model
                state['fingerprint'] = fingerprint
                state['token_count'] = tokens
                logger.info(
                    'Cache Gemini réutilisé %s (%s outils, %s tokens).',
                    existing.name,
                    len(tools_schema),
                    tokens,
                )
                return state['name'], state['model'], state['token_count']
            except Exception:
                logger.warning('Impossible de prolonger le cache Gemini, recréation.', exc_info=True)
                try:
                    client.caches.delete(name=existing.name)
                except Exception:
                    pass

        created = client.caches.create(
            model=model,
            config=types.CreateCachedContentConfig(
                display_name=display_name,
                system_instruction=system_prompt,
                tools=openai_tools_to_gemini(tools_schema),
                ttl=ttl,
            ),
        )
        usage = getattr(created, 'usage_metadata', None)
        tokens = getattr(usage, 'total_token_count', None) if usage else None
        state['name'] = created.name
        state['model'] = model
        state['fingerprint'] = fingerprint
        state['token_count'] = tokens
        logger.info(
            'Cache Gemini créé %s (%s outils, %s tokens, ttl=%s).',
            created.name,
            len(tools_schema),
            tokens,
            ttl,
        )
        return state['name'], state['model'], state['token_count']


def _directeur_state():
    return {
        'name': _cache_name,
        'model': _cache_model,
        'fingerprint': _cache_fingerprint,
        'token_count': _cache_token_count,
    }


def _sync_directeur_state(state):
    global _cache_name, _cache_model, _cache_fingerprint, _cache_token_count
    _cache_name = state['name']
    _cache_model = state['model']
    _cache_fingerprint = state['fingerprint']
    _cache_token_count = state['token_count']


def _enseignant_state():
    return {
        'name': _enseignant_cache_name,
        'model': _enseignant_cache_model,
        'fingerprint': _enseignant_cache_fingerprint,
        'token_count': _enseignant_cache_token_count,
    }


def _sync_enseignant_state(state):
    global _enseignant_cache_name, _enseignant_cache_model
    global _enseignant_cache_fingerprint, _enseignant_cache_token_count
    _enseignant_cache_name = state['name']
    _enseignant_cache_model = state['model']
    _enseignant_cache_fingerprint = state['fingerprint']
    _enseignant_cache_token_count = state['token_count']


def reset_cache_state():
    global _cache_name, _cache_model, _cache_fingerprint, _cache_token_count
    global _enseignant_cache_name, _enseignant_cache_model
    global _enseignant_cache_fingerprint, _enseignant_cache_token_count
    with _lock:
        _cache_name = None
        _cache_model = None
        _cache_fingerprint = None
        _cache_token_count = None
    with _enseignant_lock:
        _enseignant_cache_name = None
        _enseignant_cache_model = None
        _enseignant_cache_fingerprint = None
        _enseignant_cache_token_count = None


def ensure_tools_cache(
    system_prompt,
    model,
    tools_schema=None,
    persona='directeur',
    profile=None,
):
    """
    Crée ou réutilise le cache prompt + outils.
    Retourne (name, model, token_count) ou None si indisponible.
    """
    if not cache_enabled():
        return None
    schema = tools_schema if tools_schema is not None else TOOLS_SCHEMA
    if persona == 'enseignant_primaire':
        from school_admin.services.assistant_enseignant_primaire_tools import (
            get_enseignant_primaire_tools_schema,
        )

        schema = get_enseignant_primaire_tools_schema()
        display = CACHE_DISPLAY_NAME_ENSEIGNANT
        lock = _enseignant_lock

        def get_state():
            return _enseignant_state()

        def sync_state(state):
            _sync_enseignant_state(state)
    else:
        suffix = (profile or 'directeur').strip().lower() or 'directeur'
        display = f'{CACHE_DISPLAY_NAME}-{suffix}'
        lock = _lock

        def get_state():
            return _directeur_state()

        def sync_state(state):
            _sync_directeur_state(state)

    try:
        state = get_state()
        result = _reuse_or_create_cache(
            system_prompt,
            model,
            display_name=display,
            tools_schema=schema,
            state=state,
            lock=lock,
        )
        sync_state(state)
        return result
    except Exception:
        logger.exception('Impossible de créer le cache Gemini, repli sans cache.')
        reset_cache_state()
        return None
