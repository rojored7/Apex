# Instalar APEX en un servidor

Guía para la persona que instala APEX por primera vez en el servidor del box. Cubre una instalación
nueva de la versión 0.1.0. Para actualizar un servidor ya instalado, usa `actualizar.md`; para el
respaldo y la restauración, `respaldo-y-restauracion.md`. Todos los comandos se corren desde la
raíz del repositorio, en el servidor, salvo donde se diga lo contrario.

**TLS: todavía no; v0.1 es de LAN (P7); Caddy en v0.2.** APEX se sirve por HTTP dentro de la red
local del box. La contraseña y la cookie de sesión viajan en claro por esa red. No lo publiques en
Internet. Esa decisión queda escrita en el `.env` con `ALLOW_INSECURE_COOKIE=true` (paso 4).

## 1. Qué necesitas

- Un servidor Linux de 64 bits (por ejemplo Ubuntu Server 24.04) con 2 GB de memoria libres y 10 GB
  de disco.
- Acceso con `sudo` y conexión a Internet para instalar Docker y construir las imágenes.
- Una máquina aparte (tu computador) para generar la identidad de restauración y guardar las copias
  de la KEK. Esas piezas **no** viven en el servidor.

## 2. Docker Engine y Compose

Sigue la guía oficial de Docker para tu distribución (`https://docs.docker.com/engine/install/`):
instala `docker-ce`, `docker-ce-cli`, `containerd.io` y los plugins `docker-buildx-plugin` y
`docker-compose-plugin`. Después:

```
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"
```

Cierra la sesión y entra de nuevo para que el grupo surta efecto. Comprueba:

```
docker version
docker compose version
systemctl is-enabled docker
```

`systemctl is-enabled docker` debe decir `enabled`: así el servidor levanta Docker (y los
contenedores con `restart: unless-stopped`) solo después de un reinicio.

También hacen falta `git`, `curl` y `openssl` (`sudo apt-get install -y git curl openssl`).

## 3. Obtener la versión

```
git clone <url del repositorio> apex
cd apex
git fetch --tags
git checkout v0.1.0
git rev-parse 'v0.1.0^{commit}'
```

El último comando imprime el SHA de la etiqueta. Compáralo con el SHA de cierre que está en el
`CHANGELOG.md` (sección `0.1.0`) o en la página del Release: si no coinciden, no sigas.

## 4. Archivos de entorno

Hay dos, los dos con modo 600 y fuera de git (`.gitignore` ya los excluye):

```
umask 077
cp .env.example .env
cp .env.ops.example .env.ops
chmod 600 .env .env.ops
```

**`.env`** (lo que lee el api): cambia al menos
`ENV=production`, `FRONT_BASE_URL=http://<ip o nombre del servidor>[:puerto]` (el puerto debe
coincidir con `WEB_PORT`; el 80 se omite), `TRUSTED_PROXIES=172.30.0.10/32` (la IP fija de Nginx,
no la cambies salvo que cambies `APEX_WEB_IP`) y `ALLOW_INSECURE_COOKIE=true` (aceptas P7: sin TLS).
`CORS_ORIGINS` queda vacío (Nginx sirve front y api en el mismo origen); nunca pongas `*`. No pongas
contraseñas ni `POSTGRES_*` en este archivo.

**`.env.ops`** (todo lo demás): reemplaza **cada** `cambiar-esto`. Las cuatro contraseñas se generan
una por una, distintas entre sí, de 48 caracteres:

```
openssl rand -hex 24
```

Úsalas en `POSTGRES_PASSWORD`, `APEX_API_DB_PASSWORD`, `APEX_WORKER_DB_PASSWORD` y
`APEX_BACKUP_DB_PASSWORD`, y pon la de `POSTGRES_PASSWORD` también dentro de `DATABASE_URL`.
`POSTGRES_DB` es el nombre de la base (`apex`). `WEB_PORT` es el puerto del servidor (80 por
omisión). Comprueba que no quedó ningún valor de ejemplo:

