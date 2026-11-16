from django.apps import AppConfig
from django.utils.module_loading import autodiscover_modules


class CoreConfig(AppConfig):
    name = "apps.core"
    label = "core"

    def ready(self) -> None:
        # Cada app declara sus permisos en su permissions.py; importarlos los registra.
        autodiscover_modules("permissions")
