from datetime import timedelta
import hashlib
import json
from django.db import transaction
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType
from school_admin.model.push_delivery_model import PushDelivery
from school_admin.model.fcm_token_model import FCMToken


def enqueue(users, title, body, data=None):
    ids = []
    for user in {(type(u), u.pk): u for u in users}.values():
        content_type = ContentType.objects.get_for_model(user)
        values = dict(content_type=content_type, object_id=user.pk, title=title[:255], body=body, data=data or {})
        event_key = (data or {}).get('event_key')
        source_keys = {'evaluation_id', 'presence_id', 'annonce_id', 'emploi_id', 'sanction_id', 'periode_id'}
        if not event_key and source_keys.intersection(data or {}):
            canonical = {key: value for key, value in (data or {}).items() if not key.startswith('_push_')}
            event_key = json.dumps([title, body, canonical], sort_keys=True, default=str)
        if event_key:
            key = hashlib.sha256(f'{content_type.pk}:{user.pk}:{event_key}'.encode()).hexdigest()
            job, created = PushDelivery.objects.get_or_create(dedup_key=key, defaults=values)
        else:
            job, created = PushDelivery.objects.create(**values), True
        if created:
            ids.append(job.pk)
    from school_admin.services.task_dispatcher import run_after_commit
    for job_id in ids:
        run_after_commit(deliver, 'school_admin.tasks.celery_tasks.deliver_push_task', job_id)
    return {'success_count': 0, 'failure_count': 0, 'queued_count': len(ids), 'responses': []}


def deliver(job_id):
    from school_admin.services.firebase_service import FirebaseService
    with transaction.atomic():
        job = PushDelivery.objects.select_for_update().get(pk=job_id)
        if job.status in ('sent', 'skipped', 'failed') or job.next_attempt > timezone.now():
            return
        tokens = list(FCMToken.objects.filter(content_type=job.content_type, object_id=job.object_id, is_active=True).values_list('token', flat=True))
        previously_sent = set(job.data.get('_push_delivered_tokens', []))
        tokens = [token for token in tokens if token not in previously_sent]
        job.attempts += 1
        if not tokens:
            job.status = 'sent' if previously_sent else 'skipped'
            job.last_error = '' if previously_sent else 'Aucun appareil actif.'
        else:
            data = dict(job.data)
            notification_ids = data.pop('_push_notification_ids', {})
            data.pop('_push_delivered_tokens', None)
            result = FirebaseService.send_multicast(tokens, job.title, job.body, data)
            if result.get('success_count', 0):
                job.status = 'sent'
                job.delivered_at = timezone.now()
                successful = [token for token, response in zip(tokens, result.get('responses', [])) if response.success]
                job.data = {**job.data, '_push_delivered_tokens': list(previously_sent | set(successful))}
                if result.get('failure_count', 0):
                    job.status = 'failed' if job.attempts >= 5 else 'pending'
                    job.next_attempt = timezone.now() + timedelta(minutes=2 ** job.attempts)
                notification_id = notification_ids.get(str(job.object_id))
                models = {'parent': 'NotificationParent', 'eleve': 'NotificationEleve',
                          'professeur': 'NotificationEnseignant', 'etablissement': 'NotificationDirecteur',
                          'personneladministratif': 'NotificationPersonnel'}
                if notification_id and job.content_type.model in models:
                    from django.apps import apps
                    apps.get_model('school_admin', models[job.content_type.model]).objects.filter(pk=notification_id).update(notification_push_envoyee=True)
            else:
                job.status = 'failed' if job.attempts >= 5 else 'pending'
                job.last_error = str(result.get('error') or 'Aucun appareil servi.')[:1000]
                job.next_attempt = timezone.now() + timedelta(minutes=2 ** job.attempts)
        job.save()
