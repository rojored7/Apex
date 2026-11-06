# Crítica 2 del plan del Sprint 6 (`sprint-06-plan.md` enmendado, ronda 2, en `47d2bee`)

Fecha: 2026-11-06. Agente: plan-critic, ronda 2, solo lectura (Read, Grep, Glob; sin `docker`). Verificado: las decisiones S6-D56..D80, las contradicciones 9, 16 y 25 a 28 y los pasos 43 a 45. No verificado: los pasos de W0-2.3 (E3), W0-1.1 y 86 (se citan en las decisiones), ni nada que dependa de `docker`. El agente no tenía herramienta de escritura: el orquestador volcó el informe tal cual y añadió sus decisiones al final.

## Veredicto: RECHAZADO (dos bloqueantes de arreglo pequeño; E1..E9 y O1, O3, O4, O5, O11 están aplicadas en el texto)

## Bloqueantes

**B1. `openbao → local` y `local → openbao` de la fila `sign` cambian la llave, no solo la referencia (S6-D80, paso 43, prueba del paso 44 línea 556, contradicción 16).**
- `api/src/app/core/crypto/migration.py:6-7,52` excluye `sign` porque la fila guarda una referencia (`local:sign-ed25519` en `local_provider.py:35`, `apex-sign-audit` en `openbao_provider.py:43`), no material envuelto con la KEK. Esa razón sigue en pie.
- El material de esas dos llaves no es el mismo: `sign-ed25519.key` es un archivo local y la llave de Transit no es exportable. El plan solo cambia la referencia con `sign_key_ref()`, que no existe hoy en `api/src` (grep: 0 resultados); el plan la introduce.
- Resultado: tras migrar, el proveedor nuevo verifica con otra llave. Las firmas ya guardadas en `audit.signatures` darían `invalid`. D62 lo trataría como cadena rota (`ok=false`, `broken_at_seq`) y dispararía `audit_chain_broken`.
- La prueba del paso 44 dice «una firma hecha antes de migrar sigue verificando por `key_id` con el proveedor nuevo». No puede ponerse en verde sin conservar la clave pública de cada `key_id`, y el plan no la menciona ni habla de importar la llave a Transit.
- El ensayo no lo detecta: la fila `sign` nace ya `openbao` y aún no tiene firmas. En producción con firmas `local` previas sí revienta.
- Enmienda E10: o bien (a) `migrate-provider` rechaza las filas `sign` que tengan firmas en `audit.signatures` (salida 2 `signatures_reference_key`), o bien (b) la fila guarda la clave pública y `verify_signatures` verifica con ella.

**B2. El `real-ip.conf` renderizado y versionado deja el árbol sucio y `deploy.sh` se niega a desplegar (S6-D64, contradicción 28, O5).**
- `infra/deploy.sh:101` sale con 2 si `git status --porcelain` no está vacío. El mismo chequeo está en `:218`, después del checkout de la etiqueta.
- El plan regenera `infra/nginx/snippets/real-ip.conf` con `sed` cuando `APEX_CADDY_IP` difiere del valor por defecto. Ese archivo está versionado, así que queda modificado y el siguiente despliegue falla. Lo mismo ocurre con `prod-smoke.sh` y `tls-smoke.sh`.
- Enmienda E11: renderizar fuera del árbol, en `${DEPLOY_STATE_DIR}/real-ip.conf` (o en `docs/scratch/`, ya ignorado en `.gitignore:57`), y que Compose monte ese archivo con una variable (`APEX_REAL_IP_CONF`). El `.conf` versionado sigue siendo el valor por defecto horneado. `test_deploy_script.sh` debe comprobar que `git status --porcelain` queda vacío tras renderizar con una IP distinta.

## Altas

**A1. S6-D77: `ENV=staging` no existe.** `api/src/app/core/config.py:200` define `ENV: Literal["dev", "production"]`. D77 dice «valor ya admitido por `Settings`; se verifica en W0-5.1»: es falso. Su alternativa abre `ALLOW_DOMAIN_PORT` en producción cuando `APEX_TLS_ISSUER=internal`, y eso contradice su propia regla. Decidir ya (E12): (a) la alternativa, acotada a hosts `*.localhost`; o (b) añadir `staging` al `Literal`. Recomendación: (a).

**A2. Nginx con `proxy_request_buffering on` (`infra/nginx/snippets/proxy-api.conf:2`).**
- Nginx lee el cuerpo entero (6m en el location de subida) a `/var/cache/nginx`, tmpfs de `web` (`infra/compose.yml:405`), y solo entonces abre la conexión al api. Reenvía con `Content-Length` aunque el cliente use `chunked`.
- Detrás de Nginx el corte en el byte 5.242.881 de `request.stream()` solo actúa para cuerpos entre 5.242.881 y 6 MiB, y ahí el `Content-Length` ya viene declarado: el api responde 413 sin leer.
- «0 trozos» solo es medible llamando al api directamente (ASGI o httpx). Las pruebas de `Content-Length` falso, `chunked` e iterador infinito deben ser de api, no de E2E. La demo 3 y el E2E no probarán el corte por trozos: escribirlo en D59 y en el paso 85.
- El tmpfs de `/var/cache/nginx` no tiene `size=` y hereda la mitad de la RAM: acotarlo (`size=64m`).
- `default.conf:30` pone hoy `5m` en el server y D23 sube a 6m solo en el location de subida: confirmar que el `5m` global no corta antes.

## Medias

