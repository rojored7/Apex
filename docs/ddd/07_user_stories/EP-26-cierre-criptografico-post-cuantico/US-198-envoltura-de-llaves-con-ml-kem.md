# US-198 · Como administrador quiero que las DEK se envuelvan con ML-KEM detrás del mismo KeyProvider para que la protección de las llaves resista computación cuántica

- **Épica:** EP-26 · Cierre criptográfico post-cuántico
- **Bounded context:** Crypto (`core/crypto`, `KeyProvider`)
- **Versión:** v1.0
- **Actor:** administrador
- **Tamaño:** 8
- **Prioridad:** P1 necesaria para la versión
- **Refinamiento:** Criterios completos; BDD solo de flujo principal
- **Pantalla:** Ninguna (historia sin front; el algoritmo de envoltura se ve en `Llaves`)

## Historia

Como administrador
quiero que las llaves de datos nuevas se envuelvan con ML-KEM sin cambiar ningún módulo de negocio
para que un atacante que guarde hoy las llaves envueltas no pueda abrirlas mañana con un computador cuántico

## Contexto de dominio

- **Aggregate / entidades:** `CryptoKey` (nuevo atributo de algoritmo de envoltura), `CryptoOp`.
- **Reglas que aplica:** el algoritmo va en el dato, no en el código; el que llama nunca elige llave ni algoritmo; material en claro nunca persistido; licencias (liboqs-python solo en esta versión y debe pasar el chequeo; riesgo 5 de `00b_impact_analysis.md`).
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** ninguna nueva (el algoritmo se lee de `crypto_keys`)

## Alcance

- **Backend:** columna `wrap_algorithm` en `crypto_keys` (`aes256-gcm-kw` o el de Transit actual y `ML-KEM-768`); `OpenBaoProvider.wrap/unwrap` con ML-KEM si Transit lo implementa; si no, un adaptador híbrido detrás del mismo `KeyProvider` que usa `oqs` (liboqs-python) para encapsular una llave efímera que envuelve la DEK, con la llave privada ML-KEM protegida por Transit. Las DEK nuevas nacen envueltas con ML-KEM; las existentes se re-envuelven en US-199.
- **Front:** No aplica.

## Criterios de aceptación

1. `crypto_keys.wrap_algorithm` existe y se llena para todas las llaves (migración en tres pasos: columna nula, llenar con el algoritmo actual, obligatoria).
2. Con `CRYPTO_WRAP_ALG=ML-KEM-768`, una DEK creada por rotación queda envuelta con ML-KEM y `wrap_algorithm = ML-KEM-768`; se desenvuelve al arrancar y los datos se leen igual.
3. Una DEK envuelta con el algoritmo anterior sigue desenvolviéndose: el proveedor elige el algoritmo por `wrap_algorithm` del registro.
4. Ningún módulo fuera de `core/crypto` cambia; la prueba `test_banned_imports.py` incluye `oqs` y sigue en verde.
5. El chequeo de licencias de CI acepta liboqs-python (MIT) y la librería nativa liboqs (MIT); falla si entra otra dependencia prohibida.
6. La imagen del api con la librería nativa construye en CI y su tamaño queda documentado.
7. Cada `wrap` y `unwrap` deja fila en `crypto_ops` con `key_id` y versión; nunca material.
8. Prueba de ida y vuelta: cifrar un dato con una DEK envuelta con ML-KEM, reiniciar el proceso, descifrarlo.

## Escenarios BDD

```gherkin
# language: es
Característica: Envoltura de llaves con ML-KEM

  Escenario: Llave nueva envuelta con ML-KEM
    Dado que el sistema está configurado para envolver con ML-KEM-768
    Cuando se rota la llave de "member.document"
    Entonces la llave nueva queda registrada con envoltura ML-KEM-768
    Y después de reiniciar el API los documentos se leen correctamente

  Escenario: Llave antigua sigue funcionando
    Dado que la llave de "member.phone" está envuelta con el algoritmo anterior
    Cuando el API arranca con envoltura ML-KEM configurada
    Entonces los teléfonos se siguen leyendo sin cambios
```

## Endpoints

- Ninguno.

## Pantalla

- Ninguna propia; `Llaves` (US-143) muestra `wrap_algorithm` en el inventario.

## Notas técnicas

- **Migración:** sí; `crypto.crypto_keys.wrap_algorithm` en tres pasos.
- **Trigger / restricciones:** CHECK con los valores permitidos.
- **Funciones puras a probar:** selección de algoritmo por registro.
- **Pruebas:** ida y vuelta con OpenBao de `compose.dev.yml`; reinicio de proceso; arquitectura; licencias.
- **Archivos principales:** `api/src/app/core/crypto/openbao_provider.py`, `provider.py`, `models.py`, `api/pyproject.toml`, `api/Dockerfile`.
- **Irreversibilidad:** esta historia no re-envuelve llaves existentes, pero cambia cómo se protegen las nuevas; `CLAUDE.md` exige detenerse y preguntar antes de cualquier decisión irreversible sobre llaves. Antes de activar `ML-KEM-768` en producción: backup verificado (US-196) y aprobación explícita del dueño.

## Supuestos

- Supuesto: se usa ML-KEM-768 (nivel 3, el mismo del grupo híbrido TLS de EP-20); la épica no fija el parámetro.
- Supuesto: si OpenBao no implementa ML-KEM, la llave privada ML-KEM del adaptador se guarda envuelta por Transit (clásico) y la protección post-cuántica efectiva depende de esa decisión; requiere confirmación en el gate.

## Dependencias

- US-134 · Proveedor OpenBao

## INVEST

- **Independiente:** cambio contenido en `core/crypto`.
- **Negociable:** OpenBao nativo o adaptador con liboqs.
- **Valiosa:** cierra la preparación post-cuántica del producto.
- **Estimable:** acotada al proveedor y una columna; incertidumbre en la disponibilidad de ML-KEM en Transit.
- **Pequeña:** 8 puntos, límite del sprint; se parte si el adaptador liboqs es necesario.
- **Testeable:** ida y vuelta, reinicio, licencias.

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas de integración con OpenBao real en verde; cobertura de 80 % o más en lo tocado
- [ ] Migración aplicada con `alembic upgrade head` y reversible
- [ ] Chequeo de licencias en verde
- [ ] Revisión de seguridad del PR aprobada