```
grep -c 'cambiar-esto' .env .env.ops
```

Debe dar `0` en los dos. `deploy.sh` revisa esto mismo (modo, dueño, contraseñas) antes de tocar nada.

## 5. Llaves de respaldo

El respaldo usa tres juegos de llaves. Las imágenes ya traen `age` y `minisign`; el servidor no los
necesita instalados. Primero construye la imagen de respaldo:

```
docker compose --env-file .env --env-file .env.ops -f infra/compose.yml build backup
```

**a) Identidad `age` de restauración (en tu computador, no en el servidor).** Genérala con
`age-keygen -o apex-restauracion.txt`. El archivo contiene una línea que empieza por
`AGE-SECRET-KEY-1<...>`: es la llave privada; guárdala en dos copias fuera del servidor y nunca la
copies a él. La línea `# public key: age1...` es la parte pública: pégala en `.env.ops` como
`BACKUP_AGE_RECIPIENT`.

**b) Identidad de verificación y llave de firma (en el servidor, en una carpeta tuya).**

```
mkdir -p "$HOME/apex-secretos" && chmod 700 "$HOME/apex-secretos"
docker run --rm -v "$HOME/apex-secretos:/k" --entrypoint sh apex-backup:local -c \
  'age-keygen -o /k/backup-verify-identity.txt && minisign -G -W -p /k/backup-sign.pub -s /k/backup-sign.key'
sudo chown 10001:10001 "$HOME/apex-secretos"/backup-*
sudo chmod 600 "$HOME/apex-secretos"/backup-*
```

(`minisign -G -W` crea la llave sin contraseña: el servicio de respaldo la usa solo y la protege el
modo 600.) En `.env.ops`:

- `BACKUP_AGE_VERIFY_RECIPIENT`: la línea `# public key: age1...` de `backup-verify-identity.txt`
  (`sudo grep 'public key' "$HOME/apex-secretos/backup-verify-identity.txt"`).
- `BACKUP_VERIFY_IDENTITY_FILE=/home/<tu usuario>/apex-secretos/backup-verify-identity.txt`.
- `BACKUP_SIGN_KEY_FILE=/home/<tu usuario>/apex-secretos/backup-sign.key`.
- `BACKUP_SIGN_PUBKEY`: la segunda línea de `backup-sign.pub` (empieza por `RW`).

La identidad de verificación permite descifrar los respaldos locales: por eso solo se monta en el
servicio `backup` y se arranca con `infra/compose.verify.yml` (paso 7). Sin ella el respaldo queda
`ok_unverified`.

**c) Destino remoto (recomendado).** Sin `BACKUP_RCLONE_REMOTE` el respaldo vive en el mismo disco
que la base y no sobrevive a su pérdida (P3). Si tienes un cubo S3 compatible, configura
`BACKUP_RCLONE_REMOTE=apex:<cubo>/<ruta>` y las `RCLONE_CONFIG_APEX_*` con una credencial **sin**
permiso de borrado (política en `respaldo-y-restauracion.md`).

## 6. Construir y levantar

```
export GIT_SHA=v0.1.0
DC="docker compose --env-file .env --env-file .env.ops -f infra/compose.yml -f infra/compose.verify.yml"
$DC build
$DC up -d db
$DC --profile tools run --rm tools init-keys
```

`GIT_SHA` es la versión que publicará `/health`; usa la etiqueta, nunca una rama. `init-keys` crea
en el volumen `keys` la KEK, la llave de firma del bus y el par JWT, con modo 600, y no sobrescribe
nada. Después:

```
$DC up -d
$DC ps
```

El orden lo resuelve Compose: `db`, luego `migrate` (migraciones con el propietario), `dbsetup`
(roles y permisos), `api`, y por último `worker`, `web` y `backup`. `migrate` y `dbsetup` terminan
con código 0 y quedan `exited`; es lo esperado. Espera a que `api`, `worker`, `web` y `backup`
estén `healthy` (hasta dos minutos la primera vez).

## 7. Primer administrador

Crea `.env.seed` (solo lo lee el servicio `tools`):

