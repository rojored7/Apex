# US-032 · Como equipo quiero hashear y verificar contraseñas con argon2id para que una base filtrada no revele las contraseñas del equipo ni de los socios

- **Épica:** EP-03 · Seguridad de la plataforma
- **Bounded context:** `core/security`
- **Versión:** v0.1
- **Actor:** equipo
- **Tamaño:** 2
- **Prioridad:** P0 ruta crítica
- **Refinamiento:** Lista para sprint
- **Pantalla:** Ninguna (historia sin front)

## Historia

Como equipo
quiero `hash_password`, `verify_password` y `needs_rehash` con argon2id en `core/security.py`
para que Auth guarde solo hashes resistentes a fuerza bruta y pueda subir los parámetros sin forzar un cambio de contraseña

## Contexto de dominio

- **Aggregate / entidades:** `User.password_hash` (consumido por US-041).
- **Reglas que aplica:** `CLAUDE.md` Seguridad (argon2id); bus punto 8 (`argon2` solo en `core/security`).
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** `security.hash_password(plain) -> str`, `security.verify_password(hash, plain) -> bool`, `security.needs_rehash(hash) -> bool`

## Alcance

- **Backend:** wrapper sobre `argon2-cffi` (`PasswordHasher` con tipo `ID`), parámetros desde configuración con valores por defecto de la librería. Política mínima de contraseña: 12 caracteres o más.
- **Front:** No aplica

## Criterios de aceptación

1. `hash_password("Secreta-1234")` devuelve una cadena que empieza por `$argon2id$`.
2. Dos hashes de la misma contraseña son distintos (sal aleatoria).
3. `verify_password(h, "Secreta-1234")` es `True` y `verify_password(h, "secreta-1234")` es `False`; un hash malformado devuelve `False` sin lanzar excepción.
4. `needs_rehash` es `True` para un hash creado con parámetros más bajos que los configurados.
5. `hash_password` con menos de 12 caracteres lanza `WeakPasswordError` (lo traduce a 422 quien lo use).
6. Ni la contraseña ni el hash aparecen en logs (prueba de captura de log).

## Escenarios BDD

```gherkin
# language: es
Característica: Hash de contraseñas

  Escenario: Hashear y verificar
    Cuando se hashea "Secreta-1234"
    Entonces el hash empieza por "$argon2id$"
    Y verificar "Secreta-1234" contra el hash es verdadero

  Escenario: Contraseña incorrecta
    Dado el hash de "Secreta-1234"
    Cuando se verifica "secreta-1234"
    Entonces el resultado es falso

  Escenario: Contraseña demasiado corta
    Cuando se intenta hashear "corta"
    Entonces se lanza WeakPasswordError

  Escenario: Parámetros actualizados
    Dado un hash creado con memoria menor a la configurada
    Cuando se consulta si necesita rehash
    Entonces la respuesta es verdadera
```

## Endpoints

- Ninguno.

## Pantalla

- Ninguna.

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** no aplica.
- **Funciones puras a probar:** las tres, con parámetros bajos en tests para velocidad.
- **Pruebas:** unitarias.
- **Archivos principales:** `api/src/app/core/security.py`, `api/tests/core/test_passwords.py`.

## Supuestos

- Supuesto: longitud mínima de 12 caracteres (misma que US-041, US-045 y US-048); los documentos no definen política de contraseña.

## Dependencias

- US-002 · Proyecto api con uv, ruff, mypy y pytest

## INVEST

- **Independiente:** solo la librería.
- **Negociable:** política mínima y parámetros.
- **Valiosa:** protege credenciales.
- **Estimable:** tres funciones.
- **Pequeña:** medio día.
- **Testeable:** resultados booleanos.

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
