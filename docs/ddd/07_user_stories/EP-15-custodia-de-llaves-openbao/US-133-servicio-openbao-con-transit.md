# US-133 · Como administrador quiero un OpenBao con motor Transit en el Compose del gimnasio para que la llave maestra deje de vivir en un archivo del servidor de aplicación

- **Épica:** EP-15 · Custodia de llaves con OpenBao
- **Bounded context:** Crypto (soporte); servicio `openbao` en `infra/`
- **Versión:** v0.2
- **Actor:** administrador
- **Tamaño:** 5
- **Prioridad:** P0 ruta crítica
- **Refinamiento:** Criterios completos; BDD solo de flujo principal
- **Pantalla:** Ninguna (historia sin front)

## Historia

Como administrador
quiero un servicio `openbao` con Transit habilitado, una llave por `data_class` y un procedimiento de desellado documentado
para custodiar la KEK y las llaves de firma fuera del proceso del api

## Contexto de dominio

- **Aggregate / entidades:** CryptoKey (las llaves de Transit respaldan las KEK por `data_class`).
- **Reglas que aplica:** RN-13; `CLAUDE.md` (OpenBao MPL-2.0 aceptado solo sin modificar; secretos por `.env` o volumen, nunca en imagen); `04_architecture_decision.md` sección 4 (desellado con llaves fuera del servidor).
- **Eventos que emite:** ninguno.
- **Eventos que consume:** ninguno.
- **Funciones puras:** ninguna.

## Alcance

- **Backend:** `infra/openbao/config.hcl` (almacenamiento en volumen `openbao-data`, listener solo en la red interna de Compose, sin UI expuesta), servicio `openbao` en `infra/compose.yml` y `compose.dev.yml` (modo dev para pruebas), script `infra/openbao/bootstrap.sh` idempotente que inicializa (Shamir 3 de 5), habilita Transit, crea las llaves `apex-kek-<data_class>` para las cinco clases de v0.1 y `apex-sign-audit`, y crea una política y un token o AppRole para el api con permisos solo de `encrypt`, `decrypt`, `sign`, `verify` y `rotate` sobre esas llaves. Documento `docs/operacion/openbao.md` con desellado tras reinicio y recuperación ante pérdida de una llave de desellado.
- **Front:** No aplica.

## Criterios de aceptación

1. `openbao` no publica puertos al host en `compose.yml`; solo `api` y `worker` lo alcanzan por la red interna.
2. `bootstrap.sh` ejecutado dos veces no crea llaves duplicadas ni cambia las existentes (idempotente).
3. Existen llaves de Transit para `member.document`, `member.phone`, `member.email`, `member.birth_date`, `member.emergency_contact` y una de firma para auditoría.
4. La política del api no permite exportar llaves (`exportable = false`, `allow_plaintext_backup = false`) ni administrar el servidor.
5. Las llaves de desellado y el token raíz nunca se escriben en el repositorio, la imagen ni los logs; el script las muestra una sola vez y el documento indica guardarlas fuera del servidor en al menos dos lugares.
6. Tras reiniciar el contenedor, OpenBao queda sellado y el procedimiento documentado lo desella con 3 de las 5 llaves.
7. La versión de OpenBao queda fijada en la imagen y su licencia MPL-2.0 sin modificar queda en `NOTICE`.

## Escenarios BDD

```gherkin
# language: es
Característica: Servicio OpenBao con Transit

  Escenario: Inicializar OpenBao por primera vez
    Dado un servicio "openbao" recién creado
    Cuando el administrador ejecuta "bootstrap.sh"
    Entonces Transit queda habilitado con una llave por cada data_class de v0.1
    Y el api tiene un token con permisos solo de encrypt, decrypt, sign, verify y rotate

  Escenario: Bootstrap repetido no altera llaves
    Dado que "bootstrap.sh" ya se ejecutó
    Cuando el administrador lo ejecuta de nuevo
    Entonces las llaves conservan su versión
    Y no se generan nuevas llaves de desellado
```

## Endpoints

- Ninguno del api. API de OpenBao interna (`/v1/transit/...`).

## Pantalla

- Ninguna.

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** no aplica.
- **Funciones puras a probar:** ninguna.
- **Pruebas:** smoke en CI con OpenBao en modo dev; prueba de idempotencia del bootstrap.
- **Archivos principales:** `infra/openbao/config.hcl`, `infra/openbao/bootstrap.sh`, `infra/compose.yml`, `docs/operacion/openbao.md`.

## Supuestos

- Supuesto: esquema Shamir de 5 llaves con umbral 3 (los documentos no fijan el número).
- Supuesto: autenticación del api con AppRole o token con TTL renovable, entregado por volumen; los documentos solo dicen "token o credenciales por volumen o `.env`".

## Dependencias

- US-005 · Dockerfile del api y Compose.

## INVEST

- **Independiente:** infraestructura aislada; no toca el bus todavía.
- **Negociable:** umbral Shamir y método de autenticación.
- **Valiosa:** saca la llave maestra del servidor de aplicación.
- **Estimable:** configuración conocida.
- **Pequeña:** un servicio, un script y un documento.
- **Testeable:** smoke e idempotencia.

## Definición de terminado

- [ ] `shellcheck` en verde
- [ ] Smoke de OpenBao en CI en verde
- [ ] Licencia registrada en `NOTICE`
- [ ] Revisión de PR aprobada
