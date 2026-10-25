// S3-F3 · paso "1 · Socio" de Membresia_Vender.html.
// - Sin socio: buscador (useMembersSearch de shared/data, 300 ms de espera). El texto vive solo en
//   memoria (S2-D41): puede ser un documento o un teléfono y nunca llega a la URL. Cada resultado
//   dice su plan y su estado; un socio inactivo aparece pero no se puede elegir (el api respondería
//   422 `member_inactive`). Los dados de baja no se ofrecen.
// - Con socio: tarjeta con el nombre y "Cambiar socio" (un botón, o un enlace a la venta sin socio
//   cuando el socio vino fijo en la URL).
// DESIGN-GAP: el diseño muestra bajo el socio "Mensual vigente hasta 28 oct 2026 · la nueva empieza
// el 29 oct"; la búsqueda no trae la fecha de fin (llega con B9, S3-F2): se muestra plan y estado.
import { Check } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router";
import { useDebouncedValue } from "../../../shared/hooks/useDebouncedValue";
import { memberFullName, useMembersSearch, type MemberOption } from "../../../shared/data/members";
import { Button } from "../../../shared/ui/Button";
import { Field } from "../../../shared/ui/Field";
import { cx } from "../../../shared/ui/cx";
import { STATUS_LABELS, type MembershipStatusView } from "../../../shared/ui/statusLabel";
import { SELL_MESSAGES } from "../membershipErrors";
import { NEW_MEMBER_PATH, SELL_PATH } from "../membershipLinks";
import styles from "./Sell.module.css";

export const SEARCH_DELAY_MS = 300;

export interface SelectedMember {
  id: string;
  /** null: vino fijo en la URL sin nombre (renovar desde un enlace directo). */
  name: string | null;
}

export interface MemberStepProps {
  member: SelectedMember | null;
  /** El socio vino fijo en la URL: "Cambiar socio" lleva a la venta sin socio. */
  fixed: boolean;
  error?: string | undefined;
  onSelect: (member: SelectedMember) => void;
  onClear: () => void;
}

/** "Socio elegido" cuando el nombre no se conoce (sin GET /members/{id} hasta B9). */
export const UNNAMED_MEMBER = "Socio elegido";

function isStatusView(value: string): value is MembershipStatusView {
  return Object.hasOwn(STATUS_LABELS, value);
}

/** "Mensual · Al día", "Por vencer", "Sin membresía". */
function membershipNote(option: MemberOption): string {
  const status = option.membership_status && isStatusView(option.membership_status) ? STATUS_LABELS[option.membership_status] : null;
  const parts = [option.plan_name, status].filter((part): part is string => Boolean(part));
  return parts.length > 0 ? parts.join(" · ") : "Sin membresía";
}

/** "1 socio encontrado", "3 socios encontrados". */
function foundText(count: number): string {
  return count === 1 ? "1 socio encontrado" : `${String(count)} socios encontrados`;
}

/**
 * Resultados de la búsqueda. Revisión S3-F3 (MEDIUM 5): el estado (buscando, sin resultados, error,
 * cuántos) se anuncia en una región `status` que siempre está montada.
 */
function SearchResults({ query, onSelect }: { query: string; onSelect: (member: SelectedMember) => void }) {
  const search = useMembersSearch(query);
  const active = query.trim() !== "";
  const options = active && search.isSuccess ? search.data.items.filter((option) => option.deleted_at === null) : [];
  let status: { text: string; visible: boolean } | null = null;
  if (!active) status = null;
  else if (search.isError) status = { text: SELL_MESSAGES.searchFailed, visible: true };
  else if (search.isPending) status = { text: "Buscando…", visible: true };
  else if (options.length === 0) status = { text: "No encontramos socios con ese texto. Revisa la búsqueda o crea el socio.", visible: true };
  else status = { text: foundText(options.length), visible: false };
  return (
    <>
      <div role="status" aria-label="Resultado de la búsqueda">
        {status ? <p className={cx(status.visible ? (search.isError ? styles.fieldError : styles.note) : styles.srOnly)}>{status.text}</p> : null}
      </div>
      {options.length > 0 ? (
        <ul className={styles.results} aria-label="Socios encontrados">
          {options.map((option) => {
            const inactive = option.status !== "active";
            const name = memberFullName(option);
            return (
              <li key={option.id}>
                <button
                  type="button"
                  className={styles.option}
                  disabled={inactive}
                  onClick={() => {
                    onSelect({ id: option.id, name });
                  }}
                >
                  <span className={styles.optionText}>
                    <span className={styles.optionName}>{name}</span>
                    <span className={styles.note}>{inactive ? "Inactivo: reactívalo antes de venderle" : membershipNote(option)}</span>
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      ) : null}
    </>
  );
}

export function MemberStep({ member, fixed, error, onSelect, onClear }: MemberStepProps) {
  const [text, setText] = useState("");
  const query = useDebouncedValue(text, SEARCH_DELAY_MS);
  // Revisión S3-F3 (MEDIUM 3): al elegir, el foco va a "Cambiar socio"; al cambiar, al buscador
  // (el control que tenía el foco desaparece en los dos casos).
  const selectedRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const focusNext = useRef<"change" | "search" | null>(null);
  useEffect(() => {
    if (focusNext.current === "change") selectedRef.current?.querySelector<HTMLButtonElement>("button")?.focus();
    if (focusNext.current === "search") searchRef.current?.focus();
    focusNext.current = null;
  }, [member]);

  return (
    <section className={styles.box} aria-labelledby="sell-member-title">
      <h2 id="sell-member-title" className={styles.h2}>
        1 · Socio
      </h2>
      {member ? (
        <div ref={selectedRef} className={styles.selected}>
          <span className={styles.check} aria-hidden="true">
            <Check size={18} />
          </span>
          <span className={styles.selectedText}>
            <strong>{member.name ?? UNNAMED_MEMBER}</strong>
          </span>
          {fixed ? (
            <Link className={styles.link} to={SELL_PATH}>
              Cambiar socio
            </Link>
          ) : (
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
          )}
        </div>
      ) : (
        <>
          <Field
            ref={searchRef}
            label="Buscar socio"
            name="member-search"
            type="search"
            autoComplete="off"
            placeholder="Buscar por nombre, documento o teléfono"
            value={text}
            error={error}
            onChange={(event) => {
              setText(event.target.value);
            }}
            onKeyDown={(event) => {
              // Revisión S3-F3 (MEDIUM 4): Enter en el buscador no envía la venta.
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
          <Link className={styles.link} to={NEW_MEMBER_PATH}>
            ¿No está? Crear socio nuevo
          </Link>
        </>
      )}
    </section>
  );
}
