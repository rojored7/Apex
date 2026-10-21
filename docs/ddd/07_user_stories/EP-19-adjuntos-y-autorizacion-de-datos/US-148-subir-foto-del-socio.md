# US-148 · Como coach quiero subir la foto del socio al crearlo o editarlo para reconocerlo en recepción y en el check-in

- **Épica:** EP-19 · Adjuntos y autorización de tratamiento de datos
- **Bounded context:** Attachments (+ Members como cliente)
- **Versión:** v0.3
- **Actor:** administrador, coach
- **Tamaño:** 3
- **Prioridad:** P2 mejora
- **Refinamiento:** Criterios completos; BDD solo de flujo principal
- **Pantalla:** `Socio_Form` (`/socios/nuevo`, `/socios/:id/editar`, campo foto)

## Historia

Como coach o administrador
quiero subir la foto del socio desde su formulario
para reconocerlo de un vistazo en la ficha y en recepción

## Contexto de dominio

- **Aggregate / entidades:** `Attachment(kind = photo)`, `Member`.
- **Reglas que aplica:** 5 MB, bytes mágicos, nombre aleatorio (US-147); RN-15 (rol); la foto no es sensible por defecto.
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** las de US-147

## Alcance

- **Backend:** `POST /api/v1/members/{id}/attachments` con `kind=photo` (multipart); la foto vigente es la más reciente de `kind = photo`; `GET /api/v1/members/{id}` incluye `photo_attachment_id`.
- **Front:** control de foto en `Socio_Form` con vista previa, mensaje de error de tamaño o tipo, y miniatura en el encabezado de `Socio_Ficha`.

## Criterios de aceptación

1. Admin y coach pueden subir; socio recibe 403; sin token, 401.
2. Una foto JPEG o PNG de hasta 5 MB responde 201 con `{ id, kind, mime, size_bytes, created_at }` y queda como foto vigente del socio.
3. Un PDF con `kind=photo` o un archivo de más de 5 MB devuelve 422 con `field: "file"` y el formulario muestra el error sin perder el resto de los datos.
4. Subir a un socio inexistente o dado de baja devuelve 404.
5. La foto se sirve solo por el API (`GET /api/v1/attachments/{id}` de US-150), nunca por una ruta estática de Nginx.
6. Subir una foto nueva no borra la anterior; la anterior deja de ser la vigente.
7. La subida queda auditada con el usuario.

## Escenarios BDD

```gherkin
# language: es
Característica: Foto del socio

  Escenario: El coach sube la foto al editar un socio
    Dado que inicié sesión como coach
    Y estoy editando al socio "Laura Gómez"
    Cuando adjunto una foto JPEG de 1,2 MB y guardo
    Entonces veo la foto en la ficha de "Laura Gómez"
    Y la subida queda en la auditoría con mi usuario

  Escenario: Foto demasiado pesada
    Dado que estoy editando un socio
    Cuando adjunto una imagen de 6 MB
    Entonces veo "La foto supera 5 MB" junto al campo foto
    Y los demás datos del formulario se conservan
```

## Endpoints

- `POST /api/v1/members/{id}/attachments` — rol(es): admin, coach — entrada: multipart `file`, `kind=photo` — salida: `AttachmentOut` — códigos: 201, 401, 403, 404, 413, 422

## Pantalla

- `Socio_Form`, campo foto (vista previa y errores); encabezado de `Socio_Ficha` con la miniatura. Al crear, la foto se sube después del `POST /members` exitoso con el `id` devuelto.

## Notas técnicas

- **Migración:** no (usa la tabla de US-147).
- **Trigger / restricciones:** ninguna nueva.
- **Funciones puras a probar:** ninguna nueva.
- **Pruebas:** router (rol, tipos, tamaño, 404), front (vista previa, error, orden crear-luego-subir).
- **Archivos principales:** `api/src/app/modules/attachments/router.py`, `web/src/features/members/components/PhotoField.tsx`.

## Supuestos

- Supuesto: si la creación del socio funciona y la subida de la foto falla, el socio queda creado sin foto y el formulario lo informa (no hay transacción entre ambas peticiones).

## Dependencias

- US-147 · Almacenamiento seguro de adjuntos
- US-075 · Editar socio (formulario de edición)

## INVEST

- **Independiente:** solo agrega un campo al formulario existente.
- **Negociable:** recorte y tamaño de la miniatura.
- **Valiosa:** reconocer al socio en recepción.
- **Estimable:** un endpoint y un campo.
- **Pequeña:** sí.
- **Testeable:** tipos y tamaños verificables.

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas de router en verde; cobertura de 80 % o más en lo tocado
- [ ] Front: pruebas de componente y página; sin colores literales
- [ ] `docs/openapi.json` regenerado
- [ ] Revisión de PR aprobada
