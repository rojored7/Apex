# Actualizar APEX en un servidor

Guía para la persona que pone una versión nueva en un servidor ya instalado (`instalar-en-servidor.md`).
La actualización se hace con **un solo comando**, `infra/deploy.sh`, que verifica todo antes de tocar
nada, respalda, construye las imágenes en el propio servidor, levanta la versión y comprueba que
quedó sana. No usa registro de imágenes: construye desde el código de la etiqueta.

## Antes de empezar

1. **La versión y su SHA.** Una versión es una etiqueta `vX.Y.Z`. Su SHA completo (40 caracteres) está
   en el `CHANGELOG.md` (cuerpo de la sección de esa versión) o en la página del Release de GitHub.
   Cópialo del Release (o del `CHANGELOG.md` publicado), **no del clon del servidor**: `--expect-sha` existe
   para que una etiqueta movida o falsificada no se despliegue, y un SHA tomado del mismo clon que se
   quiere comprobar no comprueba nada.
2. **La copia de la KEK.** Ten a mano el archivo `kek.age` que exportaste (`respaldo-y-restauracion.md`).
   `deploy.sh` no lo descifra; exige que exista, sea legible y empiece por la cabecera de `age`
   (`age-encryption.org/v1`) como constancia de que la copia está hecha.
3. **El servidor sano.** `docker compose --env-file .env --env-file .env.ops -f infra/compose.yml ps`
   con `db` en marcha. Este script actualiza un servidor instalado; no instala.
4. **Los archivos de entorno.** `.env` y `.env.ops` con modo 600, tuyos, sin valores `cambiar-esto`,
   no versionados.

## Paso a paso

Desde la raíz del repositorio, en el servidor:

```
git fetch --tags
bash infra/deploy.sh --ref v0.1.0 --expect-sha <SHA de 40 caracteres> --kek-file /ruta/a/kek.age --i-know-unsigned-ref
```

En v0.1 las etiquetas no se firman (la firma llega en v0.2), así que `--i-know-unsigned-ref` es
obligatorio: sin la bandera el script sale con 2 ("etiqueta sin firma verificable"). Al pasarla aceptas
que la única garantía es el SHA que copiaste del Release.

Si usas la identidad de verificación del respaldo (lo recomendado), añade el archivo de Compose
adicional para que el servicio `backup` no la pierda al recrearse:

```
DEPLOY_COMPOSE_EXTRA=infra/compose.verify.yml bash infra/deploy.sh --ref v0.1.0 --expect-sha <SHA> --kek-file /ruta/a/kek.age --i-know-unsigned-ref
```

Lo que hace, en orden (si algo de los pasos 1 a 5 falla, no se tocó nada del servidor: el código solo
pasa a la etiqueta al final de la preverificación y, si luego algo la rechaza, vuelve a donde estaba):

1. Valida los argumentos: `--ref` debe ser `vX.Y.Z` (nunca una rama) y `--expect-sha` 40 caracteres.
2. `git fetch --tags`; la etiqueta debe resolver exactamente al SHA esperado.
3. Exige una firma verificable: con `.github/allowed_signers` usa `git verify-tag`; sin ese archivo (v0.1)
   o con firma inválida sale con 2 salvo que pases `--i-know-unsigned-ref`.
4. Exige el árbol de trabajo limpio.
5. Revisa `.env` y `.env.ops` (modo, dueño, sin seguimiento de git, sin ejemplos, contraseñas de 24
   caracteres o más y distintas), la copia de la KEK y, si hay respaldo, `BACKUP_AGE_RECIPIENT` y
   `BACKUP_SIGN_PUBKEY`. Después pasa al SHA de la etiqueta (`git checkout -q --detach`), valida
   `docker compose config -q` y que `db` esté en marcha; si algo de eso falla, devuelve el código.
6. Hace un respaldo `pre-deploy` (dos archivos cifrados y un manifiesto firmado) y comprueba que está
   completo y que su firma verifica. Si falla, no sigue.
