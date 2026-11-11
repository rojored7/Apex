# Verificación acotada del plan del Sprint 6 (ronda 3, `sprint-06-plan.md` en `53b7e36`)

Fecha: 2026-11-11. Agente: plan-critic (Fable, solo lectura). No es una tercera crítica completa (el flujo admite dos): verifica que las enmiendas E10..E13, M1 y M2 de la crítica 2 están aplicadas como decidió el orquestador. El agente no tenía herramienta de escritura: el orquestador volcó el informe y añadió la corrección final.

## Veredicto: APROBADO CON OBSERVACIONES (una inconsistencia de E12, corregida por el orquestador antes del gate)

## Enmiendas

- **E10 aplicada.** `migrate-provider` sigue excluyendo `sign` y sale 2 `signatures_reference_key` (l.559, l.255, l.1216); el código lo confirma (`core/crypto/migration.py:6,52`, S5-D183). El cambio de proveedor de la firma es `rotate-key audit.signature --provider` (l.560, l.1216). `crypto_keys.public_key` va en `0021` con CHECK (l.177). Sin `unavailable` ni muestreo (l.3, l.142, l.180, l.223, l.254). La prueba nueva de rotación de proveedor está en el paso 44 (l.560) e incluye verificar una firma antigua por `key_id` sin llamadas al proveedor. El paso 44 está reescrito y la contradicción 16 citada en §12.
- **E11 aplicada (l.462, l.466).** `real-ip.conf` en `${DEPLOY_STATE_DIR}`, montado por `APEX_REAL_IP_CONF` con el `.conf` versionado por defecto; `test_deploy_script.sh` exige `git status --porcelain` vacío, cubre la IP por defecto y que no toca `infra/nginx/`.
- **E12 aplicada en la lógica, con una contradicción (l.352, l.1194):** sin `staging`; la tabla del puerto exige `ALLOW_DOMAIN_PORT=true`, host `*.localhost` y `APEX_TLS_ISSUER=internal`, y falla en producción con otro host; prueba en el paso 7 (W0-5.1). La contradicción se describe en Observaciones 1.
- **E13 aplicada (l.220, l.382, l.462, l.1056).** Corte por trozos, `Content-Length` falso, `chunked` e iterador infinito por ASGI sin Nginx; a través de Nginx, 5.242.881 → 413 del api (el `5m` global no corta antes porque el location específico manda) y 6 MiB → 413 de Nginx; tmpfs `/var/cache/nginx` con `size=64m` exigido en `test_compose_config.sh`. `infra/nginx/default.conf:30` tiene hoy `client_max_body_size 5m` global.
- **M1 aplicada (l.465, l.1196).** `test_caddyfile.sh` comprueba que `/.well-known/acme-challenge/x` no da 308; el ACME real con dominio queda como paso humano en `tls.md`.
- **M2 aplicada (l.462), contrastada con `infra/compose.yml`.** Tienen `cap_drop` los nueve servicios que lista el paso 27 (`api`, `backup`, `dbsetup`, `migrate`, `openbao-bootstrap`, `openbao`, `tools`, `web`, `worker`; grep: 9 coincidencias); `db` (l.20) no lo tiene y lo gana con cinco capacidades; `caddy` nace con `NET_BIND_SERVICE`. Con `caddy` son 11 servicios.
- **Numeración continua (150 pasos).** 150 cabeceras `**Paso N ·`; la suma por slice en §12 da 150 (33 de Wave 0, 23 de A, 19 de B, 32 de C, 15 de R1 y E1, 28 de front). §10 y §11 al día.

## Observaciones

1. **[Corregida antes del gate] `APEX_TLS_ISSUER` contradecía a E12.** E12 y §11.9 decían que el api lee `APEX_TLS_ISSUER`, pero D77 (l.225-226) y el paso 7 (l.352, l.357) la dejan en `.env.ops.example` y `NON_API_ENV_VARS` solo para `caddy`, y el paso 8 no la pasa al `environment` del `api`; con `extra="forbid"` el validador no podía leerla. **Decisión del orquestador (S6-D77 final):** el api NO lee `APEX_TLS_ISSUER`; su excepción depende solo de `ALLOW_DOMAIN_PORT=true` y host `*.localhost`; que el emisor `internal` solo acompañe a hosts `*.localhost` lo exige `test_caddyfile.sh` sobre la configuración de Caddy. D77 y §11.9 reescritos en el plan; el paso 7 y el aislamiento quedan como estaban (variable solo de `caddy`).
2. Los pasos 38 y 44 no decían qué rellena `public_key` en instalaciones que ya tuvieran la fila `sign` (hoy no existe ninguna). **Añadido al paso 38:** la rellena quien crea la fila (`init-keys --data-class audit.signature` y el bootstrap) y, si una instalación la tuviera sin clave pública, `init-keys --data-class audit.signature` la completa de forma idempotente y lo audita.
3. Sin hallazgos nuevos contra S6-D34..D55 ni contra el código en las líneas revisadas.
