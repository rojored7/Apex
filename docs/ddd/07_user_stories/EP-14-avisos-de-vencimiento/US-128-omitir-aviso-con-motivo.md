# US-128 · Como coach quiero omitir un aviso con motivo para no molestar a un socio que ya sé que va a renovar y dejar el porqué registrado

- **Épica:** EP-14 · Avisos de vencimiento
- **Bounded context:** Notifications (esquema `notifications`)
- **Versión:** v0.2
- **Actor:** administrador, coach
- **Tamaño:** 2
- **Prioridad:** P1 necesaria para la versión
- **Refinamiento:** Criterios completos; BDD solo de flujo principal
- **Pantalla:** `PorAvisarHoy` (`/avisos/hoy`, modal Omitir)

## Historia

Como coach o administrador
quiero marcar un aviso como omitido escribiendo el motivo
para cerrar la lista del día sin enviar mensajes innecesarios y que quede constancia de la decisión

## Contexto de dominio

- **Aggregate / entidades:** `Notification`.
- **Reglas que aplica:** `skip` exige motivo (`02_domain_model.md` 2.10); auditoría de `NotificationSkipped`.
- **Eventos que emite:** `NotificationSkipped`
- **Eventos que consume:** ninguno
- **Funciones puras:** `notifications.can_skip(status) -> bool`

## Alcance

- **Backend:** `POST /notifications/{id}/skip`.
- **Front:** `ConfirmModal` con campo de motivo en `PorAvisarHoy`.

## Criterios de aceptación

1. `POST /api/v1/notifications/{id}/skip` con `reason` no vacío (tras recortar espacios, 3 a 500 caracteres) marca `status = skipped`, `skip_reason`, `sent_by` = usuario y emite `NotificationSkipped` (auditado).
2. Sin `reason` o con texto vacío responde 422 con `field = reason`.
3. Solo se omiten avisos `pending` o `failed`; uno `sent` o `skipped` responde 409.
4. Un aviso omitido desaparece de `GET /notifications/today` y aparece en el historial.
5. Admin y coach pueden omitir; un socio recibe 403.

## Escenarios BDD

```gherkin
# language: es
Característica: Omitir aviso

  Escenario: Omitir con motivo
    Dado que inicié sesión como coach
    Y hay un aviso pendiente para Juan Ríos
    Cuando lo omito con el motivo "Renueva el viernes, habló en recepción"
    Entonces el aviso queda "skipped" con ese motivo
    Y ya no aparece en "Por avisar hoy"

  Escenario: Omitir sin motivo
    Dado que inicié sesión como coach
    Cuando omito un aviso sin escribir motivo
    Entonces la respuesta es 422 con "field" igual a "reason"
```

## Endpoints

- `POST /api/v1/notifications/{id}/skip` — rol(es): admin, coach — entrada: `{ reason }` — códigos: 200, 401, 403, 404, 409, 422

## Pantalla

- `PorAvisarHoy`, modal Omitir: campo de motivo obligatorio, botón deshabilitado mientras esté vacío, mensaje de error del API en el campo.

## Notas técnicas

- **Migración:** no.
- **Funciones puras a probar:** `can_skip` para los cuatro estados.
- **Pruebas:** pura; service y router (422, 409, 403); Vitest del modal; E2E compartido con US-127.
- **Archivos principales:** `api/src/app/modules/notifications/service.py`, `web/src/features/notifications/components/SkipModal.tsx`.

## Supuestos

- Supuesto: longitud del motivo de 3 a 500 caracteres; no está definida.

## Dependencias

- US-127 · Por avisar hoy y enlace de WhatsApp

## INVEST

- **Independiente:** una acción sobre la cola.
- **Negociable:** longitud del motivo.
- **Valiosa:** cierra el ciclo diario.
- **Estimable:** un endpoint y un modal.
- **Pequeña:** 2.
- **Testeable:** 422 y 409 binarios.

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas de service y router en verde; cobertura de 80 % o más en lo tocado
- [ ] Front: prueba del modal; sin colores literales
- [ ] Auditoría verificada
- [ ] Revisión de PR aprobada
