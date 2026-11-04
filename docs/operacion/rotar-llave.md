# Rotar una llave de cifrado y retirar la anterior

Guía para la persona que opera APEX. Rotar una llave hace que lo que se cifre desde ese momento use una llave nueva y recifra los datos existentes. No revoca respaldos ya hechos ni sirve si la KEK está comprometida (ver el final). Ninguna orden de aquí imprime material de llaves; no pegues salidas con identificadores de llave en canales públicos.

## Cuándo rotar

- Por política (por ejemplo, una vez al año) o tras un cambio de personas con acceso al servidor.
- Tras una sospecha de exposición de la base (no de la KEK: si la KEK se filtró, esta rotación no basta).
- No rotes mientras corre una restauración, una importación de socios ni un despliegue.

## Antes de empezar (todo debe estar en verde)

1. Un respaldo reciente de la base: `pg_dump` de `apex` (o el último respaldo automático de `latest.json` con `verify: ok`).
2. Un respaldo de la KEK recién exportado y verificado, según `docs/operacion/respaldo-y-restauracion.md`: `export-kek` y luego `verify-kek-backup` con resultado `failed=0`. Sin esto, `retire-key` se niega más adelante.
3. Anota el motivo (hasta 200 caracteres, sin datos personales: nada de correos ni números de seis o más dígitos, y no escribas nombres ni cédulas en `--reason`: la guía no puede detectarlos y el motivo queda en la auditoría).

## Rotar

Desde la raíz del repositorio, con `DC="docker compose --env-file .env --env-file .env.ops -f infra/compose.yml"`:

```
$DC --profile tools run --rm tools rotate-key member.document --reason "rotación anual 2026" --as <correo de un admin>
```

- Cambia `member.document` por la clase que toque (`member.phone`, `member.email`, `member.birth_date`, `member.emergency_contact`). `attachment.sensitive` no se puede rotar hasta EP-18 (G-09).
- Imprime `rotate-key: total=N` y luego `rotate-key: hecho=X/N` por cada lote de 500 filas. Cada lote es una transacción corta: el sistema sigue atendiendo, y los datos se leen con cualquiera de las dos llaves durante el proceso. No hace falta `--db-timeouts off`.
- CPU: cada fila se descifra y se vuelve a cifrar en el proceso del comando. Con decenas de miles de filas tarda unos minutos y usa un núcleo; hazlo en horario de poca carga.
- El api no necesita reinicio: aprende la llave nueva en la siguiente petición autenticada (`keyring.refresh_current`).
- Termina con `rotate-key: llave anterior en decrypt_only; retirar con retire-key`. La llave anterior sigue sirviendo para descifrar: aún no está retirada.
- `--index` rota la llave del índice ciego (la que sirve para buscar por documento, teléfono o correo) y recalcula todos los índices en una sola transacción. Se niega con más de 50.000 filas. La búsqueda sigue funcionando al terminar.
- `--batch-size N` cambia el tamaño del lote (1 a 5000).

## Si se interrumpe o falla

- Si se corta (cierre de la terminal, reinicio, base ocupada), repite el MISMO comando: reanuda el mismo trabajo desde donde quedó y no crea una versión nueva ni recifra lo ya migrado.
- `rotación en curso`: otro proceso está iniciando la misma rotación; espera unos segundos y repite. Si el proceso de rotación murió y dejó una conexión huérfana, el siguiente intento puede seguir viendo `rotación en curso` hasta que Postgres cierre esa sesión (`tcp_keepalives`): espera, o cierra la sesión desde `pg_stat_activity` como propietario (`pg_terminate_backend`).
- `quedan filas con la llave anterior (bloqueadas por otra escritura)`: el comando saltó filas que otra transacción tenía bloqueadas y, tras cinco pasadas de 1 s, aún siguen; repite el comando.
- `la base está ocupada`: el comando ya reintentó tres veces (1 s entre intentos); repite en unos minutos.
- `un lote falló; repita el comando`: el trabajo queda en estado `failed`, los datos siguen legibles y no se pierde nada. Repite el comando; si vuelve a fallar, avisa al equipo con la hora (no copies mensajes con datos).
- Para ver el estado: `SELECT status, total, done FROM crypto.crypto_jobs ORDER BY created_at DESC LIMIT 3` (solo lectura).

## Retirar la llave anterior (irreversible)

Solo cuando ya no quede ninguna fila con la llave anterior. Retirar la deja inutilizable para siempre.

1. Identifica la llave anterior: `SELECT id, version, state FROM crypto.crypto_keys WHERE data_class = 'member.document' AND purpose = 'encrypt' ORDER BY version` (solo lectura; la `decrypt_only` más vieja).
2. Ejecuta, con una terminal:

```
$DC --profile tools run --rm tools retire-key <key_id> --as <correo de un admin> --confirm-audit-blobs <N>
```

Para ver los conteos, corre primero con `--confirm-audit-blobs 0`: el comando imprime `retire-key: filas_negocio=F` y `retire-key: audit_blobs=A` y se niega si `N` no coincide con `A`. Copia `A` y repite con `--confirm-audit-blobs A`.

`retire-key` exige tres cosas y se niega (salida 2) si falta alguna:

- **Cero filas de negocio** con esa llave (`filas_negocio=0`), contadas en el momento bajo bloqueo de la llave.
- **El conteo confirmado de blobs en `audit_log`** (`--confirm-audit-blobs`). La bitácora de auditoría es inmutable y puede guardar valores cifrados con la llave vieja. Esas copias NO se recifran: al retirar la llave quedarán ilegibles para siempre (el historial dirá `key_retired`). Confirmar el conteo es aceptar esa pérdida de lectura.
- **Respaldo reciente de la KEK y del manifiesto:** un `verify-kek-backup` correcto de una persona en las últimas 24 horas, y un `latest.json` con su firma `.minisig`, `verify: ok` y de menos de 24 horas. Todo fallo del manifiesto da el mismo mensaje: `no hay un latest.json reciente con firma adjunta en /data/backups (verify: ok)`. Si hace falta, `--manifest <ruta>` apunta a otro manifiesto.

`--manifest` solo vale bajo `BACKUP_DIR` (en el contenedor, `/data/backups`) y sin enlaces simbólicos; fuera de ahí da el mismo mensaje fijo. La firma `.minisig` se exige como archivo adjunto, pero `tools` no la verifica criptográficamente (la imagen del api no trae `minisign`; ver S4B-D149): `restore.sh` sí la verifica.

`retire-key` recorre `audit.audit_log` completo para contar los blobs (lectura secuencial, sin índice por diseño): es una operación rara y tarda en proporción al tamaño de la tabla.

Al terminar imprime `retire-key: llave retirada` y deja una entrada de auditoría con ambos conteos.

## Qué NO hace la rotación

- No revoca respaldos anteriores: un respaldo de la base hecho antes de rotar sigue abriéndose con la KEK de entonces.
- No protege si la KEK está comprometida: quien tenga la KEK también desenvuelve la llave nueva. Ese caso (cambiar la KEK y re-envolver todo) corresponde a la versión con OpenBao (v0.2).
- No cambia la contraseña de nadie ni las llaves JWT o de firma.
