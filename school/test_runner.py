"""Nettoie même une base de test dont les migrations échouent au démarrage."""
import re

from django.db import connections
from django.test.runner import DiscoverRunner


class IsolatedPostgresRunner(DiscoverRunner):
    def run_tests(self, *args, **kwargs):
        connection = connections['default']
        name = connection.settings_dict['TEST']['NAME']
        if not re.fullmatch(r'test_aria_audit_[0-9a-f]{12}', name):
            raise ValueError('Nom de base de test isolée invalide.')
        try:
            return super().run_tests(*args, **kwargs)
        finally:
            connection.close()
            with connection._nodb_cursor() as cursor:
                cursor.execute('DROP DATABASE IF EXISTS ' + connection.ops.quote_name(name))
