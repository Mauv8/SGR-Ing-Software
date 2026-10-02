"""
Modelos del Sistema de Gestión de Resultados (SGR).

Las reglas de negocio documentadas en la Etapa 2 viven aquí, en el modelo, y no
en los formularios ni en las plantillas. El motivo es que una regla escrita en
la pantalla sólo se cumple cuando el usuario pasa por esa pantalla: el panel de
administración, una carga masiva o una futura API la saltarían sin aviso.
"""

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models, transaction
from django.utils import timezone


# ---------------------------------------------------------------------------
# Estructura institucional
# ---------------------------------------------------------------------------

class Delegacion(models.Model):
    """Unidad territorial de la Municipalidad.

    Define el ámbito de visibilidad de los datos: un usuario sólo accede a la
    información de su propia delegación (CU-07).
    """

    nombre = models.CharField(max_length=120, unique=True)
    territorio = models.CharField(max_length=160, blank=True)
    activa = models.BooleanField(default=True)

    class Meta:
        verbose_name = "delegación"
        verbose_name_plural = "delegaciones"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class Cargo(models.Model):
    """Puesto de trabajo al que se asocian funciones e ítems medibles."""

    nombre = models.CharField(max_length=120, unique=True)
    descripcion = models.TextField(blank=True)
    vigente = models.BooleanField(default=True)

    class Meta:
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class ItemMedicion(models.Model):
    """Unidad concreta de trabajo que se contabiliza para evaluar a un cargo.

    Regla de vigencia: un ítem desactivado deja de ofrecerse en registros
    nuevos, pero sigue siendo visible en los históricos. Por eso se desactiva
    (`activo = False`) en lugar de eliminarse.
    """

    nombre = models.CharField(max_length=160)
    unidad = models.CharField(max_length=40, default="unidad")
    cargo = models.ForeignKey(Cargo, on_delete=models.PROTECT, related_name="items")
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "ítem de medición"
        verbose_name_plural = "ítems de medición"
        ordering = ["cargo__nombre", "nombre"]
        constraints = [
            models.UniqueConstraint(
                fields=["cargo", "nombre"], name="item_unico_por_cargo"
            )
        ]

    def __str__(self):
        return f"{self.nombre} ({self.cargo})"


class Periodo(models.Model):
    """Intervalo de fechas dentro del cual se acumulan los registros.

    Un período cerrado es inmutable: no admite registros nuevos. Esa regla
    protege los resultados ya medidos de cambios posteriores.
    """

    ABIERTO = "ABIERTO"
    CERRADO = "CERRADO"
    ESTADOS = [(ABIERTO, "Abierto"), (CERRADO, "Cerrado")]

    nombre = models.CharField(max_length=80, unique=True)
    fecha_inicio = models.DateField()
    fecha_termino = models.DateField()
    estado = models.CharField(max_length=8, choices=ESTADOS, default=ABIERTO)

    class Meta:
        verbose_name = "período"
        verbose_name_plural = "períodos"
        ordering = ["-fecha_inicio"]

    def __str__(self):
        return self.nombre

    @property
    def esta_cerrado(self):
        return self.estado == self.CERRADO

    def contiene(self, fecha):
        return self.fecha_inicio <= fecha <= self.fecha_termino

    def clean(self):
        errores = {}

        if self.fecha_inicio and self.fecha_termino:
            if self.fecha_inicio >= self.fecha_termino:
                errores["fecha_termino"] = (
                    "La fecha de término debe ser posterior a la de inicio."
                )
            else:
                # Dos períodos no pueden solaparse: si lo hicieran, una misma
                # actividad podría pertenecer a dos mediciones distintas.
                solapados = Periodo.objects.filter(
                    fecha_inicio__lte=self.fecha_termino,
                    fecha_termino__gte=self.fecha_inicio,
                ).exclude(pk=self.pk)
                if solapados.exists():
                    errores["fecha_inicio"] = (
                        "El período se superpone con "
                        f"«{solapados.first()}»."
                    )

        if errores:
            raise ValidationError(errores)


