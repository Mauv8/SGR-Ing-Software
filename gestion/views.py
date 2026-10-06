"""
Vistas del Sprint: HU-01 (actividades), HU-02 (compromisos) y HU-05
(evidencias y verificación).

Todas las vistas exigen sesión iniciada (`login_required`) y todas las
consultas pasan por `del_ambito_de(usuario)`, de modo que nadie ve datos de
otra delegación (CU-07).
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import (
    ActividadForm, CambioEstadoForm, CompromisoForm, DecisionForm, EvidenciaForm,
)
from .models import Actividad, Compromiso, Evidencia, Usuario, avance_aprobado


def exigir_rol(usuario, *roles):
    """Corta la petición con 403 si el usuario no tiene alguno de los roles."""
    if usuario.rol not in roles and not usuario.is_superuser:
        raise PermissionDenied


@login_required
def inicio(request):
    usuario = request.user
    contexto = {}
    if usuario.rol == Usuario.FUNCIONARIO:
        mias = Actividad.objects.del_ambito_de(usuario)
        contexto["total_actividades"] = mias.count()
        contexto["avance"] = avance_aprobado(mias)
    if usuario.rol == Usuario.VERIFICADOR:
        contexto["pendientes"] = evidencias_del_verificador(usuario).filter(
            estado=Evidencia.PENDIENTE,
        ).count()
    if usuario.delegacion_id or usuario.ve_toda_la_institucion:
        agenda = Compromiso.objects.del_ambito_de(usuario)
        contexto["vencidos"] = sum(1 for c in agenda if c.vencido)
    return render(request, "gestion/inicio.html", contexto)


# ---------------------------------------------------------------------------
# HU-01 · Actividades
# ---------------------------------------------------------------------------

@login_required
def actividades(request):
    """CU-06 · Consultar actividades del ámbito, con búsqueda por código."""
    visibles = Actividad.objects.del_ambito_de(request.user).select_related(
        "item", "funcionario",
    )
    buscar = request.GET.get("q", "").strip()
    if buscar:
        visibles = visibles.filter(Q(codigo__icontains=buscar) | Q(accion__icontains=buscar))
    return render(request, "gestion/actividades.html", {
        "actividades": visibles,
        "buscar": buscar,
        "avance": avance_aprobado(visibles),
    })


@login_required
def actividad_nueva(request):
    """CU-01 · Registrar actividad (sólo funcionarios)."""
    exigir_rol(request.user, Usuario.FUNCIONARIO)
    form = ActividadForm(request.POST or None, usuario=request.user)
    if request.method == "POST" and form.is_valid():
        actividad = form.save()
        messages.success(
            request,
            f"Actividad registrada con el código {actividad.codigo}. "
            "Use ese código para nombrar la fotografía de respaldo.",
        )
        return redirect("actividad_detalle", pk=actividad.pk)
    return render(request, "gestion/actividad_form.html", {"form": form})


@login_required
def actividad_detalle(request, pk):
    actividad = get_object_or_404(Actividad.objects.del_ambito_de(request.user), pk=pk)
    puede_subir = request.user.pk == actividad.funcionario_id
    return render(request, "gestion/actividad_detalle.html", {
        "actividad": actividad,
        "evidencias": actividad.evidencias.all(),
        "form": EvidenciaForm() if puede_subir else None,
    })


# ---------------------------------------------------------------------------
# HU-05 · Evidencias y verificación
# ---------------------------------------------------------------------------

@login_required
@require_POST
def evidencia_subir(request, pk):
    actividad = get_object_or_404(Actividad.objects.del_ambito_de(request.user), pk=pk)
    if request.user.pk != actividad.funcionario_id:
        raise PermissionDenied
    form = EvidenciaForm(request.POST, request.FILES)
    if form.is_valid():
        evidencia = form.save(commit=False)
        evidencia.actividad = actividad
        evidencia.subida_por = request.user
        evidencia.save()
        messages.success(request, f"Evidencia {evidencia.codigo} enviada a revisión.")
    else:
        for error in form.errors.get("archivo", []):
            messages.error(request, error)
    return redirect("actividad_detalle", pk=actividad.pk)


def evidencias_del_verificador(usuario):
    """Un verificador revisa las evidencias de su delegación."""
    qs = Evidencia.objects.select_related("actividad", "subida_por")
    if usuario.ve_toda_la_institucion:
        return qs
    return qs.filter(actividad__funcionario__delegacion=usuario.delegacion)


@login_required
def evidencia_archivo(request, pk):
    """Entrega el archivo sólo a quien puede ver la actividad (RNF-006).

    Las evidencias no se publican en una carpeta abierta: cada descarga pasa
    por esta vista, que revisa el ámbito del usuario.
    """
    evidencia = get_object_or_404(Evidencia, pk=pk)
    visible = Actividad.objects.del_ambito_de(request.user).filter(pk=evidencia.actividad_id).exists()
    if not visible and request.user.rol == Usuario.VERIFICADOR:
        visible = evidencias_del_verificador(request.user).filter(pk=pk).exists()
    if not visible:
        raise PermissionDenied
    return FileResponse(evidencia.archivo.open("rb"))


@login_required
def verificacion(request):
    exigir_rol(request.user, Usuario.VERIFICADOR)
    evidencias = evidencias_del_verificador(request.user)
    return render(request, "gestion/verificacion.html", {
        "pendientes": evidencias.filter(estado=Evidencia.PENDIENTE),
        "revisadas": evidencias.exclude(estado=Evidencia.PENDIENTE)[:20],
    })


@login_required
def verificacion_decidir(request, pk):
    exigir_rol(request.user, Usuario.VERIFICADOR)
    evidencia = get_object_or_404(evidencias_del_verificador(request.user), pk=pk)
    form = DecisionForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            evidencia.decidir(
                request.user, form.cleaned_data["decision"], form.cleaned_data["observacion"],
            )
        except ValidationError as error:
            form.add_error(None, error)
        else:
            messages.success(request, f"Evidencia {evidencia.codigo}: {evidencia.get_estado_display()}.")
            return redirect("verificacion")
    return render(request, "gestion/verificacion_decidir.html", {"evidencia": evidencia, "form": form})


# ---------------------------------------------------------------------------
# HU-02 · Compromisos
# ---------------------------------------------------------------------------

@login_required
def compromisos(request):
    agenda = Compromiso.objects.del_ambito_de(request.user).select_related("responsable")
    estado = request.GET.get("estado", "")
    if estado in dict(Compromiso.ESTADOS):
        agenda = agenda.filter(estado=estado)
    return render(request, "gestion/compromisos.html", {
        "compromisos": agenda,
        "estados": Compromiso.ESTADOS,
        "estado": estado,
    })


@login_required
def compromiso_nuevo(request):
    exigir_rol(request.user, Usuario.FUNCIONARIO, Usuario.COORDINADOR)
    form = CompromisoForm(request.POST or None, usuario=request.user)
    if request.method == "POST" and form.is_valid():
        compromiso = form.save()
        messages.success(request, f"Compromiso {compromiso} registrado como Ingresado.")
        return redirect("compromiso_detalle", pk=compromiso.pk)
    return render(request, "gestion/compromiso_form.html", {"form": form})


@login_required
def compromiso_detalle(request, pk):
    compromiso = get_object_or_404(Compromiso.objects.del_ambito_de(request.user), pk=pk)
    form = CambioEstadoForm(request.POST or None)
    puede_cambiar = compromiso.puede_cambiar_estado(request.user) and compromiso.estado_siguiente
    if request.method == "POST":
        if not puede_cambiar:
            raise PermissionDenied
        if form.is_valid():
            try:
                compromiso.cambiar_estado(
                    request.user, compromiso.estado_siguiente, form.cleaned_data["observacion"],
                )
            except ValidationError as error:
                form.add_error(None, error)
            else:
                messages.success(request, f"Estado actualizado a {compromiso.get_estado_display()}.")
                return redirect("compromiso_detalle", pk=compromiso.pk)
    return render(request, "gestion/compromiso_detalle.html", {
        "compromiso": compromiso,
        "historial": compromiso.historial.select_related("autor"),
        "form": form if puede_cambiar else None,
        "siguiente": dict(Compromiso.ESTADOS).get(compromiso.estado_siguiente),
    })
