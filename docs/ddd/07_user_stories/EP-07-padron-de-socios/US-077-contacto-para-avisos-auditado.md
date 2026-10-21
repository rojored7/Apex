# US-077 · Como administrador quiero que cada descifrado del contacto de un socio para enviarle un aviso quede auditado con su propósito para demostrar el uso legítimo de sus datos

- **Épica:** EP-07 · Padrón de socios
- **Bounded context:** Members (esquema `members`), proveedor (Customer/Supplier) de Notifications
- **Versión:** v0.1
- **Actor:** administrador
- **Tamaño:** 2
- **Prioridad:** P2 mejora (contrato preparado para EP-14)
- **Refinamiento:** Lista para sprint
- **Pantalla:** Ninguna (historia sin front)

## Historia

Como administrador responsable de los datos ante la Ley 1581
quiero que Members exponga `contact_for_notification(member_id, purpose)`, que entregue solo el teléfono y el correo del socio y audite cada descifrado con su propósito
para que el módulo de avisos nunca descifre datos por su cuenta y quede rastro de para qué se usó cada contacto

## Contexto de dominio

- **Aggregate / entidades:** `Member` (`Phone`, `Email`).
- **Reglas que aplica:** RN-13 (descifrado auditado); `03_context_map.md` sección 2 (Notifications → Members, audita con propósito `notify`) y sección 5 (ningún contexto descifra campos que no son suyos); RN-14 (un socio dado de baja no se contacta).
- **Eventos que emite:** `SensitiveFieldRevealed(member_id, field, user_id = null, purpose)` por cada campo descifrado
- **Eventos que consume:** ninguno
- **Funciones puras:** `members.validate_purpose(purpose) -> None | MemberError`

## Alcance

- **Backend:** `members.service.contact_for_notification(member_id, purpose, by=None) -> Contact { first_name, phone | None, email | None }`; propósitos admitidos: `notify` (v0.2) y `auth_link` (envío de enlaces, v0.2); descifra con el bus, registra `crypto_ops` con el mismo `batch_id` para los dos campos y escribe auditoría `reveal` con el propósito; nunca expuesto por HTTP.
- **Front:** No aplica.

## Criterios de aceptación

1. `contact_for_notification` devuelve `first_name`, `phone` y `email` en claro solo como valor de retorno de la función; no tiene endpoint HTTP (la prueba de rutas no encuentra ninguna ruta que la exponga).
2. Un `purpose` fuera de `notify` y `auth_link` lanza `MemberError` y no descifra nada.
3. Cada llamada deja una entrada de auditoría `reveal` por campo descifrado con `purpose`, `record_id` y `user_id` (nulo si la llama el worker) y una fila en `crypto_ops` con verbo `decrypt`; ninguna contiene el valor.
4. Un socio dado de baja o inexistente lanza `MemberNotContactable` sin descifrar.
5. Un campo vacío se devuelve como `None` y no genera operación de descifrado.
6. Una prueba de arquitectura verifica que el módulo `notifications` (cuando exista) no importa `core.crypto.bus` para campos de socios: solo llama a este service.

## Escenarios BDD

```gherkin
# language: es
Característica: Contacto para avisos auditado

  Antecedentes:
    Dado un socio "Laura Gómez" con teléfono "3001234567" y correo "laura@correo.co"

  Escenario: Obtener contacto para avisar
    Cuando el worker pide el contacto de "Laura Gómez" con propósito "notify"
    Entonces recibe el teléfono "3001234567" y el correo "laura@correo.co"
    Y quedan dos entradas de auditoría "reveal" con propósito "notify"
    Y quedan dos operaciones de descifrado con el mismo lote

  Escenario: Propósito no admitido
    Cuando se pide el contacto con propósito "marketing"
    Entonces la llamada falla con un error de dominio
    Y no se descifra ningún campo

  Escenario: Socio dado de baja
    Dado que "Laura Gómez" fue dada de baja
    Cuando el worker pide su contacto con propósito "notify"
    Entonces la llamada falla con "MemberNotContactable"
    Y no se descifra ningún campo
```

## Endpoints

- Ninguno (contrato interno de `members.service`, consumido por EP-14).

## Pantalla

- Ninguna.

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** no aplica.
- **Funciones puras a probar:** `validate_purpose`.
- **Pruebas:** service con base real (descifrado, auditoría con propósito, `batch_id`, socio dado de baja, campos vacíos); prueba de arquitectura de rutas (no expuesta).
- **Archivos principales:** `api/src/app/modules/members/service.py`, `api/src/app/modules/members/exceptions.py`.

## Supuestos

- Supuesto: el catálogo de propósitos es `notify` y `auth_link`; las fuentes solo nombran `notify`.
- Supuesto: la entrada de auditoría guarda el propósito en el campo `after` como `{ "field": "phone", "purpose": "notify" }`, porque `AuditEntry` no tiene columna `purpose`.

## Dependencias

- US-069 · Registrar socio.
- US-029 · Bitácora crypto_ops por lote.

## INVEST

- **Independiente:** contrato interno; se prueba sin Notifications.
- **Negociable:** catálogo de propósitos.
- **Valiosa:** evidencia legal del uso de contactos y frontera clara entre contextos.
- **Estimable:** una función de service.
- **Pequeña:** 1 a 2 días.
- **Testeable:** auditoría y descifrado verificables en base real.

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
