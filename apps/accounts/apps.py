from typing import Any

from django.apps import AppConfig
from django.db.models.signals import post_migrate


def _sincronizar_catalogo(sender: AppConfig, **kwargs: Any) -> None:
    # Import tardío obligado: los modelos no existen cuando Django carga apps.py.
    from .services import sincronizar_permisos

    sincronizar_permisos()


class AccountsConfig(AppConfig):
    name = "apps.accounts"
    label = "accounts"

    def ready(self) -> None:
        # SRS 2.7: el catálogo de permisos se sincroniza a la tabla en cada migración.
        post_migrate.connect(_sincronizar_catalogo, sender=self)
