"""
Carga un conjunto mínimo de datos ficticios para probar el prototipo.

Se implementa como comando y no como fixture JSON por dos razones: las
contraseñas se generan con el algoritmo de Django en lugar de quedar escritas
en el repositorio, y el comando es idempotente, de modo que puede ejecutarse
varias veces sin duplicar registros.

    python manage.py cargar_datos_demo

Los datos son inventados. No corresponden a funcionarios ni vecinos reales.
"""

from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.db import transaction

from gestion.models import Cargo, Delegacion, ItemMedicion, Periodo, Usuario

CLAVE_DEMO = "Sgr.Demo.2026"


class Command(BaseCommand):
    help = "Crea delegaciones, cargos, ítems, períodos y usuarios de prueba."

    @transaction.atomic
    def handle(self, *args, **opciones):
        hoy = date.today()

        rural, _ = Delegacion.objects.get_or_create(
            nombre="Delegación Rural",
            defaults={"territorio": "Sector norte"},
        )
        costera, _ = Delegacion.objects.get_or_create(
            nombre="Delegación Costera",
            defaults={"territorio": "Borde costero"},
        )

        territorial, _ = Cargo.objects.get_or_create(
            nombre="Territorial OO.CC.",
            defaults={"descripcion": "Trabajo territorial con organizaciones comunitarias."},
        )
        social, _ = Cargo.objects.get_or_create(
            nombre="Encargado del Área Social",
            defaults={"descripcion": "Atención social de casos."},
        )

        items = {
            territorial: [
                ("Visita a organización comunitaria", "visita"),
                ("Reunión con dirigentes", "reunión"),
                ("Catastro de necesidades", "catastro"),
            ],
            social: [
                ("Atención social presencial", "atención"),
                ("Derivación a red de apoyo", "derivación"),
            ],
        }
        for cargo, lista in items.items():
            for nombre, unidad in lista:
                ItemMedicion.objects.get_or_create(
                    cargo=cargo, nombre=nombre, defaults={"unidad": unidad},
                )

        # Un ítem desactivado, para poder comprobar que no aparece en registros
        # nuevos pero sí se conserva en los históricos.
        ItemMedicion.objects.get_or_create(
            cargo=territorial, nombre="Entrega de folletería",
            defaults={"unidad": "entrega", "activo": False},
        )

        periodo_vigente, _ = Periodo.objects.get_or_create(
            nombre=f"Período {hoy.year} · en curso",
            defaults={
                "fecha_inicio": hoy - timedelta(days=60),
                "fecha_termino": hoy + timedelta(days=30),
            },
        )
        # Un período cerrado anterior, para comprobar la regla de inmutabilidad.
        Periodo.objects.get_or_create(
            nombre=f"Período {hoy.year} · cerrado",
            defaults={
                "fecha_inicio": hoy - timedelta(days=200),
                "fecha_termino": hoy - timedelta(days=61),
                "estado": Periodo.CERRADO,
            },
        )

        personas = [
            ("jlopez", "Javiera", "López", Usuario.FUNCIONARIO, rural, territorial),
            ("rmunoz", "Rodrigo", "Muñoz", Usuario.FUNCIONARIO, costera, territorial),
            ("psoto", "Paula", "Soto", Usuario.FUNCIONARIO, rural, social),
            ("ccarrasco", "Carlos", "Carrasco", Usuario.COORDINADOR, rural, None),
            ("avera", "Andrea", "Vera", Usuario.ADMINISTRADOR, None, None),
        ]
        creados = 0
        for username, nombre, apellido, rol, delegacion, cargo in personas:
            if Usuario.objects.filter(username=username).exists():
                continue
            usuario = Usuario.objects.create_user(
                username=username,
                password=CLAVE_DEMO,
                first_name=nombre,
                last_name=apellido,
                email=f"{username}@ejemplo.cl",
                rol=rol,
                delegacion=delegacion,
                cargo=cargo,
            )
            if rol == Usuario.ADMINISTRADOR:
                usuario.is_staff = True
                usuario.save(update_fields=["is_staff"])
            creados += 1

        self.stdout.write(self.style.SUCCESS(
            f"Datos de prueba listos. Usuarios nuevos: {creados}. "
            f"Período vigente: {periodo_vigente}."
        ))
        self.stdout.write(
            f"Clave de todos los usuarios de prueba: {CLAVE_DEMO}"
        )
