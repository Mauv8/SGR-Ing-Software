from django.apps import AppConfig


class GestionConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "gestion"
    verbose_name = "Gestión de resultados"

    def ready(self):
        # Registra las señales de auditoría de inicio y cierre de sesión.
        from . import seguridad  # noqa: F401
