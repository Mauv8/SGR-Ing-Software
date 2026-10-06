"""
Pruebas unitarias, de integración y funcionales del Sprint.

Cada método empieza su descripción con el identificador del caso del Plan
de Pruebas (CP-xx), para que la salida de `manage.py test -v 2` sirva como
evidencia de ejecución.
"""

from datetime import timedelta

from django.core.exceptions import ValidationError
from django.urls import reverse

from gestion.models import (
    Actividad, CambioEstado, Compromiso, Evidencia, avance_aprobado,
)

from .base import BaseSprint, imagen


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

class LoginTests(BaseSprint):

    def test_cp01_login_con_credenciales_validas(self):
        """CP-01 Login válido lleva al inicio."""
        r = self.client.post(reverse("login"), {"username": "jlopez", "password": "Clave.Prueba.2026"})
        self.assertRedirects(r, reverse("inicio"))

    def test_cp02_login_con_credenciales_invalidas(self):
        """CP-02 Login inválido: acceso denegado con mensaje genérico."""
        r = self.client.post(reverse("login"), {"username": "jlopez", "password": "123"})
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)
        # El mensaje no indica si falló el usuario o la contraseña.
        self.assertNotContains(r, "no existe")
        self.assertNotContains(r, "Traceback")

    def test_cp03_ruta_privada_sin_sesion_redirige_al_login(self):
        """CP-03 Sin sesión, toda ruta privada redirige al login."""
        for nombre in ["inicio", "actividades", "actividad_nueva", "compromisos", "verificacion"]:
            r = self.client.get(reverse(nombre))
            self.assertEqual(r.status_code, 302, nombre)
            self.assertTrue(r.url.startswith(reverse("login")), nombre)


# ---------------------------------------------------------------------------
# HU-01 · Registrar actividad
# ---------------------------------------------------------------------------

class ActividadTests(BaseSprint):

    def test_cp04_registrar_actividad_valida_genera_codigo(self):
        """CP-04 HU-01: actividad válida se guarda y muestra su código."""
        self.entrar(self.funcionario)
        r = self.client.post(reverse("actividad_nueva"), self.datos_actividad(), follow=True)
        actividad = Actividad.objects.get()
        self.assertTrue(actividad.codigo.startswith(f"ACT-{self.hoy.year}-"))
        self.assertContains(r, actividad.codigo)
        self.assertEqual(actividad.periodo, self.periodo)

    def test_cp05_campo_obligatorio_vacio_no_guarda(self):
        """CP-05 HU-01: campo obligatorio vacío informa error y no guarda."""
        self.entrar(self.funcionario)
        r = self.client.post(reverse("actividad_nueva"), self.datos_actividad(contacto="", telefono=""))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "No se guardó el registro")
        self.assertEqual(Actividad.objects.count(), 0)

    def test_cp06_telefono_con_formato_invalido(self):
        """CP-06 HU-01: teléfono inválido se rechaza."""
        self.entrar(self.funcionario)
        self.client.post(reverse("actividad_nueva"), self.datos_actividad(telefono="abc"))
        self.assertEqual(Actividad.objects.count(), 0)

    def test_cp07_fecha_sin_periodo_se_rechaza(self):
        """CP-07 HU-01: fecha fuera de todo período se rechaza."""
        self.entrar(self.funcionario)
        fecha = (self.hoy - timedelta(days=200)).isoformat()
        r = self.client.post(reverse("actividad_nueva"), self.datos_actividad(fecha=fecha))
        self.assertContains(r, "No existe un período")
        self.assertEqual(Actividad.objects.count(), 0)

    def test_cp08_solo_el_funcionario_registra_actividades(self):
        """CP-08 HU-01: un verificador no puede registrar actividades (403)."""
        self.entrar(self.verificador)
        self.assertEqual(self.client.get(reverse("actividad_nueva")).status_code, 403)

    def test_cp09_busqueda_por_codigo(self):
        """CP-09 CU-06: buscar por código devuelve la actividad del ámbito."""
        actividad = self.crear_actividad()
        self.entrar(self.funcionario)
        r = self.client.get(reverse("actividades"), {"q": actividad.codigo})
        self.assertContains(r, actividad.codigo)

    def test_cp10_busqueda_sin_coincidencias(self):
        """CP-10 CU-10: búsqueda sin resultados informa y no falla."""
        self.entrar(self.funcionario)
        r = self.client.get(reverse("actividades"), {"q": "NO-EXISTE"})
        self.assertContains(r, "No hay actividades que coincidan")


