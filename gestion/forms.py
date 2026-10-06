"""
Formularios del SGR.

Los formularios sólo arman la pantalla y filtran las opciones según el
usuario. Las reglas de negocio se comprueban en el modelo (`clean()`), que
el formulario llama automáticamente al validar.
"""

from django import forms
from django.core.exceptions import ValidationError

from .models import Actividad, Compromiso, Evidencia, ItemMedicion, Periodo, Usuario
from .seguridad import es_imagen_real

# Límite de tamaño de una evidencia: 5 MB.
TAMANO_MAXIMO = 5 * 1024 * 1024
EXTENSIONES_PERMITIDAS = ("jpg", "jpeg", "png")


class ActividadForm(forms.ModelForm):
    """CU-01 · Registrar actividad."""

    class Meta:
        model = Actividad
        fields = ["fecha", "item", "descripcion", "accion", "contacto", "telefono", "cantidad"]
        widgets = {
            "fecha": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "descripcion": forms.Textarea(attrs={"rows": 3, "placeholder": "Describa qué se hizo…"}),
        }

    def __init__(self, *args, usuario, **kwargs):
        super().__init__(*args, **kwargs)
        self.usuario = usuario
        # CU-06: sólo se ofrecen los ítems vigentes del cargo del funcionario.
        self.fields["item"].queryset = ItemMedicion.objects.filter(
            cargo=usuario.cargo, activo=True,
        )
        self.instance.funcionario = usuario

    def clean(self):
        datos = super().clean()
        fecha = datos.get("fecha")
        if fecha:
            # El período se deduce de la fecha: el funcionario no lo elige.
            periodo = Periodo.objects.filter(
                fecha_inicio__lte=fecha, fecha_termino__gte=fecha,
            ).first()
            if periodo is None:
                raise ValidationError({"fecha": "No existe un período de medición para esa fecha."})
            self.instance.periodo = periodo
        return datos


class EvidenciaForm(forms.ModelForm):
    """HU-05 · Adjuntar evidencia fotográfica."""

    class Meta:
        model = Evidencia
        fields = ["archivo"]
        widgets = {"archivo": forms.ClearableFileInput(attrs={"accept": ".jpg,.jpeg,.png"})}

    def clean_archivo(self):
        archivo = self.cleaned_data["archivo"]
        extension = archivo.name.rsplit(".", 1)[-1].lower() if "." in archivo.name else ""
        if extension not in EXTENSIONES_PERMITIDAS:
            raise ValidationError("Sólo se aceptan imágenes JPG o PNG.")
        if archivo.size > TAMANO_MAXIMO:
            raise ValidationError("El archivo supera el máximo de 5 MB.")
        if not es_imagen_real(archivo, extension):
            raise ValidationError("El contenido del archivo no corresponde a una imagen JPG o PNG.")
        return archivo


class DecisionForm(forms.Form):
    """HU-05 · Decisión del verificador."""

    decision = forms.ChoiceField(
        label="Decisión",
        choices=[
            (Evidencia.APROBADA, "Aprobar"),
            (Evidencia.RECHAZADA, "Rechazar"),
            (Evidencia.CORRECCION, "Solicitar corrección"),
        ],
        widget=forms.RadioSelect,
    )
    observacion = forms.CharField(
        label="Observación", required=False, max_length=500,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="Obligatoria al rechazar o solicitar corrección.",
    )


class CompromisoForm(forms.ModelForm):
    """CU-02 · Registrar compromiso."""

    class Meta:
        model = Compromiso
        fields = [
            "actividad", "solicitante", "territorio", "responsable",
            "apoyo", "fecha_comprometida", "descripcion",
        ]
        widgets = {
            "fecha_comprometida": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "descripcion": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, usuario, **kwargs):
        super().__init__(*args, **kwargs)
        # Responsables y actividades de origen se limitan al ámbito del usuario.
        self.fields["responsable"].queryset = Usuario.objects.filter(
            delegacion=usuario.delegacion, is_active=True,
        ).exclude(rol=Usuario.ADMINISTRADOR)
        self.fields["actividad"].queryset = Actividad.objects.del_ambito_de(usuario)
        self.fields["actividad"].required = False
        self.instance.delegacion = usuario.delegacion
        self.instance.creado_por = usuario


class CambioEstadoForm(forms.Form):
    """CU-11 · Cambiar estado del compromiso."""

    observacion = forms.CharField(
        label="Observación", max_length=500,
        widget=forms.Textarea(attrs={"rows": 3}),
    )
