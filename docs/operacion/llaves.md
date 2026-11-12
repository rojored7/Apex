# Llaves: inventario y estado del custodio

Alcance: lectura del inventario de llaves del bus de criptografía por el api (S6-B1, US-143). Rotar, retirar y migrar siguen en `rotar-llave.md` y `openbao.md`; esta guía solo explica qué se ve y cómo leerlo. Las cubetas del router de llaves se resumen al final; el CBOM y la rotación desde el panel llegan en B2 y B3.

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
