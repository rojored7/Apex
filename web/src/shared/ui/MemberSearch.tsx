// Fase 4 del Sprint 3 (M3): el buscador de socio de la venta (MemberStep, Membresia_Vender.html "1 ·
// Socio") y del panel "Registrar pago" (Pagos.html "Buscar socio"). Antes cada feature tenía su copia
// y ya divergían (la venta deshabilitaba al inactivo; el panel no lo distinguía). Es presentacional: la
// feature busca (useMemberSearch de shared/data), resuelve cada opción (nombre, nota y si se puede
// elegir; S3-D99) y decide qué hacer al elegir.
// - El texto vive solo en memoria (S2-D41): puede ser un documento o un teléfono y nunca llega a la URL.
// - El estado de la búsqueda (buscando, error, sin resultados o cuántos) se anuncia en una región
//   `status` que siempre está montada (revisión S3-F3, MEDIUM 5).
// - Enter en el buscador no envía el formulario de la pantalla (revisión S3-F3, MEDIUM 4).
import type { ReactNode, Ref } from "react";
import { Field } from "./Field";
import styles from "./MemberSearch.module.css";

/** Una opción ya resuelta por la feature. */
export interface MemberSearchOption {
  id: string;
  name: string;
  /** "Mensual · Al día", "Sin membresía" o por qué no se puede elegir. */
  note: string;
  disabled?: boolean;
}

/** idle: sin texto; short (S7-F4): faltan letras para buscar; pending: buscando; error: falló; done: llegaron `options`. */
export type MemberSearchStatus = "idle" | "short" | "pending" | "error" | "done";

export interface MemberSearchProps {
  name: string;
  value: string;
  onChange: (text: string) => void;
  inputRef?: Ref<HTMLInputElement> | undefined;
  /** El error del formulario (por ejemplo "Elige el socio"). */
  error?: string | undefined;
  status: MemberSearchStatus;
  options: readonly MemberSearchOption[];
  /** Lo que se dice cuando no hay resultados. */
  emptyText: string;
  /** Lo que se dice cuando la búsqueda falló. */
  failedText: string;
  /** Se llama al tocar la fila por defecto; con `renderOption` la fila trae sus propias acciones y no hace falta. */
  onSelect?: (option: MemberSearchOption) => void;
  /** S7-F4: `gym` es la tablet del box (campo de 56 px). */
  size?: "md" | "gym";
  /** Lo que se dice en estado `short`. */
  shortText?: string | undefined;
  placeholder?: string;
  /** S7-F4: la fila completa (foto, estado y acciones propias); sustituye al botón de la fila. */
  renderOption?: (option: MemberSearchOption) => ReactNode;
}

/** "1 socio encontrado", "3 socios encontrados". */
export function foundText(count: number): string {
  return count === 1 ? "1 socio encontrado" : `${String(count)} socios encontrados`;
}

interface Announcement {
  text: string;
  tone: "note" | "error" | "hidden";
}

function announcementOf(status: MemberSearchStatus, count: number, { emptyText, failedText, shortText }: Pick<MemberSearchProps, "emptyText" | "failedText" | "shortText">): Announcement | null {
  if (status === "idle") return null;
  if (status === "short") return { text: shortText ?? "Escribe más letras para buscar.", tone: "note" };
  if (status === "error") return { text: failedText, tone: "error" };
  if (status === "pending") return { text: "Buscando…", tone: "note" };
  if (count === 0) return { text: emptyText, tone: "note" };
  return { text: foundText(count), tone: "hidden" };
}

const TONE_CLASS = { note: styles.note, error: styles.fieldError, hidden: styles.srOnly } as const;

export function MemberSearch({ name, value, onChange, inputRef, error, status, options, emptyText, failedText, onSelect, size = "md", shortText, placeholder = "Buscar por nombre, documento o teléfono", renderOption }: MemberSearchProps) {
  const shown = status === "done" ? options : [];
  const announcement = announcementOf(status, shown.length, { emptyText, failedText, shortText });
  return (
    <>
      <Field
        ref={inputRef}
        label="Buscar socio"
        name={name}
        type="search"
        size={size === "gym" ? "lg" : "md"}
        autoComplete="off"
        placeholder={placeholder}
        value={value}
        error={error}
        onChange={(event) => {
          onChange(event.target.value);
        }}
        onKeyDown={(event) => {
          if (event.key === "Enter") event.preventDefault();
        }}
      />
      <div role="status" aria-label="Resultado de la búsqueda">
        {announcement ? <p className={TONE_CLASS[announcement.tone]}>{announcement.text}</p> : null}
      </div>
      {shown.length > 0 ? (
        <ul className={styles.results} aria-label="Socios encontrados">
          {shown.map((option) => (
            <li key={option.id}>
              {renderOption ? (
                renderOption(option)
              ) : (
                <button
                  type="button"
                  className={styles.option}
                  disabled={option.disabled === true}
                  onClick={() => {
                    onSelect?.(option);
                  }}
                >
                  <span className={styles.optionText}>
                    <span className={styles.optionName}>{option.name}</span>
                    <span className={styles.note}>{option.note}</span>
                  </span>
                </button>
              )}
            </li>
          ))}
        </ul>
      ) : null}
    </>
  );
}
