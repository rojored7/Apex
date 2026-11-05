# Respaldo y restauración de APEX

Guía para la persona que opera el servidor del box. Está escrita para el día malo: si el servidor se perdió, esta página y las tres piezas de abajo bastan para recuperar socios, pagos y auditoría. Ninguna orden de aquí imprime una llave; no pegues nunca una frase, una identidad ni una llave en un chat, un correo o un ticket.

## Las tres piezas que necesitas guardar

Sin cualquiera de las tres, los datos personales no se pueden recuperar. Guárdalas **fuera del servidor** y en **dos copias** cada una, en lugares distintos (por ejemplo, un gestor de contraseñas y un USB en una caja fuerte).

1. **La KEK exportada** (`kek.age`): la llave maestra de los datos cifrados (documento, teléfono, correo, nacimiento y contacto de emergencia de los socios), envuelta con `age -p`. El archivo por sí solo no sirve a un atacante: está cifrado con una frase.
2. **La frase de la KEK.** La pide `age` en la terminal al exportar. Si la dejas vacía, `age` genera una frase segura y la muestra **una sola vez**: es el camino recomendado; anótala en ese momento. APEX nunca ve ni guarda la frase.
3. **La identidad `age` de restauración** (`AGE-SECRET-KEY-1...`): descifra los archivos de respaldo de la base y de los uploads. Su parte pública (`age1...`) es `BACKUP_AGE_RECIPIENT` en `.env.ops`; la privada nunca vive en el servidor.

Además necesitas, para comprobar que un respaldo es auténtico, la **llave pública de firma** (`backup-sign.pub`, la de `minisign`). La llave privada de firma sí vive en el servidor, solo en el servicio `backup`.

## Qué hace el respaldo automático

Cada noche el servicio `backup` deja en el volumen `backups` dos archivos cifrados (la base y los uploads), una tercera pieza con `CRYPTO_PROVIDER=openbao` (la instantánea de OpenBao, abajo) y un manifiesto firmado (`latest.json` y `latest.json.minisig`). Sin `BACKUP_RCLONE_REMOTE`, ese volumen está en el mismo disco que la base: no es un respaldo fuera de la máquina. Copia los archivos a otro sitio.

## La base y la instantánea de OpenBao van siempre en pareja (S5-B13)

Con OpenBao, las llaves que abren los datos cifrados ya no están en un archivo sino dentro de OpenBao, y su estado vive en el volumen `openbao-data`. Por eso el respaldo guarda **dos cosas que se corresponden**: la base y la instantánea raft de OpenBao tomada en el mismo momento (`<juego>-openbao.snap.age`, cifrada con la misma llave `age` que los demás archivos; la instantánea en claro nunca toca el disco). El manifiesto la declara en `openbao_snapshot` (nombre, tamaño, `sha256` y `verified`, que es `true` cuando se descifró con la identidad de verificación y dio el mismo contenido).

- **Siempre en pareja:** restaurar una sin la otra deja datos cifrados que ninguna llave abre, o llaves sin datos. Un respaldo sin la entrada `openbao_snapshot` con `verified: true` no sirve para retirar la KEK local (`retire-local-kek`) ni para migrar de proveedor; `backup_check` informa `snapshot` en el detalle de la corrida.
- **Cómo se toma:** el servicio `backup` entra a la red `custody` y lee el token de la política `apex-backup-snapshot` de su propio volumen `openbao-token-backup` (solo lectura). Ese token solo puede leer `sys/storage/raft/snapshot`; no descifra nada. El token entra a `curl` por un archivo de configuración efímero en `/tmp` (`curl -K`), nunca por argumentos. Si el volumen no tiene token (instalación sin OpenBao), el paso se omite con una línea `info` y el respaldo sigue.
- **Si la instantánea falla** el juego de la base queda guardado, pero la corrida sale con error, no se aplica retención y el manifiesto no trae `openbao_snapshot`: corrija el acceso a OpenBao y repita.
- **Firma verificada también en Python:** el worker (`backup_check`) y `retire-key` verifican la firma `minisign` del manifiesto con `BACKUP_SIGN_PUBKEY` (la llave pública, que no es secreta). Sin esa variable el worker no verifica la firma y lo deja dicho (`firma_verificada = 0`, aviso en el log); con ella, una firma ausente o mala es `corrupt`.

