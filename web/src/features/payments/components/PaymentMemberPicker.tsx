// S3-F4 · el socio del panel "Registrar pago" (Pagos.html: "Buscar socio" arriba del panel).
// - Sin socio: buscador (useMembersSearch de shared/data, 300 ms de espera). El texto vive solo en
//   memoria (S2-D41): puede ser un documento o un teléfono y nunca llega a la URL. El estado de la
//   búsqueda se anuncia en una región `status` siempre montada. Los dados de baja no se ofrecen.
// - Con socio: su nombre y, si se eligió en el panel, "Cambiar socio".
import { useEffect, useRef, useState } from "react";
import { memberFullName, useMembersSearch } from "../../../shared/data/members";
import { useDebouncedValue } from "../../../shared/hooks/useDebouncedValue";
import { Button } from "../../../shared/ui/Button";
import { Field } from "../../../shared/ui/Field";
import { cx } from "../../../shared/ui/cx";
import { PAYMENT_MESSAGES } from "../paymentErrors";
import styles from "./Payments.module.css";
import type { PanelMember } from "./useRegisterPaymentForm";

export const SEARCH_DELAY_MS = 300;

/** El nombre cuando el socio vino en la URL y todavía no se conoce. */
export const UNNAMED_MEMBER = "Socio elegido";

export interface PaymentMemberPickerProps {
  member: PanelMember | null;
  /** El socio se eligió en el panel: se puede cambiar. */
  canChange: boolean;
  onSelect: (member: PanelMember) => void;
  onClear: () => void;
}

const foundText = (count: number): string => (count === 1 ? "1 socio encontrado" : `${String(count)} socios encontrados`);

function SearchResults({ query, onSelect }: { query: string; onSelect: (member: PanelMember) => void }) {
  const search = useMembersSearch(query);
  const active = query.trim() !== "";
  const options = active && search.isSuccess ? search.data.items.filter((option) => option.deleted_at === null) : [];
  let status: { text: string; visible: boolean; error: boolean } | null = null;
  if (active && search.isError) status = { text: PAYMENT_MESSAGES.searchFailed, visible: true, error: true };
  else if (active && search.isPending) status = { text: "Buscando…", visible: true, error: false };
  else if (active && options.length === 0) status = { text: "No encontramos socios con ese texto. Revisa la búsqueda.", visible: true, error: false };
  else if (active) status = { text: foundText(options.length), visible: false, error: false };
  return (
    <>
      <div role="status" aria-label="Resultado de la búsqueda">
        {status ? <p className={cx(status.visible ? (status.error ? styles.fieldError : styles.note) : styles.srOnly)}>{status.text}</p> : null}
      </div>
      {options.length > 0 ? (
        <ul className={styles.results} aria-label="Socios encontrados">
          {options.map((option) => {
            const name = memberFullName(option);
            return (
              <li key={option.id}>
                <button
                  type="button"
                  className={styles.option}
                  onClick={() => {
                    onSelect({ id: option.id, name });
                  }}
                >
                  <span className={styles.optionName}>{name}</span>
                  {option.plan_name ? <span className={styles.note}>{option.plan_name}</span> : null}
                </button>
              </li>
            );
          })}
        </ul>
      ) : null}
    </>
  );
}

export function PaymentMemberPicker({ member, canChange, onSelect, onClear }: PaymentMemberPickerProps) {
  const [text, setText] = useState("");
  const query = useDebouncedValue(text, SEARCH_DELAY_MS);
  // Al elegir, el foco va a "Cambiar socio"; al cambiar, al buscador (el control que tenía el foco
  // desaparece en los dos casos).
  const selectedRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const focusNext = useRef<"change" | "search" | null>(null);
  useEffect(() => {
    if (focusNext.current === "change") selectedRef.current?.querySelector<HTMLButtonElement>("button")?.focus();
    if (focusNext.current === "search") searchRef.current?.focus();
    focusNext.current = null;
  }, [member]);

  if (member) {
    return (
      <div ref={selectedRef} className={styles.selected}>
        <span className={styles.selectedText}>
          <span className={styles.selectedLabel}>Socio</span>
          <strong>{member.name ?? UNNAMED_MEMBER}</strong>
        </span>
        {canChange ? (
          <Button
            variant="secondary"
            onClick={() => {
              setText("");
              focusNext.current = "search";
              onClear();
            }}
          >
            Cambiar socio
          </Button>
        ) : null}
      </div>
    );
  }
  return (
    <div className={styles.section}>
      <Field
        ref={searchRef}
        label="Buscar socio"
        name="payment-member-search"
        type="search"
        autoComplete="off"
        placeholder="Buscar por nombre, documento o teléfono"
        value={text}
        onChange={(event) => {
          setText(event.target.value);
        }}
        onKeyDown={(event) => {
          // Enter en el buscador no envía el pago.
          if (event.key === "Enter") event.preventDefault();
        }}
      />
      <SearchResults
        query={query}
        onSelect={(selected) => {
          focusNext.current = "change";
          onSelect(selected);
        }}
      />
    </div>
  );
}