7. Etiqueta las imágenes que corren ahora como `apex-api:prev-<fecha>`, `apex-web:prev-<fecha>` y
   `apex-backup:prev-<fecha>` y guarda `deploy-<fecha>.state.json`.
8. Construye las imágenes con `GIT_SHA=<etiqueta>` y ejecuta `docker compose up -d`. `migrate` y
   `dbsetup` corren solos antes del api.
9. Pregunta cada 3 segundos a `http://127.0.0.1:<WEB_PORT>/api/v1/health` hasta
   `DEPLOY_HEALTH_TIMEOUT` (120 s por omisión) y exige `"db":"ok"` y `"migrations":"ok"`.
   Con OpenBao sellado (`"crypto":"sealed"`, HTTP 503 con `db` y `migrations` en `ok`) el despliegue
   **sale con 0** y avisa "api en estado sellado: desellar OpenBao": no es un fallo; desselle según
   `docs/operacion/openbao.md` §4 y el api se recupera solo en 40 segundos o menos (S5-B3).
10. Lee el entorno del api (`/proc/1/environ`): no debe traer contraseñas de operación, debe usar el rol
    `apex_api` y su `APP_VERSION` debe ser la etiqueta.
11. Imprime `despliegue listo: versión ...`.

`APP_VERSION` (la `version` de `/health`) sale de `GIT_SHA` en el `up`: `deploy.sh` exporta `GIT_SHA=<etiqueta>` en la construcción y
en el arranque. Si arrancas el stack a mano sin exportarla, `version` sale `dev`.

Los archivos de estado quedan fuera del repositorio, en `${XDG_STATE_HOME:-$HOME/.local/state}/apex-deploy/`
(o en `DEPLOY_STATE_DIR` si lo defines). Conserva esa carpeta mientras dure la versión.

## Qué significa cada salida

| Salida | Significa | Qué hacer |
|---|---|---|
| `0` | Desplegado y sano. | Entra a la aplicación y revisa. Nada más. |
| `2` | Se rechazó en la preverificación. **No se tocó nada** (el mensaje dice por qué: SHA distinto, árbol sucio, `.env` con modo 644, contraseña corta, `db` detenida...). | Corrige lo que dice y repite. |
| `1` y el mensaje habla de respaldo | El respaldo `pre-deploy` falló o quedó incompleto. No se construyó ni se levantó nada. | Revisa `docker compose logs backup`, la identidad y la llave de firma; repite. |
| `1` y el mensaje habla de construcción | La construcción falló. Lo que corría no se tocó. | Lee el error de `docker compose build`; repite. |
| `1` tras `up -d` o por la salud | El servidor quedó con la versión nueva a medias o sin sanar. Imprime las últimas 100 líneas del log del api y escribe `rollback-<fecha>.txt`. | Sigue la sección siguiente. |

Opciones para casos excepcionales (usa solo si sabes por qué):
`--i-know-no-backup` (no hace respaldo `pre-deploy`: la base no tendrá vuelta atrás) y
`--i-know-unsigned-ref` (obligatoria en v0.1: continúa sin firma de etiqueta verificable). `DEPLOY_SKIP_BUILD=1` reutiliza imágenes ya construidas, pero solo si su
etiqueta `org.opencontainers.image.revision` coincide con `--ref`.

## Si salió 1 después de levantar: volver atrás

`rollback-<fecha>.txt` lista las etiquetas `prev-*`, el respaldo previo y los comandos para volver al
código y a las imágenes anteriores. **El script no restaura la base.** Si la migración nueva ya corrió,
volver a la imagen vieja no deshace el esquema. Decide con `docs/RUNBOOK.md` sección 12
("Despliegue, rollback y `migrations: mismatch`"): primero intenta que la versión nueva sane (a veces
el api solo necesitaba más tiempo: `curl` al `/health` otra vez); si no, vuelve al código y las imágenes
anteriores con `rollback-<fecha>.txt` y, solo si el esquema nuevo lo exige, restaura el respaldo
`pre-deploy` con `restore.sh` (`respaldo-y-restauracion.md`).
