"""
Controles de seguridad transversales del SGR.

- Bitácora de inicios y cierres de sesión (Ley 21.459: trazabilidad de accesos).
- Bloqueo temporal tras intentos fallidos (OWASP A07, fuerza bruta).
- Cabecera Content-Security-Policy (OWASP A05).
- Comprobación del contenido real de las imágenes (OWASP A04).
"""

from datetime import timedelta

from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.core.exceptions import ValidationError
from django.dispatch import receiver
from django.utils import timezone

from .models import RegistroAuditoria

INTENTOS_MAXIMOS = 5
MINUTOS_BLOQUEO = 15


# --- Bitácora de accesos ---------------------------------------------------

@receiver(user_logged_in)
def auditar_ingreso(sender, request, user, **kwargs):
    RegistroAuditoria.registrar(request, "LOGIN_OK", usuario=user.username)


@receiver(user_logged_out)
def auditar_salida(sender, request, user, **kwargs):
    if user is not None:
        RegistroAuditoria.registrar(request, "LOGOUT", usuario=user.username)


@receiver(user_login_failed)
def auditar_fallo(sender, credentials, request=None, **kwargs):
    # Nunca se guarda la contraseña intentada, sólo el usuario.
    RegistroAuditoria.registrar(
        request, "LOGIN_FALLIDO", usuario=str(credentials.get("username", ""))[:150],
    )


# --- Bloqueo por intentos fallidos -----------------------------------------

def esta_bloqueado(username):
    """Cuenta los fallos de los últimos 15 minutos posteriores al último ingreso."""
    desde = timezone.now() - timedelta(minutes=MINUTOS_BLOQUEO)
    ultimo_ok = (
        RegistroAuditoria.objects.filter(usuario=username, accion="LOGIN_OK", fecha__gte=desde)
        .values_list("fecha", flat=True).first()
    )
    if ultimo_ok:
        desde = ultimo_ok
    fallos = RegistroAuditoria.objects.filter(
        usuario=username, accion="LOGIN_FALLIDO", fecha__gte=desde,
    ).count()
    return fallos >= INTENTOS_MAXIMOS


class LoginConBloqueoForm(AuthenticationForm):
    """Formulario de ingreso que rechaza cuentas bloqueadas antes de autenticar."""

    def clean(self):
        username = self.cleaned_data.get("username")
        if username and esta_bloqueado(username):
            RegistroAuditoria.registrar(self.request, "LOGIN_BLOQUEADO", usuario=username)
            raise ValidationError(
                f"Usuario bloqueado temporalmente por {INTENTOS_MAXIMOS} intentos fallidos. "
                f"Intente nuevamente en {MINUTOS_BLOQUEO} minutos o contacte al administrador.",
                code="bloqueado",
            )
        return super().clean()


# --- Cabecera Content-Security-Policy --------------------------------------

class ContentSecurityPolicyMiddleware:
    """Sólo se cargan recursos del propio sitio: frena la mayoría de los XSS."""

    POLITICA = (
        "default-src 'self'; img-src 'self'; style-src 'self' 'unsafe-inline'; "
        "script-src 'self'; frame-ancestors 'none'; form-action 'self'; base-uri 'self'"
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        respuesta = self.get_response(request)
        respuesta.setdefault("Content-Security-Policy", self.POLITICA)
        return respuesta


# --- Contenido real de las imágenes ----------------------------------------

FIRMAS = {
    "jpg": (b"\xff\xd8\xff",),
    "jpeg": (b"\xff\xd8\xff",),
    "png": (b"\x89PNG\r\n\x1a\n",),
}


def es_imagen_real(archivo, extension):
    """Compara los primeros bytes con la firma del formato declarado.

    La extensión la elige quien sube el archivo; los primeros bytes no se
    pueden falsear sin dejar de ser un ejecutable válido.
    """
    archivo.seek(0)
    cabecera = archivo.read(8)
    archivo.seek(0)
    return any(cabecera.startswith(firma) for firma in FIRMAS.get(extension, ()))
