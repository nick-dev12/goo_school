from django.core.management.base import BaseCommand
from django.utils import timezone
from school_admin.model.push_delivery_model import PushDelivery
from school_admin.services.push_delivery import deliver


class Command(BaseCommand):
    help = 'Reprend les notifications push persistantes en attente.'

    def handle(self, **options):
        ids = list(PushDelivery.objects.filter(status='pending', next_attempt__lte=timezone.now()).values_list('pk', flat=True)[:500])
        for job_id in ids:
            deliver(job_id)
        self.stdout.write(f'{len(ids)} envoi(s) traité(s).')
