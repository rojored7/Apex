# US-034 · Como equipo quiero las dependencias current_user y require_role para que cada endpoint declare quién puede usarlo y el API lo haga cumplir siempre

- **Épica:** EP-03 · Seguridad de la plataforma
- **Bounded context:** `core/security`
- **Versión:** v0.1
- **Actor:** equipo
- **Tamaño:** 3
- **Prioridad:** P0 ruta crítica
- **Refinamiento:** Lista para sprint
- **Pantalla:** Ninguna (historia sin front)

## Historia

Como equipo
quiero `current_user` y `require_role("admin" | "coach" | "member", ...)` como dependencias de FastAPI
para que el coach no pueda anular pagos, el socio solo vea lo suyo y ningún endpoint quede abierto por olvido

## Contexto de dominio

- **Aggregate / entidades:** `User` (lectura de `is_active`, `locked_at`, `deleted_at`).
- **Reglas que aplica:** RN-15 (rol por endpoint; coach no anula ni borra; socio solo lo suyo); `BRECHAS.md` sección 5 vía EP-03 (`DELETE /members/{id}`, `POST /memberships/{id}/cancel`, `POST /payments/{id}/void` solo admin).
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** `security.role_allowed(user_role, allowed_roles) -> bool`

## Alcance

- **Backend:** `current_user` lee `Authorization: Bearer`, decodifica (US-033), carga el usuario por `auth.service` y rechaza si no existe, está inactivo, bloqueado o dado de baja. Deja `user_id` en un `contextvar` para auditoría (US-016) y bitácora cripto (US-029). `require_role(*roles)` devuelve una dependencia que exige `current_user` y que el rol esté en la lista; marca la ruta con un atributo que la prueba US-035 detecta. Errores con el envelope (US-017): `401 unauthorized` y `403 forbidden`.
- **Front:** No aplica

## Criterios de aceptación

1. Una petición sin cabecera `Authorization` a una ruta con `require_role` recibe 401 con `error.code = "unauthorized"`.
2. Un token válido de coach en una ruta `require_role("admin")` recibe 403 con `error.code = "forbidden"`.
3. Un token válido de un usuario que fue bloqueado después de emitir el token recibe 401 (se comprueba el estado en cada petición).
4. Un token de un usuario con `deleted_at` recibe 401.
5. `require_role("admin", "coach")` deja pasar a ambos y rechaza a `member` con 403.
6. Después de `current_user`, el `user_id` está disponible para la auditoría de esa petición.
7. Los mensajes de 401 y 403 no revelan si el usuario existe ni por qué falló el token.

## Escenarios BDD

```gherkin
# language: es
Característica: Control de acceso por rol

  Antecedentes:
    Dado una ruta de prueba que exige el rol admin

  Escenario: Administrador autorizado
    Dado un access token válido de un administrador activo
    Cuando llama a la ruta
    Entonces recibe 200

  Escenario: Coach sin permiso
    Dado un access token válido de un coach
    Cuando llama a la ruta
    Entonces recibe 403 con error.code "forbidden"

  Escenario: Sin token
    Cuando se llama a la ruta sin cabecera Authorization
    Entonces recibe 401 con error.code "unauthorized"

  Escenario: Usuario bloqueado con token aún vigente
    Dado un administrador con token vigente que luego fue bloqueado
    Cuando llama a la ruta
    Entonces recibe 401
```

## Endpoints

- Ninguno propio; aplica a todos los endpoints con rol.

## Pantalla

- Ninguna.

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** no aplica.
- **Funciones puras a probar:** `role_allowed`.
- **Pruebas:** router con `httpx.AsyncClient` sobre rutas de prueba; casos 200, 401, 403.
- **Archivos principales:** `api/src/app/core/security.py`, `api/tests/core/test_require_role.py`.
- **Nota:** `current_user` llama a `auth.service`; mientras US-041 no exista se prueba con un doble del service.

## Supuestos

- Ninguno.

## Dependencias

- US-033 · JWT Ed25519
- US-020 · create_app, migraciones y health
- US-041 · cuentas de usuario (suave: current_user carga el usuario; se prueba con un doble hasta entonces; agregado en consolidación)

## INVEST

- **Independiente:** prueba con rutas de prueba y doble del service.
- **Negociable:** forma de pasar varios roles.
- **Valiosa:** hace cumplir RN-15.
- **Estimable:** dos dependencias.
- **Pequeña:** dos días.
- **Testeable:** códigos 200/401/403.

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
- [ ] Front: pruebas de componente y página; sin colores literales (si aplica)
- [ ] Migración aplicada con `alembic upgrade head` y reversible (si aplica)
- [ ] `docs/openapi.json` regenerado (si cambia el contrato)
- [ ] Auditoría verificada para las tablas tocadas (si aplica)
- [ ] Revisión de PR aprobada
