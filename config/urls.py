"""Rutas del proyecto SGR.

Las rutas de la aplicación se incorporan en la jornada siguiente, junto con la
autenticación. Por ahora el proyecto expone el panel de administración, que es
donde se cargan los datos institucionales.
"""

from django.contrib import admin
from django.urls import path
from django.views.generic import RedirectView

admin.site.site_header = "Sistema de Gestión de Resultados"
admin.site.site_title = "SGR"
admin.site.index_title = "Administración del SGR"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", RedirectView.as_view(pattern_name="admin:index", permanent=False)),
]
