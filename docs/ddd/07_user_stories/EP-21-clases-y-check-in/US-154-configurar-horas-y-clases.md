# US-154 · Como administrador quiero configurar las horas de atención y los valores por defecto de las clases para que el horario y el check-in usen las reglas de mi gimnasio

- **Épica:** EP-21 · Clases, horario y check-in
- **Bounded context:** Settings (esquema `settings`), consumido por Classes
- **Versión:** v0.4
- **Actor:** administrador
- **Tamaño:** 2
- **Prioridad:** P0 ruta crítica de la versión
- **Refinamiento:** Criterios completos; BDD solo de flujo principal
- **Pantalla:** `Config` (`/sistema/configuracion`, pestañas Horas y Clases)

## Historia

Como administrador
quiero definir las horas de atención y el cupo por defecto, la ventana de check-in y si se permite superar el cupo
para que las franjas y el check-in sigan las reglas de mi box sin tocar código

## Contexto de dominio

- **Aggregate / entidades:** `SettingsSection` claves `hours` y `classes`.
- **Reglas que aplica:** Q11 (`classes`: `default_capacity` por defecto 15, `checkin_window_min` por defecto 30; N-38/N-39 elimina `allow_over_capacity`); `settings.validate_section` pura; cada cambio auditado; RN-15 (solo admin).
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** `settings.validate_section("hours", value)`, `settings.validate_section("classes", value)`

## Alcance

- **Backend:** esquemas Pydantic `HoursSection` y `ClassesSection`; valores por defecto sembrados al migrar; `settings.service.classes()` para que `classes.service` lea los valores.
- **Front:** pestañas Horas (siete días con apertura y cierre o cerrado) y Clases (tres campos) en `Config`.

## Criterios de aceptación

1. `GET /api/v1/settings/classes` sin configuración previa devuelve `{ default_capacity: 15, checkin_window_min: 30 }`.
2. `PATCH /api/v1/settings/classes` valida: `default_capacity` entero de 1 a 100; `checkin_window_min` entero de 0 a 240 (N-18); un valor inválido devuelve 422 con `field`.
3. `PATCH /api/v1/settings/hours` valida que cada día tenga `closed: true` o `opens_at < closes_at` en formato `HH:MM` (hora local de Bogotá); un día con apertura posterior al cierre devuelve 422.
4. Solo admin; coach y socio reciben 403.
5. Cada cambio deja una fila de auditoría con antes y después e incrementa `version`.
6. `validate_section` es pura y tiene pruebas para cada límite.

## Escenarios BDD

```gherkin
# language: es
Característica: Horas y parámetros de clases

  Escenario: El administrador sube el cupo por defecto
    Dado que inicié sesión como administrador
    Cuando cambio el cupo por defecto a 18 y guardo la pestaña Clases
    Entonces la sección classes queda con default_capacity 18
    Y queda una fila de auditoría con el valor anterior 15 y el nuevo 18

  Escenario: Horario incoherente
    Dado que inicié sesión como administrador
    Cuando pongo el lunes con apertura 21:00 y cierre 05:00
    Entonces recibo 422 con field "hours.monday"
```

## Endpoints

- `GET /api/v1/settings/{section}` (`hours`, `classes`) — rol(es): admin — códigos: 200, 401, 403
- `PATCH /api/v1/settings/{section}` — rol(es): admin — entrada: valor completo o parcial de la sección — salida: sección validada — códigos: 200, 401, 403, 422

## Pantalla

- `Config`, pestañas Horas y Clases. Estados de carga, error y guardado.

## Notas técnicas

- **Migración:** de datos no; los valores por defecto viven en el esquema Pydantic (la fila se crea al primer `PATCH`).
- **Trigger / restricciones:** ninguna.
- **Funciones puras a probar:** `validate_section` para `hours` y `classes`.
- **Pruebas:** puras, router (rol, 422), front (formularios).
- **Archivos principales:** `api/src/app/modules/settings/schemas.py`, `web/src/features/system/components/ClassesSettings.tsx`.

## Supuestos

- Supuesto: la sección `hours` tiene la forma `{ monday..sunday: { closed: bool, opens_at: "HH:MM", closes_at: "HH:MM" } }` en hora de Bogotá; ningún documento fija su contenido. Las horas no restringen la creación de franjas (solo informan) salvo que el gate decida otra cosa.
- Supuesto: límites fijados por N-18 (cupo 1 a 100, ventana 0 a 240 minutos).

## Dependencias

- US-054 · Secciones de configuración validadas

## INVEST

- **Independiente:** solo dos secciones de configuración.
- **Negociable:** forma de `hours`.
- **Valiosa:** parámetros del check-in sin código.
- **Estimable:** dos esquemas y dos pestañas.
- **Pequeña:** sí.
- **Testeable:** validaciones binarias.

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas puras y de router en verde; cobertura de 80 % o más en lo tocado
- [ ] Front: pruebas de componente; sin colores literales
- [ ] `docs/openapi.json` regenerado
- [ ] Auditoría verificada para `settings`
- [ ] Revisión de PR aprobada