- **M1.** `redir … 308` explícito en el sitio `http://` frente a ACME HTTP-01: Caddy atiende `/.well-known/acme-challenge/*` antes de los handlers del sitio, pero el sitio manual desactiva el redirect automático y no hay prueba de que el challenge siga pasando. Añadir a `test_caddyfile.sh` que `/.well-known/acme-challenge/x` no devuelve 308, o dejarlo como paso humano explícito en `tls.md`.
- **M2.** La lista de servicios con `cap_drop` (E9: «nueve», faltan `db` y `caddy`) no se contrastó línea por línea con `compose.yml`.

## Observaciones

- Numeración: 150 `**Paso N**` por grep (coincide); no hay pasos insertados. La cobertura de C1..C9, H-1, H-2 y M-1..M-11 no cambia respecto a la crítica 1; M-4 pasa a los pasos 76 y 85-86 con cuerpo crudo.
- Aplicadas con redacción verificable: E1 (D59, D73, contradicciones 9 y 26), E4 (D78), E5 (contradicción 25 y paso 110), E6 (D61 con `guard_jobs_insert` y residual), E7 (D80), E8 (D64), E9 (D64), O1 (D62), O3 (D77), O4 (D79), O5 (D64 y contradicción 28) y O11 (paso 43).
- E3 y las partes de F4 (`api.upload` con `fetch body: File`, `ROUTES.md`) constan en D59 y no se releyeron en sus pasos.
- S6-D56..D80 no contradicen S6-D34..D55, salvo B1 en la contradicción 16 frente a S5-D183.

## Supuestos verificados

- `ENV=staging` ya admitido por Settings → FALSO (`config.py:200`, solo `dev|production`).
- Nginx hornea `default.conf` y `snippets/` en el build → CONFIRMADO (`web/Dockerfile:22-23`).
- `deploy.sh` exige árbol limpio → CONFIRMADO (`infra/deploy.sh:101,218`).
- `proxy_request_buffering on` en el proxy del api → CONFIRMADO (`proxy-api.conf:2`).
- tmpfs `/var/cache/nginx` en `web`, sin `size` → CONFIRMADO (`compose.yml:405`).
- `sign` excluido de `migrate-provider` por código, no por la guarda → CONFIRMADO (`migration.py:6,52`).
- `sign_key_ref()` existe en `src` → FALSO (el plan lo introduce).
- `.gitignore` cubre `docs/scratch/ensayo/` → CONFIRMADO (`.gitignore:57`).

## Qué falta para APROBAR

1. E10: resolver la migración de la fila `sign` y reescribir la prueba del paso 44 (línea 556) y la contradicción 16.
2. E11: sacar el `real-ip.conf` renderizado del árbol versionado y probar que `git status --porcelain` queda vacío tras `deploy.sh`.
3. E12: decidir D77 sin `staging` y sin contradecir la regla de producción.
4. E13: precisar en D59 y en el paso 85 que el corte por trozos se prueba en el api sin Nginx, y acotar el tmpfs de `web`.

## Decisiones del orquestador (ronda 3, sin tercera crítica completa: el flujo admite dos; una verificación acotada de E10..E13 precede al gate)

- **E10, decisión (a) + (b) (S6-D81).** `migrate-provider` sigue excluyendo las filas `sign` (y lo dice: salida 2 `signatures_reference_key` si alguien fuerza `--data-class audit.signature`); el cambio de proveedor de la firma es una llave NUEVA (`rotate-key audit.signature --provider <nuevo>`, nuevo `key_id`), nunca la migración de la referencia. Además `crypto_keys` guarda la clave pública de cada fila `sign` (columna `public_key` en `0021`, llenada por `init-keys --data-class` y por el bootstrap desde `transit/keys/apex-sign-audit` o derivada del archivo local), y `verify_signatures` verifica Ed25519 con esa clave pública en el api sin llamar al proveedor: así las firmas antiguas verifican por `key_id` aunque la llave esté retirada, y la verificación funciona con OpenBao sellado (cierra M-1 de forma completa, no solo con estado `unavailable`: la firma es lo único que exige Transit). La prueba del paso 44 se reescribe: «una firma hecha con la llave anterior verifica por `key_id` con su clave pública tras rotar la llave de firma al proveedor nuevo». La contradicción 16 se reescribe en esos términos y S5-D183 queda intacta.
- **E11 (S6-D82).** `real-ip.conf` se renderiza en `${DEPLOY_STATE_DIR}/real-ip.conf` (en los smokes, en un directorio temporal) y Compose lo monta por la variable `APEX_REAL_IP_CONF` con el `.conf` versionado como valor por defecto; `test_deploy_script.sh` comprueba `git status --porcelain` vacío tras renderizar con otra IP.
- **E12 (S6-D77 corregida).** Sin `staging`: `ALLOW_DOMAIN_PORT=true` solo con `APEX_TLS_ISSUER=internal` y host `*.localhost`; con `ENV=production` y cualquier otro host, un puerto en `APEX_DOMAIN` falla el arranque. W0-5.1 lo prueba.
- **E13 (S6-D59 y paso 85 precisados).** El corte por trozos, `Content-Length` falso, `chunked` e iterador infinito se prueban en el api por ASGI sin Nginx; detrás de Nginx el tope efectivo es `client_max_body_size 6m` del location (413 JSON) y el `5m` global del server se verifica que no corta antes (location más específico); el tmpfs `/var/cache/nginx` de `web` lleva `size=64m`.
- **M1 (S6-D64 precisada).** `test_caddyfile.sh` comprueba que `/.well-known/acme-challenge/x` no responde 308 en el sitio `http://`, y `tls.md` deja el ACME real con dominio como paso humano. **M2:** el planner enumera por grep los servicios sin `cap_drop` en el paso 27.
