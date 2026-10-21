# APEX — Guía de diseño del front

Esta carpeta es la fuente de verdad del front. Antes de crear o cambiar cualquier pantalla o componente, leer este archivo y abrir el HTML de la pantalla en `screens/`.

## Qué hay en esta carpeta

- `DESIGN.md` — esta guía: colores, tipografía, componentes y patrones.
- `ROUTES.md` — mapa de rutas de React Router, qué pantalla va en cada ruta, qué rol la ve y qué datos necesita.
- `SCREENS-INDEX.md` — índice de las 37 pantallas con su archivo.
- `screens/<Clave>.html` y `screens/<Clave>.dark.html` — cada pantalla como HTML estático, en claro y oscuro. Es la referencia visual: estructura, textos, estados y acciones. Los enlaces entre archivos funcionan en el navegador.
- `prototipo.html` — las 37 pantallas en una sola página navegable con interruptor de tema.
- `tokens.css` — variables CSS listas para importar. `tokens.json` — las mismas en JSON.
- `assets/logo/` — logo en tres versiones.

## Reglas que no se negocian

1. Todo color sale de `tokens.css`. Nunca un hex literal en un componente.
2. Toda lista tiene búsqueda, filtros, orden y paginación desde el servidor. Nunca se cargan todos los registros. Funciona igual con 10 socios que con 1.000.
3. Crear y editar usan el mismo formulario. Dar de baja, anular y congelar son modales con confirmación; anular pide motivo.
4. Un pago nunca se edita: se anula con motivo y se crea otro.
5. Cada ficha tiene una pestaña Historial que muestra la auditoría de ese registro.
6. Datos cifrados (documento, teléfono, correo, fecha de nacimiento, medidas) se muestran enmascarados; "Mostrar" los descifra y eso queda registrado.
7. Pesos colombianos sin decimales con separador de miles: `$ 120.000`. Fechas en español corto: `20 oct 2026`. Hora de Bogotá.
8. Español de Colombia en toda la interfaz. Tuteo con el socio, tono directo con el equipo.
9. Botones y campos: mínimo 44 px de alto en el panel, 56 px en check-in y registro de resultados.
10. Accesibilidad: botones reales (`<button>`, `<a href>`), `label` en cada campo, foco visible (borde azul), contraste 4,5:1 en texto. El color nunca lleva solo el significado: todo estado tiene texto.

## Color

Tres colores de marca y grises de apoyo.

- `--apex-blue` #009FE3: el azul del logo. Botón principal, estado "al día", barra de progreso, pestaña activa, selección. Sobre blanco no sirve para texto pequeño (2,9:1): por eso el botón principal lleva texto negro, y los enlaces usan `--blue-deep`.
- `--black` #0E0E0E: barra superior, ítem activo del menú, pantalla TV, texto principal en claro.
- `--white`: tarjetas y tablas en claro.
- `--blue-deep`: enlaces, texto azul, hover del botón principal (ahí sí con texto blanco).
- `--blue-tint`: fondo de la tarjeta o fila que pide atención.
- `--surface`, `--card`, `--line`, `--muted`: grises de trabajo. Cambian con el tema.
- `--danger`: solo anular, dar de baja y estado "vencido". `--warning`: estado "por vencer" y avisos pendientes.

Estados de membresía:
- Al día: relleno `--apex-blue`, texto `--black`.
- Por vencer: borde `--warning`, texto `--warning`.
- Vencido / Sin plan: relleno `--danger`, texto blanco.
- Congelado / Inactivo: borde `--line`, texto `--muted`.

## Temas

- Panel de administración: claro por defecto, oscuro si el usuario lo elige (preferencia guardada).
- Check-in, registro de resultados y TV: oscuro por defecto (`<html data-theme="dark">` en esas rutas).
- Portal del socio: sigue el tema del teléfono (`prefers-color-scheme`).
- En oscuro: el ítem activo del menú y las selecciones pasan a fondo claro con texto negro; el botón principal no cambia (azul con texto negro); el logo cambia a la versión de wordmark blanco.

## Tipografía

- `--font-display` Michroma: nombre APEX, títulos de pantalla (`.w-h1`), títulos de grupo del menú, TV. Siempre mayúsculas, frases cortas. Nunca en párrafos, tablas ni botones.
- `--font-ui` Titillium Web: todo lo demás. Pesos 400, 600, 700.
- Cifras en columnas o KPIs: `font-variant-numeric: tabular-nums`.
- Se cargan desde Google Fonts (ya en `tokens.css`). Si el box no tiene internet estable, descargar las dos familias a `public/fonts/` y cambiar el `@import` por `@font-face`.

