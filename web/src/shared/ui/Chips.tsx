// US-063 T7: chips de filtro rápido por estado con conteo ("Al día 210"). El estado activo
// se comunica con aria-pressed, fondo negro e icono de verificación, no solo con color.
// DESIGN-GAP: "Pendiente de pago" (pending_payment, Q3) no está dibujado en las pantallas
// HTML; se usa el tono de "Por vencer" (borde y texto --warning), como indica DESIGN.md.
import { Check } from "lucide-react";
import { formatCount } from "../../core/i18n/format";
import { cx } from "./cx";
import styles from "./Chips.module.css";

export interface ChipOption {
  value: string;
  label: string;
  count?: number;
  tone?: "warning" | "danger";
}

export interface ChipsProps {
  /** Nombre accesible del grupo ("Estado"). */
  label: string;
  mode: "single" | "multiple";
  options: ChipOption[];
  value: readonly string[];
  onChange: (value: string[]) => void;
}

function nextValue(mode: ChipsProps["mode"], current: readonly string[], clicked: string): string[] {
  const isOn = current.includes(clicked);
  if (mode === "single") return isOn ? [] : [clicked];
  return isOn ? current.filter((v) => v !== clicked) : [...current, clicked];
}

export function Chips({ label, mode, options, value, onChange }: ChipsProps) {
  return (
    <div role="group" aria-label={label} className={styles.chips}>
      {options.map((option) => {
        const isOn = value.includes(option.value);
        return (
          <button
            key={option.value}
            type="button"
            aria-pressed={isOn}
            className={cx(styles.chip, option.tone && styles[option.tone], isOn && styles.active)}
            onClick={() => {
              onChange(nextValue(mode, value, option.value));
            }}
          >
            {isOn ? <Check size={16} aria-hidden="true" data-testid="chip-check" /> : null}
            <span>{option.label}</span>
            {option.count !== undefined ? <span className={styles.count}>{formatCount(option.count)}</span> : null}
          </button>
        );
      })}
    </div>
  );
}
