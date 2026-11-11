# Adjuntos

Alcance: almacén de archivos adjuntos del api (volumen `uploads` o S3). El resto de la guía llega en C1.

## Variables

- `STORAGE_PROVIDER`: `local` (por defecto) o `s3` (apagado en v0.3). Va en `.env`.
- `S3_ENDPOINT_URL`, `S3_BUCKET`, `S3_REGION`, `S3_ACCESS_KEY_ID`: van en `.env`. Con `s3` las cinco variables `S3_*` son obligatorias; el endpoint es `https` salvo `ENV=dev`.
- `S3_SECRET_ACCESS_KEY`: va en `.env.ops` y solo la recibe el api. Nunca la pongas en `.env`: ese archivo lo leen `worker` y `tools` por `env_file` y heredarían el secreto (la prueba `test_env_example` prohíbe la clave en `.env.example` y `test_env_isolation.sh` la detecta en un stack vivo). El endpoint es solo esquema y host: una URL con usuario, contraseña, consulta o fragmento se rechaza al arrancar.
- `S3_ENABLE_PRODUCTION`: `false` por defecto. Con `s3` y `ENV=production` debe ser `true` o el api no arranca.
- Topes por usuario (en `.env`): `USER_ATTACHMENTS_UPLOAD_LIMIT_PER_MIN` (10), `USER_ATTACHMENTS_PHOTO_LIMIT_PER_MIN` (600), `USER_ATTACHMENTS_DOWNLOAD_LIMIT_PER_MIN` (30) y `USER_ATTACHMENTS_DOWNLOAD_LIMIT_PER_HOUR` (200).
