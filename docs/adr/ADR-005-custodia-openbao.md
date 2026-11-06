# ADR-005 · Custodia de la KEK con OpenBao Transit

## Estado

Aceptado el 2026-11-04 (Sprint 5, v0.2; S5-D2, S5-D6, S5-D8, S5-D48 a S5-D50, S5-D73 y S5-D106). Cambiar el modelo de custodia, el reparto de las llaves de desellado o la forma de envolver las DEK exige detenerse y preguntar: una vez que `crypto.crypto_keys.wrapped_material` guarda texto de Transit, la única copia de la KEK vive en el volumen de OpenBao.

## Contexto

En v0.1 la KEK es un archivo de 32 bytes (`kek.bin`, modo 600) en el volumen `keys`, que montan el api y el worker (ADR-002). Un compromiso del api, o una copia del volumen junto con un volcado de la base, abre todos los datos personales cifrados. El plan de v0.2 saca la KEK del servidor de aplicación y la deja en OpenBao, con el motor Transit, sin cambiar el formato del blob, el AAD ni el índice ciego, que son irreversibles.

Fuerzas en juego:

- El equipo es pequeño y el operador no es técnico: un reinicio del servidor deja OpenBao sellado y los datos personales ilegibles hasta que alguien lo deselle. Hace falta un estado degradado explícito, no un fallo mudo.
- Perder la llave envolvente o un número suficiente de llaves de desellado es perder todos los datos. La custodia no puede depender de una sola persona.
- Las DEK se abren una sola vez al arrancar el proceso (`Keyring.load_all`): sellar OpenBao con el api arriba no corta lecturas, y el interruptor de emergencia real es revocar tokens y reiniciar.
- El api y el worker deben ser el eslabón más débil que se pueda tolerar: un RCE en el api no debe poder leer ni la KEK ni un volcado de ella.

## Decisión

1. **Transit con una sola llave.** `apex-kek` (`aes256-gcm96`, `exportable=false`, `allow_plaintext_backup=false`) envuelve todas las DEK y las llaves de índice, con `associated_data = b"apx-dek-wrap"`. El puerto `KeyProvider` conserva `wrap(dek)` y `unwrap(wrapped)`; `OpenBaoProvider` es `async` con `httpx.AsyncClient`, sin seguir redirecciones ni leer el proxy del entorno. La columna `crypto_keys.provider` manda sobre el prefijo del texto envuelto (`apxw1` o `vault:`), que solo se comprueba como coherencia. `apex-sign-audit` (`ed25519`) se crea y queda sin uso hasta v0.3.
2. **Tokens por servicio, con políticas mínimas.** El api puede `encrypt` y `decrypt` con `apex-kek` y renovar su token; el worker solo `decrypt`; `tools` puede `encrypt` y `decrypt` con `apex-kek` (la re-envoltura de `migrate-provider` y `rotate-kek` es `unwrap` + `wrap` en el api, porque `transit/rewrap` de OpenBao 2.7.2 no conserva el `associated_data`, S5-D55a), leer la llave, `rotate` y `config` solo con `allowed_parameters = min_decryption_version` (S5-D191); nunca `rewrap`, `delete` ni `trim` (corregido al cierre del Sprint 5, S5-D271; la política es `infra/openbao/policies/apex-tools.hcl`). La política de respaldo es la única con una ruta `sys/` (`sys/storage/raft/snapshot`, lectura, ruta exacta). Los tokens son periódicos, viven en un volumen por servicio, montado de solo lectura, y se rotan cada 90 días y tras cualquier incidente.
3. **Desellado Shamir con 5 llaves y umbral 3.** `bootstrap.sh` inicializa solo con `--first-install` y la confirmación escrita `INICIALIZAR`; sobre un volumen vacío sin ella aborta con "volumen de OpenBao vacío: restaurar snapshot", para no fabricar una llave nueva en silencio. La raíz nunca se imprime y se revoca al terminar. Tras cada reinicio hay que desellar con tres llaves; la llave entra por la API (`/v1/sys/unseal`) leída de stdin tras un `read -rs` con el historial de la shell desactivado, nunca por `argv` ni escrita literal en la línea de comandos.
4. **Custodia 2 / 2 / 1.** El titular guarda 2 llaves, el operador 2 y una quinta copia sellada queda con un tercero (caja de seguridad o notario), nunca en manos de una de las dos partes. Titular más copia, u operador más copia, reúnen el quórum de 3; ninguna parte sola lo alcanza. La pérdida de una llave se resuelve con `rekey` por una segunda persona. Inicializar y repartir son pasos humanos.
5. **Snapshot firmado y cifrado.** El servicio `backup` toma el snapshot raft de OpenBao y lo incluye en el manifiesto firmado con `minisign`, con `openbao_snapshot.verified = true` tras restaurarlo y descifrar una cadena de prueba en un OpenBao limpio. `migrate-provider` (salvo `--dry-run`), `rotate-kek` y `retire-local-kek` exigen un manifiesto firmado de menos de 24 horas con esa marca: dump y snapshot se restauran en pareja.
6. **`migrate-provider` y retiro de la KEK local.** `migrate-provider --from local --to openbao` reenvuelve las DEK por llave, con una transacción por llave y verificación del nuevo envoltorio, reanudable y sin recifrar datos. Después, `compose.openbao.yml` quita `keys` de api y worker, y `retire-local-kek` (confirmación escrita `RETIRAR`) borra `kek.bin` del volumen que solo monta `tools`. `deploy.sh` avisa si `CRYPTO_PROVIDER=openbao` y `kek.bin` sigue en `keys`.
7. **Estado sellado y 503.** `/health.crypto` toma `ok`, `sealed` o `unreachable` y el api responde 503 `crypto_unavailable` en las rutas que usan el bus; el healthcheck de Compose tolera ese 503 mientras `db` y `migrations` estén en `ok`, para que Nginx y el worker no queden sin arrancar. Un sondeo cada 20 s (caché de 5 s) recupera el keyring sin reiniciar; `/health` nunca llama a `try_load`.
8. **Lo que este modelo NO protege.** Quien comprometa el token del api (o un RCE en el api con acceso a la red `custody`) puede pedir a OpenBao que descifre cualquier DEK mientras el token viva: Transit evita la fuga de la KEK, no el uso de la llave. El HTTP interno de `custody` no lleva TLS (la red es `internal: true`; TLS en `custody` queda para v0.3, titular, EP-20). Un propietario de la base puede desactivar triggers (`apex_owner` es no superusuario, no un límite absoluto). Sellar no revoca nada: las DEK ya están en memoria.

