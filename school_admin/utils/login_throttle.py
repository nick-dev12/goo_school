"""
Limitation des tentatives de connexion sur le formulaire principal (IP + identifiant).

La logique est appliquée uniquement côté serveur (le cache) : contourner le JS
ne supprime pas le blocage. Clé = hachage (IP, identifiant normalisé) pour ne pas
stocker l'identifiant en clair dans le backend de cache.
"""
from __future__ import annotations

import hashlib
import hmac
import time
from typing import Any

from django.conf import settings
from django.core.cache import cache

CACHE_KEY_PREFIX = "login_main_throttle:v1"
ATTEMPT_LIMIT = 5
# Durées après chaque série de 5 échecs : 5 min, 15 min, 30 min
LOCK_DURATIONS_FIRST = (300, 900, 1800)
CACHE_TIMEOUT_SEC = 3 * 24 * 3600


def _throttle_secret() -> bytes:
    return (getattr(settings, "SECRET_KEY", "") or "fallback").encode()


def _normalize_username(raw: str) -> str:
    return (raw or "").strip().lower()[:255]


# Mandataires locaux de confiance : Nginx est le seul à joindre Daphne (127.0.0.1:8001) et il écrase
# l'en-tête X-Real-IP avec l'adresse réelle du visiteur. Sans cela, tout le monde aurait l'adresse 127.0.0.1.
TRUSTED_PROXIES = {'127.0.0.1', '::1'}


def get_client_ip(request) -> str:
    remote = (request.META.get('REMOTE_ADDR') or 'unknown')[:45]
    if remote in TRUSTED_PROXIES:
        real = (request.META.get('HTTP_X_REAL_IP') or '').strip()
        if real:
            return real[:45]
    trust = getattr(settings, 'LOGIN_THROTTLE_TRUST_X_FORWARDED_FOR', False)
    if trust:
        xff = request.META.get('HTTP_X_FORWARDED_FOR')
        if xff:
            return xff.split(',')[0].strip()[:45]
    return remote


def _cache_key(ip: str, username_norm: str) -> str:
    payload = f"{ip}\0{username_norm}".encode()
    digest = hmac.new(_throttle_secret(), payload, hashlib.sha256).hexdigest()
    return f"{CACHE_KEY_PREFIX}:{digest}"


# Plafond par adresse, tous identifiants confondus : freine l'essai d'un même mot de passe sur des
# centaines de comptes. Large, car une école entière peut sortir sur Internet par la même adresse.
IP_FAILURE_LIMIT = 100
IP_WINDOW_SEC = 15 * 60
IP_LOCK_SEC = 15 * 60


def _ip_key(ip: str) -> str:
    digest = hmac.new(_throttle_secret(), f"ip\0{ip}".encode(), hashlib.sha256).hexdigest()
    return f"{CACHE_KEY_PREFIX}:ip:{digest}"


def _ip_seconds_remaining(ip: str) -> int:
    state = cache.get(_ip_key(ip)) or {}
    locked_until = state.get('locked_until')
    return max(0, int(locked_until - time.time() + 0.5)) if locked_until and locked_until > time.time() else 0


def _register_ip_failure(ip: str) -> int:
    key = _ip_key(ip)
    now = time.time()
    state = cache.get(key) or {}
    if state.get('locked_until') and state['locked_until'] > now:
        return int(state['locked_until'] - now + 0.5)
    fails = [t for t in state.get('fails', []) if t > now - IP_WINDOW_SEC] + [now]
    if len(fails) >= IP_FAILURE_LIMIT:
        cache.set(key, {'fails': [], 'locked_until': now + IP_LOCK_SEC}, IP_LOCK_SEC + 60)
        return IP_LOCK_SEC
    cache.set(key, {'fails': fails}, IP_WINDOW_SEC + 60)
    return 0


def _default_state() -> dict[str, Any]:
    return {"fails": 0, "strike": 0, "locked_until": None}


def _lock_duration_seconds(strike_index: int) -> int:
    """strike_index 0 → 5 min, 1 → 15 min, 2 → 30 min, puis 60, 120, 240… min (plafon 24 h)."""
    if strike_index < len(LOCK_DURATIONS_FIRST):
        return LOCK_DURATIONS_FIRST[strike_index]
    n = strike_index - len(LOCK_DURATIONS_FIRST)
    minutes = 60 * (2**min(n, 14))
    return min(minutes * 60, 24 * 3600)


def get_state(request, username_raw: str) -> dict[str, Any]:
    ip = get_client_ip(request)
    un = _normalize_username(username_raw)
    key = _cache_key(ip, un)
    state = cache.get(key)
    if not state:
        return _default_state()
    lu = state.get("locked_until")
    if lu is not None and lu <= time.time():
        state = {**state, "locked_until": None}
        cache.set(key, state, CACHE_TIMEOUT_SEC)
    return state


def get_seconds_remaining(request, username_raw: str) -> int:
    ip_lock = _ip_seconds_remaining(get_client_ip(request))
    state = get_state(request, username_raw)
    lu = state.get("locked_until")
    account_lock = max(0, int(lu - time.time() + 0.5)) if lu else 0
    return max(ip_lock, account_lock)


def clear_on_success(request, username_raw: str) -> None:
    ip = get_client_ip(request)
    un = _normalize_username(username_raw)
    cache.delete(_cache_key(ip, un))


def register_auth_failure(request, username_raw: str) -> int:
    """
    Enregistre un échec d'authentification (mot de passe incorrect).
    Retourne le nombre de secondes avant nouvel essai si verrouillage
    (déjà actif ou déclenché), sinon 0.
    """
    ip = get_client_ip(request)
    ip_lock = _register_ip_failure(ip)
    un = _normalize_username(username_raw)
    key = _cache_key(ip, un)
    state = cache.get(key) or _default_state()
    lu = state.get("locked_until")
    now = time.time()
    if lu is not None and lu > now:
        return max(ip_lock, int(lu - now + 0.5))

    if lu is not None and lu <= now:
        state["locked_until"] = None

    state["fails"] = int(state.get("fails") or 0) + 1
    if state["fails"] >= ATTEMPT_LIMIT:
        strike = int(state.get("strike") or 0)
        duration = _lock_duration_seconds(strike)
        state["locked_until"] = now + duration
        state["strike"] = strike + 1
        state["fails"] = 0
        cache.set(key, state, CACHE_TIMEOUT_SEC)
        return max(ip_lock, duration)

    cache.set(key, state, CACHE_TIMEOUT_SEC)
    return ip_lock
