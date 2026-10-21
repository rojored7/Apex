# Bloque para pegar en el CLAUDE.md del repositorio

Copia esto tal cual dentro del `CLAUDE.md` que está en la raíz del repo (si no existe, créalo con este contenido).

---

## Front: diseño aprobado

La carpeta `docs/design/` es la fuente de verdad del front. Antes de crear o modificar cualquier pantalla, componente o estilo:

1. Lee `docs/design/DESIGN.md` completo (colores, tipografía, componentes, patrones, reglas).
2. Busca la ruta que vas a construir en `docs/design/ROUTES.md`: ahí está la pantalla de referencia, el rol que la ve y los endpoints que consume.
3. Abre el HTML de esa pantalla en `docs/design/screens/<Clave>.html` y reprodúcelo en React con los mismos textos, la misma estructura, los mismos estados y las mismas acciones. Mira también `<Clave>.dark.html` para el tema oscuro.
4. Usa solo las variables de `docs/design/tokens.css` (importado en `src/core/styles/tokens.css`). Ningún color ni fuente literal en componentes.
5. Los componentes compartidos viven en `src/shared/ui/` con los nombres que da `DESIGN.md` (TopBar, SideNav, PageHeader, Button, StatusTag, FilterBar, DataTable, Pagination, Chips, Tabs, KpiCard, SidePanel, ConfirmModal, Field, MaskedValue, HistoryAside). Si uno no existe, créalo ahí antes de usarlo en una pantalla; nunca dupliques estilos por pantalla.
6. Toda lista se pagina en el servidor. Todo formulario usa React Hook Form + Zod. Todo dato del servidor pasa por TanStack Query.
7. Si algo del diseño no se puede cumplir o falta una pantalla, no inventes: deja un comentario `// DESIGN-GAP:` explicando qué falta y sigue con lo demás.

Orden de construcción del front (sigue el roadmap del plan): login y layout del panel → socios → planes → membresías y pagos → inicio → clases y check-in → movimientos, WODs y resultados → atleta → avisos → sistema → TV → portal del socio.
