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

    # ------------------------------------------------------------------
    # Avance (RN-003 / RN-009)
    # ------------------------------------------------------------------

    @property
    def esta_aprobada(self):
        """Una actividad suma al avance sólo si tiene evidencia aprobada."""
        return self.evidencias.filter(estado=Evidencia.APROBADA).exists()

    @property
    def estado_evidencia(self):
        """Estado de la evidencia más reciente, para mostrar en listados."""
        ultima = self.evidencias.order_by("-subida_en").first()
        return ultima.get_estado_display() if ultima else "Sin evidencia"


def avance_aprobado(actividades):
    """Suma la cantidad de las actividades que tienen evidencia aprobada.

    Es la regla central del SGR: registrar no es lo mismo que cumplir. Una
    actividad sin evidencia, o con evidencia rechazada, no suma.
    """
    total = (
        actividades.filter(evidencias__estado=Evidencia.APROBADA)
        .distinct()
        .aggregate(total=models.Sum("cantidad"))["total"]
    )
    return total or 0


# ---------------------------------------------------------------------------
# Evidencias y verificación (HU-05)
# ---------------------------------------------------------------------------

def ruta_evidencia(instancia, nombre_original):
    """Guarda el archivo con un nombre aleatorio.

    No se usa el nombre que trae el archivo: así se evita que alguien suba
    «../../config/settings.py» o un nombre que revele datos de un vecino.
    """
    import uuid
    extension = nombre_original.rsplit(".", 1)[-1].lower()
    return f"evidencias/{uuid.uuid4().hex}.{extension}"


class Evidencia(models.Model):
    """Fotografía que respalda una actividad (RF-009, RF-010).

    El registro (funcionario) y la decisión (verificador) quedan separados:
    quien sube la evidencia no puede aprobarla.
    """

    PENDIENTE = "PENDIENTE"
    APROBADA = "APROBADA"
    RECHAZADA = "RECHAZADA"
    CORRECCION = "CORRECCION"
    ESTADOS = [
        (PENDIENTE, "Pendiente de revisión"),
        (APROBADA, "Aprobada"),
        (RECHAZADA, "Rechazada"),
        (CORRECCION, "Corrección solicitada"),
    ]

    codigo = models.CharField(max_length=30, unique=True, editable=False)
    actividad = models.ForeignKey(
        Actividad, on_delete=models.PROTECT, related_name="evidencias",
    )
    archivo = models.FileField(upload_to=ruta_evidencia)
    subida_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="evidencias_subidas",
    )
    subida_en = models.DateTimeField(auto_now_add=True)
    estado = models.CharField(max_length=10, choices=ESTADOS, default=PENDIENTE)
    verificador = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="evidencias_revisadas", null=True, blank=True,
    )
    revisada_en = models.DateTimeField(null=True, blank=True)
    observacion = models.TextField("observación", blank=True, max_length=500)

    class Meta:
        verbose_name = "evidencia"
        verbose_name_plural = "evidencias"
        ordering = ["-subida_en"]

    def __str__(self):
        return self.codigo

    def save(self, *args, **kwargs):
        if not self.codigo:
            numero = Evidencia.objects.filter(actividad=self.actividad).count() + 1
            self.codigo = f"{self.actividad.codigo}-EV{numero}"
        super().save(*args, **kwargs)

    def decidir(self, verificador, decision, observacion=""):
        """Registra la decisión del verificador (RF-010).

        Guarda quién decidió, cuándo y por qué. Rechazar o pedir corrección
        exige observación: sin motivo el funcionario no sabe qué corregir.
        """
        if decision not in (self.APROBADA, self.RECHAZADA, self.CORRECCION):
            raise ValidationError("Decisión no válida.")
        if self.estado != self.PENDIENTE:
            raise ValidationError("La evidencia ya fue revisada.")
        if verificador.rol != Usuario.VERIFICADOR:
            raise ValidationError("Sólo un verificador puede revisar evidencias.")
        if verificador.pk == self.subida_por_id:
            raise ValidationError("No puede revisar una evidencia subida por usted.")
        if decision != self.APROBADA and not observacion.strip():
            raise ValidationError("Debe indicar el motivo del rechazo o la corrección.")
        self.estado = decision
        self.verificador = verificador
        self.revisada_en = timezone.now()
        self.observacion = observacion.strip()
        self.save(update_fields=["estado", "verificador", "revisada_en", "observacion"])


# ---------------------------------------------------------------------------
# Agenda colectiva: compromisos (HU-02)
# ---------------------------------------------------------------------------

class CompromisoQuerySet(models.QuerySet):
    def del_ambito_de(self, usuario):
        """La agenda es colectiva dentro de la delegación (RF-013)."""
        if not usuario.is_authenticated:
            return self.none()
        if usuario.ve_toda_la_institucion:
            return self
        return self.filter(delegacion=usuario.delegacion)


