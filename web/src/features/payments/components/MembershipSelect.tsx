// S3-F4 · la membresía del panel "Registrar pago" (Pagos.html: "Membresía *" con "Mensual 25 sep–24
// oct · saldo $60.000"). Las membresías abiertas del socio con su saldo; debajo, el saldo de la
// elegida. Carga, error con Reintentar y vacío con un enlace a vender (el "Nueva venta…" del diseño).
import type { UseQueryResult } from "@tanstack/react-query";
import type { UseFormReturn } from "react-hook-form";
import { Link } from "react-router";
import { formatCop } from "../../../core/i18n/format";
import type { MembershipRowView } from "../../../shared/data/memberships";
import { Button } from "../../../shared/ui/Button";
import { Field } from "../../../shared/ui/Field";
import { membershipOptionText } from "../lib/balance";
import { PAYMENT_MESSAGES } from "../paymentErrors";
import type { RegisterPaymentFormValues } from "../schemas";
import styles from "./Payments.module.css";

export interface MembershipSelectProps {
  form: UseFormReturn<RegisterPaymentFormValues>;
  memberId: string;
  memberships: UseQueryResult<MembershipRowView[]>;
  options: MembershipRowView[];
  balance: number | null;
}

function SellLink({ memberId }: { memberId: string }) {
  return (
    <Link className={styles.link} to={`/membresias/vender?socio=${encodeURIComponent(memberId)}`}>
      Vender una membresía
    </Link>
  );
}

export function MembershipSelect({ form, memberId, memberships, options, balance }: MembershipSelectProps) {
  const error = form.formState.errors.membershipId?.message;
  if (options.length === 0) {
    if (memberships.isError) {
      return (
        <div className={styles.section}>
          <p className={styles.fieldError}>{PAYMENT_MESSAGES.membershipsFailed}</p>
          <Button
            variant="secondary"
            loading={memberships.isFetching}
            onClick={() => {
              void memberships.refetch();
            }}
          >
            Reintentar
          </Button>
        </div>
      );
    }
    if (memberships.isPending) return <p className={styles.note}>Cargando las membresías del socio…</p>;
    return (
      <div className={styles.section}>
        <p className={styles.note}>{PAYMENT_MESSAGES.noOpenMemberships}</p>
        <SellLink memberId={memberId} />
      </div>
    );
  }
  return (
    <div className={styles.section}>
      <Field label="Membresía" name="membershipId" required error={error}>
        {(control) => (
          <select {...control} {...form.register("membershipId")}>
            <option value="">Elige la membresía</option>
            {options.map((membership) => (
              <option key={membership.id} value={membership.id}>
                {membershipOptionText(membership)}
              </option>
            ))}
          </select>
        )}
      </Field>
      {balance !== null ? <p className={styles.balance}>Saldo pendiente: {formatCop(balance)}</p> : null}
    </div>
  );
}
