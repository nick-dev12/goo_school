"""
Tâches Celery (notifications, temps réel).
"""
from __future__ import annotations

import logging

from celery import shared_task
from django.db import transaction

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def send_annonce_notifications_task(self, annonce_id: int) -> None:
    from school_admin.services.notification_tasks import _send_annonce_notifications

    try:
        _send_annonce_notifications(annonce_id)
    except Exception as exc:
        logger.exception('Echec notification annonce %s', annonce_id)
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def send_emploi_publication_task(self, emploi_id: int) -> None:
    from school_admin.services.notification_tasks import _send_emploi_publication

    try:
        _send_emploi_publication(emploi_id)
    except Exception as exc:
        logger.exception('Echec notification emploi %s', emploi_id)
        raise self.retry(exc=exc)


@shared_task
def celery_ping() -> str:
    return 'pong'


@shared_task
def emit_realtime_event_task(
    etablissement_id: int,
    event_type: str,
    payload: dict | None = None,
) -> None:
    from school_admin.services.realtime_service import emit_etablissement_event

    emit_etablissement_event(etablissement_id, event_type, payload or {})
