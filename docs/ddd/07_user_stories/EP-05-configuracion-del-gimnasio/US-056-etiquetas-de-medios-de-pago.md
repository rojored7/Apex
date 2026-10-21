# US-056 · Como administrador quiero ponerle nombre visible a los medios de pago para que recepción los reconozca al registrar cada pago

- **Épica:** EP-05 · Configuración del gimnasio
- **Bounded context:** Settings (esquema `settings`, módulo `settings`); consumido por Payments
- **Versión:** v0.1
- **Actor:** administrador
- **Tamaño:** 2
- **Prioridad:** P1 necesaria para la versión
- **Refinamiento:** Lista para sprint
- **Pantalla:** `Config` (`/sistema/configuracion`, pestaña "Medios de pago")

## Historia

Como administrador
quiero definir la etiqueta y la ayuda que se muestra para efectivo, Nequi y Bre-B
para que recepción elija el medio correcto y sepa qué referencia pedir al registrar un pago

## Contexto de dominio

- **Aggregate / entidades:** `SettingsSection(key = payment_methods)`.
- **Reglas que aplica:** S8 (medios de pago son un enum fijo en v0.1: `cash`, `nequi`, `breb`; uno nuevo exige migración); `settings.service.payment_methods()` devuelve el enum decorado con las etiquetas (`05_service_design.md` 3).
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** `settings.validate_section("payment_methods", value)`; `settings.decorate_methods(enum, labels) -> list[MethodOut]`.

## Alcance

- **Backend:** esquema `PaymentMethodsSettings`; `settings.service.payment_methods()` para Payments; `GET /settings/payment_methods` y `PATCH /settings/payment_methods`.
- **Front:** pestaña "Medios de pago" de `Config` con una fila por medio fijo (no se pueden agregar ni quitar): etiqueta y texto de ayuda.

## Criterios de aceptación

1. El esquema tiene exactamente las claves `cash`, `nequi` y `breb`, cada una con `label` (obligatoria, 1 a 30 caracteres) y `hint` (opcional, hasta 120 caracteres); los valores por defecto son "Efectivo", "Nequi" y "Bre-B".
2. Enviar una clave distinta de las tres (por ejemplo `tarjeta`) responde 422 con `field: "value.tarjeta"`; el enum de `payments.method` no cambia.
3. Una `label` vacía responde 422 con `field` del medio correspondiente.
4. `settings.service.payment_methods()` devuelve `[{ code: "cash", label, hint }, { code: "nequi", ... }, { code: "breb", ... }]` en ese orden y es lo que usa el `SidePanel` de registrar pago (US-095).
5. Cambiar una etiqueta no modifica ningún pago ya registrado: los pagos guardan el `code`, no la etiqueta.
6. El cambio queda en auditoría con antes y después.
7. Un coach recibe 403 en `PATCH`; la lectura de etiquetas para registrar pagos le llega por el endpoint de pagos, no por `/settings`.
8. El front no ofrece botón de agregar ni eliminar medios y muestra la nota "Para agregar un medio nuevo se requiere una actualización del sistema".

## Escenarios BDD

```gherkin
# language: es
Característica: Etiquetas de medios de pago

  Antecedentes:
    Dado un admin con sesión en la pestaña "Medios de pago"

  Escenario: Cambiar la ayuda de Nequi
    Cuando escribe la ayuda "Pide los últimos 4 dígitos del comprobante" para "Nequi"
    Y pulsa "Guardar"
    Entonces ve "Cambios guardados"
    Y el panel de registrar pago muestra esa ayuda al elegir Nequi

  Escenario: Intentar agregar un medio
    Cuando se envía "PATCH /settings/payment_methods" con la clave "tarjeta"
    Entonces recibe 422 con field "value.tarjeta"

  Escenario: Etiqueta vacía
    Cuando borra la etiqueta de "Efectivo" y guarda
    Entonces ve el error bajo la etiqueta de "Efectivo"

  Escenario: El coach no edita medios de pago
    Dado un coach con sesión
    Cuando envía "PATCH /settings/payment_methods"
    Entonces recibe 403
```

## Endpoints

- `GET /api/v1/settings/payment_methods` — rol(es): admin — códigos: 200, 401, 403.
- `PATCH /api/v1/settings/payment_methods` — rol(es): admin — entrada: `{ value: { cash: { label, hint? }, nequi: {...}, breb: {...} }, version }` — códigos: 200, 401, 403, 409, 422.

## Pantalla

- `Config`, pestaña "Medios de pago": tres filas fijas con etiqueta y ayuda.

## Notas técnicas

- **Migración:** no.
- **Funciones puras a probar:** `decorate_methods` con etiquetas por defecto y personalizadas; `validate_section` con clave extra.
- **Pruebas:** router (422, 403), service (Payments recibe las etiquetas), front (pestaña sin botones de agregar).
- **Archivos principales:** `api/src/app/modules/settings/schemas.py`, `service.py`; `web/src/features/system/components/PaymentMethodsForm.tsx`.

## Supuestos

- Supuesto: además de la etiqueta, cada medio tiene un texto de ayuda (`hint`) para recepción; los documentos solo hablan de "etiquetas".

## Dependencias

- US-055 · Datos del gimnasio (estructura de pestañas de `Config`)

## INVEST

- **Independiente:** solo requiere la pantalla de configuración.
- **Negociable:** el texto de ayuda es opcional.
- **Valiosa:** menos errores al elegir el medio de pago.
- **Estimable:** un esquema y una pestaña.
- **Pequeña:** uno o dos días.
- **Testeable:** el enum fijo se prueba con una clave extra.

## Definición de listo

- [x] Criterios de aceptación verificables
- [x] Escenarios BDD con camino feliz, error y rol
- [x] Endpoints y roles definidos
- [x] Dependencias identificadas
- [x] Sin preguntas abiertas que bloqueen (o supuesto declarado)

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas de reglas puras y de service con PostgreSQL real en verde; cobertura de 80 % o más en lo tocado
- [ ] Pruebas de router: rol, validación y envelope de error
- [ ] Front: pruebas de componente; sin colores literales
- [ ] `docs/openapi.json` regenerado
- [ ] Auditoría verificada para `settings.settings_sections`
- [ ] Revisión de PR aprobada
