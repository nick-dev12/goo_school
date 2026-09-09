"""Tâches Celery du projet — import explicite pour enregistrement worker."""
from school_admin.tasks.celery_tasks import (  # noqa: F401
    celery_ping,
    emit_realtime_event_task,
    send_annonce_notifications_task,
    send_emploi_publication_task,
)
