"""Datos comunes para las pruebas de integración y seguridad del Sprint."""

from datetime import date, timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from gestion.models import (
    Actividad, Cargo, Compromiso, Delegacion, Evidencia, ItemMedicion, Periodo, Usuario,
)

CLAVE = "Clave.Prueba.2026"

# Cabecera mínima de un PNG real: sirve para distinguir una imagen verdadera
# de un archivo cualquiera renombrado como .png.
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def imagen(nombre="foto.png", contenido=PNG, tipo="image/png"):
    return SimpleUploadedFile(nombre, contenido, content_type=tipo)


@override_settings(MEDIA_ROOT="/tmp/sgr-pruebas-evidencias", ALLOWED_HOSTS=["testserver"])
class BaseSprint(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.hoy = date.today()
        cls.rural = Delegacion.objects.create(nombre="Delegación Rural")
        cls.costera = Delegacion.objects.create(nombre="Delegación Costera")
        cls.cargo = Cargo.objects.create(nombre="Territorial OO.CC.")
        cls.item = ItemMedicion.objects.create(nombre="Visita a organización", cargo=cls.cargo)
        cls.periodo = Periodo.objects.create(
            nombre="Período vigente",
            fecha_inicio=cls.hoy - timedelta(days=30),
            fecha_termino=cls.hoy + timedelta(days=30),
        )

        def crear(username, rol, delegacion=None, cargo=None, nombre=""):
            return Usuario.objects.create_user(
                username=username, password=CLAVE, rol=rol,
                delegacion=delegacion, cargo=cargo, first_name=nombre,
            )

        cls.funcionario = crear("jlopez", Usuario.FUNCIONARIO, cls.rural, cls.cargo, "Javiera")
        cls.colega = crear("psoto", Usuario.FUNCIONARIO, cls.rural, cls.cargo, "Paula")
        cls.otro = crear("rmunoz", Usuario.FUNCIONARIO, cls.costera, cls.cargo, "Rodrigo")
        cls.coordinador = crear("ccarrasco", Usuario.COORDINADOR, cls.rural, nombre="Carlos")
        cls.verificador = crear("mvega", Usuario.VERIFICADOR, cls.rural, nombre="Marcela")
        cls.verificador_costa = crear("lrojas", Usuario.VERIFICADOR, cls.costera, nombre="Luis")

    # --- ayudantes -------------------------------------------------------

    def entrar(self, usuario):
        self.client.force_login(usuario)

    def datos_actividad(self, **extra):
        datos = {
            "fecha": self.hoy.isoformat(),
            "item": self.item.pk,
            "descripcion": "Reunión de coordinación con la junta de vecinos.",
            "accion": "Visita realizada",
            "contacto": "Junta de Vecinos N°4",
            "telefono": "+56912345678",
            "cantidad": 1,
        }
        datos.update(extra)
        return datos

    def crear_actividad(self, funcionario=None, **extra):
        actividad = Actividad(
            funcionario=funcionario or self.funcionario, periodo=self.periodo,
            item=self.item, fecha=self.hoy, descripcion="Descripción de prueba",
            accion="Visita", contacto="Contacto", telefono="+56912345678",
        )
        for campo, valor in extra.items():
            setattr(actividad, campo, valor)
        actividad.full_clean()
        actividad.save()
        return actividad

    def crear_evidencia(self, actividad):
        return Evidencia.objects.create(
            actividad=actividad, archivo=imagen(), subida_por=actividad.funcionario,
        )

    def crear_compromiso(self, responsable=None, fecha=None, **extra):
        responsable = responsable or self.funcionario
        return Compromiso.objects.create(
            delegacion=responsable.delegacion, solicitante="Vecina del sector",
            territorio="Sector 3", responsable=responsable,
            fecha_comprometida=fecha or self.hoy + timedelta(days=5),
            descripcion="Retiro de escombros", creado_por=responsable, **extra,
        )
