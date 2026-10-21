// US-063 T6: barra de filtros (Socios_Lista.html): buscador (flex 2) + selects (flex 1) +
// rango de fechas + ordenar + Limpiar. El buscador espera 300 ms sin teclear antes de avisar.
// En celular se apila. DESIGN-GAP: el plegado "Filtros ▾" del portal no se construye aquí;
// llega con las pantallas del portal (v1.0).
import { useEffect, useId, useRef, useState } from "react";
import { useDebouncedValue } from "../hooks/useDebouncedValue";
import { Button } from "./Button";
import { Field } from "./Field";
import styles from "./FilterBar.module.css";

export const SEARCH_DEBOUNCE_MS = 300;

export interface FilterOption {
  value: string;
  label: string;
}

export interface FilterSelect {
  name: string;
  label: string;
  value: string;
  options: FilterOption[];
  /** Texto de la opción vacía; por defecto "Cualquiera". */
  anyLabel?: string;
}

/** Fechas civiles AAAA-MM-DD (sin zona). */
export interface DateRange {
  from: string;
  to: string;
}

export interface FilterBarProps {
  query: string;
  onQueryChange: (q: string) => void;
  /** Borra búsqueda, filtros y orden (useListParams.clear también vuelve offset a 0). */
  onClear: () => void;
  searchLabel?: string;
  searchPlaceholder?: string;
  selects?: FilterSelect[];
  onSelectChange?: (name: string, value: string) => void;
  dateRange?: DateRange & { label: string; onChange: (range: DateRange) => void };
  sort?: { label?: string; value: string; options: FilterOption[]; onChange: (value: string) => void };
}

function SearchInput({
  query,
  onQueryChange,
  label,
  placeholder,
  resetToken,
}: {
  query: string;
  onQueryChange: (q: string) => void;
  label: string;
  placeholder: string | undefined;
  resetToken: number;
}) {
  const [text, setText] = useState(query);
  const [syncedQuery, setSyncedQuery] = useState(query);
  const [syncedReset, setSyncedReset] = useState(resetToken);
  // La URL manda: si la búsqueda cambia desde fuera (Limpiar, atrás), el campo la sigue.
  if (query !== syncedQuery || resetToken !== syncedReset) {
    setSyncedQuery(query);
    setSyncedReset(resetToken);
    setText(query);
  }

  const debounced = useDebouncedValue(text, SEARCH_DEBOUNCE_MS);
  const latest = useRef({ query, onQueryChange });
  useEffect(() => {
    latest.current = { query, onQueryChange };
  });
  useEffect(() => {
    if (debounced !== latest.current.query) latest.current.onQueryChange(debounced);
  }, [debounced]);

  return (
    <div className={styles.search}>
      <Field
        label={label}
        name="q"
        type="search"
        autoComplete="off"
        {...(placeholder ? { placeholder } : {})}
        value={text}
        onChange={(event) => {
          setText(event.target.value);
        }}
      />
    </div>
  );
}

export function FilterBar({
  query,
  onQueryChange,
  onClear,
  searchLabel = "Buscar",
  searchPlaceholder,
  selects = [],
  onSelectChange,
  dateRange,
  sort,
}: FilterBarProps) {
  const rangeId = useId();
  const [resetToken, setResetToken] = useState(0);

  return (
    <form
      role="search"
      className={styles.bar}
      onSubmit={(event) => {
        event.preventDefault();
      }}
    >
      <SearchInput query={query} onQueryChange={onQueryChange} label={searchLabel} placeholder={searchPlaceholder} resetToken={resetToken} />
      {selects.map((select) => (
        <div key={select.name} className={styles.select}>
          <Field label={select.label} name={select.name}>
            {(control) => (
              <select
                {...control}
                value={select.value}
                onChange={(event) => {
                  onSelectChange?.(select.name, event.target.value);
                }}
              >
                <option value="">{select.anyLabel ?? "Cualquiera"}</option>
                {select.options.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            )}
          </Field>
        </div>
      ))}
      {dateRange ? (
        <fieldset className={styles.range} aria-labelledby={rangeId}>
          <legend id={rangeId} className={styles.legend}>
            {dateRange.label}
          </legend>
          <Field
            label="Desde"
            name="from"
            type="date"
            value={dateRange.from}
            {...(dateRange.to ? { max: dateRange.to } : {})}
            onChange={(event) => {
              dateRange.onChange({ from: event.target.value, to: dateRange.to });
            }}
          />
          <Field
            label="Hasta"
            name="to"
            type="date"
            value={dateRange.to}
            {...(dateRange.from ? { min: dateRange.from } : {})}
            onChange={(event) => {
              dateRange.onChange({ from: dateRange.from, to: event.target.value });
            }}
          />
        </fieldset>
      ) : null}
      {sort ? (
        <div className={styles.select}>
          <Field label={sort.label ?? "Ordenar por"} name="sort">
            {(control) => (
              <select
                {...control}
                value={sort.value}
                onChange={(event) => {
                  sort.onChange(event.target.value);
                }}
              >
                {sort.value === "" ? <option value="">Predeterminado</option> : null}
                {sort.options.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            )}
          </Field>
        </div>
      ) : null}
      <div className={styles.clear}>
        <Button
          variant="secondary"
          onClick={() => {
            setResetToken((n) => n + 1);
            onClear();
          }}
        >
          Limpiar
        </Button>
      </div>
    </form>
  );
}
