"""Sauvegarde PostgreSQL et médias ; aucune donnée ni secret dans stdout."""
import os
from pathlib import Path
import subprocess
import tarfile

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Sauvegarde PostgreSQL (format custom) et médias dans un dossier privé.'

    def add_arguments(self, parser):
        parser.add_argument('--output', required=True)

    def handle(self, *args, **options):
        db = settings.DATABASES['default']
        if db['ENGINE'] != 'django.db.backends.postgresql':
            raise CommandError('Sauvegarde prévue pour PostgreSQL uniquement.')
        target = Path(options['output']).resolve()
        target.mkdir(parents=True, exist_ok=True, mode=0o700)
        dump = target / 'database.dump'
        media_archive = target / 'media.tar.gz'
        if dump.exists() or media_archive.exists():
            raise CommandError('Le dossier contient déjà une sauvegarde.')
        env = {**os.environ, 'PGPASSWORD': str(db.get('PASSWORD', ''))}
        try:
            subprocess.run([
                'pg_dump', '--format=custom', '--no-owner', '--no-acl',
                '--host', str(db.get('HOST') or 'localhost'),
                '--port', str(db.get('PORT') or '5432'),
                '--username', str(db['USER']), '--file', str(dump), str(db['NAME']),
            ], env=env, check=True, capture_output=True)
            media = Path(settings.MEDIA_ROOT)
            if media.exists():
                with tarfile.open(media_archive, 'w:gz') as archive:
                    archive.add(media, arcname='media')
        except (OSError, subprocess.CalledProcessError) as exc:
            raise CommandError('Sauvegarde échouée ; vérifier pg_dump, accès et espace disque.') from exc
        self.stdout.write(self.style.SUCCESS('Sauvegarde terminée. Tester sa restauration avant livraison.'))