## Alternativas descartadas

- **Una llave de Transit por `data_class` (US-133):** un token abre todas las clases de todos modos, así que no suma aislamiento real y obligaría a cambiar `wrap`/`unwrap`, `bootstrap`, el keyring, `rotate-key`, la suite de contrato y el formato de `wrapped_material`. Rotar la KEK es un solo `rewrap` de unas ocho filas.
- **Dejar la KEK local y endurecer el volumen:** no separa nada si el api es comprometido; el archivo sigue legible por el proceso.
- **KMS en la nube o HSM:** costo y dependencia externa para un gimnasio; OpenBao corre en el mismo servidor, con licencia MPL-2.0 sin modificar.
- **Auto-desellado con un KMS externo:** mueve la confianza a otro servicio y a otra cuenta; con un operador no técnico se prefiere el desellado manual documentado con un estado degradado visible.
- **Una sola persona con las cinco llaves, o dos partes con la quinta copia repartida entre ellas:** una persona es un punto único de pérdida y de coacción; la quinta copia en manos de una parte le daría el quórum sola.
- **`bao operator unseal` con la llave en `argv`:** la deja en la lista de procesos y en el historial; se usa la API con stdin.
- **Políticas amplias y tokens de larga vida sin rotación:** descartadas por la revisión de seguridad; AppRole y rotación automática pasan a v0.3 con el operador como dueño.

## Consecuencias

- El volumen `openbao-data` pasa a ser el único sitio donde vive la KEK: su snapshot firmado, la custodia 2/2/1 y el ensayo de restauración son obligaciones operativas, no opcionales. Perder tres de las cinco llaves, o el volumen sin snapshot, equivale a perder los datos cifrados.
- Cada reinicio del servidor exige desellar con tres llaves; hasta entonces el api responde 503 `crypto_unavailable` en las rutas con datos sensibles y `/health` lo dice. El procedimiento vive en `docs/operacion/openbao.md`.
- El worker pasa a descifrar solo teléfono y correo (clases limitadas) y recibe un token de solo `decrypt`.
- Hay dos redes: `default` y `custody` (`internal: true`); `web`, `db` y `backup` no están en `custody` (el respaldo sí desde B13, para el snapshot).
- Los datos y el formato de los blobs no cambian: el cambio de proveedor es reversible (`openbao` a `local`) mientras la KEK local siga respaldada; `retire-local-kek` es el punto sin retorno y por eso exige respaldo verificado, snapshot firmado y confirmación escrita.
- Añadir una pieza de operación (OpenBao, tokens, desellado) a cambio de que un compromiso del api deje de bastar para leer la KEK.

## Cómo se verifica

- `api/tests/crypto/test_local_provider.py` fija la envoltura `apxw1` y el contrato del proveedor local; `api/tests/crypto/test_provider_startup.py` el arranque por proveedor. La suite de contrato común y las pruebas de `OpenBaoProvider`, de recuperación, de `migrate-provider` y de `retire-local-kek` llegan con los slices S5-B1, S5-B2 y S5-B3 y se citan aquí cuando existan.
- `api/tests/migrations/test_db_grants.py` fija los permisos por tabla y columna de `crypto.crypto_keys` por rol; la guarda de la tabla se prueba con la migración `0015` en S5-W0-3.
- `api/tests/architecture/test_third_party_confinement.py` confina las bibliotecas de red y `api/tests/architecture/test_crypto_bus_importers.py` vigila la puerta única del bus.
- `api/tests/architecture/test_adr_docs.py` comprueba el formato de este documento.
- Fuera de `api/tests/`: `scripts/ci/test_openbao_infra.sh` (políticas, `bootstrap.sh`, `config.hcl`, S5-W0-2) y `scripts/ci/openbao-smoke.sh` (sellar, ver el 503, desellar y comprobar que todo vuelve).
- Cambiar cualquier decisión de este documento exige detenerse y preguntar.
