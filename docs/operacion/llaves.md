# Llaves: inventario y estado del custodio

Alcance: lectura del inventario de llaves del bus de criptografía por el api (S6-B1, US-143). Rotar, retirar y migrar siguen en `rotar-llave.md` y `openbao.md`; esta guía solo explica qué se ve y cómo leerlo. Las cubetas del router de llaves se resumen al final; el CBOM se describe al final.

## El inventario: `GET /api/v1/crypto/keys`

Solo admin (cubeta `staff-read`, 120 por minuto), sin caché (`Cache-Control: no-store`) y de solo lectura: no escribe `crypto_ops` ni auditoría. Devuelve la página habitual `{items, total, limit, offset}` (25 por defecto, 200 como máximo) más un bloque `summary`.

Cada llave trae `id`, `purpose` (`encrypt`, `index` o `sign`), `data_class`, `algorithm`, `version`, `state` (`active`, `decrypt_only` o `retired`), `provider` (`local` u `openbao`), `created_at`, `rotated_at`, `age_days` y `records_count`. Nunca trae material de llave, claves públicas ni la referencia interna de las llaves de firma.

- Filtros: `purpose`, `state`, `provider`, `data_class` (exacta, formato `clase.campo`) y `q` (contiene, sin distinguir mayúsculas, sobre `data_class`; `%` y `_` valen como texto). Un valor fuera de lista da 422.
- Orden fijo: `data_class`, `purpose` y `version` descendente (la versión más nueva primero).
- `age_days`: días completos desde `created_at` hasta `rotated_at`; en una llave que no se ha rotado, hasta hoy. Una llave `decrypt_only` queda con la edad congelada en su rotación.
- `records_count`: cuántos registros protege la clase. Las filas `encrypt` e `index` de una misma clase muestran el mismo número. Es nulo para `audit.signature` y `kek.backup` (no hay registros de negocio que contar) y para cualquier clase sin columnas cifradas ni lector registrado.

## El bloque `summary`

- `active_count`: llaves `active` de todo el inventario (no solo las de la página).
- `operations_today`: filas de `crypto_ops` del día de Bogotá (de 00:00 a 24:00 hora de Bogotá, no UTC).
- `running_jobs`: trabajos del bus en estado `running` (rotaciones, recifrados, migraciones).
- `provider.names`: proveedores que custodian hoy, es decir los de las filas `active`, sin repetir (`["local"]`, `["openbao"]` o ambos mientras dura una migración). Una llave `decrypt_only` en otro proveedor no cuenta.
- `provider.state`: `ok`, `sealed`, `unreachable` o `unknown`. Es el mismo estado de `/health.crypto` (ver `openbao.md` §5). `unknown` es normal justo tras arrancar, antes de la primera observación; `sealed` pide desellar (`openbao.md` §4) y `unreachable` pide revisar la red `custody` y el servicio OpenBao.

## La bitácora de operaciones y los trabajos (US-144)

`GET /crypto/ops` lista la bitácora `crypto_ops` (solo lectura, solo admin, sin caché). Orden fijo: la más reciente primero (`at` y, en empate, `id` descendentes). Cada fila trae quién (`user_id`), qué (`verb`), sobre qué (`data_class`, `key_id`, `key_version`, `record_id`), el `result` (`ok` o `error`), el `batch_id` de las operaciones de un mismo lote y `count` (las filas iguales de un lote se agregan). Nunca trae material de llave ni el texto de un error del proveedor. Filtros, todos opcionales y combinables:

- `from` y `to`: instantes con zona, rango `[from, to)`. Piso 2020-01-01, techo mañana, y como mucho 366 días entre los dos. Un rango invertido, vacío, sin zona o fuera de tope da 422 con `field` `from` o `to`.
- `verb`: `encrypt`, `decrypt`, `index`, `sign`, `verify`, `wrap`, `unwrap`, `rotate` o `export`. `result`: `ok` o `error`.
- `data_class`: la clase exacta (`member.document`). `key_id`, `user_id` y `batch_id`: UUID exactos.
- `q`: texto libre que busca solo dentro de `data_class` (sin distinguir mayúsculas; `%` y `_` valen como texto). No busca ids, verbos ni errores.

`GET /crypto/jobs` lista los trabajos `crypto_jobs` (rotaciones, recifrados, migraciones de proveedor y re-envolturas), del más reciente al más antiguo (`created_at` y `id` descendentes). Filtros: `status` (`pending`, `running`, `done`, `failed`), `kind` (`rotate`, `reencrypt`, `migrate_provider`, `rewrap`), `data_class` y `q` (igual que arriba). Cada fila trae `total`, `done` y `percent`: el avance entero de 0 a 100 (`done * 100 // total`, redondeado hacia abajo, de modo que solo llega a 100 al terminar; `total = 0` da 0). El texto `error` de un trabajo fallido no se expone: se consulta en los registros del worker.

