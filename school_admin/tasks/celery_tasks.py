"""
Tâches Celery (notifications, temps réel).
"""
from __future__ import annotations

import logging

from celery import shared_task
from django.db import transaction

logger = logging.getLogger(__name__)


@shared_task
def deliver_push_task(job_id):
    from school_admin.services.push_delivery import deliver
    deliver(job_id)


@shared_task
def retry_pending_push():
    from django.utils import timezone
    from school_admin.model.push_delivery_model import PushDelivery
    from school_admin.services.push_delivery import deliver
    for job_id in PushDelivery.objects.filter(status='pending', next_attempt__lte=timezone.now()).values_list('pk', flat=True)[:500]:
        deliver(job_id)


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


@shared_task
def envoyer_relances_impayes_task() -> dict:
    """Relances SMS / WhatsApp quotidiennes si le flag établissement / groupe est actif."""
    from school_admin.services.recouvrement import envoyer_relances_automatiques

    return envoyer_relances_automatiques()


@shared_task
def verifier_moratoires_task() -> int:
    """Rupture automatique des moratoires dont une échéance est impayée."""
    from school_admin.services.recouvrement import verifier_rupture_moratoires

    return verifier_rupture_moratoires()


@shared_task
def generer_rappels_task() -> dict:
    """Rappels automatiques : notification persistante + push pour chaque action à faire."""
    from school_admin.services.rappels import generer

    stats = generer()
    stats.pop('detail', None)
    return stats