## Logo

- `apex-logo-dark-bg.png`: wordmark blanco. Barra superior del panel, TV, portal en oscuro.
- `apex-logo-light-bg.png`: wordmark negro. Login, recibos, correos, portal en claro.
- `apex-mark.png`: solo isotipo. Icono de la PWA (`manifest.json`), favicon, avatar vacío.
- No recolorear el isotipo. No ponerlo sobre azul. Margen libre igual a la altura del isotipo.

## Estructura de la app

Tres zonas con layout propio:

1. **Acceso** (`Login.html`): tarjeta centrada sobre `--surface`.
2. **Panel** (admin y coach): barra superior negra con logo + menú lateral de 232 px + área principal con padding 24 px. En celular el menú se pliega en un botón ☰ y se vuelve un cajón. Ver `Inicio.html`.
3. **Portal del socio**: una columna, máximo 600 px centrada en escritorio, menú inferior de 5 pestañas (Inicio, Pagos, WODs, Progreso, Yo). Ver `Portal_Inicio.html`.

Aparte: **TV** (`TV.html`, 1920×1080, sin interacción, se abre con token) y las pantallas de **gimnasio** (`CheckIn.html`, `Resultados_Registro.html`), pensadas para tablet 1024×768 en horizontal.

## Componentes y patrones

Los nombres de clase de los HTML (`w-btn`, `w-tag`, `w-tbl`…) son solo de referencia. En React cada uno es un componente en `src/shared/ui/`:

- **TopBar**: fondo negro, logo, nombre del gimnasio, fecha y hora de Bogotá, usuario y rol, Salir.
- **SideNav**: grupos (Inicio · Hoy · Gestión · Entrenamiento · Avisos · Sistema). Sistema solo para admin. Ítem activo: fondo negro, texto blanco.
- **PageHeader**: título en Michroma + total a la derecha del título + acciones a la derecha. Breadcrumb encima cuando es una ficha o un formulario.
- **Button**: `primary` (azul, texto negro), `secondary` (borde negro), `danger` (borde y texto rojo), tamaño `gym` (56 px, 18 px). Siempre `<button>` o `<a>`.
- **StatusTag**: píldora con los estados de arriba.
- **FilterBar**: buscador (flex 2) + selects (flex 1) + ordenar. En celular se apila; en el portal se pliega en "Filtros ▾".
- **DataTable**: dentro de una caja con `overflow-x: auto`; cabecera en mayúsculas `--muted`; primera columna siempre enlace a la ficha; sin botones de editar o borrar en las filas. En celular se convierte en lista de tarjetas (ver `Socios_Movil.html`).
- **Pagination**: tamaño de página (25/50/100), "1–25 de 342", anterior/siguiente.
- **Chips** de filtro rápido por estado, con conteo (`Al día 210`). Activo: fondo negro.
- **Tabs**: línea inferior azul en la activa. En fichas, la última siempre es Historial.
- **KpiCard**: etiqueta `--muted`, cifra `--text-kpi`, nota. La que pide atención lleva fondo `--blue-tint` y borde azul.
- **SidePanel**: formulario corto sobre la lista (planes, movimientos, usuarios, reglas). Cierra con ✕ y Cancelar.
- **ConfirmModal**: pregunta clara en el título, consecuencia en una frase, campo Motivo cuando aplica, botones Volver y la acción en `danger`.
- **Field**: label arriba, control de 44 px, error debajo en `--danger`; si es un duplicado, el error enlaza al registro existente.
- **MaskedValue**: valor enmascarado (`CC •••• 4417`) + enlace Mostrar.
- **HistoryAside**: historial reciente del registro, a la derecha en escritorio, al final en celular.

## Las pantallas de gimnasio

`CheckIn.html` y `Resultados_Registro.html` tienen reglas propias: oscuro por defecto, botones de 56 px, buscador de 20 px, una sola tarea por pantalla, lista de "ya llegaron" o "ya registrados" siempre visible, botón "Guardar y siguiente" que avanza solo. Nunca se bloquea el check-in: un socio vencido entra y queda marcado en rojo.

## Qué NO hacer

- No usar librerías de componentes con su propio estilo (MUI, Ant). Tailwind o CSS modules sobre `tokens.css` está bien.
- No degradados, no sombras fuertes, no emojis como iconos. Iconos: Lucide (ISC) en 20 px.
- No scroll horizontal de página: solo las tablas se desplazan dentro de su caja.
- No "cargar todo": cada lista pide al servidor con `page`, `page_size`, `q`, filtros y `sort`.
