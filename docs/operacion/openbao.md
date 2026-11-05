# OpenBao: custodia de llaves

Procedimiento de operación de OpenBao (Sprint 5, v0.2; S5-D10 a D12, S5-D74 a D77, S5-D103, S5-D104, S5-D106; fundamento en `docs/adr/ADR-005-custodia-openbao.md`). OpenBao guarda la llave maestra (`apex-kek`) que envuelve las llaves de datos del bus de criptografía. Si se pierde, se pierden los datos cifrados: lea este documento entero antes de instalar y téngalo a mano cada vez que reinicie el servidor.

Todos los comandos se corren desde la raíz del repositorio, con:

```
DC="docker compose --env-file .env --env-file .env.ops -f infra/compose.yml"
```

Cuando `.env` dice `CRYPTO_PROVIDER=openbao`, añada `-f infra/compose.openbao.yml` a `DC` (api y worker dejan de montar `keys`; `deploy.sh` lo hace solo). En desarrollo vea la sección "Desarrollo".

## 1. Qué hay y qué no hay

- Servicio `openbao`: imagen por digest, solo en la red interna `custody` (sin salida y sin puertos al anfitrión), raíz de solo lectura, sin capacidades, usuario 100:1000. Guarda su estado (raft) en el volumen `openbao-data`.
- Servicio `openbao-bootstrap` (perfil `bootstrap`): se corre a mano, interactivo y sin log de contenedor. Instala, desella y reemite tokens.
- Un token por servicio en su propio volumen (`openbao-token-api`, `-worker`, `-tools`, `-backup`), de solo lectura en el servicio y con dueño uid 10001, modo 600. El api puede cifrar y descifrar con `apex-kek`; el worker, solo descifrar; `tools`, además, recifrar y rotar. Ninguno puede borrar ni leer la llave. La política de respaldo (`apex-backup-snapshot`, solo lectura de `sys/storage/raft/snapshot`) tiene su propio token en el volumen `openbao-token-backup`, montado solo de lectura en el servicio `backup` (S5-B13): con él el respaldo guarda la instantánea raft cifrada junto a la base (`docs/operacion/respaldo-y-restauracion.md`). No descifra nada.
- Un OpenBao **reiniciado queda sellado**. Hasta que se desselle con tres llaves, el api no puede abrir llaves nuevas (sección 4).
- El HTTP entre servicios y OpenBao no lleva TLS: la red `custody` es interna. El TLS llega con Caddy (EP-20).

## 2. Instalar (una sola vez, en un volumen vacío)

Pasos humanos: necesita estar presente el titular y el operador (sección 3), tener a mano cinco sobres numerados y ver la pantalla sin que nadie más la vea ni la grabe.

1. Compruebe `APEX_CUSTODY_SUBNET` en `.env.ops` (por omisión `172.30.1.0/24`; no debe solapar `APEX_SUBNET`) y baje la imagen: `$DC pull openbao`.
2. Levante OpenBao vacío: `$DC up -d openbao` y espere `healthy` (`$DC ps openbao`). Estar sin inicializar y sellado cuenta como sano.
3. Inicialice con una terminal real (no use `-T`, no redirija, no use `tee`, `script`, `tmux` con registro ni grabación de pantalla):

   ```
   $DC --profile bootstrap run --rm openbao-bootstrap --first-install
   ```

4. Escriba `INICIALIZAR`. El script crea 5 llaves con umbral 3, desella con tres y **muestra las cinco llaves por pantalla una sola vez**: no quedan en ningún archivo, en el log ni en la salida de Docker. Cópielas a mano a los cinco sobres (sección 3). Cuando estén guardadas escriba `GUARDADAS`: el script borra la pantalla. Después ejecute `clear` y cierre la terminal (y su historial de desplazamiento) antes de que otra persona la use.
5. El script habilita `transit`, crea `apex-kek` (`aes256-gcm96`, no exportable, sin respaldo en claro) y `apex-sign-audit` (`ed25519`, sin uso hasta v0.3), escribe las cuatro políticas, deja un token periódico de 768 horas en cada volumen de token, revoca la raíz inicial y termina. La raíz nunca se imprime.
6. Compruebe: `$DC exec -T openbao bao status` (`Sealed false`, `Total Shares 5`, `Threshold 3`).
7. Levante el resto: `$DC up -d`.

