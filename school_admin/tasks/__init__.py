"""Tâches Celery du projet — import explicite pour enregistrement worker."""
from school_admin.tasks.celery_tasks import (  # noqa: F401
    celery_ping,
    deliver_push_task,
    envoyer_relances_impayes_task,
    generer_rappels_task,
    retry_pending_push,
    verifier_moratoires_task,
    emit_realtime_event_task,
    send_annonce_notifications_task,
    send_emploi_publication_task,
)
