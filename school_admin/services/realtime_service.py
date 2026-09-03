"""
Service d'émission d'événements temps réel (WebSocket via Redis Channel Layer).
"""
from __future__ import annotations

import logging
from typing import Any

from asgiref.sync import async_to_sync
from django.conf import settings

logger = logging.getLogger(__name__)


def emit_etablissement_event(etablissement_id: int, event_type: str, payload: dict[str, Any] | None = None) -> None:
    """
    Diffuse un événement à tous les clients connectés à un établissement.

    Exemple :
        emit_etablissement_event(1, 'eleve.inscrit', {'eleve_id': 42, 'classe_id': 3})
    """
    if not etablissement_id:
        return

    try:
        from channels.layers import get_channel_layer

        channel_layer = get_channel_layer()
        if channel_layer is None:
            logger.debug('Channel layer indisponible, événement ignoré: %s', event_type)
            return

        async_to_sync(channel_layer.group_send)(
            f'etablissement_{etablissement_id}',
            {
                'type': 'realtime.event',
                'event_type': event_type,
                'payload': payload or {},
            },
        )
    except Exception as exc:
        logger.exception('Erreur emission temps reel [%s]: %s', event_type, exc)


def is_realtime_enabled() -> bool:
    return bool(getattr(settings, 'REDIS_URL', None))
