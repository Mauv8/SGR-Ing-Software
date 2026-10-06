"""
CP-32 · RNF-003 Concurrencia: varios usuarios guardando al mismo tiempo.

Sólo se ejecuta sobre PostgreSQL: SQLite bloquea la base completa y no
permite comprobar el bloqueo de fila que usa el correlativo.
"""

import threading
import unittest
from datetime import date, timedelta

from django.db import connection
from django.test import TransactionTestCase

from gestion.models import Actividad, Cargo, Delegacion, ItemMedicion, Periodo, Usuario


@unittest.skipUnless(connection.vendor == "postgresql", "Requiere PostgreSQL")
class ConcurrenciaTests(TransactionTestCase):

    def test_cp32_registros_simultaneos_no_duplican_codigo(self):
        """CP-32 RNF-003: 20 registros simultáneos reciben 20 códigos distintos."""
        hoy = date.today()
        delegacion = Delegacion.objects.create(nombre="Delegación Rural")
        cargo = Cargo.objects.create(nombre="Territorial OO.CC.")
        item = ItemMedicion.objects.create(nombre="Visita", cargo=cargo)
        periodo = Periodo.objects.create(
            nombre="Vigente", fecha_inicio=hoy - timedelta(days=5), fecha_termino=hoy + timedelta(days=5),
        )
        funcionario = Usuario.objects.create_user(
            username="jlopez", password="x", rol=Usuario.FUNCIONARIO, delegacion=delegacion, cargo=cargo,
        )
        errores = []

        def registrar():
            try:
                Actividad.objects.create(
                    funcionario=funcionario, periodo=periodo, item=item, fecha=hoy,
                    descripcion="Simultánea", accion="Visita", contacto="C", telefono="+56912345678",
                )
            except Exception as error:  # se informa en la aserción final
                errores.append(error)
            finally:
                connection.close()

        hilos = [threading.Thread(target=registrar) for _ in range(20)]
        for hilo in hilos:
            hilo.start()
        for hilo in hilos:
            hilo.join()

        self.assertEqual(errores, [])
        codigos = list(Actividad.objects.values_list("codigo", flat=True))
        self.assertEqual(len(codigos), 20)
        self.assertEqual(len(set(codigos)), 20)
