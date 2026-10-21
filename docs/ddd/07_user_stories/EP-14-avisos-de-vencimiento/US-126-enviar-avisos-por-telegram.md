# US-126 · Como administrador quiero enviar avisos por Telegram para llegar a los socios que prefieren ese canal

- **Épica:** EP-14 · Avisos de vencimiento
- **Bounded context:** Notifications (`channels/telegram.py`)
- **Versión:** v0.2
- **Actor:** administrador
- **Tamaño:** 3
- **Prioridad:** P2 mejora
- **Refinamiento:** Criterios completos; BDD solo de flujo principal
- **Pantalla:** Ninguna

## Historia

Como administrador
quiero que los avisos con canal `telegram` se envíen por el bot del gimnasio
para cubrir a los socios que no leen el correo

## Contexto de dominio

- **Aggregate / entidades:** `Notification`; adaptador `TelegramChannel` del puerto `NotificationChannel`.
- **Reglas que aplica:** licencias (`httpx` directo; prohibido `python-telegram-bot` por LGPL); Q12 (token solo en `.env`); auditoría de envío.
- **Eventos que emite:** `NotificationSent`, `NotificationFailed`
- **Eventos que consume:** ninguno
- **Funciones puras:** `telegram.build_payload(chat_id, text) -> dict`

## Alcance

- **Backend:** `TelegramChannel` con `httpx` a `https://api.telegram.org/bot<token>/sendMessage`, registrado en la fase de envío de US-125.
- **Front:** No aplica.

## Criterios de aceptación

1. Un aviso `pending` con `channel = telegram` se envía con `chat_id` igual a `settings.channels.telegram.default_chat_id`; respuesta `ok: true` deja `sent` y emite `NotificationSent`.
2. Una respuesta `ok: false`, un 4xx/5xx o un timeout deja `failed` con `last_error` que no contiene el token del bot ni la URL completa; emite `NotificationFailed`.
3. Los reintentos siguen la misma política de US-125.
4. El token se lee de `TELEGRAM_BOT_TOKEN` en `.env`; nunca se guarda en base, auditoría ni logs.
5. El chequeo de licencias de CI falla si aparece `python-telegram-bot` en las dependencias.
6. Timeout explícito de 10 s por llamada.

## Escenarios BDD

```gherkin
# language: es
Característica: Avisos por Telegram

  Escenario: Enviar un aviso por Telegram
    Dado que Telegram está habilitado con un chat por defecto
    Y hay un aviso pendiente por Telegram
    Cuando el worker corre la fase de envío
    Entonces el aviso queda "sent"

  Escenario: Token inválido
    Dado que Telegram responde 401 por token inválido
    Cuando el worker corre la fase de envío
    Entonces el aviso queda "failed"
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
- **Pruebas:** canal con `httpx.MockTransport`; prueba de que el token no aparece en `last_error` ni en logs.
- **Archivos principales:** `api/src/app/modules/notifications/channels/telegram.py`.

## Supuestos

- Supuesto: en v0.2 los avisos por Telegram van al `default_chat_id` del gimnasio (un grupo o canal interno), porque el modelo no guarda un `chat_id` por socio. Si se quiere enviar al socio directo, hace falta un campo nuevo en Members (pregunta abierta).

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
