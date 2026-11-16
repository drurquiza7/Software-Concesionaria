import os
import secrets

from cryptography.fernet import Fernet

# Los secretos de test se generan en cada corrida: no hay ninguno en el repositorio.
os.environ.setdefault("DJANGO_SECRET_KEY", secrets.token_urlsafe(64))
os.environ.setdefault("FIELD_ENCRYPTION_KEYS", Fernet.generate_key().decode())
os.environ.setdefault("DJANGO_ALLOWED_HOSTS", "testserver,localhost")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("CELERY_BROKER_URL", "memory://")

from .base import *

DEBUG = False

# Hasher rápido solo para la suite; el de producción se verifica en un test aparte.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