Si ejecuta `bootstrap.sh` sin `--first-install` sobre un volumen vacío, aborta con "volumen de OpenBao vacío: restaurar snapshot": un volumen vacío en un servidor que ya tuvo OpenBao se restaura desde el snapshot; nunca se vuelve a inicializar, porque una llave nueva deja ilegibles los datos ya cifrados.

## 3. Custodia de las cinco llaves (2 / 2 / 1)

Con cinco llaves y umbral 3 (S5-D106):

| Quién | Llaves | Dónde |
|---|---|---|
| Titular | 2 | Sobres sellados, en sitios distintos, fuera del servidor |
| Operador | 2 | Sobres sellados, en sitios distintos, fuera del servidor |
| Tercero ajeno a ambos | 1 | Copia sellada en una caja de seguridad o con un notario |

Titular más la copia, u operador más la copia, reúnen las tres llaves; ninguna de las dos partes llega sola al quórum. Nunca guarde la quinta copia en manos de una de las dos partes, ni dos llaves en el mismo sobre, ni ninguna llave en el servidor, en un gestor de contraseñas compartido o en el correo. Cada sobre lleva el número de la llave y la fecha, y no dice para qué sirve.

Esto es un paso humano: el reparto lo hacen el titular y el operador al terminar la instalación, y lo confirman por escrito. Revise que cada sobre existe y está intacto una vez al año.

## 4. Desellar tras cada reinicio

Tras reiniciar el servidor, Docker o el servicio `openbao`, OpenBao queda sellado. El api sigue arriba y `deploy.sh` lo informa ("api en estado sellado: desellar OpenBao"), pero el api no puede descifrar datos nuevos hasta que se desselle.

Se necesitan **tres llaves, tecleadas por al menos dos personas de partes distintas** (titular o operador, más el tercero si hace falta). La llave se teclea con `read -rs` (sin eco), se pasa por `stdin` y nunca va en un argumento, ni escrita en la línea de comandos, ni en un archivo (S5-D103). Repita el bloque para cada llave:

```
set +o history
read -rs -p "Llave de desello: " K; echo
printf '{"key":"%s"}' "$K" | $DC exec -T openbao wget -q -O - --header 'Content-Type: application/json' --post-file=/dev/stdin http://127.0.0.1:8200/v1/sys/unseal
unset K
set -o history
```

La respuesta trae `"progress"` y `"sealed"`; al tercer acierto dice `"sealed":false`. Compruebe con `$DC exec -T openbao bao status`. Con las tres llaves puestas, el api se recupera sin reiniciar (el sondeo de recuperación tarda hasta 40 segundos); `bash scripts/ci/openbao-smoke.sh` ensaya el ciclo completo en un entorno desechable.

Si una llave no funciona, no la repita más de dos veces: una llave equivocada no daña nada, pero repetirla no ayuda. Pruebe con otra.

## 5. Valores de `/health.crypto`

El campo `crypto` de `GET /health` (S5-D15, llega con B1 y B2) significa:

| Valor | Qué significa | Qué hacer |
|---|---|---|
| `ok` | OpenBao responde, está desellado y el api tiene sus llaves abiertas. | Nada. |
| `sealed` | OpenBao responde pero está sellado. El api devuelve 503 `crypto_unavailable` en las rutas con datos sensibles. `db` y `migrations` siguen en `ok`: el api no está caído y por eso su healthcheck no lo reinicia. | Desellar (sección 4). |
| `unreachable` | El api no alcanza OpenBao (servicio detenido, red `custody` caída, token expirado o revocado). | `$DC ps openbao`, `$DC logs --tail 50 openbao`; si el token expiró o se revocó, reemitir (sección 6). |

Un 503 con `crypto: sealed` y `db` y `migrations` en `ok` es un estado esperado tras un reinicio, no un fallo del despliegue.

## 6. Rotar los tokens

Los tokens son periódicos (768 horas) y cada servicio los renueva solo mientras corre. Se **reemiten cada 90 días y tras cualquier incidente** (M-2): reemitir crea tokens nuevos, y recién después revoca los anteriores de api, worker y tools.