## Destino remoto: un cubo donde APEX no puede borrar

Si configuras `BACKUP_RCLONE_REMOTE=apex:<cubo>/<ruta>`, el servicio `backup` sube cada juego con
`rclone copyto --immutable`: **copia un archivo con su nombre exacto y no borra ni reemplaza nada**.
Ni la retención de APEX ni un servidor comprometido deben poder borrar tus copias, así que la
credencial de `RCLONE_CONFIG_APEX_ACCESS_KEY_ID` / `RCLONE_CONFIG_APEX_SECRET_ACCESS_KEY` debe tener
solo permiso para **escribir y listar**, nunca para borrar. Política de ejemplo para un cubo S3 (el
usuario de `apex` solo puede `PutObject` y `ListBucket`; sin `DeleteObject`, sin `DeleteObjectVersion`):

```
{
  "Version": "2012-10-17",
  "Statement": [
    { "Effect": "Allow", "Action": ["s3:PutObject"], "Resource": "arn:aws:s3:::<cubo>/<ruta>/*" },
    { "Effect": "Allow", "Action": ["s3:ListBucket"], "Resource": "arn:aws:s3:::<cubo>" }
  ]
}
```

Activa además el versionado del cubo y una regla de ciclo de vida del proveedor para expirar copias
viejas: la limpieza la hace el proveedor, no APEX. Si tu proveedor no es S3, aplica lo mismo: solo
escritura y listado. Una credencial con permiso de borrado anula la razón de tener la copia remota.

## Hacer el respaldo de la KEK (una vez, y tras cada cambio de KEK)

Desde la raíz del repositorio, con una terminal interactiva (no sirve por tubería ni desde un script sin terminal):

```
docker volume create apex-kek-salida
docker run --rm --user 0 -v apex-kek-salida:/s --entrypoint sh apex-backup:local -c 'chown 10001:10001 /s && chmod 700 /s'
docker compose --env-file .env --env-file .env.ops -f infra/compose.yml --profile tools run --rm -v apex-kek-salida:/salida tools export-kek --out /salida/kek.age --as <correo de un admin>
docker run --rm -v apex-kek-salida:/s:ro --entrypoint cat apex-backup:local /s/kek.age > kek.age
docker volume rm apex-kek-salida
```

El volumen nombrado desechable evita dejar carpetas abiertas (`chmod 777`) en el disco del servidor. `age` pide la frase dos veces. Copia `kek.age` a las dos copias fuera del servidor y bórralo del servidor. El comando no sobrescribe un archivo existente, no escribe bajo la carpeta de respaldos ni bajo la carpeta de la KEK viva, y deja una entrada en la auditoría y en la bitácora de cifrado (sin material).

## Comprobar el respaldo de la KEK cada mes

```
docker volume create apex-kek-salida
docker run --rm --user 0 -i -v apex-kek-salida:/s --entrypoint sh apex-backup:local -c 'cat > /s/kek.age && chown -R 10001:10001 /s && chmod 700 /s' < kek.age
docker compose ... --profile tools run --rm -v apex-kek-salida:/salida:ro tools verify-kek-backup /salida/kek.age --as <correo>
docker volume rm apex-kek-salida
```

Escribe la misma frase. Dice `verify-kek-backup: total=N failed=M`. Salida 0 con `failed=0`: el respaldo abre todas las llaves de datos de la base. Salida 1: alguna llave no abre (la KEK exportada no corresponde a la base actual: exporta de nuevo). Salida 2: el archivo o la frase están mal. Esta prueba no escribe la KEK en ningún archivo.

## Restaurar paso a paso (servidor nuevo o base perdida)

Necesitas: las tres piezas, la llave pública de firma y los archivos del juego de respaldo (`latest.json`, `latest.json.minisig` y los dos `.age`) en el volumen `backups`.

