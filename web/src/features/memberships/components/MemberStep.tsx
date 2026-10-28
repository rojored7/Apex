// S3-F3 · paso "1 · Socio" de Membresia_Vender.html.
// - Sin socio: el buscador común (shared/ui/MemberSearch con useMemberSearch de shared/data, 300 ms
//   de espera; Fase 4 M3). Cada resultado dice su plan, su estado y hasta cuándo va su membresía
//   (`membership_end_date` de S3-B9b; pendiente 2 de V1); un socio inactivo aparece pero no se puede
//   elegir (el api respondería 422 `member_inactive`). Los dados de baja no se ofrecen.
// - Con socio: tarjeta con el nombre, la nota de su membresía (si se eligió en el buscador) y
//   "Cambiar socio" (un botón, o un enlace a la venta sin socio cuando el socio vino fijo en la URL).
import { Check } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";
import { memberFullName, memberSearchNote, UNNAMED_MEMBER, useMemberSearch, type MemberOption } from "../../../shared/data/members";
import { useSelectionFocus } from "../../../shared/hooks/useSelectionFocus";
import { Button } from "../../../shared/ui/Button";
import { MemberSearch, type MemberSearchOption } from "../../../shared/ui/MemberSearch";
import { SELL_MESSAGES } from "../membershipErrors";
import { NEW_MEMBER_PATH, SELL_PATH } from "../membershipLinks";
import styles from "./Sell.module.css";

export { MEMBER_SEARCH_DELAY_MS as SEARCH_DELAY_MS, UNNAMED_MEMBER } from "../../../shared/data/members";

export interface SelectedMember {
  id: string;
  /** null: vino fijo en la URL sin nombre (renovar desde un enlace directo). */
  name: string | null;
  /** "Mensual · Al día · hasta el 28 oct 2026" si se eligió en el buscador. */
  note?: string | null;
}

export interface MemberStepProps {
  member: SelectedMember | null;
  /** El socio vino fijo en la URL: "Cambiar socio" lleva a la venta sin socio. */
  fixed: boolean;
  error?: string | undefined;
  onSelect: (member: SelectedMember) => void;
  onClear: () => void;
}

export const INACTIVE_NOTE = "Inactivo: reactívalo antes de venderle";
const EMPTY_TEXT = "No encontramos socios con ese texto. Revisa la búsqueda o crea el socio.";

/** La venta no se le hace a un socio inactivo (422 `member_inactive`): aparece deshabilitado. */
function toOption(option: MemberOption): MemberSearchOption {
  const inactive = option.status !== "active";
  return { id: option.id, name: memberFullName(option), note: inactive ? INACTIVE_NOTE : memberSearchNote(option), disabled: inactive };
}

export function MemberStep({ member, fixed, error, onSelect, onClear }: MemberStepProps) {
  const [text, setText] = useState("");
  const search = useMemberSearch(text);
  const { selectedRef, searchRef, focusChangeNext, focusSearchNext } = useSelectionFocus(member);
  const options = search.options.map(toOption);

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
            {member.note ? <span className={styles.note}>{member.note}</span> : null}
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
                focusSearchNext();
                onClear();
              }}
            >
              Cambiar socio
            </Button>
          )}
        </div>
      ) : (
        <>
          <MemberSearch
            name="member-search"
            value={text}
            onChange={setText}
            inputRef={searchRef}
            error={error}
            status={search.status}
            options={options}
            emptyText={EMPTY_TEXT}
            failedText={SELL_MESSAGES.searchFailed}
            onSelect={(picked) => {
              focusChangeNext();
              onSelect({ id: picked.id, name: picked.name, note: picked.note });
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
