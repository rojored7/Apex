# US-152 · Como administrador quiero que el sistema se sirva por HTTPS con TLS automático e intercambio híbrido post-cuántico para usarlo desde fuera del local sin que las contraseñas ni los datos viajen en claro

- **Épica:** EP-20 · Acceso cifrado con TLS híbrido
- **Bounded context:** ninguno de negocio (borde: `caddy` delante de `nginx`, `infra/`)
- **Versión:** v0.3
- **Actor:** administrador
- **Tamaño:** 5
- **Prioridad:** P1 necesaria para la versión
- **Refinamiento:** Criterios completos; BDD solo de flujo principal
- **Pantalla:** Ninguna (historia sin front)

## Historia

Como administrador
quiero que, cuando configuro un dominio, el sistema obtenga y renueve solo su certificado y negocie `X25519MLKEM768`
para entrar desde mi celular fuera del gimnasio con el tráfico protegido hoy y frente a un descifrado futuro

## Contexto de dominio

- **Aggregate / entidades:** ninguno.
- **Reglas que aplica:** P7 (solo LAN en v0.1; Caddy con TLS en v0.3 cuando haya dominio; Caddy es opcional); `04_architecture_decision.md` sección 4 (TLS automático, X25519MLKEM768); licencias permitidas (Caddy Apache 2.0, sin módulos con licencia prohibida); nada de secretos en imagen.
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** ninguna

## Alcance

- **Backend:** servicio `caddy` en `infra/compose.yml` bajo un perfil `tls` (por ejemplo `docker compose --profile tls up`), `infra/caddy/Caddyfile` con `{$APEX_DOMAIN}`, `curves x25519mlkem768 x25519`, proxy a `nginx:80`, volúmenes `caddy_data` y `caddy_config`; variables `APEX_DOMAIN` y `ACME_EMAIL` en `.env.example`; prueba con el CA de staging de Let's Encrypt.
- **Front:** No aplica.

## Criterios de aceptación

1. Con `APEX_DOMAIN` configurado y el perfil `tls` activo, Caddy obtiene un certificado y sirve el front y `/api/v1` por HTTPS en el puerto 443.
2. Un cliente con soporte (por ejemplo OpenSSL 3.5 o un navegador actual) negocia el grupo `X25519MLKEM768` (verificable con `openssl s_client -groups X25519MLKEM768`).
3. Un cliente sin soporte híbrido cae a `X25519` y la conexión funciona.
4. Solo se aceptan TLS 1.2 y 1.3; TLS 1.0 y 1.1 se rechazan.
5. La renovación funciona contra el CA de staging sin intervención (prueba documentada); los certificados persisten en el volumen `caddy_data` entre reinicios.
6. Nginx deja de publicar el puerto 80 al host cuando el perfil `tls` está activo; solo Caddy expone 80 y 443.
7. La imagen de Caddy usada es la oficial sin módulos adicionales, y su licencia queda en `NOTICE`.
8. Una prueba de SSL Labs o equivalente con el dominio real da calificación A o superior (evidencia adjunta al PR o al runbook).

## Escenarios BDD

```gherkin
# language: es
Característica: TLS automático con intercambio híbrido

  Escenario: Conexión segura desde fuera del gimnasio
    Dado que el administrador configuró el dominio "box.apex.co" y activó el perfil tls
    Cuando abro "https://box.apex.co/login" desde un navegador actual
    Entonces la conexión usa TLS 1.3 con el grupo X25519MLKEM768
    Y veo la pantalla de acceso

  Escenario: Cliente sin soporte post-cuántico
    Dado un cliente que solo ofrece X25519
    Cuando se conecta a "https://box.apex.co"
    Entonces la conexión se establece con X25519
```

## Endpoints

- Ninguno nuevo (es el borde de red).

## Pantalla

- Ninguna.

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** ninguna.
- **Funciones puras a probar:** ninguna.
- **Pruebas:** smoke en `compose.dev.yml` con un dominio local y la CA interna de Caddy; script `scripts/workflow/tls-smoke.sh` que comprueba el grupo negociado.
- **Archivos principales:** `infra/compose.yml`, `infra/caddy/Caddyfile`, `.env.example`, `docs/runbooks/tls.md`.

## Supuestos

- Supuesto: la versión de Caddy elegida ya soporta `x25519mlkem768` en la directiva `curves` (Caddy 2.10 o superior); si no, la historia se bloquea hasta actualizar.
- Supuesto: el dominio y el reenvío de puertos del router del gimnasio los configura el operador fuera del sistema.

## Dependencias

- US-038 · Cabeceras de seguridad y CSP (Nginx detrás de Caddy)
- US-005 · Dockerfile del API y Compose

## INVEST

- **Independiente:** es una capa de borde opcional.
- **Negociable:** perfil de Compose y versión de Caddy.
- **Valiosa:** condición para el portal desde fuera (EP-25).
- **Estimable:** configuración y pruebas de red.
- **Pequeña:** sí.
- **Testeable:** grupo negociado y versiones de TLS verificables.

## Definición de terminado

- [ ] Compose valida (`docker compose config`) con y sin el perfil `tls`
- [ ] Smoke de TLS en verde
- [ ] Chequeo de licencias en verde y `NOTICE` actualizado
- [ ] Runbook de TLS escrito
- [ ] Revisión de PR aprobada
