# SGR · Sistema de Gestión de Resultados

Prototipo del sistema de registro y medición de actividades para las
delegaciones municipales de La Serena. Corresponde a la Etapa 3 del proyecto de
Ingeniería de Software TI2043.

**Equipo:** Alejandra Campusano · Polette Henríquez · Mauro Valdivia
**Docente:** Francisco Caiceo León · INACAP La Serena · Primavera 2026

---

## Alcance de este sprint

El prototipo implementa la cadena mínima que permite demostrar el ciclo de
registro bajo control de acceso:

| Incluido | Caso de uso |
|---|---|
| Autenticación con usuario y contraseña | — |
| Roles con ámbito acotado por delegación | CU-07 |
| Registro de actividad con validaciones | CU-01, CU-05, CU-08 |
| Listado de actividades del ámbito del usuario | CU-06 |

Quedan fuera, y se abordan en la iteración siguiente, la evidencia fotográfica,
los compromisos de la agenda colectiva, las atenciones sociales y el semáforo de
cumplimiento. La razón es de alcance, no de valor: cada funcionalidad adicional
amplía la superficie que debe probarse y asegurarse dentro del mismo plazo.

---

## Puesta en marcha

Requiere Python 3.11 o superior.

```bash
python -m venv .venv
source .venv/bin/activate          # en Windows: .venv\Scripts\activate
pip install -r requirements.txt

python manage.py migrate
python manage.py cargar_datos_demo
python manage.py createsuperuser
python manage.py runserver
```

El panel de administración queda en `http://127.0.0.1:8000/admin/`.

### Usuarios de prueba

El comando `cargar_datos_demo` crea cinco usuarios ficticios. Todos comparten la
clave `Sgr.Demo.2026`, que es válida únicamente en desarrollo.

| Usuario | Rol | Delegación | Cargo |
|---|---|---|---|
| `jlopez` | Funcionario | Rural | Territorial OO.CC. |
| `rmunoz` | Funcionario | Costera | Territorial OO.CC. |
| `psoto` | Funcionario | Rural | Área Social |
| `ccarrasco` | Coordinador | Rural | — |
| `avera` | Administrador | — | — |

Los datos son inventados y no corresponden a funcionarios ni vecinos reales.

---

## Pruebas

```bash
python manage.py test gestion -v 2      # pruebas unitarias y de integración
python manage.py check --deploy         # revisión de configuración de seguridad
```

La salida de ambos comandos constituye evidencia del plan de pruebas.
`check --deploy` informa advertencias mientras `DJANGO_DEBUG` esté activo: ese
es el comportamiento esperado en desarrollo y se verifica en limpio al definir
las variables de producción.

---

## Decisiones de diseño

**Las reglas de negocio viven en el modelo.** Las validaciones están en
`gestion/models.py`, en los métodos `clean()`, y no en los formularios. Una
regla escrita en la pantalla sólo se cumple cuando el usuario pasa por esa
pantalla; el panel de administración o una carga masiva la saltarían sin aviso.

**El ámbito de visibilidad está centralizado.** Toda consulta de actividades
pasa por `Actividad.objects.del_ambito_de(usuario)`. Concentrarlo en un punto
evita que una vista nueva olvide el filtro y exponga datos de otra delegación.

**El código de actividad usa un correlativo con bloqueo de fila.** Dos usuarios
que guarden en el mismo instante no pueden obtener el mismo número. Es la
respuesta concreta al requisito no funcional de concurrencia.

**La configuración sensible se lee del entorno.** `DJANGO_SECRET_KEY` y
`DJANGO_DEBUG` no están en el repositorio, y el proyecto se niega a arrancar en
producción con la clave de desarrollo.

**El modelo de usuario es propio desde el inicio.** Sustituirlo después de
aplicar las migraciones es costoso, de modo que `gestion.Usuario` extiende
`AbstractUser` desde la primera migración.

---

## Estructura

```
config/          configuración del proyecto y rutas
gestion/         aplicación del dominio
  models.py        entidades y reglas de negocio
  admin.py         panel de administración
  tests.py         pruebas de las reglas
  management/      comando de carga de datos de prueba
```

---

## Base de datos

El prototipo usa SQLite por simplicidad de puesta en marcha. PostgreSQL es el
destino declarado en el diagrama de despliegue de la Etapa 2; el cambio es de
configuración y no afecta al código de la aplicación.
