import pytest
from django.test import Client

from config.settings import base, prod


def test_las_contrasenas_se_guardan_con_argon2() -> None:
    assert base.PASSWORD_HASHERS[0] == "django.contrib.auth.hashers.Argon2PasswordHasher"


def test_cookies_de_sesion_seguras() -> None:
    assert base.SESSION_COOKIE_HTTPONLY is True
    assert base.SESSION_COOKIE_SAMESITE == "Lax"
    assert prod.SESSION_COOKIE_SECURE is True
    assert prod.CSRF_COOKIE_SECURE is True
    assert prod.DEBUG is False


def test_csrf_activo_y_tenant_despues_de_la_autenticacion() -> None:
    orden = base.MIDDLEWARE
    assert "django.middleware.csrf.CsrfViewMiddleware" in orden
    assert orden.index("apps.accounts.middleware.TenantMiddleware") > orden.index(
        "django.contrib.auth.middleware.AuthenticationMiddleware"
    )


def test_colas_de_celery() -> None:
    assert [cola.name for cola in base.CELERY_TASK_QUEUES] == ["default", "media", "meli"]
    assert base.CELERY_TASK_SERIALIZER == "json"


@pytest.mark.django_db
def test_healthz_responde_sin_sesion() -> None:
    respuesta = Client().get("/healthz")
    assert respuesta.status_code == 200
    assert respuesta.json() == {"status": "ok", "database": True, "redis": True}