# ---------------------------------------------------------------------------
# HU-05 · Evidencias y verificación
# ---------------------------------------------------------------------------

class EvidenciaTests(BaseSprint):

    def test_cp11_adjuntar_evidencia_valida(self):
        """CP-11 HU-05: imagen válida queda vinculada al código de la actividad."""
        actividad = self.crear_actividad()
        self.entrar(self.funcionario)
        self.client.post(reverse("evidencia_subir", args=[actividad.pk]), {"archivo": imagen()})
        evidencia = Evidencia.objects.get()
        self.assertEqual(evidencia.codigo, f"{actividad.codigo}-EV1")
        self.assertEqual(evidencia.estado, Evidencia.PENDIENTE)

    def test_cp12_formato_no_permitido_se_rechaza(self):
        """CP-12 HU-05: archivo .pdf se rechaza con el motivo."""
        actividad = self.crear_actividad()
        self.entrar(self.funcionario)
        r = self.client.post(
            reverse("evidencia_subir", args=[actividad.pk]),
            {"archivo": imagen("informe.pdf", b"%PDF-1.4", "application/pdf")}, follow=True,
        )
        self.assertContains(r, "Sólo se aceptan imágenes JPG o PNG")
        self.assertEqual(Evidencia.objects.count(), 0)

    def test_cp13_archivo_sobre_5mb_se_rechaza(self):
        """CP-13 HU-05: archivo mayor a 5 MB se rechaza."""
        actividad = self.crear_actividad()
        self.entrar(self.funcionario)
        grande = b"\x89PNG\r\n\x1a\n" + b"\x00" * (5 * 1024 * 1024 + 1)
        r = self.client.post(
            reverse("evidencia_subir", args=[actividad.pk]), {"archivo": imagen(contenido=grande)}, follow=True,
        )
        self.assertContains(r, "5 MB")
        self.assertEqual(Evidencia.objects.count(), 0)

    def test_cp14_aprobar_evidencia_suma_al_avance(self):
        """CP-14 RN-003: evidencia aprobada suma al avance una sola vez."""
        actividad = self.crear_actividad()
        evidencia = self.crear_evidencia(actividad)
        self.assertEqual(avance_aprobado(Actividad.objects.all()), 0)
        self.entrar(self.verificador)
        self.client.post(reverse("verificacion_decidir", args=[evidencia.pk]), {"decision": Evidencia.APROBADA})
        evidencia.refresh_from_db()
        self.assertEqual(evidencia.estado, Evidencia.APROBADA)
        self.assertEqual(evidencia.verificador, self.verificador)
        self.assertIsNotNone(evidencia.revisada_en)
        self.assertEqual(avance_aprobado(Actividad.objects.all()), 1)

    def test_cp15_evidencia_rechazada_no_suma(self):
        """CP-15 RN-009: evidencia rechazada no suma y conserva el motivo."""
        actividad = self.crear_actividad()
        evidencia = self.crear_evidencia(actividad)
        self.entrar(self.verificador)
        self.client.post(
            reverse("verificacion_decidir", args=[evidencia.pk]),
            {"decision": Evidencia.RECHAZADA, "observacion": "La foto no muestra la actividad."},
        )
        evidencia.refresh_from_db()
        self.assertEqual(evidencia.estado, Evidencia.RECHAZADA)
        self.assertEqual(evidencia.observacion, "La foto no muestra la actividad.")
        self.assertEqual(avance_aprobado(Actividad.objects.all()), 0)

    def test_cp16_rechazo_sin_observacion_no_se_guarda(self):
        """CP-16 RF-010: rechazar sin motivo no se permite."""
        evidencia = self.crear_evidencia(self.crear_actividad())
        with self.assertRaises(ValidationError):
            evidencia.decidir(self.verificador, Evidencia.RECHAZADA, "")
        evidencia.refresh_from_db()
        self.assertEqual(evidencia.estado, Evidencia.PENDIENTE)

    def test_cp17_evidencia_no_se_revisa_dos_veces(self):
        """CP-17 RF-010: una evidencia ya revisada no cambia de decisión."""
        evidencia = self.crear_evidencia(self.crear_actividad())
        evidencia.decidir(self.verificador, Evidencia.APROBADA)
        with self.assertRaises(ValidationError):
            evidencia.decidir(self.verificador, Evidencia.RECHAZADA, "cambio")

    def test_cp18_solo_el_autor_adjunta_evidencia(self):
        """CP-18 HU-05: una colega no puede adjuntar evidencia a mi actividad."""
        actividad = self.crear_actividad()
        self.entrar(self.colega)
        r = self.client.post(reverse("evidencia_subir", args=[actividad.pk]), {"archivo": imagen()})
        # La colega no ve la actividad ajena: la respuesta es 404.
        self.assertEqual(r.status_code, 404)
        self.assertEqual(Evidencia.objects.count(), 0)


