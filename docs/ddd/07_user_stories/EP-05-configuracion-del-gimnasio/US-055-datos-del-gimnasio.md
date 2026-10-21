# US-055 · Como administrador quiero editar los datos de mi gimnasio desde la pantalla de configuración para que aparezcan correctos en el sistema sin pedirle a nadie que toque archivos

- **Épica:** EP-05 · Configuración del gimnasio
- **Bounded context:** Settings (esquema `settings`, módulo `settings`)
- **Versión:** v0.1
- **Actor:** administrador
- **Tamaño:** 3
- **Prioridad:** P1 necesaria para la versión
- **Refinamiento:** Lista para sprint
- **Pantalla:** `Config` (`/sistema/configuracion`, pestaña "Gimnasio")

## Historia

Como administrador
quiero editar el nombre, NIT, dirección y contacto de mi gimnasio en una pantalla
para que esos datos salgan bien en el sistema (y después en los recibos) sin depender de nadie

## Contexto de dominio

- **Aggregate / entidades:** `SettingsSection(key = gym)`.
- **Reglas que aplica:** esquema propio por sección, auditado (US-054); RN-15 (solo admin).
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** `settings.validate_section("gym", value)`.

## Alcance

- **Backend:** esquema Pydantic `GymSettings` registrado para `gym`.
- **Front:** pantalla `Config` con `PageHeader` y `Tabs` (una pestaña por sección habilitada en v0.1: Gimnasio, Medios de pago, Privacidad, Membresías); la pestaña Gimnasio con formulario React Hook Form + Zod y botón "Guardar" por sección.

## Criterios de aceptación

1. El esquema `gym` tiene `name` (obligatorio, 1 a 80 caracteres), `legal_id` (NIT, opcional, solo dígitos y un guion, hasta 15 caracteres), `address` (opcional, hasta 120), `city` (opcional, hasta 60), `phone` (opcional, hasta 20) y `contact_email` (opcional, correo válido).
2. Guardar con `name` vacío responde 422 con `field: "value.name"`; el front muestra el error bajo el campo "Nombre".
3. Guardar un `contact_email` mal formado responde 422 con `field: "value.contact_email"`.
4. Al guardar con éxito el front muestra "Cambios guardados", actualiza la versión local y no recarga las otras pestañas.
5. Si el API responde 409 `version_conflict`, el front muestra "Otra persona cambió esta sección. Recarga para ver los cambios." y no sobrescribe.
6. Salir de una pestaña con cambios sin guardar pide confirmación con `ConfirmModal`.
7. La entrada "Configuración" del `SideNav` y la ruta `/sistema/configuracion` solo existen para `admin`; un coach que abre la ruta ve "Sin permiso" (US-053) y el API le responde 403.
8. El cambio queda en auditoría con antes y después (lo garantiza US-054).
9. Los campos de la pantalla cumplen 44 px, foco visible y no usan colores literales.

## Escenarios BDD

```gherkin
# language: es
Característica: Datos del gimnasio

  Antecedentes:
    Dado un admin con sesión en "/sistema/configuracion"

  Escenario: Guardar los datos del box
    Cuando escribe el nombre "APEX CrossFit Bogotá" y el NIT "901234567-8"
    Y pulsa "Guardar" en la pestaña "Gimnasio"
    Entonces ve "Cambios guardados"
    Y al recargar la pantalla ve los mismos datos

  Escenario: Nombre vacío
    Cuando borra el nombre y pulsa "Guardar"
    Entonces ve el error bajo "Nombre"
    Y la sección no cambia

  Escenario: Edición simultánea
    Dado que otro admin guardó la sección "gym" después de que la abrió
    Cuando pulsa "Guardar"
    Entonces ve "Otra persona cambió esta sección"

  Escenario: El coach no ve configuración
    Dado un coach con sesión
    Cuando abre "/sistema/configuracion"
    Entonces ve "Sin permiso"
```

## Endpoints

- `GET /api/v1/settings/gym` — rol(es): admin — códigos: 200, 401, 403.
- `PATCH /api/v1/settings/gym` — rol(es): admin — entrada: `{ value: { name, legal_id?, address?, city?, phone?, contact_email? }, version }` — códigos: 200, 401, 403, 409, 422.

## Pantalla

- `Config` de `docs/design/screens/` en `/sistema/configuracion`: estructura de pestañas y pestaña "Gimnasio". Las pestañas de horas, canales, clases y TV no se muestran hasta sus versiones. Estados: cargando, guardando, error por campo, conflicto.

## Notas técnicas

- **Migración:** no (usa `settings_sections`).
- **Funciones puras a probar:** `validate_section("gym", ...)` con NIT válido e inválido.
- **Pruebas:** router (422 con `field`), front (Vitest de la pestaña con Zod y conflicto 409), E2E Playwright corto "admin guarda datos del gimnasio".
- **Archivos principales:** `api/src/app/modules/settings/schemas.py`; `web/src/features/system/pages/ConfigPage.tsx`, `web/src/features/system/components/GymSettingsForm.tsx`, `web/src/features/system/schemas.ts`.

## Supuestos

- Supuesto: los campos de `gym` (nombre, NIT, dirección, ciudad, teléfono, correo de contacto) no están definidos en los documentos; se toman del uso esperado en el recibo (EP-16) y de la pantalla `Config`.

## Dependencias

- US-054 · Secciones de configuración validadas
- US-061 · Panel layout, TopBar y SideNav
- US-064 · Encabezado, pestañas y KPI

## INVEST

- **Independiente:** solo requiere el backend de secciones y el kit.
- **Negociable:** los campos del gimnasio son ajustables.
- **Valiosa:** el dueño configura su box sin ayuda.
- **Estimable:** un esquema y una pestaña.
- **Pequeña:** dos o tres días incluyendo la estructura de pestañas.
- **Testeable:** cada validación tiene un error visible.

## Definición de listo

- [x] Criterios de aceptación verificables
- [x] Escenarios BDD con camino feliz, error y rol
- [x] Endpoints y roles definidos
- [x] Dependencias identificadas
- [x] Sin preguntas abiertas que bloqueen (o supuesto declarado)

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas de reglas puras en verde; cobertura de 80 % o más en lo tocado
- [ ] Pruebas de router: rol, validación y envelope de error
- [ ] Front: pruebas de componente y página; sin colores literales
- [ ] `docs/openapi.json` regenerado
- [ ] Auditoría verificada para `settings.settings_sections`
- [ ] Revisión de PR aprobada
