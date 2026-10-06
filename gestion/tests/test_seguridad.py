"""
Pruebas de seguridad (OWASP Top 10 2021) y de cumplimiento de la Ley 21.459.

Cada prueba indica el caso del Plan de Pruebas (CP-Sxx) y la categoría OWASP
que verifica.
"""

from django.apps import apps
from django.test import Client, override_settings
from django.urls import reverse

from gestion.models import Actividad, Evidencia

from .base import CLAVE, BaseSprint, imagen


def bitacora():
    """Devuelve el modelo de auditoría o falla la prueba si no existe."""
    try:
        return apps.get_model("gestion", "RegistroAuditoria")
    except LookupError:
        raise AssertionError("No existe una bitácora de auditoría (RegistroAuditoria).")


class ControlDeAccesoTests(BaseSprint):
    """A01 · Pérdida de control de acceso."""

    def test_cps01_funcionario_no_ve_actividad_de_otra_delegacion(self):
        """CP-S01 A01: acceso directo por URL a una actividad ajena → 404."""
        ajena = self.crear_actividad(funcionario=self.otro)
        self.entrar(self.funcionario)
        self.assertEqual(self.client.get(reverse("actividad_detalle", args=[ajena.pk])).status_code, 404)

    def test_cps02_evidencia_ajena_no_se_descarga(self):
        """CP-S02 A01: descargar la evidencia de otra delegación → 403."""
        evidencia = self.crear_evidencia(self.crear_actividad(funcionario=self.otro))
        self.entrar(self.funcionario)
        self.assertEqual(self.client.get(reverse("evidencia_archivo", args=[evidencia.pk])).status_code, 403)

    def test_cps03_funcionario_no_entra_a_verificacion(self):
        """CP-S03 A01: un funcionario no accede al módulo del verificador → 403."""
        self.entrar(self.funcionario)
        self.assertEqual(self.client.get(reverse("verificacion")).status_code, 403)

    def test_cps04_verificador_no_revisa_otra_delegacion(self):
        """CP-S04 A01: verificador de Costera no revisa evidencias de Rural → 404."""
        evidencia = self.crear_evidencia(self.crear_actividad())
        self.entrar(self.verificador_costa)
        r = self.client.post(reverse("verificacion_decidir", args=[evidencia.pk]), {"decision": "APROBADA"})
        self.assertEqual(r.status_code, 404)

    def test_cps05_funcionario_no_entra_al_panel_de_administracion(self):
        """CP-S05 A01: el panel /admin/ no está disponible para un funcionario."""
        self.entrar(self.funcionario)
        r = self.client.get("/admin/")
        self.assertNotEqual(r.status_code, 200)


class InyeccionTests(BaseSprint):
    """A03 · Inyección (SQL y XSS)."""

    def test_cps06_inyeccion_sql_en_busqueda(self):
        """CP-S06 A03: «' OR '1'='1» en la búsqueda no expone otras filas."""
        self.crear_actividad(funcionario=self.otro)
        self.entrar(self.funcionario)
        r = self.client.get(reverse("actividades"), {"q": "' OR '1'='1' --"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.context["actividades"]), 0)

    def test_cps07_xss_almacenado_se_muestra_escapado(self):
        """CP-S07 A03: un <script> guardado en la descripción se muestra como texto."""
        actividad = self.crear_actividad(descripcion="<script>alert('xss')</script>")
        self.entrar(self.funcionario)
        r = self.client.get(reverse("actividad_detalle", args=[actividad.pk]))
        self.assertNotContains(r, "<script>alert('xss')</script>", html=False)
        self.assertContains(r, "&lt;script&gt;")


class CsrfYSesionTests(BaseSprint):
    """A01/A07 · CSRF y gestión de sesión."""

    def test_cps08_post_sin_token_csrf_se_rechaza(self):
        """CP-S08 CSRF: un formulario enviado sin token se rechaza (403)."""
        cliente = Client(enforce_csrf_checks=True)
        cliente.force_login(self.funcionario)
        r = cliente.post(reverse("actividad_nueva"), self.datos_actividad())
        self.assertEqual(r.status_code, 403)
        self.assertEqual(Actividad.objects.count(), 0)

    def test_cps09_cerrar_sesion_invalida_la_sesion(self):
        """CP-S09 A07: tras salir, las rutas privadas vuelven a pedir login."""
        self.entrar(self.funcionario)
        self.client.post(reverse("logout"))
        self.assertEqual(self.client.get(reverse("inicio")).status_code, 302)

    def test_cps10_cookie_de_sesion_no_accesible_desde_javascript(self):
        """CP-S10 A07: la cookie de sesión es HttpOnly."""
        r = self.client.post(reverse("login"), {"username": "jlopez", "password": CLAVE})
        self.assertTrue(r.cookies["sessionid"]["httponly"])


