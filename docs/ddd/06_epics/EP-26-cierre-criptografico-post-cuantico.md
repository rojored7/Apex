# EP-26 · Cierre criptográfico post-cuántico

- **Versión del plan:** v1.0 (versión 1.0, puntos 3 y 4).
- **Bounded context:** Crypto (soporte) y el contenedor `backup`.
- **Estimación relativa:** L.

## Objetivo de negocio

Cerrar la v1.0 con la protección de datos completa y demostrable: backups que no se pueden falsificar, un inventario criptográfico que el gimnasio puede entregar a quien lo audite, y llaves envueltas con un algoritmo que resiste computación cuántica. Es lo que permite decir con evidencia que los datos de los socios están protegidos hoy y en diez años.

## Actores

- Administrador u operador: genera el CBOM, verifica backups.
- Contenedor `backup` y worker: firman y verifican.

## Capacidades incluidas

- Firma de cada backup con ML-DSA usando la clase de dato `backup.signature`; verificación de la firma antes de restaurar y en `backup_check`.
- Informe CBOM exportado desde `crypto_keys` con `cli cbom --format cyclonedx` (y `GET /crypto/cbom` si no se adelantó en EP-18).
- Envoltura de llaves con ML-KEM cuando OpenBao Transit lo implemente; si no, con `liboqs-python` detrás del mismo `KeyProvider`, sin que ningún módulo cambie (el algoritmo va en el dato).
- `liboqs-python` entra solo en esta versión (riesgo 5 de `00b_impact_analysis.md`) y pasa el chequeo de licencias.
- Re-envoltura de las DEK existentes con ML-KEM como `CryptoJob` reanudable, sin recifrar los datos.

## Fuera de alcance

- Cambiar el cifrado de campos (AES-256-GCM se mantiene).
- Certificación externa del inventario.

## Criterios de éxito medibles

- Un backup alterado un solo byte falla la verificación de firma y `backup_check` lo reporta.
- El CBOM en CycloneDX valida contra el esquema y lista cada llave con algoritmo, proveedor, versión y estado.
- Después de la re-envoltura con ML-KEM, todos los datos se leen sin recifrar y `crypto_keys` registra el algoritmo de envoltura nuevo.
- El job de re-envoltura se puede interrumpir y reanudar sin dejar llaves inutilizables.

## Dependencias

- EP-15 Custodia de llaves con OpenBao.
- EP-17 Auditoría firmada post-cuántica (mismo patrón de firma ML-DSA).
- EP-18 Administración de llaves de cifrado (inventario y jobs).
- EP-13 Puesta en marcha y continuidad (servicio `backup` y `backup_check`).

## Riesgos

- Dependencia de que OpenBao implemente ML-KEM; la alternativa con `liboqs-python` agrega una librería nativa a la imagen.
- Re-envolver llaves es una operación irreversible en la práctica; `CLAUDE.md` exige detenerse y preguntar antes.
- Fechas de CBOM ambiguas entre v0.3 y v1.0 (ver preguntas abiertas).

## Pantallas del diseño que habilita

- Botón "Exportar CBOM" de `Llaves` (si no se habilitó en v0.3).