class Compromiso(models.Model):
    """Compromiso futuro del «tubo de trabajo» (RF-013, RF-014)."""

    INGRESADO = "INGRESADO"
    PENDIENTE = "PENDIENTE"
    EN_PROCESO = "EN_PROCESO"
    REALIZADO = "REALIZADO"
    ESTADOS = [
        (INGRESADO, "Ingresado"),
        (PENDIENTE, "Pendiente"),
        (EN_PROCESO, "En proceso"),
        (REALIZADO, "Realizado"),
    ]
    # Sólo se avanza un paso a la vez: Ingresado → Pendiente → En proceso →
    # Realizado (diagrama de estados de la Etapa 2).
    SIGUIENTE = {
        INGRESADO: PENDIENTE,
        PENDIENTE: EN_PROCESO,
        EN_PROCESO: REALIZADO,
    }

    actividad = models.ForeignKey(
        Actividad, on_delete=models.PROTECT, related_name="compromisos",
        null=True, blank=True, verbose_name="actividad de origen",
    )
    delegacion = models.ForeignKey(
        Delegacion, on_delete=models.PROTECT, related_name="compromisos",
    )
    solicitante = models.CharField(max_length=160)
    territorio = models.CharField(max_length=160)
    responsable = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="compromisos_asignados",
    )
    apoyo = models.CharField("área de apoyo", max_length=120, blank=True)
    fecha_comprometida = models.DateField()
    descripcion = models.TextField("descripción", max_length=1000)
    estado = models.CharField(max_length=10, choices=ESTADOS, default=INGRESADO, editable=False)
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="compromisos_creados",
    )
    creado_en = models.DateTimeField(auto_now_add=True)

    objects = CompromisoQuerySet.as_manager()

    class Meta:
        verbose_name = "compromiso"
        verbose_name_plural = "compromisos"
        ordering = ["fecha_comprometida"]

    def __str__(self):
        return f"C-{self.pk} · {self.solicitante}"

    @property
    def vencido(self):
        """Vencido = la fecha ya pasó y todavía no está realizado (RF-019)."""
        return (
            self.estado != self.REALIZADO
            and self.fecha_comprometida < timezone.localdate()
        )

    @property
    def estado_siguiente(self):
        return self.SIGUIENTE.get(self.estado)

    def clean(self):
        errores = {}
        if self._state.adding and self.fecha_comprometida and \
                self.fecha_comprometida < timezone.localdate():
            errores["fecha_comprometida"] = "La fecha comprometida no puede estar en el pasado."
        if self.responsable_id and self.delegacion_id and \
                self.responsable.delegacion_id != self.delegacion_id:
            errores["responsable"] = "El responsable debe pertenecer a la misma delegación."
        if errores:
            raise ValidationError(errores)

    def puede_cambiar_estado(self, usuario):
        """El responsable o el coordinador de la delegación (CU-11)."""
        if usuario.ve_toda_la_institucion:
            return True
        if usuario.rol == Usuario.COORDINADOR:
            return usuario.delegacion_id == self.delegacion_id
        return usuario.pk == self.responsable_id

    def cambiar_estado(self, usuario, nuevo_estado, observacion):
        """Aplica una transición válida y deja historial (RF-014, CU-11)."""
        if not self.puede_cambiar_estado(usuario):
            raise ValidationError("No tiene permiso para cambiar este compromiso.")
        if nuevo_estado != self.estado_siguiente:
            raise ValidationError(
                f"Transición no permitida desde «{self.get_estado_display()}»."
            )
        if not observacion or not observacion.strip():
            raise ValidationError("La observación es obligatoria.")
        with transaction.atomic():
            anterior = self.estado
            self.estado = nuevo_estado
            self.save(update_fields=["estado"])
            CambioEstado.objects.create(
                compromiso=self, estado_anterior=anterior,
                estado_nuevo=nuevo_estado, autor=usuario,
                observacion=observacion.strip(),
            )


class CambioEstado(models.Model):
    """Historial de un compromiso: anterior, nuevo, autor, fecha y observación."""

    compromiso = models.ForeignKey(
        Compromiso, on_delete=models.PROTECT, related_name="historial",
    )
    estado_anterior = models.CharField(max_length=10, choices=Compromiso.ESTADOS)
    estado_nuevo = models.CharField(max_length=10, choices=Compromiso.ESTADOS)
    autor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    fecha = models.DateTimeField(auto_now_add=True)
    observacion = models.TextField("observación", max_length=500)

    class Meta:
        verbose_name = "cambio de estado"
        verbose_name_plural = "cambios de estado"
        ordering = ["fecha"]

    def __str__(self):
        return f"{self.compromiso}: {self.estado_anterior} → {self.estado_nuevo}"


# ---------------------------------------------------------------------------
# Bitácora de auditoría (RNF-008, Ley 21.459)
# ---------------------------------------------------------------------------

class RegistroAuditoria(models.Model):
    """Traza de las operaciones críticas: quién, qué, cuándo y desde dónde.

    Es de sólo inserción: un registro guardado no se modifica ni se elimina,
    porque una bitácora que se puede alterar no sirve como evidencia.
    """

    fecha = models.DateTimeField(auto_now_add=True)
    usuario = models.CharField(max_length=150)
    accion = models.CharField(max_length=30, db_index=True)
    entidad = models.CharField(max_length=60, blank=True)
    identificador = models.CharField(max_length=40, blank=True)
    detalle = models.CharField(max_length=300, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        verbose_name = "registro de auditoría"
        verbose_name_plural = "bitácora de auditoría"
        ordering = ["-fecha"]

    def __str__(self):
        return f"{self.fecha:%d-%m-%Y %H:%M} {self.usuario} {self.accion}"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise PermissionError("La bitácora no admite modificaciones.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError("La bitácora no admite eliminaciones.")

    @classmethod
    def registrar(cls, request, accion, objeto=None, detalle="", usuario=None):
        if usuario is None:
            usuario = request.user.username if request and request.user.is_authenticated else "anónimo"
        return cls.objects.create(
            usuario=usuario,
            accion=accion,
            entidad=objeto.__class__.__name__ if objeto is not None else "",
            identificador=str(getattr(objeto, "codigo", None) or getattr(objeto, "pk", "") or ""),
            detalle=detalle[:300],
            ip=request.META.get("REMOTE_ADDR") if request else None,
        )
