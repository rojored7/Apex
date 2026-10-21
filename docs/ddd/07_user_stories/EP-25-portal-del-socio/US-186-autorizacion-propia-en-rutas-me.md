# US-186 · Como socio quiero que el portal solo me muestre mis datos para tener la certeza de que nadie más ve mi información ni yo la de otros

- **Épica:** EP-25 · Portal del socio
- **Bounded context:** Portal (módulo `portal`, sin esquema), sobre `core/security`
- **Versión:** v1.0
- **Actor:** socio
- **Tamaño:** 3
- **Prioridad:** P0 ruta crítica
- **Refinamiento:** Criterios completos; BDD solo de flujo principal
- **Pantalla:** Ninguna (base de todas las rutas `/mi/*`)

## Historia

Como socio
quiero que cada consulta del portal use solo mi identidad de la sesión
para que cambiar un identificador en la URL o en el cuerpo nunca me muestre datos de otro socio

## Contexto de dominio

- **Aggregate / entidades:** `User(role = member, member_id)`.
- **Reglas que aplica:** RN-15 (socio solo lo suyo), invariante de User.
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** ninguna

## Alcance

- **Backend:** dependencia `current_member_id` en `modules/portal/router.py` que exige `require_role("member")`, lee `member_id` del usuario (no del JWT editable por el cliente sin verificar: del usuario cargado por el `sub` firmado) y lo pasa a los services; ninguna ruta `/me/*` acepta `member_id` en path, query o cuerpo. Prueba de arquitectura `test_me_routes_owner_only.py`.
- **Front:** No aplica (las pantallas usan solo rutas `/me/*`).

## Criterios de aceptación

1. Todas las rutas bajo `/api/v1/me` declaran `require_role("member")` y obtienen el `member_id` del usuario autenticado; la prueba de arquitectura falla si una ruta `/me/*` no usa `current_member_id`.
2. Ningún esquema de entrada de `/me/*` tiene un campo `member_id`; si el cliente lo envía, se ignora (Pydantic `extra = "forbid"` devuelve 422) y nunca cambia el socio consultado.
3. Por cada ruta `/me/*` existe una prueba anti IDOR: con dos socios A y B, el token de A nunca devuelve datos de B aunque se pasen ids de recursos de B (pagos, recibos, resultados); un recurso de B pedido por id con el token de A devuelve 404.
4. Admin y coach reciben 403 en `/me/*` (v1.0 no tiene portal para coach, P6).
5. Un usuario `member` bloqueado, dado de baja o cuyo socio está dado de baja recibe 401 en `/me/*`.
6. Un usuario `member` recibe 403 en todas las rutas de panel (`/members`, `/payments`, `/memberships`, etc.), verificado por la prueba de rutas con rol (US-035) ampliada.

## Escenarios BDD

```gherkin
# language: es
Característica: Solo mis datos en el portal

  Escenario: El socio consulta sus pagos
    Dado que los socios "Laura" y "Juan" tienen pagos registrados
    Y que "Laura" inició sesión en el portal
    Cuando consulta sus pagos
    Entonces solo ve los pagos de "Laura"

  Escenario: Intento de ver el recibo de otro socio
    Dado que "Laura" conoce el id de un pago de "Juan"
    Cuando pide el recibo de ese pago desde su portal
    Entonces el sistema responde que no existe
    Y no entrega ningún dato de "Juan"
```

## Endpoints

- Todas las rutas `/api/v1/me/*` — rol(es): member — códigos: 401, 403, 404 según el caso.

## Pantalla

- Ninguna.

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** ninguna.
- **Funciones puras a probar:** ninguna.
- **Pruebas:** arquitectura (recorre rutas `/me`), router anti IDOR parametrizado por ruta, prueba de `extra = "forbid"`.
- **Archivos principales:** `api/src/app/modules/portal/router.py`, `api/tests/architecture/test_me_routes_owner_only.py`.

## Supuestos

- Supuesto: los recursos de otro socio pedidos por id responden 404 y no 403, para no revelar su existencia.

## Dependencias

- US-185 · Crear cuenta de portal (existen usuarios member)
- US-034 · Dependencias current_user y require_role

## INVEST

- **Independiente:** dependencia y pruebas transversales.
- **Negociable:** 404 frente a 403.
- **Valiosa:** sin ella no hay portal seguro.
- **Estimable:** una dependencia y una batería de pruebas.
- **Pequeña:** pocos días.
- **Testeable:** pruebas anti IDOR por ruta.

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas de router y de arquitectura en verde; cobertura de 80 % o más en lo tocado
- [ ] Revisión de seguridad del PR aprobada
