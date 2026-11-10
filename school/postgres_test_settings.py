"""Validation à froid des migrations sur une base PostgreSQL jetable unique."""
from copy import deepcopy
from uuid import uuid4

from .test_settings import *  # noqa: F403
from .settings import DATABASES as PROJECT_DATABASES

DATABASES = deepcopy(PROJECT_DATABASES)
DATABASES['default']['TEST'] = {'NAME': 'test_aria_audit_' + uuid4().hex[:12]}
MIGRATION_MODULES = {}
TEST_RUNNER = 'school.test_runner.IsolatedPostgresRunner'
