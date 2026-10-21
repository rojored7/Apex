# EP-11 · Auditoría y trazabilidad

- **Versión del plan:** v0.1 (Tarea 8 y `BRECHAS.md` sección 2, "Auditoría").
- **Bounded context:** Audit (soporte, esquema `audit`). El hook de escritura y la cadena de hashes nacen en EP-01; aquí se exponen la consulta y la verificación.
- **Estimación relativa:** M.

## Objetivo de negocio

Que el dueño pueda responder "quién hizo qué, cuándo y sobre qué registro" ante cualquier duda: un pago anulado, un socio dado de baja, una cédula consultada en claro. Y que pueda demostrar que ese historial no fue alterado (RN-16), lo que también sirve como evidencia frente a la Ley 1581.

## Actores

- Administrador: consulta la auditoría global y verifica la cadena.
- Administrador y coach: ven el historial de un socio en su ficha.
- CLI: `verify-audit` para verificar sin entrar al sistema.

## Capacidades incluidas

### Backend
- `audit.service.list` con filtros de rango de fechas, usuario, tabla (entidad), registro, acción (`insert`, `update`, `delete`, `reveal`, `export`, `login`, `verify`) y búsqueda `q`; paginado.
- `audit.service.verify()`: recorre toda la cadena; con más de 100.000 filas corre en segundo plano y devuelve el resultado de la última verificación.
- La verificación queda registrada como acción `verify`.
- Endpoints solo admin: `GET /audit`, `POST /audit/verify`. Historial por registro: `GET /members/{id}/audit` (admin y coach).
- `cli verify-audit`.
- Suscripción a `SensitiveFieldRevealed`, `UserLocked` y `SessionsRevoked` (y, desde v0.2, a los eventos de avisos).

### Front
- Pantalla de auditoría con filtros, tabla, detalle con antes y después (los campos cifrados se muestran como blob, nunca en claro) y botón "Verificar cadena" con el resultado.
- Pestaña Historial de la ficha del socio con `HistoryAside`.

## Fuera de alcance

- Firma nocturna de la cadena con ML-DSA (EP-17).
- Exportación de la auditoría.

## Criterios de éxito medibles

- Prueba de detección de una fila alterada a mano: la verificación señala el `seq` exacto donde se rompe (criterio de salida de la Tarea 8).
- Toda acción sobre tablas auditadas de v0.1 (socios, planes, membresías, pagos, usuarios, settings) aparece en la lista con usuario y fecha.
- Ningún valor en claro de un campo cifrado aparece en `before` o `after`.
- La verificación sobre 100.000 filas de prueba termina en menos de 60 segundos o queda en segundo plano sin bloquear el API.
- Un coach recibe 403 en `GET /audit` y 200 en el historial de un socio.

## Dependencias

- EP-01 Núcleo compartido (hook, cadena y trigger append-only).
- EP-04 Identidad y acceso (usuario de cada acción).
- EP-06 Layout y componentes compartidos del front.
- EP-07 Padrón de socios (pestaña Historial).

## Riesgos

- Crecimiento de la tabla: con 1.000 socios y operación diaria la cadena crece rápido; la verificación completa puede volverse lenta.
- Que se agregue una tabla nueva sin `__audited__ = True`; conviene una prueba de arquitectura con la lista de tablas que deben auditarse.

## Pantallas del diseño que habilita

- `Auditoria`, pestaña Historial de `Socio_Ficha`.
