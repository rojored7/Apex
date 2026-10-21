# US-150 · Como coach quiero ver y descargar los adjuntos de un socio desde su ficha con rastro de auditoría para consultar su autorización sin exponerla sin control

- **Épica:** EP-19 · Adjuntos y autorización de tratamiento de datos
- **Bounded context:** Attachments (+ Members)
- **Versión:** v0.3
- **Actor:** administrador, coach
- **Tamaño:** 3
- **Prioridad:** P1 necesaria para la versión
- **Refinamiento:** Criterios completos; BDD solo de flujo principal
- **Pantalla:** `Socio_Ficha` (`/socios/:id`, pestaña Adjuntos)

## Historia

Como coach o administrador
quiero ver la lista de adjuntos del socio y descargarlos desde su ficha
para consultar su autorización o su foto dejando constancia de quién lo hizo

## Contexto de dominio

- **Aggregate / entidades:** `Attachment`.
- **Reglas que aplica:** descarga solo con rol y auditada; los sensibles se descifran por el bus (RN-13); RN-15; RN-16 (la auditoría queda en la cadena).
- **Eventos que emite:** `SensitiveFieldRevealed(member_id, field = "attachment:<id>", user_id)` al descargar un adjunto sensible.
- **Eventos que consume:** ninguno
- **Funciones puras:** ninguna

## Alcance

- **Backend:** `GET /api/v1/members/{id}/attachments` (lista paginada de metadatos) y `GET /api/v1/attachments/{id}` (contenido, servido por el API con `Content-Type` del `mime` guardado y `Content-Disposition: attachment`).
- **Front:** pestaña Adjuntos con tabla (tipo, fecha, tamaño, quién subió) y botón Descargar.

## Criterios de aceptación

1. Ambos endpoints exigen rol `admin` o `coach`; socio recibe 403 en v0.3; sin token, 401.
2. La lista pagina con `limit` (1 a 200, por defecto 25) y `offset`, responde `{ items, total, limit, offset }` y nunca incluye el contenido ni el nombre en disco.
3. Cada descarga deja una fila de auditoría con usuario, `attachment_id` y socio; un adjunto sensible además emite `SensitiveFieldRevealed`.
4. La descarga de un adjunto sensible devuelve los bytes descifrados idénticos al original y deja una fila en `crypto_ops` con `verb = decrypt`.
5. Las respuestas de descarga llevan `Cache-Control: no-store` y `X-Content-Type-Options: nosniff`.
6. Un `id` inexistente devuelve 404; un adjunto de un socio dado de baja sigue descargable para admin y coach (evidencia legal).
7. Las fechas se muestran en hora de Bogotá.

## Escenarios BDD

```gherkin
# language: es
Característica: Adjuntos de la ficha del socio

  Escenario: El coach descarga la autorización de un socio
    Dado que inicié sesión como coach
    Y el socio "Andrés Ruiz" tiene una autorización en PDF
    Cuando abro la pestaña Adjuntos y descargo la autorización
    Entonces recibo el PDF original
    Y queda una fila de auditoría con mi usuario y el adjunto descargado

  Escenario: Un socio intenta descargar un adjunto por id
    Dado que inicié sesión con una cuenta de socio
    Cuando pido GET /api/v1/attachments/{id}
    Entonces recibo 403
```

## Endpoints

- `GET /api/v1/members/{id}/attachments` — rol(es): admin, coach — entrada: `kind?`, `limit`, `offset` — salida: `{ items: AttachmentOut[], total, limit, offset }` — códigos: 200, 401, 403, 404, 422
- `GET /api/v1/attachments/{id}` — rol(es): admin, coach — salida: bytes del archivo — códigos: 200, 401, 403, 404

## Pantalla

- `Socio_Ficha`, pestaña Adjuntos. Estados de carga, vacío ("este socio no tiene adjuntos") y error.

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** ninguna.
- **Funciones puras a probar:** ninguna.
- **Pruebas:** router (rol, cabeceras, 404), service con base real (auditoría, `crypto_ops`), front (tabla y descarga).
- **Archivos principales:** `api/src/app/modules/attachments/router.py`, `web/src/features/members/components/AttachmentsTab.tsx`.

## Supuestos

- Supuesto: la ruta de descarga es `GET /api/v1/attachments/{id}`; `ROUTES.md` solo nombra la pestaña `/attachments` del socio.

## Dependencias

- US-147 · Almacenamiento seguro de adjuntos
- US-073 · Ver ficha del socio (contenedor de pestañas)

## INVEST

- **Independiente:** lectura sobre lo ya almacenado.
- **Negociable:** columnas y vista previa.
- **Valiosa:** consulta controlada de evidencia legal.
- **Estimable:** dos endpoints y una pestaña.
- **Pequeña:** sí.
- **Testeable:** auditoría por descarga verificable.

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas de service con PostgreSQL real y de router en verde; cobertura de 80 % o más en lo tocado
- [ ] Front: pruebas de componente y página; sin colores literales
- [ ] `docs/openapi.json` regenerado
- [ ] Auditoría verificada
- [ ] Revisión de PR aprobada
