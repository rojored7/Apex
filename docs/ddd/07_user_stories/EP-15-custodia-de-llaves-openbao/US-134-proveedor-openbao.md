# US-134 · Como administrador quiero que el bus de criptografía use OpenBao como proveedor de llaves para que envolver y desenvolver las DEK ocurra en el custodio y quede registrado

- **Épica:** EP-15 · Custodia de llaves con OpenBao
- **Bounded context:** Crypto (`core/crypto/openbao_provider.py`)
- **Versión:** v0.2
- **Actor:** administrador
- **Tamaño:** 8
- **Prioridad:** P0 ruta crítica
- **Refinamiento:** Criterios completos; BDD solo de flujo principal
- **Pantalla:** Ninguna (historia sin front)

## Historia

Como administrador
quiero un `OpenBaoProvider` que implemente el puerto `KeyProvider` y se elija con `CRYPTO_PROVIDER=openbao`
para que ningún módulo cambie y la KEK nunca salga de OpenBao

## Contexto de dominio

- **Aggregate / entidades:** CryptoKey (`provider` = `openbao`), CryptoOp.
- **Reglas que aplica:** RN-13; reglas del bus de `CLAUDE.md` (única puerta; el llamador no elige llave ni algoritmo; el algoritmo va en el dato; `crypto_keys` nunca guarda material en claro); `04_architecture_decision.md` sección 5 (httpx con timeout explícito).
- **Eventos que emite:** ninguno.
- **Eventos que consume:** ninguno.
- **Funciones puras:** `openbao_provider.key_name(purpose, data_class) -> str`; mapeo de errores HTTP de OpenBao a excepciones del bus.

## Alcance

- **Backend:** `OpenBaoProvider` con `wrap`, `unwrap`, `sign`, `verify`, `rotate` y `key_info` sobre la API de Transit (`/transit/encrypt`, `/transit/decrypt`, `/transit/sign`, `/transit/verify`, `/transit/keys/<n>/rotate`, `/transit/keys/<n>`) usando `httpx.AsyncClient` con timeout explícito (`OPENBAO_TIMEOUT_S`, por defecto 5) y TLS verificado si `OPENBAO_ADDR` es HTTPS. Selección por `CRYPTO_PROVIDER` (`local` u `openbao`) en `Settings`; variables `OPENBAO_ADDR` y `OPENBAO_TOKEN_PATH`. Las DEK se desenvuelven una vez al arrancar y viven en memoria como en v0.1. Cada operación queda en `crypto_ops` con `key_id` y `key_version`. Prueba de contrato común que corre igual contra `LocalFileProvider` y `OpenBaoProvider`.
- **Front:** No aplica.

## Criterios de aceptación

1. Con `CRYPTO_PROVIDER=openbao`, el api arranca, desenvuelve las DEK con OpenBao y los cinco campos cifrados de socios se leen y escriben igual que con el proveedor local.
2. La misma suite de contrato de `KeyProvider` pasa contra `LocalFileProvider` y contra `OpenBaoProvider` con un OpenBao real de `compose.dev.yml`.
3. Ningún módulo fuera de `core/crypto` cambia; el lint `banned-api` sigue en verde.
4. El token de OpenBao se lee de archivo (`OPENBAO_TOKEN_PATH`), nunca de la imagen, y no aparece en logs ni en `crypto_ops`.
5. Toda llamada a OpenBao tiene timeout; si OpenBao no responde dentro del timeout, la operación falla con un error de dominio del bus y queda en `crypto_ops` con `result = error`.
6. `crypto_keys` guarda para las llaves de OpenBao solo metadatos y el material envuelto por Transit (`vault:v<n>:...`), nunca la DEK en claro.
7. Con un `CRYPTO_PROVIDER` desconocido, el api no arranca y el error lo nombra.

## Escenarios BDD

```gherkin
# language: es
Característica: Proveedor OpenBao

  Escenario: Leer y escribir socios con OpenBao
    Dado "CRYPTO_PROVIDER" en "openbao" y OpenBao desellado
    Cuando registro un socio con documento "1020304"
    Entonces el documento se guarda como blob "apx1."
    Y al mostrarlo en claro obtengo "1020304"
    Y "crypto_ops" registra el unwrap de la DEK con provider "openbao"

  Escenario: OpenBao no responde
    Dado OpenBao detenido
    Cuando el bus intenta desenvolver una DEK
    Entonces la operación falla después del timeout configurado
    Y "crypto_ops" registra la operación con resultado "error"
```

## Endpoints

- Ninguno del api.

## Pantalla

- Ninguna.

## Notas técnicas

- **Migración:** no (la columna `provider` ya admite `openbao` en `crypto_keys`; si es enum de base sin ese valor, migración para agregarlo).
- **Trigger / restricciones:** `crypto_ops` append-only.
- **Funciones puras a probar:** `key_name`; mapeo de errores (403, 503 sellado, timeout).
- **Pruebas:** suite de contrato parametrizada por proveedor; integración contra OpenBao real; prueba de que el token no aparece en logs.
- **Archivos principales:** `api/src/app/core/crypto/openbao_provider.py`, `api/src/app/core/crypto/provider.py`, `api/src/app/core/config.py`, `api/tests/crypto/test_provider_contract.py`.

## Supuestos

- Ninguno.

## Dependencias

- US-133 · Servicio OpenBao con Transit.
- US-023 · KeyProvider y proveedor local (puerto y suite de contrato).

## INVEST

- **Independiente:** detrás de un puerto existente.
- **Negociable:** timeouts y forma de autenticación.
- **Valiosa:** la KEK deja de estar en el disco del api.
- **Estimable:** API de Transit conocida.
- **Pequeña:** un adaptador; tamaño 8 por la integración real.
- **Testeable:** suite de contrato común.

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Suite de contrato en verde con ambos proveedores; cobertura de 80 % o más
- [ ] Prueba de integración contra OpenBao real en CI
- [ ] Revisión de PR aprobada