1. **Levanta solo la base** y crea una base vacía con el nombre de siempre. Aplica las migraciones y los roles según RUNBOOK §12 si es un servidor nuevo.
2. **Restaura la base y los uploads con `restore.sh`.** Corre dentro de la imagen `backup`, con la credencial del propietario por archivo de entorno (nunca por argumentos) y el volumen de uploads escribible solo en esta invocación:
   ```
   docker run --rm --network <red del proyecto> --env-file restore.env -v <volumen backups>:/data/backups -v <volumen uploads>:/data/uploads -v <carpeta con la identidad y la llave pública>:/k:ro -v <llave de firma del servicio>:/run/apex/backup/sign.key:ro --tmpfs /tmp --entrypoint /opt/backup/restore.sh apex-backup:local /data/backups/latest.json -i /k/id.txt -P /k/backup-sign.pub --confirm-database <nombre de la base>
   ```
   `restore.env` lleva `PGHOST`, `PGUSER`, `PGPASSWORD`, `PGDATABASE` y `BACKUP_AGE_RECIPIENT`; bórralo al terminar. El script, en este orden: verifica la firma del manifiesto, comprueba el `sha256` de los dos archivos, inspecciona el contenido del `tar` de uploads (rechaza enlaces, rutas absolutas, `..` y nombres fuera de `uploads/`), mira si la base de destino tiene datos, toma un respaldo previo (`pre-restore-<fecha>`) y solo entonces restaura. Cualquier negativa antes de ese punto sale con 2 sin tocar la base.
3. **Vuelve a dar los permisos de los roles con `dbsetup`.** `restore.sh` restaura sin permisos (`--no-acl`) y todo o nada (`--single-transaction`): si algo falla, la base queda como estaba. Los `GRANT` no vienen en el volcado, así que, antes de arrancar el api, corre `docker compose ... --profile prod-init run --rm --no-deps dbsetup` (RUNBOOK §12) sobre la base restaurada.
   La restauración copia los uploads con dueño uid 10001 y modo 600/700, pero **no retira** los archivos que ya estaban en `/data/uploads` y no vienen en el respaldo. Si quieres una réplica exacta, vacía el volumen de uploads antes de restaurar.
4. **Anota el ancla.** Al final imprime `ancla de auditoría: through_seq=N through_hash=...`. Es el punto hasta el que la cadena de auditoría estaba verificada. Después de arrancar el api, `verify-audit --as <correo>` debe decir "Cadena íntegra" y la fila más reciente de `audit.verifications` debe tener esos mismos valores.
5. **Restaura la KEK sin que toque el disco en claro.** `restore-kek` se niega por diseño a escribir bajo la carpeta de la KEK viva, así que el archivo se escribe en `/dev/shm` (un `tmpfs` en memoria de todo contenedor; `docker compose run` no tiene `--tmpfs`) y se instala en el volumen `keys` dentro de la misma ejecución; al terminar se borra (`shred -u` si existe, si no `rm`). Nada queda en el disco del servidor:
   ```
   docker volume create apex-kek-salida
   docker run --rm --user 0 -i -v apex-kek-salida:/s --entrypoint sh apex-backup:local -c 'cat > /s/kek.age && chown -R 10001:10001 /s && chmod 700 /s' < kek.age
   docker compose ... --profile tools run --rm -v apex-kek-salida:/salida:ro --entrypoint sh tools -c 'python -m app.cli restore-kek /salida/kek.age --out /dev/shm/kek.bin --as <correo> && install -m 600 /dev/shm/kek.bin /run/apex/keys/kek.bin; rc=$?; (shred -u /dev/shm/kek.bin 2>/dev/null || rm -f /dev/shm/kek.bin); exit $rc'
   docker volume rm apex-kek-salida
   ```
   Escribe la frase cuando `age` la pida. `restore-kek` corre aunque la KEK viva no exista y aunque la base no responda (sin base responde `sin bitácora`, imprime una línea JSON `restore_sin_bitacora` con el correo declarado y la hora, y sale 0; solo los errores de conexión cuentan como "base caída": cualquier otro error se muestra y el comando falla). Si la KEK fuera la equivocada, el api no arranca y el log dice `unwrap_failed` (sin material): no se ha dañado nada.