class AutenticacionTests(BaseSprint):
    """A07 · Fallas de identificación y autenticación (Ley 21.459, art. 2)."""

    def test_cps11_bloqueo_tras_intentos_fallidos(self):
        """CP-S11 A07: tras 5 intentos fallidos la cuenta se bloquea temporalmente."""
        for _ in range(5):
            self.client.post(reverse("login"), {"username": "jlopez", "password": "incorrecta"})
        r = self.client.post(reverse("login"), {"username": "jlopez", "password": CLAVE})
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertContains(r, "bloqueado", status_code=r.status_code)

    def test_cps12_contrasena_debil_se_rechaza(self):
        """CP-S12 A07: la política rechaza contraseñas cortas o comunes."""
        from django.contrib.auth.password_validation import validate_password
        from django.core.exceptions import ValidationError
        for debil in ["123456", "password", "sgr2026"]:
            with self.assertRaises(ValidationError):
                validate_password(debil, self.funcionario)


class CargaDeArchivosTests(BaseSprint):
    """A04/A08 · Diseño inseguro e integridad: carga de evidencias."""

    def test_cps13_ejecutable_renombrado_como_imagen_se_rechaza(self):
        """CP-S13 A04: un .exe renombrado a .jpg no se acepta como evidencia."""
        actividad = self.crear_actividad()
        self.entrar(self.funcionario)
        falso = imagen("foto.jpg", b"MZ\x90\x00" + b"\x00" * 64, "image/jpeg")
        self.client.post(reverse("evidencia_subir", args=[actividad.pk]), {"archivo": falso})
        self.assertEqual(Evidencia.objects.count(), 0)

    def test_cps14_nombre_de_archivo_con_ruta_no_se_respeta(self):
        """CP-S14 A01: «../../settings.png» se guarda con nombre aleatorio en evidencias/."""
        actividad = self.crear_actividad()
        self.entrar(self.funcionario)
        self.client.post(reverse("evidencia_subir", args=[actividad.pk]), {"archivo": imagen("../../settings.png")})
        evidencia = Evidencia.objects.get()
        self.assertTrue(evidencia.archivo.name.startswith("evidencias/"))
        self.assertNotIn("..", evidencia.archivo.name)
        self.assertNotIn("settings", evidencia.archivo.name)


class ConfiguracionTests(BaseSprint):
    """A05 · Configuración de seguridad incorrecta."""

    def test_cps15_cabeceras_de_seguridad(self):
        """CP-S15 A05: respuestas con X-Frame-Options, nosniff y Content-Security-Policy."""
        r = self.client.get(reverse("login"))
        self.assertEqual(r["X-Frame-Options"], "DENY")
        self.assertEqual(r["X-Content-Type-Options"], "nosniff")
        self.assertIn("Content-Security-Policy", r)

    @override_settings(DEBUG=False)
    def test_cps16_error_no_revela_detalles_internos(self):
        """CP-S16 A05: una ruta inexistente no muestra trazas ni configuración."""
        self.entrar(self.funcionario)
        r = self.client.get("/no-existe/")
        self.assertEqual(r.status_code, 404)
        self.assertNotContains(r, "Traceback", status_code=404)
        self.assertNotContains(r, "urlpatterns", status_code=404)


class AuditoriaTests(BaseSprint):
    """A09 · Registro y monitoreo (RNF-008, Ley 21.459: trazabilidad)."""

    def test_cps17_login_fallido_queda_en_bitacora(self):
        """CP-S17 A09: un intento de acceso fallido queda registrado."""
        Registro = bitacora()
        self.client.post(reverse("login"), {"username": "jlopez", "password": "incorrecta"})
        self.assertTrue(Registro.objects.filter(accion="LOGIN_FALLIDO").exists())

    def test_cps18_operaciones_criticas_quedan_en_bitacora(self):
        """CP-S18 A09: registro de actividad, evidencia y decisión quedan auditados."""
        Registro = bitacora()
        self.entrar(self.funcionario)
        self.client.post(reverse("actividad_nueva"), self.datos_actividad())
        actividad = Actividad.objects.get()
        self.client.post(reverse("evidencia_subir", args=[actividad.pk]), {"archivo": imagen()})
        self.entrar(self.verificador)
        self.client.post(reverse("verificacion_decidir", args=[Evidencia.objects.get().pk]), {"decision": "APROBADA"})
        acciones = set(Registro.objects.values_list("accion", flat=True))
        self.assertTrue({"ACTIVIDAD_CREADA", "EVIDENCIA_SUBIDA", "EVIDENCIA_REVISADA"} <= acciones, acciones)

    def test_cps19_bitacora_no_se_puede_modificar(self):
        """CP-S19 A09: un registro de la bitácora no se edita ni se borra."""
        Registro = bitacora()
        self.client.post(reverse("login"), {"username": "jlopez", "password": "incorrecta"})
        registro = Registro.objects.first()
        registro.detalle = "alterado"
        with self.assertRaises(Exception):
            registro.save()
        with self.assertRaises(Exception):
            registro.delete()
