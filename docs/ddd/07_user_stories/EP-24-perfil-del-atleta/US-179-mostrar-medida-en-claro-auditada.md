# US-179 · Como coach quiero mostrar en claro una medida corporal con registro de auditoría para ver el dato real sin perder la trazabilidad

- **Épica:** EP-24 · Perfil del atleta
- **Bounded context:** Athletes (esquema `athletes`)
- **Versión:** v0.6
- **Actor:** administrador, coach
- **Tamaño:** 2
- **Prioridad:** P1 necesaria para la versión
- **Refinamiento:** Criterios completos; BDD solo de flujo principal
- **Pantalla:** `Atleta_Perfil` (`/socios/:id/atleta`, subpestañas Resumen y Medidas, `MaskedValue`)

## Historia

Como coach
quiero pulsar "mostrar" sobre una medida enmascarada y ver su valor real
para conversar con el socio sobre su progreso dejando constancia de quién vio el dato

## Contexto de dominio

- **Aggregate / entidades:** `BodyMetric`.
- **Reglas que aplica:** RN-13 (mostrar en claro se audita), Q6 (reveal para admin y coach, siempre auditado con campo y usuario), RN-15.
- **Eventos que emite:** `SensitiveFieldRevealed(member_id, field, user_id)` (con `field` del tipo `body_metric.weight_kg`)
- **Eventos que consume:** ninguno
- **Funciones puras:** ninguna

## Alcance

- **Backend:** `athletes.service.reveal_metric(metric_id, field, by)` descifra un único campo por el bus, emite `SensitiveFieldRevealed`; Audit (US-107) lo registra como acción `reveal`.
- **Front:** `MaskedValue` de la subpestaña Medidas llama al endpoint y muestra el valor durante la sesión de la vista; al salir de la pantalla vuelve a enmascarar.

## Criterios de aceptación

1. `POST /api/v1/athletes/{member_id}/metrics/{metric_id}/reveal` con `{ field }` y rol admin o coach responde 200 con `{ field, value }` del único campo pedido.
2. `field` solo admite `weight_kg`, `height_cm`, `body_fat_pct` o `notes`; otro valor devuelve 422 con `field = field`.
3. Cada llamada exitosa deja exactamente una fila de auditoría `reveal` con `user_id`, `table_name = body_metrics`, `record_id` y el nombre del campo, y una fila en `crypto_ops` con verbo `decrypt`; el valor en claro no aparece en la auditoría ni en los logs.
4. Abrir la subpestaña sin pulsar "mostrar" no deja ninguna fila `reveal`.
5. Una medición que no pertenece al `member_id` de la ruta devuelve 404 (sin revelar su existencia).
6. Rol `member` recibe 403; sin token, 401.
7. Un campo nulo en la medición responde 200 con `value = null` y no deja fila `reveal`.

## Escenarios BDD

```gherkin
# language: es
Característica: Mostrar en claro una medida auditada

  Escenario: El coach revela el peso de una medición
    Dado que la socia "Laura Gómez" tiene una medición con peso enmascarado
    Y que el coach "Pedro" está en la subpestaña Medidas
    Cuando pulsa "mostrar" sobre el peso
    Entonces ve "62,5 kg"
    Y la auditoría registra que "Pedro" reveló "weight_kg" de esa medición

  Escenario: Campo no permitido
    Cuando se pide revelar el campo "member_id" de la medición
    Entonces el sistema responde con error de validación en "field"
    Y no se registra ningún reveal
```

## Endpoints

- `POST /api/v1/athletes/{member_id}/metrics/{metric_id}/reveal` — rol(es): admin, coach — entrada: `{ field }` — salida: `{ field, value }` — códigos: 200, 401, 403, 404, 422

## Pantalla

- `Atleta_Perfil`: `MaskedValue` en la tabla de Medidas y en el resumen de peso actual. Estado de error si la llamada falla ("No se pudo mostrar el dato").

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** ninguno.
- **Funciones puras a probar:** ninguna; se prueba el service.
- **Pruebas:** service con base real (una fila `reveal`, una `crypto_ops`); router (roles, 404 cruzado, 422); prueba de logs sin valor en claro; Vitest de `MaskedValue` conectado.
- **Archivos principales:** `api/src/app/modules/athletes/service.py`, `router.py`; `web/src/features/athletes/components/`.

## Supuestos

- Supuesto: el endpoint de reveal de medidas no está en el contrato; se define con la misma forma que `POST /members/{id}/reveal` anidado a la medición.

## Dependencias

- US-178 · Registrar medidas corporales cifradas (existen medidas)
- US-074 · Mostrar dato sensible auditado (patrón de reveal y suscripción de auditoría)

## INVEST

- **Independiente:** solo agrega un endpoint sobre medidas existentes.
- **Negociable:** qué campos se pueden revelar.
- **Valiosa:** permite usar el dato sin romper RN-13.
- **Estimable:** reutiliza el patrón de reveal de socios.
- **Pequeña:** un endpoint y una conexión de componente.
- **Testeable:** fila `reveal` exacta y ausencia en logs.

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas de service con PostgreSQL real en verde; cobertura de 80 % o más en lo tocado
- [ ] Pruebas de router: rol, validación y envelope de error
- [ ] Front: pruebas de componente; sin colores literales
- [ ] `docs/openapi.json` regenerado
- [ ] Auditoría verificada para las tablas tocadas
- [ ] Revisión de PR aprobada
