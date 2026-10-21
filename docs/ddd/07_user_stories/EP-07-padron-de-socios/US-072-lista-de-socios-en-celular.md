# US-072 · Como dueño (administrador) o coach quiero consultar la lista de socios desde el celular para buscar a alguien cuando no estoy en recepción

- **Épica:** EP-07 · Padrón de socios
- **Bounded context:** Members (esquema `members`)
- **Versión:** v0.1
- **Actor:** administrador, coach
- **Tamaño:** 2
- **Prioridad:** P2 mejora
- **Refinamiento:** Lista para sprint
- **Pantalla:** `Socios_Movil` (`/socios` en anchos menores a 768 px)

## Historia

Como administrador o coach con el celular en la mano
quiero la lista de socios en tarjetas con búsqueda y chips
para encontrar a un socio y abrir su ficha sin computador

## Contexto de dominio

- **Aggregate / entidades:** `Member` (misma lectura que US-070 y US-071).
- **Reglas que aplica:** RN-13 (datos enmascarados); paginación `limit`/`offset`; accesibilidad de 44 px.
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** ninguna

## Alcance

- **Backend:** No aplica (usa `GET /api/v1/members` de US-070 y US-071).
- **Front:** variante responsive de `MembersListPage` según `Socios_Movil`: tarjeta por socio (nombre, estado con `StatusTag`, plan), búsqueda fija arriba, chips desplazables horizontalmente dentro de su contenedor, botón "Cargar más" que incrementa `offset` en `limit`, botón flotante "Nuevo socio".

## Criterios de aceptación

1. En anchos menores a 768 px la lista se muestra como tarjetas, no como tabla, sin desplazamiento horizontal de la página en 320 y 390 px.
2. "Cargar más" pide la siguiente página con `offset = offset anterior + limit` y agrega resultados; desaparece cuando `offset + limit >= total`.
3. Cada tarjeta es un único destino enfocable de al menos 44 px de alto que abre `/socios/:id`.
4. La búsqueda y los chips se comportan igual que en escritorio (mismos parámetros en la URL).
5. Los datos sensibles no aparecen en la tarjeta (ni enmascarados): solo nombre, estado y plan.
6. El botón "Nuevo socio" solo aparece si `useCan("members.create")` es verdadero.

## Escenarios BDD

```gherkin
# language: es
Característica: Lista de socios en celular

  Antecedentes:
    Dado un usuario autenticado con rol "coach"
    Y una pantalla de 390 por 844

  Escenario: Buscar y abrir ficha
    Dado 60 socios registrados
    Cuando busca "laura"
    Y toca la tarjeta de "Laura Gómez"
    Entonces se abre la ficha de "Laura Gómez"

  Escenario: Cargar más resultados
    Dado 60 socios registrados y un tamaño de página de 25
    Cuando toca "Cargar más" dos veces
    Entonces se ven 60 tarjetas
    Y el botón "Cargar más" desaparece

  Escenario: Error al cargar la siguiente página
    Dado que el API falla al pedir la segunda página
    Cuando toca "Cargar más"
    Entonces se conservan las primeras 25 tarjetas
    Y se muestra un mensaje de error con opción de reintentar
```

## Endpoints

- `GET /api/v1/members` — rol(es): admin, coach — ver US-070.

## Pantalla

- `Socios_Movil` (390 × 844). Estados: carga, vacío, error en página siguiente.

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** no aplica.
- **Funciones puras a probar:** ninguna.
- **Pruebas:** Testing Library con `matchMedia` simulado; Playwright a 390 × 844 con captura y prueba de desborde.
- **Archivos principales:** `web/src/features/members/components/MemberCardList.tsx`.

## Supuestos

- Supuesto: en celular se usa "Cargar más" (acumulativo) en lugar de paginación numerada; `Socios_Movil` es la referencia visual y no fija el mecanismo.

## Dependencias

- US-070 · Buscar y listar socios.

## INVEST

- **Independiente:** reutiliza el API ya existente.
- **Negociable:** "Cargar más" o desplazamiento infinito.
- **Valiosa:** el dueño consulta fuera de recepción.
- **Estimable:** una variante de presentación.
- **Pequeña:** 1 a 2 días.
- **Testeable:** comportamiento por ancho verificable.

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
