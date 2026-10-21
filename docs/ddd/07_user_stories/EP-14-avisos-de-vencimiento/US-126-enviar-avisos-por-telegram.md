# US-126 · Como administrador quiero recibir en el chat del equipo, por Telegram, el resumen diario de avisos y las alertas del worker para enterarme sin entrar al sistema

- **Épica:** EP-14 · Avisos de vencimiento
- **Bounded context:** Notifications (`channels/telegram.py`) y `core/alerts.py` (alerta interna, N-34)
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
- **Funciones puras:** `telegram.build_payload(chat_id, text) -> dict`

## Alcance

- **Backend:** `TelegramAlertSink` con `httpx` a `https://api.telegram.org/bot<token>/sendMessage`, registrado en `core/alerts.py` (G-08) al arrancar el worker.
- **Front:** No aplica.

## Criterios de aceptación

1. El resumen diario y cada alerta interna se envían con `chat_id` igual al chat del equipo configurado en `.env` (supuesto); respuesta `ok: true` deja el envío registrado en el log.
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
- **Archivos principales:** `api/src/app/modules/notifications/channels/telegram.py`.

## Supuestos

- Supuesto: el chat del equipo y el token viven en `.env` (`TELEGRAM_BOT_TOKEN` y un identificador de chat de alertas, nombre a fijar en US-011), no en `settings.channels`, porque Telegram es canal interno y no de socio (N-34). Las alertas no crean filas de `Notification`.

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
