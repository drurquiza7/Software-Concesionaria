import pytest
from django.core.exceptions import ValidationError
from django.test import RequestFactory
from pytest_django import Settings

from apps.core import validators
from apps.core.http import ip_cliente
from apps.core.ids import nuevo_id
from apps.core.ratelimit import registrar_intento


def test_cuit_valido() -> None:
    validators.validar_cuit("33693450239")


@pytest.mark.parametrize("cuit", ["33693450230", "3369345023", "33-69345023-9", "abcdefghijk"])
def test_cuit_invalido(cuit: str) -> None:
    with pytest.raises(ValidationError):
        validators.validar_cuit(cuit)


@pytest.mark.parametrize(
    ("validador", "valor"),
    [
        (validators.validar_slug, "casa-central-2"),
        (validators.validar_e164, "+5493329000000"),
        (validators.validar_color_hex, "#1F5fbf"),
        (validators.validar_zona_horaria, "America/Argentina/Buenos_Aires"),
    ],
)
def test_valores_validos(validador, valor: str) -> None:
    validador(valor)


@pytest.mark.parametrize(
    ("validador", "valor"),
    [
        (validators.validar_slug, "Casa Central"),
        (validators.validar_slug, "casa_central"),
        (validators.validar_e164, "03329 15-000000"),
        (validators.validar_e164, "+0123456789"),
        (validators.validar_color_hex, "1f5fbf"),
        (validators.validar_color_hex, "#12345"),
        (validators.validar_zona_horaria, "Marte/Olympus"),
    ],
)
def test_valores_invalidos(validador, valor: str) -> None:
    with pytest.raises(ValidationError):
        validador(valor)


def test_los_ids_son_uuid_distintos() -> None:
    assert nuevo_id() != nuevo_id()
    assert nuevo_id().version == 4


def test_rate_limit_corta_al_superar_el_limite() -> None:
    assert all(registrar_intento("prueba", "alguien", 5, 60) for _ in range(5))
    assert registrar_intento("prueba", "alguien", 5, 60) is False
    assert registrar_intento("prueba", "otro", 5, 60) is True
    assert registrar_intento("otro-ambito", "alguien", 5, 60) is True


def test_ip_sin_proxy_ignora_x_forwarded_for(settings: Settings) -> None:
    settings.TRUSTED_PROXY_COUNT = 0
    request = RequestFactory().get("/", REMOTE_ADDR="10.0.0.1", HTTP_X_FORWARDED_FOR="1.2.3.4")
    assert ip_cliente(request) == "10.0.0.1"


def test_ip_con_un_proxy_toma_la_que_agrego_el_proxy(settings: Settings) -> None:
    settings.TRUSTED_PROXY_COUNT = 1
    request = RequestFactory().get(
        "/", REMOTE_ADDR="172.18.0.2", HTTP_X_FORWARDED_FOR="6.6.6.6, 200.1.2.3"
    )
    assert ip_cliente(request) == "200.1.2.3"
