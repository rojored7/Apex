# US-007 · Como equipo quiero un `.env.example` completo y un README de arranque en 5 minutos para que cualquiera levante el proyecto sin preguntar qué variables faltan

- **Épica:** EP-00 · Cimientos del repositorio
- **Bounded context:** ninguno de negocio (raíz del repositorio)
- **Versión:** v0.1
- **Actor:** equipo
- **Tamaño:** 1
- **Prioridad:** P1 necesaria para la versión
- **Refinamiento:** Lista para sprint
- **Pantalla:** Ninguna (historia sin front)

## Historia

Como equipo
quiero `.env.example` con todas las variables de la Tarea 0 documentadas y un `README.md` con los pasos para levantar el sistema
para que un clon limpio llegue a `/health` en verde en 5 minutos sin conocimiento previo

## Contexto de dominio

- **Aggregate / entidades:** ninguno.
- **Reglas que aplica:** "Seguridad" de `CLAUDE.md` (todo por `.env`, se versiona `.env.example`, nada de secretos en el código); EP-00 sección "Configuración".
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** ninguna

## Alcance

- **Backend:** `.env.example` con `DATABASE_URL`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `JWT_PRIVATE_KEY_PATH`, `JWT_PUBLIC_KEY_PATH`, `CRYPTO_PROVIDER=local`, `CRYPTO_LOCAL_KEK_PATH`, `TZ_DISPLAY=America/Bogota`, `UPLOADS_DIR=/data/uploads`, `CORS_ORIGINS`, `SEED_ADMIN_EMAIL`, `SEED_ADMIN_PASSWORD` (un solo uso, US-041), `LOG_LEVEL`; cada variable con comentario de una línea y valores de ejemplo no reales (`cambiar-esto`).
- **Front:** No aplica.
- **Documentación:** `README.md` con requisitos (Docker, uv, Node), los comandos de la sección "Comandos" de `CLAUDE.md`, cómo crear llaves (`cli init-keys`, US-023) y la advertencia de respaldar la KEK.

## Criterios de aceptación

1. Toda variable que lee `core/config.py` (US-011) aparece en `.env.example`; una prueba compara los nombres de los campos de `Settings` con las claves del archivo y falla si falta alguna.
2. Ningún valor de `.env.example` es un secreto real (contraseñas y rutas son marcadores evidentes).
3. Siguiendo solo el README desde un clon limpio, una persona del equipo llega a `/health` en verde en 5 minutos o menos (medido una vez y anotado en el PR).
4. El README advierte en negrita que perder la KEK equivale a perder los datos cifrados.

## Escenarios BDD

```gherkin
# language: es
Característica: Arranque guiado

  Escenario: Clon limpio hasta health
    Dado un clon limpio y el README
    Cuando copio ".env.example" a ".env" y sigo los pasos del README
    Entonces "/health" responde 200 en menos de 5 minutos

  Escenario: Variable nueva sin documentar
    Dado que agrego un campo obligatorio a Settings
    Y no lo agrego a ".env.example"
    Cuando corre la prueba de consistencia
    Entonces la prueba falla nombrando la variable

  Escenario: Ejemplo sin secretos reales
    Dado el archivo ".env.example"
    Cuando reviso los valores de contraseñas y llaves
    Entonces todos son marcadores del tipo "cambiar-esto"
```

## Endpoints

- Ninguno.

## Pantalla

- Ninguna.

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** ninguno.
- **Funciones puras a probar:** ninguna.
- **Pruebas:** `tests/core/test_env_example.py` (lee `.env.example` y compara con `Settings.model_fields`), activa cuando exista US-011.
- **Archivos principales:** `.env.example`, `README.md`.

## Supuestos

- Ninguno.

## Dependencias

- US-005 · Dockerfile del api y Compose (los comandos que documenta el README).

## INVEST

- **Independiente:** solo documenta lo que ya existe.
- **Negociable:** nivel de detalle del README.
- **Valiosa:** reduce el tiempo de entrada de cualquier persona nueva.
- **Estimable:** trivial.
- **Pequeña:** medio día.
- **Testeable:** prueba de consistencia y arranque medido.

## Definición de listo

- [x] Criterios de aceptación verificables
- [x] Escenarios BDD con camino feliz, error y regla
- [x] Endpoints y roles definidos (no aplica)
- [x] Dependencias identificadas
- [x] Sin preguntas abiertas que bloqueen

## Definición de terminado

- [ ] Prueba de consistencia en verde
- [ ] Arranque medido en el PR
- [ ] Revisión de PR aprobada
