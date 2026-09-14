"""Réglages de test (SQLite mémoire, pas de Redis / secrets)."""
from .settings import *  # noqa: F403

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}

CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels.layers.InMemoryChannelLayer',
    }
}

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
    }
}

USE_CELERY = False
USE_REDIS_CACHE = False
REALTIME_LOCAL = False
PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.MD5PasswordHasher',
]

# Les migrations historiques ne s’appliquent pas à froid (colonnes déjà présentes).
# Les tests construisent le schéma à partir des modèles courants.
MIGRATION_MODULES = {
    'school_admin': None,
    'admin': None,
    'auth': None,
    'contenttypes': None,
    'sessions': None,
}
