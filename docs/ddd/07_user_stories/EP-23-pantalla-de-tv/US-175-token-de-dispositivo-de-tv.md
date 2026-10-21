# US-175 · Como administrador quiero generar y rotar el token de la TV desde Configuración para controlar qué pantalla puede mostrar el WOD y el leaderboard

- **Épica:** EP-23 · Pantalla de TV del box
- **Bounded context:** Settings (esquema `settings`, sección `tv`)
- **Versión:** v0.5
- **Actor:** administrador
- **Tamaño:** 2
- **Prioridad:** P1 necesaria para la versión
- **Refinamiento:** Criterios completos; BDD solo de flujo principal
- **Pantalla:** `Config` (`/sistema/configuracion`, pestaña TV)

## Historia

Como administrador
quiero generar un token largo para la TV y poder regenerarlo cuando sospeche que se filtró
para que solo la pantalla del box muestre el WOD y el leaderboard, y un token viejo deje de servir de inmediato

## Contexto de dominio

- **Aggregate / entidades:** `SettingsSection` con `key = tv`.
- **Reglas que aplica:** invariante de Settings: `tv.device_token` se genera, no se escribe; auditado; Q12 (nada secreto en claro dentro de la auditoría).
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** `settings.validate_section("tv", value)`

## Alcance

- **Backend:** esquema Pydantic de la sección `tv` (`device_token_hash`, `token_last4`, `rotated_at`, `refresh_seconds` por defecto 30); `settings.service.tv_regenerate_token(by)` genera el token con el generador seguro de `core/security`, guarda solo su hash y devuelve el token en claro una única vez; `settings.service.verify_tv_token(token)` para US-176.
- **Front:** pestaña TV de `Config` con los últimos 4 caracteres, fecha de rotación, botón "Regenerar token" con `ConfirmModal` y el enlace `/tv?token=…` copiable solo en la respuesta de la regeneración.

## Criterios de aceptación

1. `POST /api/v1/settings/tv/regenerate-token` genera un token de al menos 32 bytes aleatorios codificados en base64url, guarda solo su hash en la sección `tv` y responde 200 con `{ token, url }` una única vez.
2. Después de regenerar, el token anterior deja de ser válido en `verify_tv_token` de inmediato (sin caché que lo mantenga vivo).
3. `PATCH /api/v1/settings/tv` con `device_token` o `device_token_hash` en el cuerpo devuelve 422 (el token no se escribe a mano); `refresh_seconds` fuera de 10 a 300 devuelve 422.
4. `GET /api/v1/settings/tv` nunca devuelve el token ni su hash; solo `token_last4`, `rotated_at` y `refresh_seconds`.
5. La regeneración queda en auditoría con usuario y fecha; `before` y `after` contienen el hash, nunca el token en claro.
6. Solo admin; coach recibe 403.
7. `rotated_at` en UTC con zona.

## Escenarios BDD

```gherkin
# language: es
Característica: Token de la TV

  Escenario: Regenerar el token
    Dado que inicié sesión como administrador
    Y la TV usa el token actual
    Cuando regenero el token de la TV
    Entonces veo una única vez el enlace nuevo para la TV
    Y el token anterior deja de funcionar

  Escenario: Escribir el token a mano
    Cuando intento guardar la sección TV con un token escrito por mí
    Entonces el sistema rechaza el cambio indicando que el token solo se genera
```

## Endpoints

- `GET /api/v1/settings/tv` — rol(es): admin — salida: `{ token_last4, rotated_at, refresh_seconds }` — códigos: 200, 401, 403
- `PATCH /api/v1/settings/tv` — rol(es): admin — entrada: `{ refresh_seconds }` — códigos: 200, 401, 403, 422
- `POST /api/v1/settings/tv/regenerate-token` — rol(es): admin — salida: `{ token, url }` — códigos: 200, 401, 403

## Pantalla

- `Config`, pestaña TV: estado del token, botón de regenerar con confirmación, enlace copiable tras regenerar.

## Notas técnicas

- **Migración:** no (la sección se guarda en `settings.settings_sections` como JSON validado).
- **Trigger / restricciones:** ninguna.
- **Funciones puras a probar:** `validate_section("tv", ...)` rechaza `device_token`.
- **Pruebas:** service con base real (token anterior inválido, hash en auditoría), router (403 coach), front.
- **Archivos principales:** `api/src/app/modules/settings/{schemas,service,router}.py`, `web/src/features/system/pages/ConfigPage.tsx`.

## Supuestos

- Supuesto: se guarda el hash del token (no el token) para que no quede en claro en la base ni en la auditoría; el dominio dice "se genera, no se escribe" pero no fija cómo se guarda.
- Supuesto: `refresh_seconds` es configurable (por defecto 30, el valor de `ROUTES.md`).

## Dependencias

- US-054 · Secciones de configuración validadas

## INVEST

- **Independiente:** solo usa Settings.
- **Negociable:** formato del enlace y rango de refresco.
- **Valiosa:** controla quién puede mostrar la TV.
- **Estimable:** una sección y un endpoint.
- **Pequeña:** 2 puntos.
- **Testeable:** invalidación inmediata verificable.

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas de reglas puras y de service con PostgreSQL real en verde; cobertura de 80 % o más en lo tocado
- [ ] Pruebas de router: rol, validación y envelope de error
- [ ] Front: pruebas de componente; sin colores literales
- [ ] `docs/openapi.json` regenerado
- [ ] Auditoría verificada para la sección `tv`
- [ ] Revisión de PR aprobada