1. Con tres llaves a mano (dos personas, sección 4):

   ```
   $DC --profile bootstrap run --rm openbao-bootstrap --reissue-tokens
   ```

   Corre en el listener local 8210 (S5-D107). Pide tres llaves con `read -rs`, genera una raíz temporal con ellas, reescribe las políticas, emite los tres tokens y revoca la raíz.
2. Reinicie los servicios que los leen: `$DC restart api worker`. `tools` los toma en su siguiente `run`.
3. Compruebe `/health` y `$DC logs --tail 30 api`.

## 7. Interruptor de emergencia

Ante la sospecha de que un token o el api fueron comprometidos (L-1), el objetivo es que el api deje de poder usar la llave maestra:

1. Reemita los tokens (sección 6): los anteriores quedan revocados en el acto.
2. Si el incidente exige cortar de inmediato y no hay tiempo para tres llaves, detenga OpenBao y reinicie los consumidores: `$DC stop openbao && $DC restart api worker`. Con OpenBao detenido el api responde 503 `crypto_unavailable` (`/health.crypto = unreachable`).
3. Para volver: `$DC up -d openbao`, desellar (sección 4) y `$DC restart api worker`.

Tenga presente que sellar o detener OpenBao **no** borra las llaves de datos que el api ya tiene abiertas en memoria: lo que corta el acceso es revocar los tokens y reiniciar api y worker.

## 8. Perder una llave: `rekey`

Si se pierde, se daña o se expone un sobre, reparta llaves nuevas de inmediato, con una segunda persona presente y el quórum de tres llaves vigentes. `rekey` y la reemisión de tokens usan el listener local `127.0.0.1:8210` del contenedor `openbao` (S5-D107), el único donde esos endpoints están abiertos; por eso van con `-e BAO_ADDR`:

```
R8210="-e BAO_ADDR=http://127.0.0.1:8210"
$DC exec $R8210 openbao bao operator rekey -status
$DC exec $R8210 openbao bao operator rekey -init -key-shares=5 -key-threshold=3 -verify
```

Antes de iniciar, mire el estado: **`rekey -init` falla si ya hay un intento en curso**. Un intento que usted no inició es un indicio de compromiso: no se una a él ni le teclee llaves; cancélelo con `$DC exec $R8210 openbao bao operator rekey -cancel`, avise al titular y repita el procedimiento. (Lo mismo vale para un intento de generación de raíz que `--reissue-tokens` encuentre abierto: `$DC exec $R8210 openbao bao delete sys/generate-root/attempt`.) La opción `-verify` hace que las llaves nuevas deban confirmarse con el quórum antes de que reemplacen a las viejas: úsela, porque evita quedarse con llaves nuevas mal copiadas.

Anote el `Nonce` que imprime y, para cada una de tres llaves vigentes (cada persona teclea la suya, sin eco):

```
$DC exec $R8210 openbao bao operator rekey -nonce=<nonce>
```

Al completar el quórum imprime las cinco llaves nuevas **una sola vez**: repártalas como en la sección 3, destruya los sobres anteriores y repita la confirmación por escrito. Con `-verify`, complete además la verificación (`bao operator rekey -verify -nonce=<nonce-de-verificación>`, con tres llaves nuevas). Si pierde tres o más llaves y no hay snapshot, no hay forma de recuperar los datos cifrados. Residual (S5-D107): quien tenga una shell en el contenedor `openbao` o en el bootstrap alcanza ese listener, pero sin tres llaves de desello no completa ninguna operación.

## 9. Desarrollo

OpenBao de desarrollo es opcional y NO está en el arranque normal: api, worker y tools no dependen de él (`CRYPTO_PROVIDER=local`).

```
DCD="docker compose --env-file .env -f infra/compose.yml -f infra/compose.dev.yml --profile openbao"
$DCD up -d openbao
$DCD exec -T openbao bao status
bash scripts/dev/openbao-seal.sh seal       # sellar para ensayar el estado sellado
$DCD restart openbao                         # vuelve desellado solo
bash scripts/dev/openbao-seal.sh unseal      # pide la llave con read -rs
```

`dev-entrypoint.sh` inicializa con una sola llave (1/1) y guarda esa llave de desarrollo en el volumen `openbao-dev-data` (modo 600, nunca en el log) para desellar solo en cada arranque. Se niega a correr si `APEX_ENV` no es `dev` y `compose.yml` no lo menciona: no existe en producción. Para empezar de cero: `$DCD down` y `docker volume rm apex_openbao-dev-data`.

