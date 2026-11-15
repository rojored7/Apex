// S7-F5 · US-163 (front): el filtro «Última asistencia» de /socios (Socios_Lista.html).
// - Es un `<select>` que pinta FilterBar a partir de la descripción de `lastAttendanceFilter`, en la misma fila que la búsqueda.
// - Los valores son los del api (`last_attendance`): 7d, 14d, 30d, 60d (el socio no asistió en los últimos N días o nunca asistió)
//   y never (nunca asistió). Un valor desconocido de la URL no viaja.
// DESIGN-GAP: el diseño ofrece «Esta semana» y «Hace más de 10 días»; el api filtra por ausencia de 7, 14, 30 o 60 días.
import type { LastAttendanceFilterValue } from "../api";
import type { FilterSelect } from "../../../shared/ui/FilterBar";

export const LAST_ATTENDANCE_FILTER_NAME = "last_attendance";

const OPTIONS: readonly { value: LastAttendanceFilterValue; label: string }[] = [
  { value: "7d", label: "Hace más de 7 días" },
  { value: "14d", label: "Hace más de 14 días" },
  { value: "30d", label: "Hace más de 30 días" },
  { value: "60d", label: "Hace más de 60 días" },
  { value: "never", label: "Nunca" },
];

const isKnown = (value: string): value is LastAttendanceFilterValue => OPTIONS.some((option) => option.value === value);

/** El valor de la URL si es uno de los cinco del api, o "". */
export function readLastAttendance(values: readonly string[]): LastAttendanceFilterValue | "" {
  const raw = values[0] ?? "";
  return isKnown(raw) ? raw : "";
}

/** La descripción del select «Última asistencia» para FilterBar (`selects`). */
export function lastAttendanceFilter(value: LastAttendanceFilterValue | ""): FilterSelect {
  return { name: LAST_ATTENDANCE_FILTER_NAME, label: "Última asistencia", value, options: OPTIONS.map((option) => ({ ...option })) };
}
