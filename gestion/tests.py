"""
Pruebas unitarias de las reglas de negocio del SGR.

Cada prueba verifica una regla documentada en la Etapa 2. El nombre del método
describe la regla, de modo que la salida de `manage.py test -v 2` sirve como
evidencia directa para el plan de pruebas.

    python manage.py test gestion -v 2
"""

from datetime import date, timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase

from .models import (
    Actividad, Cargo, Correlativo, Delegacion, ItemMedicion, Periodo, Usuario,
)


class BaseSGR(TestCase):
    """Datos comunes a todas las pruebas."""

    @classmethod
    def setUpTestData(cls):
        hoy = date.today()
        cls.hoy = hoy

        cls.rural = Delegacion.objects.create(nombre="Delegación Rural")
        cls.costera = Delegacion.objects.create(nombre="Delegación Costera")

        cls.territorial = Cargo.objects.create(nombre="Territorial OO.CC.")
        cls.social = Cargo.objects.create(nombre="Área Social")

        cls.item_visita = ItemMedicion.objects.create(
            nombre="Visita a organización", cargo=cls.territorial,
        )
        cls.item_retirado = ItemMedicion.objects.create(
            nombre="Entrega de folletería", cargo=cls.territorial, activo=False,
        )
        cls.item_social = ItemMedicion.objects.create(
            nombre="Atención social", cargo=cls.social,
        )

        cls.periodo = Periodo.objects.create(
            nombre="Período vigente",
            fecha_inicio=hoy - timedelta(days=30),
            fecha_termino=hoy + timedelta(days=30),
        )
        cls.periodo_cerrado = Periodo.objects.create(
            nombre="Período cerrado",
            fecha_inicio=hoy - timedelta(days=120),
            fecha_termino=hoy - timedelta(days=31),
            estado=Periodo.CERRADO,
        )

        cls.javiera = Usuario.objects.create_user(
            username="jlopez", password="Clave.Prueba.2026",
            rol=Usuario.FUNCIONARIO, delegacion=cls.rural, cargo=cls.territorial,
        )
        cls.rodrigo = Usuario.objects.create_user(
            username="rmunoz", password="Clave.Prueba.2026",
            rol=Usuario.FUNCIONARIO, delegacion=cls.costera, cargo=cls.territorial,
        )
        cls.coordinador = Usuario.objects.create_user(
            username="ccarrasco", password="Clave.Prueba.2026",
            rol=Usuario.COORDINADOR, delegacion=cls.rural,
        )
        cls.admin = Usuario.objects.create_user(
            username="avera", password="Clave.Prueba.2026",
            rol=Usuario.ADMINISTRADOR,
        )

    def actividad(self, **extra):
        datos = dict(
            funcionario=self.javiera,
            periodo=self.periodo,
            item=self.item_visita,
            fecha=self.hoy,
            descripcion="Visita de coordinación con la junta de vecinos.",
            accion="Visita realizada",
            contacto="Junta de Vecinos N°4",
            telefono="+56912345678",
        )
        datos.update(extra)
        return Actividad(**datos)


class CodigoActividadTests(BaseSGR):
    """RF-008: cada actividad recibe un código único e inmutable."""

    def test_el_codigo_se_genera_al_guardar(self):
        actividad = self.actividad()
        actividad.full_clean()
        actividad.save()
        self.assertTrue(actividad.codigo.startswith(f"ACT-{self.hoy.year}-"))

    def test_dos_actividades_consecutivas_reciben_codigos_distintos(self):
        primera = self.actividad()
        primera.full_clean()
        primera.save()
        segunda = self.actividad()
        segunda.full_clean()
        segunda.save()
        self.assertNotEqual(primera.codigo, segunda.codigo)

    def test_el_correlativo_avanza_de_uno_en_uno(self):
        self.actividad().save()
        self.actividad().save()
        self.assertEqual(Correlativo.objects.get(anio=self.hoy.year).ultimo, 2)

    def test_el_codigo_no_cambia_al_volver_a_guardar(self):
        actividad = self.actividad()
        actividad.save()
        original = actividad.codigo
        actividad.accion = "Visita corregida"
        actividad.save()
        actividad.refresh_from_db()
        self.assertEqual(actividad.codigo, original)


