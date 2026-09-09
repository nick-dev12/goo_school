"""
Configuration Celery pour Goo School / Aria.
"""
import os

from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'school.settings')

app = Celery('school')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()
app.autodiscover_tasks(['school_admin.tasks.celery_tasks'], force=True)
