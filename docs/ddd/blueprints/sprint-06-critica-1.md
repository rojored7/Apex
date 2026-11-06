# Crítica 1 del plan del Sprint 6 (`sprint-06-plan.md` en `fa20a51`)

Fecha: 2026-11-06. Agente: plan-critic (Fable, solo lectura: Read, Grep, Glob; sin `docker`, `apk` ni `bao`, así que lo que depende de ellos queda como supuesto del plan). El agente no tenía herramienta de escritura: el orquestador volcó el informe tal cual.

## Veredicto: RECHAZADO (dos bloqueantes de arreglo pequeño; el resto del plan resiste)

## Bloqueantes

**B1. M-4 está mal resuelto.**
- Starlette 1.9.0 (`api/.venv/.../starlette/formparsers.py:185-192, 234`): `max_part_size` solo limita los campos de texto, es decir las partes sin `filename`. El archivo va a un `SpooledTemporaryFile` sin tope.
- `request.form()` parsea el cuerpo entero antes de devolver el control, así que el «corte por trozos de 64 KiB» de S6-D59 llega tarde. El único tope real es Nginx (6m) y un `Content-Length` que un cliente puede falsear o saltarse con `chunked`.
- El paso 86 exige 422 por `kind` inválido antes de leer el cuerpo. Pero `kind` es un campo `-F kind=photo` del multipart (P-ADJ), y no existe hasta parsear. Esa prueba es imposible de poner en verde.

**B2. Premisa falsa sobre la guarda de `0015`.**
- `0015_crypto_provider_migration.py:7-13, 57-72` no contiene `OLD.purpose <> 'sign'`. Dice expresamente «también `sign`». Una fila `sign` ya puede cambiar de proveedor si cambia `wrapped_material`, que en esas filas es la referencia.
- Lo que excluye a `sign` de `migrate-provider` es código (`core/crypto/migration.py`), no la guarda.
- Por eso son innecesarios la contradicción 16, la relajación en `0024` y el retraso de D40 a R1.

## Altas

- **A1.** W0-2.3 cambia las rutas por defecto de llaves antes de migrar el volumen en W0-2.6. El api de desarrollo con `--reload` se reinicia con la configuración nueva y arranca roto. El plan solo manda `stop worker`.
- **A2.** `volume.subpath` exige Docker Engine 26 o superior (API 1.45) en el servidor. Ni `deploy.sh` ni las guías piden esa versión mínima.
- **A3.** Si se corrige B1, también cambian F4 (pasos 134-135), `api.upload`, `ROUTES.md` y los E2E que suben `kind` en el formulario.

## Medias

- **M1.** Falta una prueba de que `AUDITABLE_TABLES` con `crypto.crypto_keys` no duplica filas `update` en una rotación.
- **M2.** `apex_api` conserva INSERT en `crypto_keys` (`grants.sql:96`) y gana INSERT en `crypto_jobs`. `guard_jobs_update` solo vigila UPDATE. Un api comprometido podría insertar un job `running` con `total=0`. El daño es acotado porque la llave anterior queda `decrypt_only`, pero D61 debe declarar el residual.
- **M3.** `TOPE_CLI_OPS` (`tests/cli/test_cli_base.py:259`) vale 260 para `rotate_key.py`, 200 para `retire_key.py` y 150 para el resto. El plan pide «<150» para los dos primeros y acumula tres modos en `keys.py`.
- **M4.** El healthcheck de Caddy con `wget --spider --max-redirect=0` aceptando 308 no está probado en BusyBox. Conviene decidir ya una ruta propia sobre HTTP, por ejemplo `respond 200` en `/_caddy_health` antes de la redirección.
- **M5.** `test_adr_docs.py` dice «cinco» en su docstring, su lista y sus mensajes. El Rojo debe actualizarlo todo, no solo el conteo.

## Observaciones

- O1: con proveedor `local` conviene verificar todas las firmas, y muestrear solo con OpenBao.
- O2: `__audit_exclude__` es aceptable, porque no toca el serializador ni `record`.
- O3: `APEX_DOMAIN` con puerto debería exigir una bandera explícita en producción.
- O4: añadir una prueba que falle si el api corre con más de un worker.
- O5: preferir el snippet renderizado por `deploy.sh` en lugar de `envsubst` con `web` `read_only`.
- O6: `compose.yml` ya tiene `cap_drop: ALL` en 8 servicios; el paso 27 debe enumerar los que faltan.
- O9: OpenSSL 3.5 en `alpine:3.22` no es verificable en solo lectura; W0-1.1 lo comprueba y el riesgo 12 trae alternativa.
- O11: `worker/runtime.py:69,105,111` y `notify.py:30` hay que migrarlos a `worker_crypto_classes()`.