6. **Comprueba**: abre la ficha de un socio y revela su documento; corre `verify-audit`; mira `/health`.
7. **Restaurar también OpenBao (`--with-openbao`).** Con OpenBao instalado, la restauración incluye su instantánea; **no la hagas a medias**. Orden:
   1. Con el volumen `openbao-data` vacío, `$DC up -d openbao` e inicialízalo **de nuevo** (`bao operator init`, 5 llaves, umbral 3): el clúster nuevo tiene su raíz inicial y sus llaves propias, que quedan sin valor. Desellalo con ellas y guarda la raíz en un archivo 600 efímero (por ejemplo en un `tmpfs`).
   2. Agrega a la orden del paso 2 `--with-openbao --openbao-token-file <archivo con la raíz>` (el contenedor debe estar en la red `custody` y ver `openbao:8200`). `restore.sh` valida la entrada `openbao_snapshot` del manifiesto firmado, copia la instantánea, comprueba su `sha256` **antes** de tocar la base y la restaura en último lugar con `sys/storage/raft/snapshot-force` (el clúster nuevo tiene otras llaves de desello; sin `-force` OpenBao rechaza la instantánea). Es un camino que no corre por defecto.
   3. **Reinicia OpenBao y desellalo con las llaves ORIGINALES** (3 de las 5 del clúster que tomó la instantánea, `docs/operacion/openbao.md` §10). Hasta el reinicio sigue desellado con la llave en memoria del clúster nuevo; las llaves nuevas ya no sirven y la raíz nueva desaparece con la restauración. **Sin las llaves originales la KEK de Transit es irrecuperable.**
   4. Comprueba con un descifrado real (`/health.crypto` en `ok` y la ficha de un socio) antes de dar por terminado.
8. **Si usas `restore.sh` sobre una base con datos** (para volver atrás un error), añade `--i-know-this-overwrites`. El respaldo previo `pre-restore-*` es tu red de seguridad; no lo borres hasta confirmar que todo está bien.

## Recuperar la KEK sin APEX

Si el código de APEX no está, la KEK sale con la herramienta `age` de cualquier equipo:

```
umask 077
age -d -o kek.bin kek.age
```

Escribe la frase. `kek.bin` debe pesar exactamente 32 bytes. Con `umask 077` queda en modo 600. Guárdalo en un lugar sin respaldo y bórralo cuando termines (`shred -u kek.bin` si existe, si no `rm`).

## Si se perdió una pieza

- **Perdiste una de las dos copias de una pieza:** haz una copia nueva hoy, desde la que queda.
- **Perdiste la frase de la KEK pero tienes el servidor vivo:** exporta de nuevo con `export-kek` (frase nueva) y guarda las dos copias; el `kek.age` viejo ya no sirve para nada.
- **Perdiste el servidor y la frase:** los datos cifrados de los socios no se pueden recuperar (nombre, apellido, pagos y fechas sí, porque están en claro). No hay puerta trasera.
- **Perdiste la identidad `age` de restauración:** los respaldos existentes no se pueden abrir. Genera una nueva (RUNBOOK §12), cambia `BACKUP_AGE_RECIPIENT` y haz un respaldo nuevo ya.
- **Perdiste las llaves de desello originales de OpenBao (menos de 3 de 5) y no hay otra copia:** la instantánea de OpenBao no se puede abrir y la KEK de Transit es irrecuperable; los datos cifrados solo se recuperan con el `kek.age` exportado (paso "Recuperar la KEK sin APEX"). Repártelas como indica `docs/operacion/openbao.md` §3.
- **Perdiste la llave pública de firma:** puedes restaurar con `--i-know-unsigned --sha256-db <hex> --sha256-uploads <hex>` si conoces los `sha256` por otro canal; sin firma, el manifiesto no prueba nada.

## Lista de comprobación de cada simulacro

- [ ] Las tres piezas están en dos lugares fuera del servidor.
- [ ] `verify-kek-backup` dio `failed=0` este mes.
- [ ] Se restauró un respaldo en una base de prueba y se reveló un documento.
- [ ] Otra persona siguió esta guía sin ayuda y llegó al mismo resultado (nombre y fecha: ____________).
