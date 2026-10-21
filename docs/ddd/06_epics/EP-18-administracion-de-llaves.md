# EP-18 · Administración de llaves de cifrado

- **Versión del plan:** v0.3 (`03_context_map.md`, Crypto "0.3 (router admin)"; `BRECHAS.md` sección 2, "API de llaves").
- **Bounded context:** Crypto (soporte), `core/crypto/router.py` y `core/crypto/service.py`.
- **Estimación relativa:** M.

## Objetivo de negocio

Que el dueño vea, sin abrir una terminal, qué llaves protegen qué datos, cuándo se rotaron por última vez y quién las usó, y que pueda rotar una llave con un clic cuando sospeche de una filtración o cuando lo pida la política. Convierte el cifrado en algo que se puede gobernar y demostrar.

## Actores

- Administrador: único con acceso.

## Capacidades incluidas

### Backend
- Router solo admin: `GET /crypto/keys` (inventario por `data_class`, propósito, algoritmo, proveedor, versión, estado, `rotated_at`, `rotate_by`), `GET /crypto/ops` (bitácora paginada), `GET /crypto/jobs` (progreso de rotaciones y migraciones).
- `POST /crypto/keys/{id}/rotate` con `reason` y `confirm: "ROTAR"`: dispara el mismo flujo de `cli rotate-key` de EP-02 en segundo plano, con progreso en `crypto_jobs`.
- Invariantes de `CryptoKey` y `CryptoJob`: una sola llave activa por propósito y clase de dato; la anterior queda en `decrypt_only` hasta que el job termine; una sola rotación en curso por clase de dato.
- Cada rotación se audita con motivo.
- `GET /crypto/cbom` (informe de inventario criptográfico) si el gate decide adelantarlo de v1.0 a v0.3; si no, el botón queda deshabilitado hasta EP-26.

### Front
- Pantalla de llaves con inventario, bitácora, jobs con barra de progreso y modal de rotar que exige escribir "ROTAR" y un motivo.

## Fuera de alcance

- Gestión de OpenBao en sí (desellado, políticas): se hace fuera del sistema.
- Formato CycloneDX del CBOM (EP-26).

## Criterios de éxito medibles

- Rotar desde la pantalla deja la llave anterior en `decrypt_only`, muestra el progreso por lotes de 500 y al terminar la retira; los datos siguen legibles durante todo el proceso.
- Un segundo intento de rotar la misma clase de dato mientras hay un job en curso devuelve 409.
- Sin `confirm: "ROTAR"` o sin motivo, la rotación devuelve 422.
- Ningún endpoint devuelve material de llave, ni envuelto ni en claro.
- Un coach recibe 403 en todas las rutas `/crypto/*`.

## Dependencias

- EP-02 Bus de criptografía (rotación, bitácora, jobs).
- EP-15 Custodia de llaves con OpenBao (proveedor de producción).
- EP-06 Layout y componentes compartidos del front.

## Riesgos

- Una rotación lanzada por error sobre una tabla grande consume CPU en horario de atención; conviene advertir el tamaño antes de confirmar.
- Fechas de CBOM ambiguas entre v0.3 y v1.0 (ver preguntas abiertas).

## Pantallas del diseño que habilita

- `Llaves`.