# ---------------------------------------------------------------------------
# Usuarios
# ---------------------------------------------------------------------------

class Usuario(AbstractUser):
    """Usuario del sistema, con su delegación y su rol.

    Se define desde el inicio del proyecto porque sustituir el modelo de
    usuario una vez aplicadas las migraciones es costoso.

    El rol VERIFICADOR existe porque la documentación declara ese actor; sus
    pantallas llegan con el módulo de evidencias, fuera del alcance de este
    sprint.
    """

    FUNCIONARIO = "FUNCIONARIO"
    COORDINADOR = "COORDINADOR"
    VERIFICADOR = "VERIFICADOR"
    ADMINISTRADOR = "ADMINISTRADOR"
    ROLES = [
        (FUNCIONARIO, "Funcionario"),
        (COORDINADOR, "Coordinador"),
        (VERIFICADOR, "Verificador"),
        (ADMINISTRADOR, "Administrador"),
    ]

    rol = models.CharField(max_length=14, choices=ROLES, default=FUNCIONARIO)
    delegacion = models.ForeignKey(
        Delegacion, on_delete=models.PROTECT,
        related_name="usuarios", null=True, blank=True,
    )
    cargo = models.ForeignKey(
        Cargo, on_delete=models.PROTECT,
        related_name="usuarios", null=True, blank=True,
    )

    class Meta:
        verbose_name = "usuario"
        verbose_name_plural = "usuarios"

    def __str__(self):
        nombre = self.get_full_name() or self.username
        return f"{nombre} ({self.get_rol_display()})"

    @property
    def es_administrador(self):
        return self.rol == self.ADMINISTRADOR

    @property
    def ve_toda_la_institucion(self):
        """Quién puede mirar más allá de su propia delegación.

        Es la base del filtro de ámbito de CU-07. Se expresa una sola vez para
        que ninguna vista invente su propio criterio.
        """
        return self.es_administrador or self.is_superuser

    def clean(self):
        # Un funcionario sin delegación no tendría ámbito que consultar, y un
        # funcionario sin cargo no tendría ítems que registrar.
        if self.rol == self.FUNCIONARIO and not self.is_superuser:
            errores = {}
            if self.delegacion_id is None:
                errores["delegacion"] = "Un funcionario debe pertenecer a una delegación."
            if self.cargo_id is None:
                errores["cargo"] = "Un funcionario debe tener un cargo asignado."
            if errores:
                raise ValidationError(errores)


# ---------------------------------------------------------------------------
# Correlativo de códigos
# ---------------------------------------------------------------------------

class Correlativo(models.Model):
    """Contador por año para generar códigos de actividad consecutivos.

    Se consulta con bloqueo de fila (`select_for_update`) para que dos usuarios
    que guarden al mismo instante no obtengan el mismo número. Es la respuesta
    concreta al requisito no funcional de concurrencia.
    """

    anio = models.PositiveIntegerField(unique=True)
    ultimo = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "correlativo"
        verbose_name_plural = "correlativos"

    def __str__(self):
        return f"{self.anio}: {self.ultimo}"

    @classmethod
    def siguiente(cls, anio):
        with transaction.atomic():
            fila, _ = cls.objects.select_for_update().get_or_create(anio=anio)
            fila.ultimo += 1
            fila.save(update_fields=["ultimo"])
            return fila.ultimo


# ---------------------------------------------------------------------------
# Registro de actividades (CU-01)
# ---------------------------------------------------------------------------

validador_telefono = RegexValidator(
    regex=r"^\+?[0-9\s]{8,15}$",
    message="Ingrese entre 8 y 15 dígitos; se admite el prefijo «+».",
)


