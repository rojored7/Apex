# US-106 · Como coach o administrador quiero ver el historial de cambios de un socio en su ficha para saber quién modificó o consultó sus datos

- **Épica:** EP-11 · Auditoría y trazabilidad
- **Bounded context:** Audit (esquema `audit`), consumido desde Members (ficha)
- **Versión:** v0.1
- **Actor:** administrador, coach
- **Tamaño:** 3
- **Prioridad:** P1 necesaria para la versión
- **Refinamiento:** Lista para sprint
- **Pantalla:** `Socio_Ficha` (`/socios/:id`, pestaña Historial con `HistoryAside`)

## Historia

Como coach o administrador
quiero ver en la ficha del socio la línea de tiempo de cambios y consultas en claro de sus datos
para responder quién lo creó, quién lo editó y quién vio su cédula o teléfono

## Contexto de dominio

- **Aggregate / entidades:** `AuditEntry` (lectura filtrada por registro).
- **Reglas que aplica:** RN-13 (los `reveal` aparecen en el historial; los valores cifrados nunca se muestran en claro), RN-16, regla de datos 6 (paginación), épica EP-11 (admin y coach ven el historial del socio).
- **Eventos que emite:** ninguno.
- **Eventos que consume:** ninguno.
- **Funciones puras:** `audit.diff` (de US-103) para resumir cada cambio.

## Alcance

- **Backend:** `GET /members/{id}/audit`, que valida que el socio exista y delega en `audit.service.list(table="members", record_id=id)`; cada fila trae acción, usuario, fecha y los nombres de campos cambiados (o el campo revelado en un `reveal`), nunca los valores cifrados.
- **Front:** pestaña Historial de `Socio_Ficha` con `HistoryAside`: frases del tipo "Ana P. editó teléfono y notas", "Juan R. mostró el documento", "Ana P. creó el socio", en orden cronológico descendente y paginado.

## Criterios de aceptación

1. `GET /api/v1/members/{id}/audit` devuelve `{ items, total, limit, offset }` con las entradas de `table_name = "members"` y `record_id = id`, incluidas las de acción `reveal`; `limit` 1 a 200 (25 por defecto).
2. Cada ítem trae `seq`, `at` (UTC), `user_id`, nombre del usuario, `action` y `fields` (nombres de campos cambiados o el campo revelado); no trae `before` ni `after`.
3. Ningún valor de campo cifrado aparece en la respuesta (prueba con un socio editado y revelado).
4. Socio inexistente devuelve 404; un socio dado de baja devuelve su historial completo, incluida la baja.
5. Rol: `require_role("admin", "coach")` (a diferencia de `GET /audit`, solo admin); `member` recibe 403; sin token, 401.
6. Una ficha abierta sin presionar "mostrar" no agrega ninguna entrada al historial.

## Escenarios BDD

```gherkin
# language: es
Característica: Historial del socio en su ficha

  Antecedentes:
    Dado la socia "Laura Gómez" creada por "Ana Pérez"
    Y que "Juan Ruiz" editó su teléfono y luego mostró su documento

  Escenario: El coach ve el historial de la socia
    Dado que estoy autenticado como "coach"
    Cuando abro la pestaña Historial de su ficha
    Entonces veo "Juan R. mostró el documento", "Juan R. editó teléfono" y "Ana P. creó el socio" en ese orden
    Y no veo el número de documento ni el teléfono

  Escenario: Abrir la ficha no deja rastro
    Dado que estoy autenticado como "coach"
    Cuando abro la ficha sin mostrar ningún dato
    Entonces el historial no tiene entradas nuevas

  Escenario: Socio inexistente
    Dado que estoy autenticado como "admin"
    Cuando pido el historial de un socio que no existe
    Entonces la respuesta es 404

  Escenario: Un socio no ve el historial por esta ruta
    Dado que estoy autenticado como "member"
    Cuando pido el historial de "Laura Gómez"
    Entonces la respuesta es 403
```

## Endpoints

- `GET /api/v1/members/{id}/audit?limit&offset` — rol(es): admin, coach — salida: `Page[MemberHistoryItem { seq, at, user_id, user_name, action, fields }]` — códigos: 200, 401, 403, 404, 422.

## Pantalla

- `Socio_Ficha` en `/socios/:id`, pestaña Historial con `HistoryAside` (carga, vacío y error).

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** ninguna.
- **Funciones puras a probar:** frase por acción (`insert`, `update` con campos, `reveal` con campo, `delete`).
- **Pruebas:** router (rol coach permitido, 404, 403 member); service (sin valores cifrados); front (frases y orden).
- **Archivos principales:** `api/src/app/modules/members/router.py`, `api/src/app/modules/audit/service.py`, `web/src/features/members/components/MemberHistoryTab.tsx`.

## Supuestos

- Supuesto: en v0.1 el historial del socio incluye solo las entradas de la tabla `members` con `record_id` igual al socio (cambios y `reveal`); los cambios de sus membresías y pagos se ven en sus pestañas y no se mezclan aquí.
- Supuesto: los `reveal` se registran con `table_name = "members"` y `record_id = id del socio`, con el nombre del campo en `after.field` (lo fija US-074 / US-107).

## Dependencias

- US-102 · Consultar auditoría (service de lista).
- US-073 · Ver ficha del socio (contenedor de pestañas).
- US-066 · Valor enmascarado e historial (`HistoryAside`).

## INVEST

- **Independiente:** reutiliza el service de US-102 con un filtro fijo.
- **Negociable:** redacción de las frases.
- **Valiosa:** rastro visible del uso de datos personales.
- **Estimable:** una ruta delegada y una pestaña.
- **Pequeña:** dos días.
- **Testeable:** ausencia de claro y frases probadas.

## Definición de listo

- [x] Criterios de aceptación verificables
- [x] Escenarios BDD con camino feliz, error y rol
- [x] Endpoints y roles definidos
- [x] Dependencias identificadas
- [x] Sin preguntas abiertas que bloqueen (o supuesto declarado)

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas de service con PostgreSQL real en verde; cobertura de 80 % o más en lo tocado
- [ ] Pruebas de router: rol, validación y envelope de error
- [ ] Front: pruebas de componente; sin colores literales
- [ ] `docs/openapi.json` regenerado
- [ ] Revisión de PR aprobada
