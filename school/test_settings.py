"""Réglages de test (SQLite mémoire, pas de Redis / secrets)."""
from .settings import *  # noqa: F403

DEBUG = False
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
LOGGING = {'version': 1, 'disable_existing_loggers': True}

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
