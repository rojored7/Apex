// S8-F2 (S8-D15): grupo de opciones excluyentes en una fila (nivel RX, RX+, Escalado; sexo del ranking).
// role="radiogroup": una sola opción en el orden de tabulación y flechas para moverse. Alto de 44 px (56 px en la tablet).
import { useRef, type KeyboardEvent } from "react";
import { cx } from "./cx";
import styles from "./Segmented.module.css";

export interface SegmentedOption {
  value: string;
  label: string;
}

export interface SegmentedProps {
  /** Nombre accesible del grupo. */
  label: string;
  options: readonly SegmentedOption[];
  value: string;
  onChange: (value: string) => void;
  size?: "default" | "large";
  disabled?: boolean;
}

export function Segmented({ label, options, value, onChange, size = "default", disabled = false }: SegmentedProps) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const activeIndex = Math.max(
    0,
    options.findIndex((option) => option.value === value),
  );

  const move = (event: KeyboardEvent<HTMLButtonElement>, from: number): void => {
    const step = event.key === "ArrowRight" || event.key === "ArrowDown" ? 1 : event.key === "ArrowLeft" || event.key === "ArrowUp" ? -1 : 0;
    if (step === 0) return;
    event.preventDefault();
    const next = (from + step + options.length) % options.length;
    const target = options[next];
    if (!target) return;
    onChange(target.value);
    refs.current[next]?.focus();
  };

  return (
    <div role="radiogroup" aria-label={label} className={cx(styles.group, size === "large" && styles.large)}>
      {options.map((option, index) => {
        const isOn = option.value === value;
        return (
          <button
            key={option.value}
            ref={(node) => {
              refs.current[index] = node;
            }}
            type="button"
            role="radio"
            aria-checked={isOn}
            tabIndex={index === activeIndex ? 0 : -1}
            disabled={disabled}
            className={cx(styles.option, isOn && styles.on)}
            onClick={() => {
              onChange(option.value);
            }}
            onKeyDown={(event) => {
              move(event, index);
            }}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