```
umask 077
cp .env.seed.example .env.seed
```

Edita `ADMIN_EMAIL` y `ADMIN_INITIAL_PASSWORD` (12 o más caracteres, que no sea común). Luego:

```
$DC --profile tools run --rm tools seed
rm -f .env.seed
```

El administrador debe cambiar la contraseña al entrar. Borra `.env.seed` de inmediato: no hace
falta para arrancar.

## 8. Respaldo de la KEK: dos copias fuera del servidor

Si pierdes la KEK pierdes para siempre los datos cifrados de los socios. **Antes de cargar datos
reales**, exporta la KEK y comprueba la copia, siguiendo `respaldo-y-restauracion.md` (sección
"Hacer el respaldo de la KEK"):

```
$DC --profile tools run --rm -v apex-kek-salida:/salida tools export-kek --out /salida/kek.age --as <correo del admin>
$DC --profile tools run --rm -v apex-kek-salida:/salida:ro tools verify-kek-backup /salida/kek.age --as <correo del admin>
```

(prepara antes el volumen `apex-kek-salida` como indica esa guía.) Guarda el `kek.age`, la frase y la
identidad de restauración en **dos copias** en lugares distintos y **fuera del servidor**. Ese
`kek.age` es también el archivo que pide `deploy.sh --kek-file` en cada actualización.

## 9. Comprobaciones de la instalación

Todas desde el servidor, con `WEB_PORT` el de tu `.env.ops` (80 si no lo cambiaste):

```
curl -s http://127.0.0.1:${WEB_PORT:-80}/api/v1/health
```

Debe mostrar `"status":"ok"`, `"db":"ok"`, `"migrations":"ok"` y la `version` `v0.1.0`. `backup`
aparecerá `unknown` hasta la primera corrida (esta noche, o ahora:
`$DC run --rm backup /opt/backup/run.sh`, que debe terminar con `listo apex-...`; luego
`$DC run --rm worker python -m app.worker.main --run-once backup_check`).

**N-6 · La IP real del cliente llega al api.** Entra a la aplicación desde otro equipo de la red
(`http://<ip del servidor>`) y mira el log:

```
$DC logs --tail 30 api
```

Las peticiones deben mostrar la IP de ese equipo, **no** `172.30.0.10` (la de Nginx). Si ves siempre
`172.30.0.10`, `TRUSTED_PROXIES` no coincide con `APEX_WEB_IP`: corrígelo y reinicia `api`.

**N-7 · El login falso tarda lo mismo que el real.** Un intento con un correo inexistente debe tardar
al menos `LOGIN_MIN_DURATION_MS` (150 ms por omisión) y menos de 250 ms en el percentil 99. Mide 200
intentos fallidos desde el servidor (ninguna cuenta real; son intentos inventados, y el límite de
intentos por IP puede responder 429: espera un minuto entre tandas de 5 o consulta
`docs/RUNBOOK.md` §1 para subir el tope temporalmente en una base de prueba, nunca en producción):

```
for i in $(seq 1 200); do
  curl -s -o /dev/null -w '%{time_total}\n' -X POST http://127.0.0.1:${WEB_PORT:-80}/api/v1/auth/login \
    -H 'Content-Type: application/json' -H 'Origin: http://localhost' \
    -d '{"email":"nadie@ejemplo.invalid","password":"clave-inventada-1234"}'
done | sort -n | awk '{a[NR]=$1} END {print "p99 s:", a[int(NR*0.99)]}'
```

El valor impreso (segundos) debe ser mayor o igual que `LOGIN_MIN_DURATION_MS / 1000` y menor que
`0.250`. Si el servidor responde 429 antes de completar las 200, anota cuántas respuestas fueron
401: la prueba con límites de producción no es medible aquí y se hace en el ensayo.

## 10. Qué sigue

- Programa una revisión mensual de `verify-kek-backup` (ver `respaldo-y-restauracion.md`).
- Para actualizar: `actualizar.md`.
- Importar socios: `importar-socios.md`.
