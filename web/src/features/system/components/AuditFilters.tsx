// S4A-F1 · US-102: la barra de filtros de /sistema/auditoria (Auditoria.html): Registro (búsqueda en
// memoria), rango de fechas, Usuario, Entidad y Acción, sobre el FilterBar del kit.
// - Usuario: las cuentas de GET /users?limit=200 por correo y "Sistema (worker)" (el usuario técnico).
// DESIGN-GAP: sin búsqueda por nombre del socio (el diseño dice "Nombre del socio o id del registro");
// el api busca por correo del usuario o por id del registro (con la entidad elegida). Los datos del
// socio no se buscan en la auditoría (RN-13); la ficha del socio enlaza su historial.
// DESIGN-GAP: el selector de usuario lista hasta 200 cuentas (GET /users no pagina más en un select).
import type { DateRange, FilterOption } from "../../../shared/ui/FilterBar";
import { FilterBar } from "../../../shared/ui/FilterBar";
import { AUDIT_ACTION_LABELS, AUDIT_TABLES, SYSTEM_USER_LABEL, type AuditFilter, type AuditUrlFilters } from "../auditFilters";
import { AUDIT_ACTIONS } from "../schemas";
import { SYSTEM_USER_ID } from "../../../shared/lib/audit-labels";

export interface AuditFiltersProps {
  filters: AuditUrlFilters;
  query: string;
  onQueryChange: (q: string) => void;
  onClear: () => void;
  onFilterChange: (name: Exclude<AuditFilter, "from" | "to">, value: string) => void;
  onRangeChange: (range: DateRange) => void;
  /** Cuentas del equipo para el selector (correo e id). */
  users: readonly { id: string; email: string }[];
}

const ACTION_OPTIONS: FilterOption[] = AUDIT_ACTIONS.map((action) => ({ value: action, label: AUDIT_ACTION_LABELS[action] }));
const TABLE_OPTIONS: FilterOption[] = AUDIT_TABLES.map((table) => ({ value: table.value, label: table.label }));
const SELECTS = ["user_id", "table", "action"] as const;

const isSelect = (name: string): name is (typeof SELECTS)[number] => (SELECTS as readonly string[]).includes(name);

export function AuditFilters({ filters, query, onQueryChange, onClear, onFilterChange, onRangeChange, users }: AuditFiltersProps) {
  const userOptions: FilterOption[] = [{ value: SYSTEM_USER_ID, label: SYSTEM_USER_LABEL }, ...users.filter((u) => u.id !== SYSTEM_USER_ID).map((u) => ({ value: u.id, label: u.email }))];
  return (
    <FilterBar
      query={query}
      onQueryChange={onQueryChange}
      onClear={onClear}
      searchLabel="Registro"
      searchPlaceholder="Correo del usuario o id del registro"
      dateRange={{ label: "Fecha", from: filters.from, to: filters.to, onChange: onRangeChange }}
      selects={[
        { name: "user_id", label: "Usuario", value: filters.user_id, options: userOptions, anyLabel: "Todos" },
        { name: "table", label: "Entidad", value: filters.table, options: TABLE_OPTIONS, anyLabel: "Todas" },
        { name: "action", label: "Acción", value: filters.action, options: ACTION_OPTIONS, anyLabel: "Todas" },
      ]}
      onSelectChange={(name, value) => {
        if (isSelect(name)) onFilterChange(name, value);
      }}
    />
  );
}