Ambas listas paginan con `limit` (25 por defecto, máximo 200) y `offset`, y leerlas no escribe en `crypto_ops`.

## Recifrado de clases sin columnas (puerto `Reencryptor`)

Una clase que se cifra pero cuyos datos no están en columnas del registro (los adjuntos sensibles, `attachment.sensitive`, desde C1) registra al arrancar quien cuenta y recifra sus registros. Mientras no lo registre, `rotate-key <clase>` sale 2 con `rotation_not_supported` y no crea trabajo ni llave. Al cerrar una rotación con registros pendientes el comando espera y repasa (cinco pasadas); si el puerto no los vacía, el trabajo queda `failed` (`pending_records`), la llave anterior sigue en `decrypt_only` y repetir el comando reanuda. El retiro (`retire-key`) cuenta columnas y los objetos que informa el puerto (`count_by_key`, entrada `objetos` en `filas_negocio`): con objetos aún cifrados con la llave se niega (sale 2) y no cambia el estado.

## La llave de firma de la auditoría

La llave `audit.signature` no se rota en sitio ni se recifra en v0.3 (S6-D69): solo se cambia de proveedor con `rotate-key audit.signature --provider <local|openbao> --reason "..." --as <correo>` (llave nueva; la anterior queda `decrypt_only` y sus firmas siguen verificando por su `key_id`). Detalle y casos de error en `rotar-llave.md` («La llave de firma de la auditoría») y `openbao.md` §12.

## El CBOM: `GET /api/v1/crypto/cbom`

Descarga JSON `apex-cbom/1` con el inventario criptográfico para auditores y para el panel «Sistema → Llaves». Solo admin, cubeta `cbom-export` (2 por minuto), `Content-Disposition: attachment; filename=apex-cbom-AAAA-MM-DD.json` (fecha de Bogotá), `Cache-Control: no-store`, `X-Content-Type-Options: nosniff` y CSP `default-src 'none'; sandbox`.

- Contiene: `format`, `generated_at`, `app_version`, `provider` (`names`, `state`), `keys` (TODAS las llaves, también `decrypt_only` y `retired`, ordenadas por `data_class`, `purpose`, `version`, con `id`, `purpose`, `data_class`, `algorithm`, `version`, `state`, `provider`, `created_at` y `rotated_at`), `fixed_algorithms` (los seis usos con algoritmo fijo: JWT, contraseñas, índices ciegos, cadena de auditoría, firma de auditoría y respaldos) y `tls`.
- No contiene: material de llave, claves públicas, referencias del proveedor, `records_count` ni `age_days`.
- `tls = {"declared": bool, "source": "configuration"}`: es una declaración, no una sonda. `declared` es verdadero cuando `APEX_DOMAIN` tiene valor; no prueba que el certificado esté vigente.
- Cada descarga deja una fila de auditoría `export` sobre `crypto.crypto_keys` con `after = {"count": n, "format": "apex-cbom/1"}`, escrita antes de enviar el cuerpo. Si la auditoría no está disponible responde 503 `busy` y no descarga nada.

## Rotar desde la pantalla: `POST /api/v1/crypto/keys/{id}/rotate` (US-145)

Solo admin. Cuerpo `{"reason": "...", "confirm": "ROTAR"}`: `confirm` exactamente `ROTAR` y `reason` de 1 a 200 caracteres, sin correos ni números de seis o más dígitos (la misma regla del CLI, `service.validate_reason`). Responde 202 con `job_id`, `new_key_id` y `previous_key_id`. Cubetas `keys-rotate` (3 por minuto) y `keys-rotate-hour` (10 por hora).

Qué pasa, en orden:

1. En UNA transacción: se abre el trabajo `running` (con `total` = registros de la clase), la llave anterior pasa a `decrypt_only`, nace la nueva `active` (versión + 1) y se escribe UNA fila `update` en la auditoría sobre `crypto.crypto_keys` (con `reason`, `data_class` y `state`; sin material ni referencias). Se confirma con `commit` y solo entonces arranca la tarea.
2. La tarea (`core/crypto/rotate_job.py`, la misma del CLI) toma el candado `apex:rotate:<clase>` en una conexión de un motor propio de una sola conexión (no resta conexiones al api), recarga el keyring y recifra de a 500 filas (de a 10 adjuntos para `attachment.sensitive`), una transacción corta por lote. Durante el proceso las filas viejas y las nuevas se leen con su llave.
3. Al terminar el trabajo queda `done` y la llave anterior sigue en `decrypt_only`. El avance se ve en `GET /crypto/jobs` (`percent`).

