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
            help='Affiche les compteurs sans envoyer (non implémenté côté envoi : lance vraiment).',
        )

    def handle(self, *args, **options):
        rompus = verifier_rupture_moratoires()
        stats = envoyer_relances_automatiques()
        self.stdout.write(
            self.style.SUCCESS(
                f"Moratoires rompus: {rompus}. Relances: {stats}"
            )
        )