# ---------------------------------------------------------------------------
# HU-02 · Compromisos
# ---------------------------------------------------------------------------

class CompromisoTests(BaseSprint):

    def datos_compromiso(self, **extra):
        datos = {
            "solicitante": "Vecina del sector",
            "territorio": "Sector 3",
            "responsable": self.funcionario.pk,
            "apoyo": "Aseo y ornato",
            "fecha_comprometida": (self.hoy + timedelta(days=7)).isoformat(),
            "descripcion": "Retiro de escombros en pasaje.",
        }
        datos.update(extra)
        return datos

    def test_cp19_crear_compromiso_queda_ingresado_y_visible(self):
        """CP-19 HU-02: compromiso válido queda Ingresado y visible en la agenda."""
        self.entrar(self.funcionario)
        self.client.post(reverse("compromiso_nuevo"), self.datos_compromiso())
        compromiso = Compromiso.objects.get()
        self.assertEqual(compromiso.estado, Compromiso.INGRESADO)
        self.entrar(self.colega)  # la agenda es colectiva en la delegación
        self.assertContains(self.client.get(reverse("compromisos")), "Vecina del sector")

    def test_cp20_compromiso_sin_responsable_ni_fecha_se_rechaza(self):
        """CP-20 RF-017: sin responsable o fecha no se guarda."""
        self.entrar(self.funcionario)
        self.client.post(reverse("compromiso_nuevo"), self.datos_compromiso(responsable="", fecha_comprometida=""))
        self.assertEqual(Compromiso.objects.count(), 0)

    def test_cp21_compromiso_con_fecha_pasada_se_rechaza(self):
        """CP-21 HU-02: fecha comprometida en el pasado se rechaza."""
        self.entrar(self.funcionario)
        ayer = (self.hoy - timedelta(days=1)).isoformat()
        self.client.post(reverse("compromiso_nuevo"), self.datos_compromiso(fecha_comprometida=ayer))
        self.assertEqual(Compromiso.objects.count(), 0)

    def test_cp22_cambio_de_estado_registra_historial(self):
        """CP-22 RF-014: el cambio guarda anterior, nuevo, autor, fecha y observación."""
        compromiso = self.crear_compromiso()
        self.entrar(self.funcionario)
        self.client.post(reverse("compromiso_detalle", args=[compromiso.pk]), {"observacion": "Se coordina con aseo."})
        compromiso.refresh_from_db()
        self.assertEqual(compromiso.estado, Compromiso.PENDIENTE)
        cambio = CambioEstado.objects.get()
        self.assertEqual(
            (cambio.estado_anterior, cambio.estado_nuevo, cambio.autor, cambio.observacion),
            (Compromiso.INGRESADO, Compromiso.PENDIENTE, self.funcionario, "Se coordina con aseo."),
        )
        self.assertIsNotNone(cambio.fecha)

    def test_cp23_transicion_no_permitida(self):
        """CP-23 CU-11: no se puede saltar de Ingresado a Realizado."""
        compromiso = self.crear_compromiso()
        with self.assertRaises(ValidationError):
            compromiso.cambiar_estado(self.funcionario, Compromiso.REALIZADO, "salto")
        self.assertEqual(CambioEstado.objects.count(), 0)

    def test_cp24_cambio_sin_observacion_se_rechaza(self):
        """CP-24 CU-11: la observación es obligatoria."""
        compromiso = self.crear_compromiso()
        self.entrar(self.funcionario)
        self.client.post(reverse("compromiso_detalle", args=[compromiso.pk]), {"observacion": ""})
        compromiso.refresh_from_db()
        self.assertEqual(compromiso.estado, Compromiso.INGRESADO)

    def test_cp25_compromiso_vencido_se_destaca(self):
        """CP-25 RF-019: compromiso vencido no realizado aparece destacado."""
        self.crear_compromiso(fecha=self.hoy - timedelta(days=2))
        self.entrar(self.funcionario)
        self.assertContains(self.client.get(reverse("compromisos")), "Vencido")

    def test_cp26_compromiso_realizado_no_figura_vencido(self):
        """CP-26 RF-019: un compromiso realizado no se marca vencido."""
        compromiso = self.crear_compromiso(fecha=self.hoy - timedelta(days=2), estado=Compromiso.REALIZADO)
        self.assertFalse(compromiso.vencido)

    def test_cp27_colega_no_responsable_no_cambia_estado(self):
        """CP-27 CU-11: quien no es responsable ni coordinador no cambia el estado."""
        compromiso = self.crear_compromiso()
        self.entrar(self.colega)
        r = self.client.post(reverse("compromiso_detalle", args=[compromiso.pk]), {"observacion": "intento"})
        self.assertEqual(r.status_code, 403)

    def test_cp28_coordinador_cambia_estado_en_su_delegacion(self):
        """CP-28 CU-11: el coordinador puede cambiar estados de su delegación."""
        compromiso = self.crear_compromiso()
        self.entrar(self.coordinador)
        self.client.post(reverse("compromiso_detalle", args=[compromiso.pk]), {"observacion": "Priorizado."})
        compromiso.refresh_from_db()
        self.assertEqual(compromiso.estado, Compromiso.PENDIENTE)