class ValidacionActividadTests(BaseSGR):
    """CU-05: el sistema rechaza los registros que incumplen una regla."""

    def test_rechaza_actividad_sin_campos_obligatorios(self):
        actividad = self.actividad(accion="", contacto="")
        with self.assertRaises(ValidationError) as caso:
            actividad.full_clean()
        self.assertIn("accion", caso.exception.error_dict)
        self.assertIn("contacto", caso.exception.error_dict)

    def test_rechaza_telefono_con_formato_invalido(self):
        actividad = self.actividad(telefono="no-es-un-telefono")
        with self.assertRaises(ValidationError) as caso:
            actividad.full_clean()
        self.assertIn("telefono", caso.exception.error_dict)

    def test_rechaza_registro_en_periodo_cerrado(self):
        actividad = self.actividad(
            periodo=self.periodo_cerrado,
            fecha=self.hoy - timedelta(days=60),
        )
        with self.assertRaises(ValidationError) as caso:
            actividad.full_clean()
        self.assertIn("periodo", caso.exception.error_dict)

    def test_rechaza_fecha_fuera_del_periodo(self):
        actividad = self.actividad(fecha=self.hoy - timedelta(days=90))
        with self.assertRaises(ValidationError) as caso:
            actividad.full_clean()
        self.assertIn("fecha", caso.exception.error_dict)

    def test_rechaza_fecha_futura(self):
        actividad = self.actividad(fecha=self.hoy + timedelta(days=1))
        with self.assertRaises(ValidationError) as caso:
            actividad.full_clean()
        self.assertIn("fecha", caso.exception.error_dict)

    def test_rechaza_item_de_otro_cargo(self):
        actividad = self.actividad(item=self.item_social)
        with self.assertRaises(ValidationError) as caso:
            actividad.full_clean()
        self.assertIn("item", caso.exception.error_dict)

    def test_rechaza_item_no_vigente_en_registros_nuevos(self):
        actividad = self.actividad(item=self.item_retirado)
        with self.assertRaises(ValidationError) as caso:
            actividad.full_clean()
        self.assertIn("item", caso.exception.error_dict)

    def test_acepta_una_actividad_valida(self):
        actividad = self.actividad()
        actividad.full_clean()
        actividad.save()
        self.assertEqual(Actividad.objects.count(), 1)


class AmbitoDeVisibilidadTests(BaseSGR):
    """CU-07: cada usuario ve sólo lo que le corresponde por rol y delegación."""

    def setUp(self):
        self.de_javiera = self.actividad()
        self.de_javiera.save()
        self.de_rodrigo = self.actividad(funcionario=self.rodrigo)
        self.de_rodrigo.save()

    def test_el_funcionario_ve_solo_sus_propias_actividades(self):
        visibles = Actividad.objects.del_ambito_de(self.javiera)
        self.assertQuerySetEqual(visibles, [self.de_javiera])

    def test_el_funcionario_no_ve_las_de_otra_delegacion(self):
        visibles = Actividad.objects.del_ambito_de(self.javiera)
        self.assertNotIn(self.de_rodrigo, visibles)

    def test_el_coordinador_ve_las_de_su_delegacion(self):
        visibles = Actividad.objects.del_ambito_de(self.coordinador)
        self.assertIn(self.de_javiera, visibles)
        self.assertNotIn(self.de_rodrigo, visibles)

    def test_el_administrador_ve_toda_la_institucion(self):
        visibles = Actividad.objects.del_ambito_de(self.admin)
        self.assertEqual(visibles.count(), 2)

    def test_un_usuario_sin_sesion_no_ve_nada(self):
        from django.contrib.auth.models import AnonymousUser
        visibles = Actividad.objects.del_ambito_de(AnonymousUser())
        self.assertEqual(visibles.count(), 0)


class PeriodoTests(BaseSGR):
    """RF-005: los períodos deben ser consistentes y no superponerse."""

    def test_rechaza_fecha_de_termino_anterior_al_inicio(self):
        periodo = Periodo(
            nombre="Período invertido",
            fecha_inicio=self.hoy,
            fecha_termino=self.hoy - timedelta(days=10),
        )
        with self.assertRaises(ValidationError) as caso:
            periodo.full_clean()
        self.assertIn("fecha_termino", caso.exception.error_dict)

    def test_rechaza_periodos_superpuestos(self):
        periodo = Periodo(
            nombre="Período solapado",
            fecha_inicio=self.hoy,
            fecha_termino=self.hoy + timedelta(days=60),
        )
        with self.assertRaises(ValidationError) as caso:
            periodo.full_clean()
        self.assertIn("fecha_inicio", caso.exception.error_dict)


class UsuarioTests(BaseSGR):
    """Un funcionario sin delegación ni cargo no podría operar el sistema."""

    def test_rechaza_funcionario_sin_delegacion_ni_cargo(self):
        usuario = Usuario(username="incompleto", rol=Usuario.FUNCIONARIO)
        with self.assertRaises(ValidationError) as caso:
            usuario.full_clean()
        self.assertIn("delegacion", caso.exception.error_dict)
        self.assertIn("cargo", caso.exception.error_dict)

    def test_la_contrasena_no_se_almacena_en_texto_plano(self):
        self.assertNotIn("Clave.Prueba.2026", self.javiera.password)
        self.assertTrue(self.javiera.check_password("Clave.Prueba.2026"))