class ActividadQuerySet(models.QuerySet):
    def del_ambito_de(self, usuario):
        """Acota el conjunto a lo que ese usuario tiene permitido ver.

        Toda consulta de actividades pasa por aquí. Centralizarlo evita que una
        vista nueva olvide el filtro y exponga datos de otra delegación, que es
        la falla de control de acceso más común.
        """
        if not usuario.is_authenticated:
            return self.none()
        if usuario.ve_toda_la_institucion:
            return self
        if usuario.rol == Usuario.COORDINADOR:
            return self.filter(funcionario__delegacion=usuario.delegacion)
        return self.filter(funcionario=usuario)


class Actividad(models.Model):
    """Actividad diaria registrada por un funcionario (CU-01).

    El código es único e inmutable: identifica la actividad ante cualquier
    evidencia que se le asocie más adelante, de modo que modificarlo rompería
    ese vínculo.
    """

    codigo = models.CharField(max_length=20, unique=True, editable=False)
    funcionario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="actividades",
    )
    periodo = models.ForeignKey(
        Periodo, on_delete=models.PROTECT, related_name="actividades",
    )
    item = models.ForeignKey(
        ItemMedicion, on_delete=models.PROTECT, related_name="actividades",
        verbose_name="ítem de medición",
    )
    fecha = models.DateField(default=timezone.localdate)
    descripcion = models.TextField("descripción", max_length=1000)
    accion = models.CharField("acción realizada", max_length=200)
    contacto = models.CharField(max_length=160)
    telefono = models.CharField(
        "teléfono", max_length=20, validators=[validador_telefono],
    )
    cantidad = models.PositiveIntegerField(default=1)
    creado_en = models.DateTimeField(auto_now_add=True)

    objects = ActividadQuerySet.as_manager()

    class Meta:
        verbose_name = "actividad"
        verbose_name_plural = "actividades"
        ordering = ["-fecha", "-creado_en"]
        indexes = [
            models.Index(fields=["funcionario", "fecha"]),
            models.Index(fields=["periodo"]),
        ]

    def __str__(self):
        return f"{self.codigo} · {self.accion}"

    def clean(self):
        errores = {}

        # El período cerrado no admite registros nuevos ni modificaciones.
        if self.periodo_id and self.periodo.esta_cerrado:
            errores["periodo"] = (
                "El período está cerrado y no admite registros nuevos."
            )

        # La fecha de la actividad debe caer dentro de su período.
        if self.periodo_id and self.fecha and not self.periodo.contiene(self.fecha):
            errores["fecha"] = (
                "La fecha queda fuera del período "
                f"«{self.periodo}» ({self.periodo.fecha_inicio} a "
                f"{self.periodo.fecha_termino})."
            )

        # No se registran actividades futuras: se informa lo hecho, no lo que
        # se piensa hacer. Lo que se piensa hacer es un compromiso.
        if self.fecha and self.fecha > timezone.localdate():
            errores["fecha"] = "No se admiten actividades con fecha futura."

        if self.item_id and self.funcionario_id:
            # El ítem debe pertenecer al cargo del funcionario; de otro modo la
            # medición dejaría de ser comparable entre funcionarios del mismo
            # cargo.
            if self.funcionario.cargo_id != self.item.cargo_id:
                errores["item"] = (
                    f"El ítem «{self.item.nombre}» no corresponde al cargo "
                    f"«{self.funcionario.cargo}»."
                )
            # Un ítem desactivado no se ofrece en registros nuevos, pero las
            # actividades históricas que lo usan se conservan intactas.
            if self._state.adding and not self.item.activo:
                errores["item"] = "El ítem de medición no está vigente."

        if errores:
            raise ValidationError(errores)

    def save(self, *args, **kwargs):
        if not self.codigo:
            anio = (self.fecha or timezone.localdate()).year
            self.codigo = f"ACT-{anio}-{Correlativo.siguiente(anio):05d}"
        super().save(*args, **kwargs)
