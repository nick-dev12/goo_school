from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Calcule et envoie les rappels automatiques (cloche + push). --dry-run n'écrit et n'envoie rien."

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Simulation : liste les rappels dus.')
        parser.add_argument('--etablissement', type=int, action='append',
                            help='Limiter à un établissement (répétable).')

    def handle(self, *args, **options):
        from school_admin.services.rappels import generer

        stats = generer(etablissement_ids=options['etablissement'], dry_run=options['dry_run'])
        for role, pk, code, stage, titre in stats.pop('detail'):
            self.stdout.write(f'  {role}#{pk}  {code or "-":8} {stage:14} {titre}')
        mode = 'SIMULATION' if options['dry_run'] else 'ENVOI'
        self.stdout.write(self.style.SUCCESS(
            f"[{mode}] {stats['rappels']} rappel(s) pour {stats['personnes']} personne(s), "
            f"{stats['etablissements']} établissement(s) ; {stats['calmes']} en heures calmes ; "
            f"{stats['erreurs']} erreur(s)."))
