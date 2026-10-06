"""Rutas del proyecto SGR."""

from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

admin.site.site_header = "Sistema de Gestión de Resultados"
admin.site.site_title = "SGR"
admin.site.index_title = "Administración del SGR"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("ingresar/", auth_views.LoginView.as_view(template_name="registration/login.html"), name="login"),
    path("salir/", auth_views.LogoutView.as_view(), name="logout"),
    path("", include("gestion.urls")),
]