## Supuestos verificados

- `Request.form` acepta `max_files`, `max_fields` y `max_part_size`: CONFIRMADO, pero que `max_part_size` acote archivos es FALSO.
- La guarda de `0015` bloquea `sign`: FALSO.
- `grants.sql:95-97,122` coincide con lo que el plan dice del api y del worker: CONFIRMADO.
- 16 cubetas hoy, y 23 con las 7 nuevas: CONFIRMADO.
- `test_adr_docs` exige exactamente 5 archivos: CONFIRMADO.
- `WORKER_CRYPTO_CLASSES` es global: CONFIRMADO.
- Compose `subpath` y `!override`, `cap_drop` de Caddy y Nginx, `envsubst`, OpenSSL 3.5: NO VERIFICABLE aquí.

## Cobertura

C1..C9 y H-1, H-2, M-1..M-11 y L-1..L-6 están todas en pasos explícitos del plan (sección 10). M-4 está presente pero defectuoso (B1), y H-2 deja el hueco de M2.

| Condición | Pasos del plan |
|---|---|
| C1 | 3-4 |
| C2 | 20-25, 34-56 |
| C3 | 57-75 y 144-150 |
| C4 | 5, 7-19, 76-107 |
| C5 | 57-59, 108-116 |
| C6 | sección 1, 82, 101, 114, V11 |
| C7 | 12-13, 26-33, 117-122 |
| C8 | 123-150 |
| C9 | V1-V12 |
| H-1 | 34-36, 38, 44, V3 |
| H-2 | 108-115, V9, V11 |
| M-1 | 50-55 |
| M-2 | 20-21, 36, 43-44 |
| M-3 | 76, 78, 97-98 |
| M-4 | 5, 12-13, 76, 78, 85-86 |
| M-5 | 4, 97-98, 129 |
| M-6 | 85-86, 97-98, 129 |
| M-7 | 26-29 |
| M-8 | 27-28, 30 |
| M-9 | 7-8, 76, 78 |
| M-10 | 4, 81 |
| M-11 | 91-92, 94, V12 |

S6-D56..D77 no contradicen S6-D34..D55. Sí chocan con el código real D61 (B2) y D59 (B1).

## Enmiendas para el planner

- **E1 (B1).** Pasar `kind` a parámetro de consulta. Leer el cuerpo con `request.stream()` acotado o con un parser propio, en lugar de `request.form()`. Probar con `Content-Length` falso y con `chunked`, y medir el spool. Reescribir D59, D73, pasos 76, 85, 86 y 134-135, W0-1.1, el riesgo 10 y P-ADJ.
- **E2 (B2).** Corregir la contradicción 16 y D61. Quitar la relajación de `sign` de `0024`. Mover `migrate-provider` con filas `sign` a A1/A2.
- **E3 (A1).** `stop api worker` durante W0-2.3, hasta migrar el volumen en W0-2.6. Añadir un caso en `deploy.sh` para el layout plano.
- **E4 (A2).** Chequeo de la versión mínima de Engine y Compose en `deploy.sh`, en las guías y en `test_deploy_script.sh`.
- **E5 (M1).** Aserción de una sola fila de auditoría por rotación.
- **E6 (M2).** Acotar el INSERT de `crypto_jobs`, o documentar el residual en D61 y `llaves.md`. ADR-005 no se toca.
- **E7 (M3).** Usar los topes reales de `TOPE_CLI_OPS` y crear un archivo por comando nuevo (`keys_layout`, `keys_data_class`, `sign_audit`, `attachments_check`).
- **E8 (M4).** Healthcheck de Caddy con ruta HTTP propia, probado en `test_caddyfile.sh`.
- **E9 (M5, O6).** Actualizar el docstring y los mensajes de `test_adr_docs` a siete. Enumerar los servicios sin `cap_drop` en el paso 27.
- Opcionales: O1, O3, O4, O5, O11.

## Decisión del orquestador

Se aplican E1..E9 y también O1, O3, O4, O5 y O11 (todas baratas y cierran huecos reales). Las enmiendas van al plan como ronda 2 (`sprint-06-plan.md` enmendado) y la segunda crítica decide.
