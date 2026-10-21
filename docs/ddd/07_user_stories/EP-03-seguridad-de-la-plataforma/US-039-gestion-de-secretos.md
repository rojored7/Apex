# US-039 · Como equipo quiero que ningún secreto viva en el código ni en las imágenes y que su presencia se valide al arrancar para que copiar el repositorio o una imagen no entregue las llaves del gimnasio

- **Épica:** EP-03 · Seguridad de la plataforma
- **Bounded context:** `core/config`, infraestructura
- **Versión:** v0.1
- **Actor:** equipo
- **Tamaño:** 2
- **Prioridad:** P1 necesaria para la versión
- **Refinamiento:** Lista para sprint
- **Pantalla:** Ninguna (historia sin front)

## Historia

Como equipo
quiero que la KEK, la llave JWT y las credenciales entren solo por volumen o `.env`, que el arranque valide que existen y que CI escanee repo e imágenes en busca de secretos
para que un descuido no publique una llave y que un despliegue incompleto falle de inmediato

## Contexto de dominio

- **Aggregate / entidades:** ninguno.
- **Reglas que aplica:** `CLAUDE.md` Seguridad (nada de secretos en código ni imágenes; `.env.example` versionado); `04_architecture_decision.md` sección 6; reglas globales de seguridad del usuario.
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** `config.missing_secrets(settings) -> list[str]`

## Alcance

- **Backend:** `Settings` marca como `SecretStr` las variables sensibles; el arranque verifica que existan los archivos de `JWT_PRIVATE_KEY_PATH` y `CRYPTO_LOCAL_KEK_PATH`. `.dockerignore` excluye `.env`, `*.pem`, `*.key`, la carpeta de llaves. CI agrega un escaneo de secretos con una herramienta de licencia permitida sobre el repo y sobre el sistema de archivos de la imagen del api.
- **Front:** No aplica

## Criterios de aceptación

1. Arrancar sin `JWT_PRIVATE_KEY_PATH` válido falla con la lista de secretos faltantes (nombres de variable, nunca valores).
2. `repr(settings)` y los logs muestran `**********` para cualquier `SecretStr`.
3. La imagen construida del api no contiene `.env`, archivos `.pem`, `.key` ni la KEK (prueba que lista el sistema de archivos de la imagen).
4. Un commit de control con una llave privada PEM falla el escaneo de secretos en CI.
5. `.env.example` contiene todas las variables con valores de ejemplo no utilizables y la prueba de configuración verifica que cada campo de `Settings` aparece en `.env.example`.

## Escenarios BDD

```gherkin
# language: es
Característica: Gestión de secretos

  Escenario: Despliegue completo
    Dado un .env con todas las variables y las llaves montadas por volumen
    Cuando arranca el API
    Entonces el arranque termina y los logs no muestran valores secretos

  Escenario: Falta la llave JWT
    Dado que el archivo de JWT_PRIVATE_KEY_PATH no existe
    Cuando arranca el API
    Entonces el arranque falla indicando "JWT_PRIVATE_KEY_PATH"

  Escenario: Llave privada en un commit
    Dado un PR que agrega un archivo con una llave privada PEM
    Cuando corre CI
    Entonces el escaneo de secretos falla
```

## Endpoints

- Ninguno.

## Pantalla

- Ninguna.

## Notas técnicas

- **Migración:** no.
- **Funciones puras a probar:** `missing_secrets`.
- **Pruebas:** unitarias de configuración, inspección de imagen en CI, escaneo de secretos.
- **Archivos principales:** `api/src/app/core/config.py`, `api/.dockerignore`, `.env.example`, `.github/workflows/ci.yml`.

## Supuestos

- Supuesto: la herramienta de escaneo de secretos se elige con licencia permitida (MIT o Apache 2.0) y se verifica en el chequeo de licencias (US-004); no está nombrada en los documentos.

## Dependencias

- US-011 · Configuración desde .env
- US-005 · Dockerfile del api y Compose

## INVEST

- **Independiente:** configuración e imagen.
- **Negociable:** herramienta de escaneo.
- **Valiosa:** evita la fuga de llaves.
- **Estimable:** acotada.
- **Pequeña:** un día.
- **Testeable:** commit de control falla.

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
