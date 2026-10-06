SGR · Kit de componentes · referencia para el código

# Kit de Componentes SGR

Las nueve piezas del prototipo, renderizadas con **el mismo CSS que está en el proyecto**. Lo que ves aquí es exactamente lo que produce `static/css/sgr.css`: si una pantalla se ve distinta, es la plantilla la que se desvió, no el kit.

## Paleta

Siete grises. El kit no tiene color porque su trabajo es fijar la estructura; el color aparece sólo donde transporta significado, y eso ocurre en dos lugares: el semáforo y el mensaje de error.

`#FCFCFD`claro · superficies

`#F0F2F3`sutil · cabecera de tabla

`#E9ECEE`relleno de campo

`#B8C0C5`borde de campo

`#98A2A8`borde secundario

`#8E989E`texto de ayuda

`#4E5960`texto · botón primario

| Medida | Valor | Variable en el CSS |
| --- | --- | --- |
| Alto de control | 36 px | --alto-control |
| Radio de esquina | 3 px (4 en el modal) | --radio |
| Etiqueta → caja | 5 px | --sep-etiqueta |
| Entre campos | 14 px | --sep-campos |
| Entre botones | 10 px | --sep-botones |

## Las nueve piezas

01

### Campo de texto

CU-01 · CU-02 · CU-03 · CU-04

Nombre de contacto*

#### Especificación

- alto 36 · relleno `#E9ECEE` · borde 1 `#B8C0C5` · radio 3
- etiqueta 12 semibold `#4E5960`
- texto 13 · marcador de posición `#8E989E`
- separación etiqueta-caja 5 · entre campos 14

#### En la plantilla

```
<div class="campo">
  <label for="{{ campo.id_for_label }}">{{ campo.label }}</label>
  {{ campo }}
</div>
```

02

### Campo largo

CU-01 · CU-03 · CU-11

Descripción

#### Especificación

- igual al campo de texto
- alto 72 · texto alineado arriba
- interior 8 / 10

#### En la plantilla

```
"descripcion": forms.Textarea(
    attrs={"placeholder": "Describa qué se hizo…"}
)
```

03

### Desplegable

CU-01 · CU-02 · CU-03 · CU-04 · CU-06

Ítem medido*

#### Especificación

- igual al campo de texto
- chevron 12 px `#98A2A8` a la derecha
- margen interior derecho 10 (32 total)

#### Regla

- La lista se acota en el formulario, pero quien decide es el modelo: una lista corta en pantalla no detiene a quien envía la petición por otro medio.

04

### Casilla

CU-03 · CU-04

[x] Esta actividad genera un compromiso en la agenda

[ ] Mantener el ítem vigente para registros nuevos

#### Especificación

- cuadro 16 × 16 · borde 1,5 `#98A2A8` · radio 2
- fondo `#FCFCFD` · separación al texto 9
- texto 13 `#4E5960`

#### En la plantilla

```
<div class="casilla">
  {{ campo }}
  <label for="{{ campo.id_for_label }}">{{ campo.label }}</label>
</div>
```

05 · 06

### Botón primario y secundario

todas las pantallas

#### Primario

- alto 36 · relleno `#4E5960` · texto `#FCFCFD` 13 semibold
- interior horizontal 16 · radio 3 · sin borde propio

#### Secundario

- fondo `#FCFCFD` · borde 1 `#98A2A8`
- texto `#4E5960` 13 semibold · radio 3
- separación entre botones 10

#### En la plantilla

```
<div class="botonera">
  <button class="boton-primario">Guardar</button>
  <a class="boton-secundario" href="…">Cancelar</a>
</div>
```

07

### Tabla

CU-02 · CU-04 · CU-06 · CU-10

| Código | Fecha | Estado |
| --- | --- | --- |
| ACT-2026-00001 | 02/10/2026 | Validada |
| ACT-2026-00002 | 01/10/2026 | Registrada |

#### Especificación

- encabezado `#F0F2F3` · texto 10 en mayúsculas `#8E989E`
- fila alto 30 · separador 1 `#B8C0C5` · celda 12
- códigos en monoespaciada

#### Regla

- Va dentro de `.tabla-contenedor`, que la desplaza de lado en pantallas angostas en vez de desplazar la página entera.

08

### Modal

CU-02 · CU-09 · CU-11

## Cambiar estado del compromiso

El estado pasará de «En proceso» a «Realizado» y quedará registrado con su nombre y la fecha.

