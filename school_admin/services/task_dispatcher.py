"""
Dispatch des tâches asynchrones : Celery (production) ou thread (fallback dev).
"""
from __future__ import annotations

import logging
import threading
from typing import Callable

from django.conf import settings
from django.db import transaction

logger = logging.getLogger(__name__)


def run_after_commit(callback: Callable, task_name: str, *args, **kwargs) -> None:
    """
    Exécute une tâche après commit de transaction.
    Utilise Celery si USE_CELERY=True et broker configuré, sinon un thread daemon.
    """

    def _dispatch() -> None:
        if getattr(settings, 'USE_CELERY', False):
            try:
                from celery import current_app

                current_app.send_task(task_name, args=args, kwargs=kwargs)
                return
            except Exception as exc:
                logger.warning('Celery indisponible (%s), fallback thread: %s', task_name, exc)

        try:
            callback(*args, **kwargs)
        except Exception as exc:
            logger.exception('Erreur tache async %s: %s', task_name, exc)

    transaction.on_commit(
        lambda: threading.Thread(
            target=_dispatch,
            name=task_name.replace('.', '-')[:40],
            daemon=True,
        ).start()
    )
