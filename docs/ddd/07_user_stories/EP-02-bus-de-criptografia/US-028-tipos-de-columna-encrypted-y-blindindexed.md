# US-028 · Como equipo quiero tipos de columna Encrypted y BlindIndexed para que un modelo declare un campo cifrado en una línea y nunca lo escriba en claro por error

- **Épica:** EP-02 · Bus de criptografía y cifrado de datos personales
- **Bounded context:** Crypto (`core/crypto/types.py`)
- **Versión:** v0.1
- **Actor:** equipo
- **Tamaño:** 5
- **Prioridad:** P0 ruta crítica
- **Refinamiento:** Lista para sprint
- **Pantalla:** Ninguna (historia sin front)

## Historia

Como equipo
quiero `Encrypted(data_class)` y `BlindIndexed(data_class)` como tipos de columna de SQLAlchemy que cifran al escribir con `aad = id del registro` y calculan el índice
para que el módulo de socios (y luego atleta y adjuntos) use el bus sin repetir código ni elegir llaves

## Contexto de dominio

- **Aggregate / entidades:** value objects cifrados de `Member` (`Document`, `Phone`, `Email`, `BirthDate`, `EmergencyContact`).
- **Reglas que aplica:** RN-13; `CLAUDE.md` bus puntos 3, 5 y 9; `04_architecture_decision.md` sección 7 (tipos en `core/crypto/types.py`, AAD = id).
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** ninguna nueva

## Alcance

- **Backend:** `Encrypted(data_class)` guarda texto (el blob) y expone en Python un valor descifrado perezoso o explícito; el cifrado usa el `id` del registro como AAD, por lo que el `id` UUID se asigna en Python antes del flush. `BlindIndexed(data_class)` es una columna `<campo>_idx` (texto, indexada) que se llena a partir del valor en claro en el mismo flush. Soporta JSON para `member.emergency_contact` (serialización canónica antes de cifrar) y fecha ISO para `member.birth_date`. Modelo de prueba en tests con los cinco campos.
- **Front:** No aplica

## Criterios de aceptación

1. Un modelo con `document: Mapped[str] = mapped_column(Encrypted("member.document"))` guarda en la columna un valor que empieza por `apx1.` y nunca el texto en claro.
2. `SELECT document FROM <tabla de prueba>` no contiene el valor en claro para ninguna fila (prueba directa con SQL).
3. Leer la entidad desde la sesión devuelve el valor en claro solo cuando el código lo pide explícitamente; serializar la entidad a log o a `repr` no muestra el valor.
4. Al cambiar el valor de un campo cifrado se recifra con la llave `active` vigente y se recalcula su `_idx` en el mismo flush.
5. Asignar `None` a un campo cifrado opcional guarda `NULL` y deja `_idx` en `NULL`.
6. `member.emergency_contact` se cifra como JSON (`{"name","phone"}`) y vuelve como el mismo diccionario.
7. `member.birth_date` se cifra como fecha ISO `AAAA-MM-DD` y vuelve como `date`.
8. Cambiar el `id` de un registro con campos cifrados no está permitido (el AAD dejaría de coincidir): el tipo lanza error si detecta el cambio.
9. La auditoría (US-016) recibe el blob, no el valor en claro, en `before` y `after`.
10. Las cinco clases de dato de v0.1 están registradas y probadas con el modelo de prueba.

## Escenarios BDD

```gherkin
# language: es
Característica: Columnas cifradas declarativas

  Escenario: Guardar un documento cifrado e indexado
    Dado un registro de prueba con documento "1.020.304"
    Cuando se hace commit
    Entonces la columna document contiene un blob "apx1..."
    Y la columna document_idx contiene el índice de "1020304"
    Y ninguna columna contiene "1020304"

  Escenario: Editar un campo cifrado
    Dado un registro con teléfono "3001234567"
    Cuando se cambia el teléfono a "3109876543" y se hace commit
    Entonces el blob del teléfono cambia
    Y phone_idx coincide con el índice de "3109876543"

  Escenario: Contacto de emergencia como JSON
    Dado un contacto de emergencia {"name":"Luz","phone":"3001112233"}
    Cuando se guarda y se vuelve a leer
    Entonces se obtiene el mismo diccionario

  Escenario: Cambiar el id de un registro cifrado
    Dado un registro con campos cifrados
    Cuando el código intenta cambiar su id
    Entonces se lanza un error y no se hace commit
```

## Endpoints

- Ninguno.

## Pantalla

- Ninguna.

## Notas técnicas

- **Migración:** no (la tabla de prueba solo existe en tests con `create_all`, permitido en pruebas).
- **Trigger / restricciones:** no aplica.
- **Funciones puras a probar:** serialización canónica del JSON del contacto (llaves ordenadas).
- **Pruebas:** integración con base real; prueba SQL directa de "sin claro"; prueba de `repr`.
- **Archivos principales:** `api/src/app/core/crypto/types.py`, `api/tests/crypto/test_types.py`.
- **Riesgo:** el tipo depende de que el `id` exista antes del flush; el `CommonColumnsMixin` (US-012) debe asignar `default=uuid4` en Python, no en la base.

## Supuestos

- Supuesto: el descifrado es explícito (por ejemplo, `member.document.reveal()` o una función del service) para que una ficha abierta sin "mostrar" no descifre; el patrón exacto se decide al implementar y se documenta en ADR-002.

## Dependencias

- US-025 · Cifrado AES-GCM y formato de blob
- US-026 · Índice ciego HMAC

## INVEST

- **Independiente:** usa solo el bus.
- **Negociable:** API exacta de lectura en claro.
- **Valiosa:** hace imposible olvidar cifrar un campo.
- **Estimable:** dos tipos y sus pruebas.
- **Pequeña:** cabe en un sprint con margen.
- **Testeable:** prueba SQL directa.

## Definición de listo

- [x] Criterios de aceptación verificables
- [x] Escenarios BDD con camino feliz, error y rol
- [x] Endpoints y roles definidos
- [x] Dependencias identificadas
- [x] Sin preguntas abiertas que bloqueen (o supuesto declarado)

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas de reglas puras y de service con PostgreSQL real en verde; cobertura de 80 % o más en lo tocado
- [ ] Pruebas de router: rol, validación y envelope de error
- [ ] Front: pruebas de componente y página; sin colores literales (si aplica)
- [ ] Migración aplicada con `alembic upgrade head` y reversible (si aplica)
- [ ] `docs/openapi.json` regenerado (si cambia el contrato)
- [ ] Auditoría verificada para las tablas tocadas (si aplica)
- [ ] Revisión de PR aprobada