#### Especificación

- ancho 400 · borde 1 `#98A2A8` · radio 4 · interior 16
- título 14 bold · texto 12,5
- botones a la derecha

#### Pendiente

- Con plantillas de Django, abrirlo sin recargar la página requiere una porción de JavaScript propio. Llega con CU-11, fuera del alcance de este sprint.

09

### Mensaje de validación

CU-05 · CU-08 · CU-09

Teléfono* Entre 8 y 15 dígitos. Se admite el prefijo «+».

- Ingrese entre 8 y 15 dígitos; se admite el prefijo «+».

#### Especificación

- barra izquierda 3 · interior 6 / 10 · texto 11
- radio `0 3 3 0` · pegado bajo el campo, separación 5
- el borde del campo también se marca

#### Desviación declarada

- El kit lo definía en gris. Aquí es rojo: un error que no se distingue de un texto informativo deja de cumplir su función.

## Semáforo

No es parte de las nueve piezas: es el único lugar donde el color transporta significado por sí solo, según la regla RN-008. Por eso cada estado lleva además su palabra — un indicador que sólo se distingue por el color excluye a quien no diferencia rojo de verde.

Al día En riesgo Atrasado

#### Colores

- verde `#1B7A47` sobre `#E4F0E9`
- ámbar `#C07708` sobre `#F8EFDE`
- rojo `#B23A2B` sobre `#F6E7E4`

#### En la plantilla

```
<span class="semaforo {{ actividad.color }}">
  {{ actividad.get_estado_display }}
</span>
```

Regla al escribir una plantilla nueva

Si una pantalla necesita algo que no está en estas nueve piezas, la decisión correcta es **agregarlo al kit y a esta página**, no resolverlo con estilos sueltos en esa plantilla. En el momento en que dos pantallas resuelven lo mismo de dos maneras, el kit deja de servir para lo que existe.

Ninguna plantilla debería traer atributos `style=` propios. Si aparece uno, es señal de que falta una pieza.

Esta página reproduce `static/css/sgr.css` del repositorio. Al cambiar el kit en el proyecto, hay que actualizarla también: una referencia desactualizada es peor que no tenerla.
---

## Aplicación en el Sprint 2 (6 de octubre de 2026)

`static/css/sgr.css` se reescribió desde este kit: variables `--alto-control`,
`--radio`, `--sep-etiqueta`, `--sep-campos` y `--sep-botones`, y las clases
`.campo`, `.casilla`, `.botonera`, `.boton-primario`, `.boton-secundario`,
`.tabla-contenedor`, `.modal`, `.mensaje-validacion` y `.semaforo`.
Las pruebas CP-33 (ninguna plantilla con `style=`) y CP-34 (el formulario de
registro usa las piezas del kit) protegen la regla de esta página.

### Desviaciones declaradas

| ID | Pieza | Kit | Proyecto | Motivo |
|---|---|---|---|---|
| D-K1 | Texto de ayuda, encabezado de tabla, marcador | `#8E989E` | `#667077` | `#8E989E` da 2,87:1 sobre `#FCFCFD` y 2,62:1 sobre `#F0F2F3`; WCAG AA exige 4,5:1. `#667077` da 4,94:1 y 4,51:1. |
| D-K2 | 07 · Tabla en pantallas angostas | Desplazamiento lateral en `.tabla-contenedor` | Filas apiladas como fichas (`table.apilable`) | El desplazamiento ocultaba la columna Estado (deficiencia U-02, prueba CP-31). |
| D-K3 | 09 · Mensaje de validación | Gris | Rojo `#B23A2B` sobre `#F6E7E4` | Ya declarada en el kit. |
| D-K4 | 03 · Chevron del desplegable | — | Archivo `static/img/chevron.svg` | La política CSP del sitio no admite imágenes `data:`. |
| D-K5 | Etiqueta «Vencido» | — | Rojo sólido con texto claro (5,80:1) | Va sobre una fila ya teñida de rojo; con el color del semáforo no se distinguía. |

### Pendiente

- Semáforo ámbar: `#C07708` sobre `#F8EFDE` da 3,13:1, bajo el mínimo de
  4,5:1 para texto. El semáforo no forma parte de este sprint; al
  implementarlo se debe oscurecer el texto ámbar.
- Modal (pieza 08): se presenta en la misma página, sin JavaScript, como
  indica el propio kit para este sprint.
