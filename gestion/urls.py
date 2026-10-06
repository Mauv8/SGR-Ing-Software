from django.urls import path

from . import views

urlpatterns = [
    path("", views.inicio, name="inicio"),
    path("actividades/", views.actividades, name="actividades"),
    path("actividades/nueva/", views.actividad_nueva, name="actividad_nueva"),
    path("actividades/<int:pk>/", views.actividad_detalle, name="actividad_detalle"),
    path("actividades/<int:pk>/evidencia/", views.evidencia_subir, name="evidencia_subir"),
    path("evidencias/<int:pk>/archivo/", views.evidencia_archivo, name="evidencia_archivo"),
    path("verificacion/", views.verificacion, name="verificacion"),
    path("verificacion/<int:pk>/", views.verificacion_decidir, name="verificacion_decidir"),
    path("compromisos/", views.compromisos, name="compromisos"),
    path("compromisos/nuevo/", views.compromiso_nuevo, name="compromiso_nuevo"),
    path("compromisos/<int:pk>/", views.compromiso_detalle, name="compromiso_detalle"),
]
