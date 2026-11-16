import pytest
from cryptography.fernet import Fernet
from django.core.exceptions import ImproperlyConfigured
from pytest_django import Settings

from apps.core import crypto
from apps.core.exceptions import ErrorDeCifrado
from apps.core.fields import EncryptedTextField


def _clave() -> str:
    return Fernet.generate_key().decode()


def test_cifrar_y_descifrar() -> None:
    cifrado = crypto.cifrar("dato reservado ñ")
    assert "dato reservado" not in cifrado
    assert crypto.descifrar(cifrado) == "dato reservado ñ"


def test_dos_cifrados_del_mismo_texto_son_distintos() -> None:
    assert crypto.cifrar("igual") != crypto.cifrar("igual")


def test_rotacion_de_claves(settings: Settings) -> None:
    vieja, nueva = _clave(), _clave()
    settings.FIELD_ENCRYPTION_KEYS = [vieja]
    cifrado_viejo = crypto.cifrar("secreto")

    settings.FIELD_ENCRYPTION_KEYS = [nueva, vieja]
    assert crypto.descifrar(cifrado_viejo) == "secreto"
    rotado = crypto.rotar(cifrado_viejo)

    settings.FIELD_ENCRYPTION_KEYS = [nueva]
    assert crypto.descifrar(rotado) == "secreto"
    with pytest.raises(ErrorDeCifrado):
        crypto.descifrar(cifrado_viejo)


def test_un_valor_alterado_no_se_descifra() -> None:
    with pytest.raises(ErrorDeCifrado):
        crypto.descifrar("no-es-un-token")
    with pytest.raises(ErrorDeCifrado):
        crypto.rotar("no-es-un-token")


def test_sin_claves_configuradas_falla(settings: Settings) -> None:
    settings.FIELD_ENCRYPTION_KEYS = []
    with pytest.raises(ImproperlyConfigured):
        crypto.cifrar("x")


def test_hash_y_comparacion() -> None:
    token = crypto.generar_token()
    assert token != crypto.generar_token()
    resumen = crypto.hash_sha256(token)
    assert len(resumen) == 64 and token not in resumen
    assert crypto.hashes_iguales(resumen, crypto.hash_sha256(token))
    assert not crypto.hashes_iguales(resumen, crypto.hash_sha256("otro"))


def test_campo_cifrado_guarda_cifrado_y_devuelve_texto() -> None:
    campo = EncryptedTextField()
    guardado = campo.get_prep_value("Juan Pérez")
    assert guardado != "Juan Pérez" and "Juan" not in guardado
    assert campo.from_db_value(guardado, None, None) == "Juan Pérez"


def test_campo_cifrado_respeta_null() -> None:
    campo = EncryptedTextField(null=True)
    assert campo.get_prep_value(None) is None
    assert campo.from_db_value(None, None, None) is None
