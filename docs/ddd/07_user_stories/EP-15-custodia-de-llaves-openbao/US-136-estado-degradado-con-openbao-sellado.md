# US-136 · Como administrador quiero que el sistema me diga claramente cuando OpenBao está sellado para saber que debo desellarlo en lugar de ver errores confusos

- **Épica:** EP-15 · Custodia de llaves con OpenBao
- **Bounded context:** Crypto y `core` (`main.py`, `/health`)
- **Versión:** v0.2
- **Actor:** administrador
- **Tamaño:** 3
- **Prioridad:** P1 necesaria para la versión
- **Refinamiento:** Criterios completos; BDD solo de flujo principal
- **Pantalla:** Ninguna (historia sin front; el estado se ve en `/health`)

## Historia

Como administrador
quiero que el api arranque en un estado degradado explícito cuando OpenBao está sellado y se recupere solo cuando lo deselle
para no perder el sistema completo ni tener que reiniciarlo a mano

## Contexto de dominio

- **Aggregate / entidades:** CryptoKey (DEK no disponibles mientras está sellado).
- **Reglas que aplica:** criterio de EP-15 "con OpenBao sellado, el API arranca en un estado degradado y explícito (`/health` lo reporta) en lugar de fallar en silencio"; RN-13 (nunca se sirve un dato cifrado sin descifrar como si fuera claro).
- **Eventos que emite:** ninguno.
- **Eventos que consume:** ninguno.
- **Funciones puras:** `crypto.health_state(provider_status, deks_loaded) -> "ok" | "sealed" | "unreachable"`.

## Alcance

- **Backend:** al arrancar, si OpenBao responde sellado o no responde, el api arranca sin DEK en memoria, `GET /health` responde 503 con `crypto: "sealed"` o `"unreachable"` y `db: "ok"`; toda operación que necesite el bus responde 503 con `error.code = "crypto_unavailable"` y mensaje en español; las rutas que no usan datos cifrados siguen funcionando (por ejemplo listas de planes). Un sondeo cada 30 s intenta desenvolver las DEK y, al lograrlo, el estado pasa a `ok` sin reiniciar. El worker omite los jobs que usan el bus mientras esté sellado y lo registra.
- **Front:** No aplica (el envelope `crypto_unavailable` lo muestra el cliente como error genérico existente).

## Criterios de aceptación

1. Con OpenBao sellado, el api arranca y `GET /health` responde 503 con `crypto: "sealed"`.
2. Con OpenBao sellado, `GET /api/v1/members/{id}` responde 503 con `error.code = "crypto_unavailable"` y nunca devuelve un blob como si fuera el valor.
3. Con OpenBao sellado, `GET /api/v1/plans` (sin datos cifrados) responde 200.
4. Al desellar OpenBao, en máximo 30 s el api desenvuelve las DEK y `GET /health` vuelve a 200 con `crypto: "ok"` sin reiniciar el contenedor.
5. El worker no ejecuta jobs que usan el bus mientras está sellado y registra el motivo; los ejecuta en el siguiente ciclo.
6. El log del api registra el cambio de estado (`sealed` → `ok`) una vez por transición, sin datos sensibles.

## Escenarios BDD

```gherkin
# language: es
Característica: Estado degradado con OpenBao sellado

  Escenario: Arrancar con OpenBao sellado
    Dado OpenBao sellado
    Cuando arranca el api
    Entonces "/health" responde 503 con "crypto" igual a "sealed"
    Y consultar la ficha de un socio responde 503 con código "crypto_unavailable"
    Y listar planes responde 200

  Escenario: Recuperación al desellar
    Dado el api en estado "sealed"
    Cuando el administrador desella OpenBao
    Entonces en máximo 30 segundos "/health" responde 200 con "crypto" igual a "ok"
```

## Endpoints

- `GET /api/v1/health` — rol: público — salida: `{ status, db, crypto, backup }` — códigos: 200, 503.
- Cualquier ruta que use el bus — códigos adicionales: 503 `crypto_unavailable`.

## Pantalla

- Ninguna.

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** no aplica.
- **Funciones puras a probar:** `health_state` con sus tres salidas.
- **Pruebas:** integración con OpenBao real sellado y desellado; router de `/health` y de una ruta de socios.
- **Archivos principales:** `api/src/app/main.py`, `api/src/app/core/crypto/bus.py`, `api/src/app/core/errors.py`.

## Supuestos

- Supuesto: con el bus sellado `/health` responde 503 (el api no puede servir su función principal), aunque US-115 deja el campo `backup` como informativo con 200.
- Supuesto: sondeo de recuperación cada 30 s.

## Dependencias

- US-134 · Proveedor OpenBao.
- US-020 · create_app, migraciones y health.
- US-020 · /health (esta historia agrega el campo crypto; agregado en consolidación)

## INVEST

- **Independiente:** cambia el arranque y el health sin tocar módulos.
- **Negociable:** intervalo de sondeo y códigos.
- **Valiosa:** un reinicio del servidor no deja al operador adivinando.
- **Estimable:** estados enumerados.
- **Pequeña:** arranque, health y un error.
- **Testeable:** sellar y desellar en integración.

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas de integración sellado/desellado en verde
- [ ] `docs/openapi.json` regenerado
- [ ] Revisión de PR aprobada
