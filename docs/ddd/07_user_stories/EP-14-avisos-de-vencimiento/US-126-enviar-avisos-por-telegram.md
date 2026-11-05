# US-126 · Como administrador quiero recibir en el chat del equipo, por Telegram, el resumen diario de avisos y las alertas del worker para enterarme sin entrar al sistema

> **Corregido en S5-W0-1** (`docs/ddd/blueprints/sprint-05-plan.md`, sección 1; `docs/ddd/DECISIONES.md`, "Sprint 5"): G-08 resuelta: Telegram es un `TelegramAlertSink` en `core/alerts_telegram.py` registrado desde `main.py` y `worker/main.py`; el chat va en `TELEGRAM_CHAT_ID` (`.env.ops`), no en `settings.channels`; `alert(code, **context)` con claves cerradas (S5-D29, S5-D58, S5-D78). Estado: READY.
>
> **Corregido en S5-V11c** (`docs/ddd/DECISIONES.md`, S5-D206, S5-D268): el criterio 3 cambia; Telegram es un canal interno de mejor esfuerzo con cola acotada y deduplicación, sin la política de reintentos del correo al socio; el resumen se regenera al día siguiente. `telegram.enabled` de Configuración apaga el envío (S5-D265).

- **Épica:** EP-14 · Avisos de vencimiento
- **Bounded context:** `core/alerts.py` y `core/alerts_telegram.py` (alerta interna, N-34; S5-D29)
- **Versión:** v0.2
- **Actor:** administrador
- **Tamaño:** 3
- **Prioridad:** P2 mejora
- **Refinamiento:** Criterios completos; BDD solo de flujo principal
- **Pantalla:** Ninguna

## Historia

Como administrador
quiero que el resumen diario de "por avisar hoy" y las alertas del worker (backup fallido, firma atrasada, OpenBao sellado) se envíen al chat del equipo por el bot del gimnasio
para enterarme sin revisar el sistema

## Contexto de dominio

- **Aggregate / entidades:** ninguno; adaptador `TelegramAlertSink` del puerto `AlertSink` (G-08).
- **Reglas que aplica:** licencias (`httpx` directo; prohibido `python-telegram-bot` por LGPL); Q12 (token solo en `.env`); auditoría de envío.
- **Eventos que emite:** ninguno (no crea filas de `Notification`, N-34)
- **Eventos que consume:** ninguno
- **Funciones puras:** `alerts_telegram.render_message(code, context, front_base_url) -> str`

## Alcance

- **Backend:** `TelegramAlertSink` con `httpx` a `https://api.telegram.org/bot<token>/sendMessage`, registrado en `core/alerts.py` (G-08) al arrancar el worker.
- **Front:** No aplica.

## Criterios de aceptación

1. El resumen diario y cada alerta interna se envían con `chat_id` igual a `TELEGRAM_CHAT_ID` (`.env.ops`); respuesta `ok: true` deja el envío registrado en el log.
2. Una respuesta `ok: false`, un 4xx/5xx o un timeout deja el envío registrado como fallido en el log, sin el token del bot ni la URL completa.
3. Los reintentos siguen la misma política de US-125.
4. El token se lee de `TELEGRAM_BOT_TOKEN` en `.env`; nunca se guarda en base, auditoría ni logs.
5. El chequeo de licencias de CI falla si aparece `python-telegram-bot` en las dependencias.
6. Timeout explícito de 10 s por llamada.

## Escenarios BDD

```gherkin
# language: es
Característica: Alertas internas por Telegram

  Escenario: Enviar el resumen al chat del equipo
    Dado que el chat del equipo está configurado
    Y hay un resumen diario pendiente de enviar
    Cuando el worker corre la fase de envío
    Entonces el resumen queda enviado al chat del equipo

  Escenario: Token inválido
    Dado que Telegram responde 401 por token inválido
    Cuando el worker corre la fase de envío
    Entonces el envío queda registrado como fallido
    Y el error registrado no contiene el token
```

## Endpoints

- Ninguno (salida HTTP a la API de Telegram).

## Pantalla

- Ninguna.

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** ninguno.
- **Funciones puras a probar:** `build_payload` con texto con caracteres especiales.
- **Pruebas:** canal con `httpx.MockTransport`; prueba de que el token no aparece en logs.
- **Archivos principales:** `api/src/app/core/alerts_telegram.py`.

## Supuestos

- Supuesto: el chat del equipo y el token viven en `.env` (`TELEGRAM_BOT_TOKEN` y `TELEGRAM_CHAT_ID`, en `.env.ops`), no en `settings.channels`, porque Telegram es canal interno y no de socio (N-34). Las alertas no crean filas de `Notification`.

## Dependencias

- US-125 · Enviar avisos por correo (fase de envío y política de reintentos)

## INVEST

- **Independiente:** solo agrega un adaptador.
- **Negociable:** destino del mensaje.
- **Valiosa:** segundo canal automático.
- **Estimable:** una llamada HTTP.
- **Pequeña:** 3.
- **Testeable:** con transporte simulado.

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas del canal en verde; cobertura de 80 % o más en lo tocado
- [ ] Licencias verificadas en CI
- [ ] Revisión de PR aprobada
