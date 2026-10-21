# US-074 · Como recepción quiero mostrar en claro un dato sensible del socio cuando lo necesito para llamarlo o verificar su cédula, dejando constancia de quién lo vio

- **Épica:** EP-07 · Padrón de socios
- **Bounded context:** Members (esquema `members`), con Crypto (bus) y Audit
- **Versión:** v0.1
- **Actor:** administrador, coach
- **Tamaño:** 3
- **Prioridad:** P0 ruta crítica
- **Refinamiento:** Lista para sprint
- **Pantalla:** `Socio_Ficha` (`/socios/:id`, botón "Mostrar" de `MaskedValue`)

## Historia

Como administrador o coach
quiero pulsar "Mostrar" sobre el documento, el teléfono, el correo, la fecha de nacimiento o el contacto de emergencia de un socio
para usar ese dato en el momento, sabiendo que la consulta queda auditada con mi usuario, el campo y el socio

## Contexto de dominio

- **Aggregate / entidades:** `Member` y sus value objects cifrados.
- **Reglas que aplica:** RN-13 (mostrar en claro se audita); Q6 (admin y coach pueden hacer `reveal`; siempre auditado con campo y usuario); el bus es la única puerta de descifrado (`decrypt(blob, aad)`).
- **Eventos que emite:** `SensitiveFieldRevealed(member_id, field, user_id)`
- **Eventos que consume:** ninguno
- **Funciones puras:** ninguna nueva

## Alcance

- **Backend:** `members.service.reveal(id, field, by) -> str` que valida el campo, descifra un solo campo con `bus.decrypt(blob, aad = id)`, registra la operación en `crypto_ops` y emite `SensitiveFieldRevealed`; esta historia escribe la entrada `reveal` con `audit.record` en la misma transacción (movido desde US-107 para evitar un ciclo); router `POST /members/{id}/reveal`.
- **Front:** conexión de `MaskedValue.onReveal` en la ficha a la mutación `revealField(id, field)`; el valor vuelve como respuesta y no se cachea.

## Criterios de aceptación

1. `POST /api/v1/members/{id}/reveal` con `{ "field": "document" }` y rol `admin` o `coach` responde 200 con `{ "field": "document", "value": "1020304" }`.
2. `field` solo admite `document`, `phone`, `email`, `birth_date` y `emergency_contact`; cualquier otro responde 422 con `field = "field"`.
3. Un usuario `member` recibe 403; sin token, 401; socio inexistente, 404.
4. Cada `reveal` exitoso deja exactamente una entrada de auditoría con `action = "reveal"`, `table_name = "members"`, `record_id`, `user_id` y el nombre del campo, y una fila en `crypto_ops` con verbo `decrypt`, `data_class` y `record_id`; ninguna de las dos contiene el valor en claro.
5. Si la auditoría o el registro en `crypto_ops` fallan, la respuesta es 500 y no se devuelve el valor (el valor nunca sale sin rastro).
6. Si el campo está vacío, responde 200 con `value = null` y también se audita el intento.
7. La respuesta lleva `Cache-Control: no-store`; el valor no se escribe en logs.
8. En el front, el valor aparece solo dentro de `MaskedValue` y se vuelve a enmascarar al ocultar, al salir de la ficha o a los 60 segundos.

## Escenarios BDD

```gherkin
# language: es
Característica: Mostrar dato sensible auditado

  Antecedentes:
    Dado un socio "Laura Gómez" con teléfono "3001234567"

  Escenario: Coach muestra el teléfono
    Dado un usuario autenticado "carlos" con rol "coach"
    Cuando pulsa "Mostrar" en el teléfono de "Laura Gómez"
    Entonces ve "3001234567"
    Y queda una entrada de auditoría "reveal" del usuario "carlos" sobre el campo "phone" de "Laura Gómez"
    Y se emite el evento SensitiveFieldRevealed

  Escenario: Campo no permitido
    Dado un usuario autenticado con rol "admin"
    Cuando pide mostrar el campo "first_name"
    Entonces recibe un error 422 con el campo "field"

  Escenario: Falla la auditoría
    Dado que la escritura de auditoría falla
    Cuando un administrador pide mostrar el documento
    Entonces recibe un error 500
    Y la respuesta no contiene el documento

  Escenario: Rol socio denegado
    Dado un usuario autenticado con rol "member"
    Cuando pide mostrar el documento de "Laura Gómez"
    Entonces recibe un error 403
    Y no queda ninguna entrada de auditoría "reveal"
```

## Endpoints

- `POST /api/v1/members/{id}/reveal` — rol(es): admin, coach — entrada: `{ field }` — salida: `{ field, value }` con `Cache-Control: no-store` — códigos: 200, 401, 403, 404, 422, 500.

## Pantalla

- `Socio_Ficha`: botón "Mostrar" de cada `MaskedValue`.

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** no aplica.
- **Funciones puras a probar:** ninguna nueva.
- **Pruebas:** service con base real (descifrado correcto, auditoría y `crypto_ops` en la misma transacción, reversión si falla la auditoría), router (rol, 422, no-store), logs sin valor; front (llamada única, sin caché).
- **Archivos principales:** `api/src/app/modules/members/{service,router,schemas}.py`, `web/src/features/members/api.ts`.

## Supuestos

- Supuesto: un intento de `reveal` sobre un campo vacío también se audita, para que el rastro cubra todas las consultas.

## Dependencias

- US-073 · Ver ficha del socio.
- US-029 · Bitácora crypto_ops por lote.
- Nota de consolidación: para evitar un ciclo con US-107, la fila de auditoría reveal la escribe esta historia (audit.record junto con SensitiveFieldRevealed); US-107 conserva login, UserLocked y SessionsRevoked

## INVEST

- **Independiente:** solo necesita la ficha y el bus.
- **Negociable:** formato de respuesta del contacto de emergencia (objeto).
- **Valiosa:** permite usar los datos sin romper RN-13.
- **Estimable:** un endpoint y una conexión en la ficha.
- **Pequeña:** 2 a 3 días.
- **Testeable:** auditoría y ausencia de valor en fallos verificables.

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
