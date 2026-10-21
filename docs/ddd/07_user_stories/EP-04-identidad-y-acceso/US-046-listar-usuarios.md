# US-046 · Como administrador quiero ver la lista de usuarios del sistema con su rol y estado para saber quién tiene acceso hoy

- **Épica:** EP-04 · Identidad y acceso
- **Bounded context:** Auth (esquema `auth`, módulo `auth`)
- **Versión:** v0.1
- **Actor:** administrador
- **Tamaño:** 3
- **Prioridad:** P1 necesaria para la versión
- **Refinamiento:** Lista para sprint
- **Pantalla:** `Usuarios` (`/sistema/usuarios`)

## Historia

Como administrador
quiero ver todos los usuarios con su rol, estado y último acceso
para saber quién puede entrar al sistema y detectar cuentas que sobran

## Contexto de dominio

- **Aggregate / entidades:** `User`.
- **Reglas que aplica:** RN-14 (los usuarios dados de baja no se listan por defecto), RN-15 (solo admin), regla de datos 6 (paginación y búsqueda).
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** `auth.user_status(user) -> "active" | "locked" | "pending_activation" | "deleted"`.

## Alcance

- **Backend:** `auth.service.list_users(q, role, status, limit, offset)` y `GET /users`.
- **Front:** pantalla `Usuarios` con `PageHeader`, `FilterBar` (búsqueda por correo, filtro de rol y de estado), `DataTable` y `Pagination`; botón "Nuevo usuario" (lo usa US-047).

## Criterios de aceptación

1. `GET /api/v1/users` solo con rol `admin` responde 200 con `{ items, total, limit, offset }`; cada ítem trae `{ id, email, role, status, member_id, last_login_at, created_at }` y nunca `password_hash` ni tokens.
2. `limit` acepta de 1 a 200 (por defecto 25) y `offset` desde 0; un `limit` de 201 o negativo responde 422 con `field: "limit"`.
3. `q` busca por correo sin distinguir mayúsculas (`ILIKE`), `role` filtra por `admin`, `coach` o `member`, y `status` por `active`, `locked`, `pending_activation` o `deleted`; un valor fuera de esos responde 422.
4. Sin filtro `status`, los usuarios con `deleted_at` no aparecen; con `status=deleted` sí.
5. `pending_activation` es el usuario que tiene un `OneTimeToken(activate)` sin usar y nunca inició sesión.
6. `last_login_at` sale de la última auditoría `login` correcta del usuario, en ISO 8601 UTC; el front la muestra en hora de Bogotá.
7. Un coach recibe 403 y un request sin token 401.
8. El orden por defecto es `email` ascendente.
9. La pantalla muestra estados de carga, vacío ("No hay usuarios con estos filtros") y error, y cada estado lleva `StatusTag` con texto (nunca solo color).
10. La entrada "Usuarios" del `SideNav` no se muestra al coach.

## Escenarios BDD

```gherkin
# language: es
Característica: Listar usuarios

  Antecedentes:
    Dado los usuarios "dueno@apex.co" admin, "ana@apex.co" coach y "luis@apex.co" coach bloqueado
    Y el usuario "viejo@apex.co" dado de baja

  Escenario: El admin ve los usuarios vigentes
    Dado un admin con sesión
    Cuando abre "/sistema/usuarios"
    Entonces ve 3 usuarios con su rol y estado
    Y "luis@apex.co" aparece con el estado "Bloqueado"
    Y "viejo@apex.co" no aparece

  Escenario: Filtrar por estado dado de baja
    Cuando el admin filtra por estado "deleted"
    Entonces solo ve "viejo@apex.co"

  Escenario: Límite de página inválido
    Cuando se pide "/users?limit=500"
    Entonces recibe 422 con field "limit"

  Escenario: El coach no puede ver usuarios
    Dado un coach con sesión
    Cuando pide "/users"
    Entonces recibe 403
```

## Endpoints

- `GET /api/v1/users` — rol(es): admin — entrada: `q`, `role`, `status`, `limit`, `offset` — salida: `{ items, total, limit, offset }` — códigos: 200, 401, 403, 422.

## Pantalla

- `Usuarios` de `docs/design/screens/` en `/sistema/usuarios`: encabezado, filtros, tabla y paginación. Las acciones por fila (editar, bloquear, cerrar sesiones, enlace) las agregan US-049 a US-052.

## Notas técnicas

- **Migración:** no.
- **Funciones puras a probar:** `user_status` para cada combinación de `locked_at`, `deleted_at` y token de activación.
- **Pruebas:** service con base real (filtros, exclusión de borrados), router (403 coach, 422 limit), front (página con datos, vacío y error).
- **Archivos principales:** `api/src/app/modules/auth/service.py`, `router.py`, `schemas.py`; `web/src/features/system/pages/UsersPage.tsx`, `web/src/features/system/api.ts`.
- `last_login_at` se obtiene vía `audit.service` (no se lee `audit` desde `auth.models`).

## Supuestos

- Supuesto: `last_login_at` se deriva de la auditoría de `login`; si se prefiere una columna en `users`, requiere migración.

## Dependencias

- US-041 · Cuentas de usuario y admin inicial
- US-034 · Dependencias current_user y require_role
- US-061 · Panel layout, TopBar y SideNav
- US-063 · Tabla, paginación, filtros y chips

## INVEST

- **Independiente:** lectura pura sobre tablas ya creadas.
- **Negociable:** columnas visibles y orden ajustables.
- **Valiosa:** el dueño ve quién tiene acceso.
- **Estimable:** un endpoint de lista y una página estándar.
- **Pequeña:** dos o tres días.
- **Testeable:** filtros y roles con resultados binarios.

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
- [ ] Front: pruebas de componente y página; sin colores literales
- [ ] `docs/openapi.json` regenerado
- [ ] Revisión de PR aprobada