# ---------------------------------------------------------------------------
# Integración: actividad → evidencia → verificación → avance → compromiso
# ---------------------------------------------------------------------------

class FlujoCompletoTests(BaseSprint):

    def test_cp29_flujo_completo_entre_modulos(self):
        """CP-29 Integración: registro, evidencia, aprobación, avance y compromiso derivado."""
        self.entrar(self.funcionario)
        self.client.post(reverse("actividad_nueva"), self.datos_actividad(cantidad=2))
        actividad = Actividad.objects.get()
        self.client.post(reverse("evidencia_subir", args=[actividad.pk]), {"archivo": imagen()})
        self.client.post(reverse("compromiso_nuevo"), {
            "actividad": actividad.pk, "solicitante": "Club deportivo", "territorio": "Sector 1",
            "responsable": self.funcionario.pk,
            "fecha_comprometida": (self.hoy + timedelta(days=3)).isoformat(),
            "descripcion": "Gestionar préstamo de sede.",
        })
        self.assertEqual(Compromiso.objects.get().actividad, actividad)

        self.entrar(self.verificador)
        evidencia = Evidencia.objects.get()
        self.client.post(reverse("verificacion_decidir", args=[evidencia.pk]), {"decision": Evidencia.APROBADA})

        self.entrar(self.funcionario)
        r = self.client.get(reverse("inicio"))
        self.assertEqual(r.context["avance"], 2)
