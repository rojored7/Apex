# EP-15 · Custodia de llaves con OpenBao

- **Versión del plan:** v0.2 (puntos 1 y 2 de la versión 0.2).
- **Bounded context:** Crypto (soporte, `core/crypto/`), adaptador `OpenBaoProvider` del puerto `KeyProvider`.
- **Estimación relativa:** L.

## Objetivo de negocio

Sacar la llave maestra del servidor de aplicación. Con la KEK en un archivo (v0.1), quien copie el disco se lleva los datos y la llave; con OpenBao Transit la llave maestra nunca sale del custodio, se puede revocar y cada uso queda registrado. Es el paso que convierte el cifrado de los datos personales en una protección real y no solo nominal.

## Actores

- Administrador u operador: instala, desella y mantiene OpenBao; ejecuta la migración de proveedor.
- Bus de criptografía: único cliente de OpenBao.

## Capacidades incluidas

- `infra/openbao/config.hcl` y servicio `openbao` en Compose, con desellado usando llaves guardadas fuera del servidor.
- Motor Transit habilitado con una llave por `data_class` y una de firma.
- `OpenBaoProvider` implementando `KeyProvider` (`wrap`, `unwrap`, `sign`, `verify`, `rotate`, `key_info`) con la API de Transit y `httpx` con timeout explícito.
- `cli migrate-provider local→openbao`: re-envuelve las DEK con la KEK de OpenBao sin recifrar datos; queda como `CryptoJob` de tipo `migrate_provider` y en `crypto_ops`.
- Selección del proveedor por `CRYPTO_PROVIDER` en `.env`; token o credenciales de OpenBao por volumen o `.env`, nunca en la imagen.
- `CryptoKey.provider` pasa de `local` a `openbao` en las llaves migradas.
- Procedimiento documentado de desellado tras un reinicio del servidor y de recuperación ante pérdida de una llave de desellado.

## Fuera de alcance

- Firma ML-DSA de la auditoría (EP-17, requiere OpenBao 2.7 o superior).
- Pantalla de llaves (EP-18).
- Envoltura con ML-KEM (EP-26).

## Criterios de éxito medibles

- Después de `migrate-provider`, todos los datos cifrados en v0.1 se leen sin recifrar y `crypto_keys` no contiene material envuelto con la KEK local.
- Borrar el archivo de la KEK local después de migrar no afecta la lectura de datos.
- Con OpenBao sellado, el API arranca en un estado degradado y explícito (`/health` lo reporta) en lugar de fallar en silencio.
- Correr `migrate-provider` dos veces no cambia nada la segunda vez (idempotente).
- Prueba de integración del `OpenBaoProvider` contra un OpenBao real en `compose.dev.yml`.

## Dependencias

- EP-02 Bus de criptografía (puerto `KeyProvider`, llaves y bitácora).
- EP-13 Puesta en marcha y continuidad (Compose de producción, backup, `deploy.sh`).

## Riesgos

- Operación por una persona no técnica: un reinicio del servidor deja OpenBao sellado y el sistema sin poder leer datos hasta desellarlo.
- Perder las llaves de desellado equivale a perder todos los datos cifrados.
- Una migración interrumpida a mitad de camino deja llaves en dos proveedores; el job debe poder reanudarse.

## Pantallas del diseño que habilita

- Ninguna propia. El inventario de llaves por proveedor se ve en `Llaves` (EP-18).
