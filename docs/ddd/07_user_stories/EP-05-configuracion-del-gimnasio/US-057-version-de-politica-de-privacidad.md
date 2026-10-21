# US-057 · Como administrador quiero registrar la versión vigente de la política de tratamiento de datos para saber qué texto aceptó cada socio

- **Épica:** EP-05 · Configuración del gimnasio
- **Bounded context:** Settings (esquema `settings`, módulo `settings`); consumido por Members (`data_consent_version`)
- **Versión:** v0.1
- **Actor:** administrador
- **Tamaño:** 2
- **Prioridad:** P1 necesaria para la versión
- **Refinamiento:** Lista para sprint
- **Pantalla:** `Config` (`/sistema/configuracion`, pestaña "Privacidad")

## Historia

Como administrador
quiero registrar qué versión de la política de tratamiento de datos está vigente y desde cuándo
para que cada autorización de un socio quede asociada a la versión que aceptó, como pide la Ley 1581

## Contexto de dominio

- **Aggregate / entidades:** `SettingsSection(key = privacy)`.
- **Reglas que aplica:** Settings ← Members (versión de la política, `03_context_map.md` 2); `Member.data_consent_version` (`02_domain_model.md` 2.1); `data_consent_at` opcional hasta v0.3 (Q16); RN-15.
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** `settings.validate_section("privacy", value)`.

## Alcance

- **Backend:** esquema `PrivacySettings`; `settings.service.current_privacy_version()` para Members; `GET/PATCH /settings/privacy`.
- **Front:** pestaña "Privacidad" de `Config` con versión, fecha de vigencia y enlace o texto de la política.

## Criterios de aceptación

1. El esquema `privacy` tiene `policy_version` (obligatoria, 1 a 20 caracteres, por ejemplo `2026-10`), `effective_from` (fecha ISO `AAAA-MM-DD`, obligatoria) y `policy_url` (opcional, URL `https`) o `policy_text` (opcional, hasta 20.000 caracteres); al menos uno de los dos últimos es obligatorio.
2. Sin `policy_url` ni `policy_text` responde 422 con `field: "value.policy_url"`.
3. Una `effective_from` mal formada responde 422 con `field: "value.effective_from"`.
4. `settings.service.current_privacy_version()` devuelve `policy_version`; Members la copia en `data_consent_version` cuando registra una autorización (en v0.1 la autorización es opcional, Q16).
5. Cambiar la versión no modifica `data_consent_version` de ningún socio existente.
6. El cambio queda en auditoría con antes y después.
7. Un coach recibe 403 en `GET` y `PATCH`.
8. El front muestra la versión vigente y la fecha en formato `20 oct 2026`, y advierte antes de guardar una versión nueva: "Los socios que ya aceptaron conservan la versión anterior."

## Escenarios BDD

```gherkin
# language: es
Característica: Versión de la política de privacidad

  Antecedentes:
    Dado un admin con sesión en la pestaña "Privacidad"
    Y la versión vigente "2026-01"

  Escenario: Publicar una versión nueva
    Cuando guarda la versión "2026-10" vigente desde "2026-10-21" con su enlace
    Entonces ve "Cambios guardados"
    Y los socios que aceptaron "2026-01" la conservan

  Escenario: Sin texto ni enlace
    Cuando guarda una versión sin enlace ni texto
    Entonces recibe 422 con field "value.policy_url"

  Escenario: El coach no ve la privacidad
    Dado un coach con sesión
    Cuando pide "GET /settings/privacy"
    Entonces recibe 403
```

## Endpoints

- `GET /api/v1/settings/privacy` — rol(es): admin — códigos: 200, 401, 403.
- `PATCH /api/v1/settings/privacy` — rol(es): admin — entrada: `{ value: { policy_version, effective_from, policy_url?, policy_text? }, version }` — códigos: 200, 401, 403, 409, 422.

## Pantalla

- `Config`, pestaña "Privacidad".

## Notas técnicas

- **Migración:** no.
- **Funciones puras a probar:** `validate_section("privacy", ...)` sin texto ni enlace, con URL `http` (rechazada) y válida.
- **Pruebas:** router (422, 403), front (pestaña y advertencia).
- **Archivos principales:** `api/src/app/modules/settings/schemas.py`, `service.py`; `web/src/features/system/components/PrivacySettingsForm.tsx`.

## Supuestos

- Supuesto: los campos de `privacy` (versión, vigencia, enlace o texto) no están definidos en los documentos; se derivan de `data_consent_version` y de la pantalla `Config`.

## Dependencias

- US-055 · Datos del gimnasio (estructura de pestañas de `Config`)

## INVEST

- **Independiente:** solo requiere la pantalla de configuración.
- **Negociable:** enlace o texto completo es elegible.
- **Valiosa:** evidencia de qué política aceptó cada socio.
- **Estimable:** un esquema y una pestaña.
- **Pequeña:** uno o dos días.
- **Testeable:** cada validación tiene `field` fijo.

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
- [ ] Front: pruebas de componente; sin colores literales
- [ ] `docs/openapi.json` regenerado
- [ ] Auditoría verificada para `settings.settings_sections`
- [ ] Revisión de PR aprobada
