# EP-06 · Layout y componentes compartidos del front

- **Versión del plan:** v0.1 (supuestos S1, S2 y S4; sección 5 de `05_service_design.md`; sección "Front: diseño aprobado" de `CLAUDE.md`).
- **Bounded context:** ninguno de negocio; es la capa de presentación compartida de `web/` (`core/`, `shared/ui/`, `layouts/`).
- **Estimación relativa:** L.

## Objetivo de negocio

Que todas las pantallas del sistema se vean y se comporten igual, con el diseño aprobado, sin que cada pantalla invente sus propios botones, tablas o colores. Así recepción aprende el sistema una vez, funciona en el computador, la tablet, el celular y la TV, y cada pantalla nueva sale más rápido y más barata.

## Actores

- Administrador y coach (panel), socio (portal), tablet del piso (check-in y resultados), TV (pantalla sin interacción).
- Equipo de desarrollo del front, consumidor del kit.

## Capacidades incluidas

- Kit completo en `web/src/shared/ui/` con los nombres de `DESIGN.md` (además de `Button`, `Field` y `StatusTag` de EP-00): `TopBar`, `SideNav`, `PageHeader`, `FilterBar`, `DataTable`, `Pagination`, `Chips`, `Tabs`, `KpiCard`, `SidePanel`, `ConfirmModal`, `MaskedValue`, `HistoryAside`.
- `Pagination` traduce página a `offset = (página - 1) * limit`, con tamaños de página 25, 50 y 100 (supuesto S2, `BRECHAS.md` D2).
- Layouts: `PanelLayout` (TopBar + SideNav), `PortalLayout` (una columna y menú inferior), `GymLayout` (tema oscuro, tablet, controles de 56 px) y `TvLayout` (1920 × 1080, sin interacción).
- Tema claro y oscuro definidos con los tokens de `tokens.css`, sin colores literales.
- `core/api/client.ts`: base `/api/v1`, envelope de error y punto de enganche para el refresh automático (lo conecta EP-04); `core/api/types.ts` generado desde `docs/openapi.json` con `openapi-typescript`.
- `core/i18n/format.ts`: dinero como `$ 120.000` (RN-01, entero en COP), fechas como `20 oct 2026`, hora de Bogotá en pantalla con UTC en el dato.
- `routes.tsx` con el mapa de `ROUTES.md`; cada ruta se habilita cuando su épica de negocio existe (supuesto S4).
- Convenciones por feature: `api.ts` (TanStack Query), `schemas.ts` (Zod), `pages/`, `components/`; formularios con React Hook Form + Zod; marcador `// DESIGN-GAP:` cuando falte algo del diseño.
- Accesibilidad: controles de 44 px (56 px en tablet), foco visible, contraste 4,5:1, el color nunca es el único portador de significado (`StatusTag` siempre lleva texto).
- Estados de carga, vacío y error en `DataTable` y `KpiCard` (las tarjetas de Inicio llegan vacías con `null` hasta su versión).
- Pruebas: Vitest y Testing Library por componente; capturas en 320, 768, 1024 y 1440 en claro y oscuro.

## Fuera de alcance

- Cualquier pantalla de negocio; cada una la construye su épica.
- Sesión, guardas por rol y refresh automático (EP-04).
- PWA del portal (opcional, no comprometida para v1.0).

## Criterios de éxito medibles

- Los 16 componentes del kit existen con prueba de componente y cobertura de 80 % o más en `shared/ui/`.
- Cero colores o fuentes literales fuera de `tokens.css` (chequeo automático en CI).
- Las capturas de los cuatro layouts en los cuatro anchos y los dos temas pasan la revisión visual sin desbordes horizontales.
- Chequeo automático de accesibilidad sin violaciones de contraste ni de foco en los componentes del kit.
- `types.ts` se regenera desde `openapi.json` y el build falla si el front usa un campo que el contrato no tiene.

## Dependencias

- EP-00 Cimientos (esqueleto de `web/`, tokens, fuentes, primeros componentes).
- EP-01 Núcleo compartido (contrato de listas, envelope de error y `openapi.json`).

## Riesgos

- Que se repliquen los HTML de referencia con sus colores hex literales; son wireframes, no código (`BRECHAS.md` sección 8).
- Sobrediseñar el kit antes de tener pantallas reales; se acota a los 16 componentes nombrados por `DESIGN.md`.
- Que el supuesto S1 no se apruebe en el gate; en ese caso esta épica sale del repositorio.

## Pantallas del diseño que habilita

- Base visual de todas las pantallas. Los patrones `P_Lista`, `P_Ficha`, `P_Formulario` y `Socios_Movil` son la referencia directa del kit; `Mapa`, `P_Lista`, `P_Ficha` y `P_Formulario` no se implementan como pantallas.
