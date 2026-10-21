# US-058 · Como administrador quiero ajustar cuántos días antes se considera "por vencer" y los límites de congelación para que las membresías sigan las políticas de mi gimnasio

- **Épica:** EP-05 · Configuración del gimnasio
- **Bounded context:** Settings (esquema `settings`, módulo `settings`); consumido por Memberships
- **Versión:** v0.1
- **Actor:** administrador
- **Tamaño:** 2
- **Prioridad:** P1 necesaria para la versión
- **Refinamiento:** Lista para sprint
- **Pantalla:** `Config` (`/sistema/configuracion`, pestaña "Membresías")

## Historia

Como administrador
quiero definir el umbral de "por vencer" y los límites de congelación de las membresías
para que el sistema aplique las políticas de mi gimnasio sin cambiar el código

## Contexto de dominio

- **Aggregate / entidades:** `SettingsSection(key = memberships)`.
- **Reglas que aplica:** Q11 (`expiring_days`, por defecto 7; RN-06 corregida: "por vencer si faltan `expiring_days` días o menos"); Q9 (`max_freeze_days_per_membership` 30, `max_freezes_per_membership` 2, `max_retroactive_days` 7); `apply_freeze` recibe los límites como parámetro y sigue siendo pura; RN-15.
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** `settings.validate_section("memberships", value)`.

## Alcance

- **Backend:** esquema `MembershipsSettings`; `settings.service.memberships_policy()` que devuelve los cuatro valores (con sus valores por defecto si la sección no se guardó); `GET/PATCH /settings/memberships`.
- **Front:** pestaña "Membresías" de `Config` con cuatro campos numéricos y su explicación.

## Criterios de aceptación

1. El esquema tiene `expiring_days` (entero de 1 a 30, por defecto 7), `max_freeze_days_per_membership` (entero de 1 a 180, por defecto 30), `max_freezes_per_membership` (entero de 0 a 10, por defecto 2) y `max_retroactive_days` (entero de 0 a 30, por defecto 7).
2. Un valor decimal, negativo o fuera de rango responde 422 con `field` del campo (por ejemplo `value.expiring_days`).
3. `settings.service.memberships_policy()` devuelve los cuatro valores; si la sección nunca se guardó devuelve los valores por defecto de `DECISIONES.md`.
4. Memberships lee estos valores solo a través de `memberships_policy()` y los pasa como parámetro a `compute_status` (US-083) y `apply_freeze` (US-089); ninguna función pura lee la configuración por sí misma.
5. Cambiar `expiring_days` no reescribe estados guardados: el cambio se refleja en el siguiente cálculo (el job diario de US-094 o la siguiente consulta).
6. El cambio queda en auditoría con antes y después.
7. Un coach recibe 403 en `GET` y `PATCH`.
8. El front muestra cada campo con su explicación ("Días antes del vencimiento en que la membresía se marca Por vencer") y el valor por defecto entre paréntesis.

## Escenarios BDD

```gherkin
# language: es
Característica: Parámetros de membresías

  Antecedentes:
    Dado un admin con sesión en la pestaña "Membresías"

  Escenario: Cambiar el umbral de por vencer
    Cuando cambia "expiring_days" de 7 a 5 y guarda
    Entonces ve "Cambios guardados"
    Y una membresía que vence en 6 días se calcula como "active" en la siguiente consulta

  Escenario: Valor fuera de rango
    Cuando escribe 0 en "max_freeze_days_per_membership" y guarda
    Entonces recibe 422 con field "value.max_freeze_days_per_membership"

  Escenario: Valores por defecto sin configurar
    Dado que la sección "memberships" nunca se guardó
    Cuando Memberships pide la política
    Entonces recibe 7, 30, 2 y 7

  Escenario: El coach no cambia la política
    Dado un coach con sesión
    Cuando envía "PATCH /settings/memberships"
    Entonces recibe 403
```

## Endpoints

- `GET /api/v1/settings/memberships` — rol(es): admin — códigos: 200, 401, 403.
- `PATCH /api/v1/settings/memberships` — rol(es): admin — entrada: `{ value: { expiring_days, max_freeze_days_per_membership, max_freezes_per_membership, max_retroactive_days }, version }` — códigos: 200, 401, 403, 409, 422.

## Pantalla

- `Config`, pestaña "Membresías". `// DESIGN-GAP:` confirmar que la pestaña "Membresías" del diseño tiene estos cuatro campos.

## Notas técnicas

- **Migración:** no.
- **Funciones puras a probar:** `validate_section("memberships", ...)` en los bordes de cada rango (0, 1, máximo, máximo + 1, decimal).
- **Pruebas:** router (422, 403), service (`memberships_policy` con y sin sección guardada), front (pestaña).
- **Archivos principales:** `api/src/app/modules/settings/schemas.py`, `service.py`; `web/src/features/system/components/MembershipsSettingsForm.tsx`.

## Supuestos

- Supuesto: los rangos permitidos (1 a 30, 1 a 180, 0 a 10, 0 a 30) no están en los documentos; `DECISIONES.md` solo fija los valores por defecto.

## Dependencias

- US-055 · Datos del gimnasio (estructura de pestañas de `Config`)

## INVEST

- **Independiente:** solo expone valores; Memberships los consume después.
- **Negociable:** los rangos son ajustables.
- **Valiosa:** el gimnasio aplica su propia política sin cambiar código.
- **Estimable:** un esquema y una pestaña.
- **Pequeña:** uno o dos días.
- **Testeable:** cada borde de rango es binario.

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
