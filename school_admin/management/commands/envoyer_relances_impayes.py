from django.core.management.base import BaseCommand

from school_admin.services.recouvrement import (
    envoyer_relances_automatiques,
    verifier_rupture_moratoires,
)


class Command(BaseCommand):
    help = "Envoie les relances SMS/WhatsApp d'impayés et vérifie les moratoires."

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Simule les relances et ruptures sans écriture ni envoi.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        rompus = verifier_rupture_moratoires(dry_run=dry_run)
        stats = envoyer_relances_automatiques(dry_run=dry_run)
        self.stdout.write(
            self.style.SUCCESS(
                f"{'SIMULATION — ' if dry_run else ''}Moratoires rompus: {rompus}. Relances: {stats}"
            )
        )
