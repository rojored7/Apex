# WODs y resultados: operación del día a día

Guía para quien opera el box. Cubre solo lo que cambia el procedimiento; el detalle del contrato
está en `docs/openapi.json`.

## Quién registra y quién corrige

- El coach registra el resultado de cada atleta desde la tablet (modo quiosco) o desde el panel.
  Cada resultado guarda su origen: «en tablet» (`kiosk`) o «en mesa» (`desk`); el origen queda a la
  vista en la ficha del socio y en «Todos los resultados» y no se puede cambiar.
- El coach corrige un resultado volviendo a registrarlo (`supersedes_id`): el anterior queda
  reemplazado y visible con `include_superseded`. En la tablet solo corrige lo que registró en esa
  misma clase.

## Me equivoqué de socio o de clase: anular un resultado (solo admin)

El coach no puede quitar un resultado ni la asistencia de un socio que ya lo tiene. Si el
resultado quedó en el socio o en la clase equivocada, lo anula un administrador:

1. Entrar al panel como admin y abrir el WOD (`/wods/<id>`), pestaña «Todos los resultados».
2. Elegir el resultado equivocado y anularlo con un motivo claro de 1 a 200 caracteres
   (`POST /api/v1/results/<id>/void` con `{"reason": "..."}`).
3. El resultado queda como `voided`: sale del leaderboard, de la ficha del socio y de la TV, pero
   se conserva con su marca, quién lo anuló, cuándo y por qué (también en la auditoría).
4. Con el resultado anulado, la asistencia equivocada ya se puede quitar y la clase ya se puede
   cancelar. Después se registra el resultado correcto, sin `supersedes_id`.

No hay forma de revertir una anulación: si fue un error, se registra de nuevo el resultado.
El motivo es texto libre: no escribas en él datos personales del socio.

## Dónde se ven los resultados y la TV desde el panel

- Ficha del socio, pestaña «Resultados»: sus marcas con el WOD, la fecha, el nivel y dónde se registró («En tablet» o «En recepción»). Un resultado pendiente dice «Por validar».
- Inicio, tarjeta «WOD de hoy»: «Ver» abre el detalle y «Registrar resultados» abre la tablet en la próxima clase de hoy que no ha terminado. Sin WOD, la tarjeta ofrece crearlo con la fecha de hoy.
- Configuración, pestaña «Pantalla de TV»: refresco, mostrar el ranking, generar un enlace nuevo y revocar el token (guía completa en `docs/operacion/tv.md`).