## 10. Restaurar la instantánea (raft) y `generate-root` (S5-B13)

La instantánea raft es la única copia del estado de OpenBao (la llave `apex-kek`, las políticas y los tokens). La toma el servicio `backup` cada noche, cifrada con `age` y firmada en el manifiesto; se restaura **siempre junto con la base del mismo juego** (`docs/operacion/respaldo-y-restauracion.md`, paso 7 de "Restaurar paso a paso"). Este apartado explica lo que hay que saber de OpenBao en ese momento.

**Qué se necesita.** (1) El juego de respaldo con `openbao_snapshot` en el manifiesto firmado; (2) la identidad `age` de restauración; (3) **tres de las cinco llaves de desello ORIGINALES** (las del clúster que tomó la instantánea; la instantánea trae ese estado y no las guarda). Sin las llaves originales no hay forma de abrirla.

**Procedimiento.**

1. Con `openbao-data` vacío (`docker volume rm`, solo si el servidor se perdió; nunca sobre un OpenBao sano), `$DC up -d openbao`. Arranca vacío y sin inicializar.
2. **Inicialícelo de nuevo**: `$DC exec -T -e BAO_ADDR=http://127.0.0.1:8200 openbao bao operator init -key-shares=5 -key-threshold=3` (la terminal muestra las llaves y la raíz **de este clúster nuevo**: no las guarde; quedan sin valor). Desselle con esas llaves (sección 4) y use la raíz inicial como token efímero.
3. Corra `restore.sh --with-openbao --openbao-token-file <archivo 600 con esa raíz>` (el contenedor del respaldo debe estar en `custody`). Restaura por `POST sys/storage/raft/snapshot-force`; con `-force` porque el clúster nuevo tiene otras llaves y OpenBao rechaza la instantánea sin él ("could not verify hash file"). Borre el archivo de la raíz al terminar. El archivo debe ser regular, sin enlaces simbólicos y, en Linux, de **modo 600** (`restore.sh` se niega si no); `--with-openbao` tampoco se admite con `--i-know-unsigned` (la instantánea se confía por el `sha256` de un manifiesto firmado). Si la restauración **falla después de empezar a tocar cosas** (respaldo previo, base o instantánea), `restore.sh` **revoca la raíz del `init` nuevo** (`curl -K`, el token nunca va por argumentos); tras un éxito también intenta revocarla y, si el almacén ya cambió y falla, lo ignora con una nota. Si revocó por un fallo y hay que reintentar, genere otra raíz con `generate-root` y las llaves del clúster nuevo (el listener `127.0.0.1:8210`, secciones 6 y 8). Una negativa previa (guardas, firma, `sha256`, base con datos) no revoca nada.
4. **Reinicie `openbao`** (`$DC restart openbao`) y desselle con las llaves **originales** (sección 4). Hasta el reinicio sigue desellado con la llave en memoria del clúster nuevo. El estado restaurado manda desde ahí: los tokens de api, worker, tools y backup vuelven a ser los del momento de la instantánea (si caducaron o se reemitieron después, reemítalos con `--reissue-tokens`, sección 6).
5. Compruebe `/health.crypto` (`ok`) y un descifrado real (la ficha de un socio).

**`generate-root`.** Es para otro caso: OpenBao **sano** pero sin raíz (el bootstrap la revoca al terminar). `--reissue-tokens` y `rekey` abren una raíz efímera por el listener local `127.0.0.1:8210` con tres llaves vigentes (secciones 6 y 8) y la revocan al terminar. En un volumen vacío no hace falta: el `init` del paso 2 entrega la raíz inicial.

**Ensayo.** `bash infra/tests/openbao_restore_e2e.sh` (Docker, recursos `apex-obe2e-*` desechables) hace todo el ciclo con OpenBao real: init, `apex-kek`, cadena envuelta, respaldo con instantánea, borrado del volumen, clúster nuevo, `restore.sh --with-openbao`, reinicio, desello con las llaves originales (las nuevas no sirven) y descifrado de la cadena original; también `prod-smoke.sh` lo corre.