Los 409 de la ruta: `key_not_active`, `purpose_not_rotatable` (`index` y `sign` no se rotan desde aquí), `rotation_running` (hay un trabajo abierto de la clase, una operación de custodia o ya corre otro rotador en el proceso), `rotation_not_supported` y `nothing_to_rotate` (la clase no tiene datos: rotar una llave que no protege nada es trabajo del CLI). 404 si la llave no existe y 503 `crypto_unavailable` con el custodio sellado (no queda nada a medias).

### Si falla o se corta

- Un error de lote deja el trabajo `failed` con un código (`decrypt_failed`, `pending_records`, `timeout` si pasa de una hora...) y la llave anterior en `decrypt_only`: no se pierde ni se bloquea nada. Para reanudar, repite el MISMO `POST` sobre la llave `active` (202 con el mismo `job_id`, sin versión nueva; deja una fila de auditoría `update` con `after = {"event": "resume", "job_id": ...}`), o `rotate-key` en el CLI. Lo mismo vale para un trabajo `running` huérfano (la tarea murió tras tres «base ocupada» o el api se apagó): con el cupo libre, el `POST` lo reanuda; si otra corrida (CLI u otro proceso) tiene el candado, la tarea queda pospuesta y el trabajo sigue `running` sin daño. La reanudación pasa por las mismas comprobaciones que una rotación nueva (sin migración o re-envoltura de la KEK abierta, clase rotable).
- Si el api se reinicia a mitad, el trabajo queda `running`: al arrancar, con el keyring cargado, `resume_running_jobs` lo termina; si el custodio arrancó sellado, lo anota en el log y lo reanuda cuando se recupere. Si ves un `running` que no avanza, revisa el log del api (`rotación fallida`, `rotación pospuesta`).

### Retirar sigue siendo del CLI

`retire-key` no está en el api (el rol `apex_api` no puede dejar una llave en `retired`: lo frena el trigger). Además de las exigencias de siempre, el manifiesto de respaldo firmado debe ser POSTERIOR al `finished_at` de la rotación (S6-D74): si no, sale 2 con `backup_older_than_rotation` (un respaldo anterior no contiene lo recifrado). Corre `backup` y repite.

### Residuales de E6 y D61 (lo que un api comprometido podría hacer)

Para rotar desde el api, `apex_api` tiene `INSERT` en `crypto.crypto_keys` y `crypto.crypto_jobs`, `UPDATE (state, rotated_at, rotated_by, updated_at)` en las llaves y `UPDATE (done, status, error, started_at, finished_at, updated_at)` en los trabajos. Las guardas de la migración `0024` lo acotan: solo `active → decrypt_only` de una llave `encrypt`, solo si al cierre de la transacción existe otra `active` de versión mayor y un trabajo `running` de la clase, con `rotated_by` un usuario real; jamás `retired`, ni filas `sign` o `index`; los trabajos del api son `rotate` `running` con `total > 0` y `done = 0`, el `done` no baja y `done` exige `done = total`.

Lo que sí podría hacer un api comprometido: insertar llaves `decrypt_only` falsas, abrir trabajos `running` sin recifrar nada, o pasar a `decrypt_only` la llave de una clase creando una nueva llave `active` de su propia DEK (los datos nuevos se cifrarían con ella). Ningún dato queda ilegible por eso: la anterior queda `decrypt_only` (nunca `retired`; retirar exige el CLI y el conteo de filas en cero) y sigue descifrando. Cómo se detecta: en «Trabajos» (`GET /crypto/jobs`) un trabajo `running` que no avanza o con `percent` en 0; en la bitácora (`GET /crypto/ops`) una llave nueva sin las filas `rotate`/`wrap` de una rotación completa; en la auditoría (`GET /audit?table=crypto.crypto_keys`) una rotación sin fila `update` de una persona. Lo que estas guardas NO prueban:

- Un `done` fabricado por un api comprometido (`UPDATE ... SET done = total, status = 'done'` más filas inventadas en `crypto_ops` o `audit_log`) NO prueba que se recifró nada. Lo prueba `retire-key`: cuenta con `count_rows_by_key`/`count_by_key` las filas que aún usan la llave anterior y se niega si no es cero. Nunca confíes en `percent` ni en el estado del trabajo para retirar.
- La atribución `rotated_by`/`created_by` es orientativa: un RCE puede suplantar a cualquier admin existente. La firma diaria del worker sella lo ocurrido antes.
- La condición «existe otra `active` de versión mayor» la satisface también una fila que el propio `apex_api` inserte (`ensure_keys` ya tiene `INSERT`): la guarda prueba la forma de la rotación, no el origen de la llave.

Residual D61: la guarda del trabajo `running` solo ve lo confirmado y lo propio de la transacción; un trabajo `running` de OTRA transacción la satisface, pero `uq_crypto_jobs_in_progress` impide dos en curso de la misma clase.
