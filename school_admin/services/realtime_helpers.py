"""Helpers temps réel (modèle TimaLove : POST JSON + WebSocket item)."""
from __future__ import annotations

from django.http import JsonResponse


def wants_json_response(request) -> bool:
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return True
    return 'application/json' in request.headers.get('Accept', '')


def json_ok(message: str | None = None, item=None, items=None, **extra):
    payload = {'ok': True}
    if message:
        payload['message'] = message
    if item is not None:
        payload['item'] = item
    if items is not None:
        payload['items'] = items
    payload.update(extra)
    return JsonResponse(payload)


def json_fail(message: str | None = None, field_errors: dict | None = None, status: int = 400):
    payload = {'ok': False}
    if message:
        payload['message'] = message
    if field_errors:
        payload['field_errors'] = field_errors
    return JsonResponse(payload, status=status)


def emit_live(etablissement_id, event_type: str, payload: dict | None = None) -> None:
    from school_admin.services.realtime_service import schedule_etablissement_event

    safe = dict(payload or {})
    safe.setdefault('event', event_type)
    schedule_etablissement_event(etablissement_id, event_type, safe)
