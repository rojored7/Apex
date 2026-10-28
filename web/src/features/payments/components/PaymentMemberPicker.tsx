// S3-F4 · el socio del panel "Registrar pago" (Pagos.html: "Buscar socio" arriba del panel).
// - Sin socio: el buscador común (shared/ui/MemberSearch con useMemberSearch de shared/data, 300 ms
//   de espera; Fase 4 M3). Los dados de baja no se ofrecen. S3-D99: un socio inactivo sí se puede
//   elegir (cobrar una membresía ya vendida no depende del estado del socio; el api lo registra) y su
//   resultado empieza por "Inactivo" para que se vea.
// - Con socio: su nombre y, si se eligió en el panel, "Cambiar socio".
import { useState } from "react";
import { memberFullName, memberSearchNote, UNNAMED_MEMBER, useMemberSearch, type MemberOption } from "../../../shared/data/members";
import { useSelectionFocus } from "../../../shared/hooks/useSelectionFocus";
import { Button } from "../../../shared/ui/Button";
import { MemberSearch, type MemberSearchOption } from "../../../shared/ui/MemberSearch";
import { PAYMENT_MESSAGES } from "../paymentErrors";
import styles from "./Payments.module.css";
import type { PanelMember } from "./useRegisterPaymentForm";

export { MEMBER_SEARCH_DELAY_MS as SEARCH_DELAY_MS, UNNAMED_MEMBER } from "../../../shared/data/members";

export interface PaymentMemberPickerProps {
  member: PanelMember | null;
  /** El socio se eligió en el panel: se puede cambiar. */
  canChange: boolean;
  onSelect: (member: PanelMember) => void;
  onClear: () => void;
}

const EMPTY_TEXT = "No encontramos socios con ese texto. Revisa la búsqueda.";

/** S3-D99: el inactivo se ofrece y se marca. */
function toOption(option: MemberOption): MemberSearchOption {
  const note = memberSearchNote(option);
  return { id: option.id, name: memberFullName(option), note: option.status === "active" ? note : `Inactivo · ${note}` };
}

export function PaymentMemberPicker({ member, canChange, onSelect, onClear }: PaymentMemberPickerProps) {
  const [text, setText] = useState("");
  const search = useMemberSearch(text);
  const { selectedRef, searchRef, focusChangeNext, focusSearchNext } = useSelectionFocus(member);

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
              focusSearchNext();
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
      <MemberSearch
        name="payment-member-search"
        value={text}
        onChange={setText}
        inputRef={searchRef}
        status={search.status}
        options={search.options.map(toOption)}
        emptyText={EMPTY_TEXT}
        failedText={PAYMENT_MESSAGES.searchFailed}
        onSelect={(picked) => {
          focusChangeNext();
          onSelect({ id: picked.id, name: picked.name });
        }}
      />
    </div>
  );
}
