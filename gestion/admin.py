"""
Panel de administración.

Se usa el panel que trae Django en lugar de construir pantallas propias de
mantenimiento. Es una decisión deliberada de alcance: el administrador ya tiene
ahí un CRUD completo, auditado y con control de permisos, de modo que el tiempo
del sprint se concentra en el flujo que sí es propio del SGR.
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import (
    Actividad, CambioEstado, Cargo, Compromiso, Correlativo, Delegacion,
    Evidencia, ItemMedicion, Periodo, Usuario,
)


@admin.register(Delegacion)
class DelegacionAdmin(admin.ModelAdmin):
    list_display = ("nombre", "territorio", "activa")
    list_filter = ("activa",)
    search_fields = ("nombre", "territorio")


@admin.register(Cargo)
class CargoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "vigente")
    list_filter = ("vigente",)
    search_fields = ("nombre",)


@admin.register(ItemMedicion)
class ItemMedicionAdmin(admin.ModelAdmin):
    list_display = ("nombre", "cargo", "unidad", "activo")
    list_filter = ("activo", "cargo")
    search_fields = ("nombre",)


@admin.register(Periodo)
class PeriodoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "fecha_inicio", "fecha_termino", "estado")
    list_filter = ("estado",)


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    list_display = ("username", "get_full_name", "rol", "delegacion", "cargo", "is_active")
    list_filter = ("rol", "delegacion", "is_active")
    search_fields = ("username", "first_name", "last_name", "email")
    # Se extienden los grupos de campos del formulario estándar para incorporar
    # los atributos propios del SGR.
    fieldsets = UserAdmin.fieldsets + (
        ("Datos del SGR", {"fields": ("rol", "delegacion", "cargo")}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ("Datos del SGR", {"fields": ("rol", "delegacion", "cargo")}),
    )


@admin.register(Actividad)
class ActividadAdmin(admin.ModelAdmin):
    list_display = ("codigo", "fecha", "funcionario", "item", "cantidad")
    list_filter = ("periodo", "fecha", "funcionario__delegacion")
    search_fields = ("codigo", "accion", "contacto")
    date_hierarchy = "fecha"
    # El código se genera en el modelo y no se edita: mostrarlo como campo de
    # sólo lectura evita que el panel ofrezca modificarlo.
    readonly_fields = ("codigo", "creado_en")

    def get_queryset(self, request):
        """El panel respeta el mismo ámbito que el resto del sistema.

        Sin esto, un coordinador con acceso al panel vería las actividades de
        todas las delegaciones, saltándose el control de CU-07.
        """
        qs = super().get_queryset(request)
        return qs.del_ambito_de(request.user)


@admin.register(Correlativo)
class CorrelativoAdmin(admin.ModelAdmin):
    list_display = ("anio", "ultimo")
    readonly_fields = ("anio", "ultimo")

    def has_add_permission(self, request):
        return False


@admin.register(Evidencia)
class EvidenciaAdmin(admin.ModelAdmin):
    list_display = ("codigo", "actividad", "estado", "verificador", "revisada_en")
    list_filter = ("estado",)
    search_fields = ("codigo",)
    # La decisión se toma en la pantalla del verificador, que registra quién
    # y cuándo; el panel sólo permite consultarla.
    readonly_fields = ("codigo", "actividad", "archivo", "subida_por", "subida_en",
                       "estado", "verificador", "revisada_en", "observacion")

    def has_add_permission(self, request):
        return False


class CambioEstadoInline(admin.TabularInline):
    model = CambioEstado
    extra = 0
    can_delete = False
    readonly_fields = ("estado_anterior", "estado_nuevo", "autor", "fecha", "observacion")

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Compromiso)
class CompromisoAdmin(admin.ModelAdmin):
    list_display = ("__str__", "delegacion", "responsable", "fecha_comprometida", "estado")
    list_filter = ("estado", "delegacion")
    readonly_fields = ("estado", "creado_por", "creado_en")
    inlines = [CambioEstadoInline]

    def get_queryset(self, request):
        return super().get_queryset(request).del_ambito_de(request.user)
