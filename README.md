# SGR · Sistema de Gestión de Resultados

Prototipo del sistema de registro y medición de actividades para las
delegaciones municipales de La Serena. Corresponde a la Etapa 3 (Sprint 2 ·
Prototipo y pruebas) del proyecto de Ingeniería de Software.

**Equipo:** Alejandra Campusano · Polette Henríquez · Mauro Valdivia
**Docente:** Francisco Caiceo León · INACAP La Serena · 2026

---

## Alcance del Sprint

| Historia (informe) | Funcionalidad | Casos de uso |
|---|---|---|
| HU-01 | Registrar y consultar actividades, con código único | CU-01, CU-05, CU-06, CU-08, CU-10 |
| HU-02 | Agenda de compromisos con estados e historial | CU-02, CU-11 |
| HU-05 | Evidencia fotográfica y validación por verificador | — |
| Transversal | Login, roles y ámbito por delegación, bitácora de auditoría | CU-07 |

Quedan para sprints siguientes: atenciones sociales (HU-03), configuración de
funciones por cargo (HU-04), semáforo de cumplimiento y doble factor (MFA).

---

## Ejecutar en Windows

Requisitos: **Python 3.11 o superior** y **Git**. PostgreSQL es opcional (ver más abajo).

```powershell
git clone https://github.com/Mauv8/SGR-Ing-Software.git
cd SGR-Ing-Software
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

python manage.py migrate
python manage.py cargar_datos_demo
python manage.py runserver
```

Abrir `http://127.0.0.1:8000/`.

### Usuarios de prueba

Clave de todos: `Sgr.Demo.2026` (sólo desarrollo). Los datos son ficticios.

| Usuario | Rol | Delegación |
|---|---|---|
| `jlopez` | Funcionario (Territorial OO.CC.) | Rural |
| `psoto` | Funcionario (Área Social) | Rural |
| `rmunoz` | Funcionario (Territorial OO.CC.) | Costera |
| `ccarrasco` | Coordinador | Rural |
| `mvega` | Verificador | Rural |
| `avera` | Administrador (panel `/admin/`) | — |

**Cuentas del equipo** (misma clave). Cada integrante tiene una cuenta por rol
para poder recorrer el flujo completo: registrar, validar y auditar.

| Integrante | Funcionario | Verificador | Administrador |
|---|---|---|---|
| Alejandra Campusano | `acampusano` | `acampusano.ver` | `acampusano.adm` |
| Polette Henríquez | `phenriquez` | `phenriquez.ver` | `phenriquez.adm` |
| Mauro Valdivia | `mvaldivia` | `mvaldivia.ver` | `mvaldivia.adm` |

Las cuentas de funcionario y verificador pertenecen a la Delegación Rural. Un
verificador no puede aprobar evidencias que él mismo subió, por eso son
cuentas distintas.

### Con PostgreSQL (base de datos del proyecto)

1. Instalar PostgreSQL 16 y crear la base:
   ```powershell
   psql -U postgres -c "CREATE USER sgr WITH PASSWORD 'una-clave-local' CREATEDB;"
   psql -U postgres -c "CREATE DATABASE sgr OWNER sgr;"
   ```
2. Antes de `migrate`, definir las variables en la misma terminal:
   ```powershell
   $env:POSTGRES_DB="sgr"; $env:POSTGRES_USER="sgr"; $env:POSTGRES_PASSWORD="una-clave-local"
   ```

Sin `POSTGRES_DB` el proyecto usa SQLite, para poder probarlo sin instalar nada más.

---

## Pruebas

```powershell
python manage.py test gestion -v 2      # 74 pruebas: unitarias, integración, seguridad, usabilidad
python manage.py check --deploy         # configuración de seguridad (con DJANGO_DEBUG=False)
pip install bandit pip-audit
bandit -r gestion config -x gestion/tests,gestion/migrations
pip-audit -r requirements.txt
```

Cada prueba indica su caso del plan (CP-01…CP-32, CP-S01…CP-S21). La prueba de
concurrencia CP-32 sólo corre sobre PostgreSQL. Las salidas de cada iteración
están en `docs/evidencias-pruebas/` y las capturas en `docs/capturas/`.

| Iteración | Resultado | Qué cambió |
|---|---|---|
| 1 | 63/69 aprobadas · pip-audit: 8 vulnerabilidades | Primera ejecución del plan |
| 2 | 69/69 · pip-audit y bandit sin hallazgos | D-01 a D-06 (seguridad) |
| 3 | 72/72 en PostgreSQL | U-01, U-02 (usabilidad), concurrencia |
| 4 | 74/74 en SQLite y PostgreSQL | D-07 (permisos del rol Administrador) |

---

## Seguridad aplicada

| Control | Dónde |
|---|---|
| Ámbito por rol y delegación en toda consulta | `del_ambito_de()` en `gestion/models.py` |
| Bitácora de sólo inserción (ingresos, fallos, cambios) | `RegistroAuditoria` |
| Bloqueo 15 min tras 5 intentos fallidos | `gestion/seguridad.py` |
| Evidencias: JPG/PNG, firma binaria, 5 MB, nombre aleatorio, descarga con permiso | `forms.py`, `views.evidencia_archivo` |
| CSRF, cookies HttpOnly, sesión de 2 horas | `config/settings.py` |
| CSP, X-Frame-Options, nosniff, Referrer-Policy; HTTPS y HSTS en producción | `config/settings.py`, `seguridad.py` |
| Secretos fuera del código (`.env`, no versionado) | `.env.example` |

---

## Despliegue en AWS EC2

`deploy/ec2_user_data.sh` instala el SGR en una instancia Ubuntu 24.04 con
PostgreSQL, Gunicorn y Nginx (HTTPS con certificado autofirmado, porque el
prototipo no tiene dominio). Se entrega como *user data* al lanzar la
instancia y deja el registro en `/var/log/sgr-instalacion.log`.

---

## Estructura

```
config/            configuración y rutas
gestion/
  models.py          entidades y reglas de negocio
  forms.py           formularios (filtran opciones por usuario)
  views.py           pantallas del sprint
  seguridad.py       bloqueo, auditoría de accesos, CSP, firma de imágenes
  tests/             plan de pruebas automatizado
templates/         pantallas (HTML)
static/css/        estilos adaptables a PC, tablet y celular
deploy/            instalación en EC2
docs/              evidencias de pruebas y capturas
```
