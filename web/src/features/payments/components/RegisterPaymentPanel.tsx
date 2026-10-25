// S3-F4 · US-095 (front): panel "Registrar pago" de Pagos.html ("Panel · Registrar pago"), sobre la
// pantalla que lo abrió (SidePanel). Lo monta RegisterPaymentPanelHost cuando la URL lo pide.
// - Socio (buscar o fijo), membresía con su saldo ("Mensual 25 oct–24 nov · saldo $ 60.000"),
//   medio, valor, referencia (Nequi y Bre-B, con el aviso M-7) y fecha y hora del pago.
// - Confirmaciones de S3-D41 con ConfirmModal: pago mayor al saldo (Q5) y posible duplicado.
// - Tras registrar: resumen "Pago registrado" con "Registrar otro pago".
// - Cerrar (✕, Cancelar, Escape) descarta lo escrito; con cambios, SidePanel pregunta antes. Mientras
//   se envía no se cierra: un error tardío pintaría un panel ya cerrado.
// DESIGN-GAP: Pagos.html no muestra la fecha del pago; el api guarda un instante (`paid_at`), así que
// se pide fecha y hora (como en la venta, S3-F3). La referencia es opcional (el diseño la marca con *,
// el api la acepta opcional, D17). "Nueva venta…" del select es un enlace a vender cuando el socio no
// tiene membresías abiertas. El buscador de socio solo aparece cuando la URL no fija socio ni
// membresía.
import { useEffect, useId, useRef } from "react";
import { formatCop } from "../../../core/i18n/format";
import type { UseQueryResult } from "@tanstack/react-query";
import type { MembershipRowView } from "../../../shared/data/memberships";
import { usePaymentMethodOptions } from "../../../shared/data/paymentMethods";
import type { PaymentPanelTarget, PaymentPrefill } from "../../../shared/lib/paymentPanel";
import { Button } from "../../../shared/ui/Button";
import { ConfirmModal } from "../../../shared/ui/ConfirmModal";
import { SidePanel } from "../../../shared/ui/SidePanel";
import { membershipText } from "../lib/balance";
import { PAYMENT_MESSAGES } from "../paymentErrors";
import type { PaymentOutView } from "../schemas";
import { PaymentFields } from "./PaymentFields";
import { PaymentMemberPicker } from "./PaymentMemberPicker";
import styles from "./Payments.module.css";
import { MembershipSelect } from "./MembershipSelect";
import { useRegisterPaymentForm, type PendingConfirmation } from "./useRegisterPaymentForm";

export const REGISTER_PANEL_TITLE = "Registrar pago";

export interface RegisterPaymentPanelProps {
  target: PaymentPanelTarget;
  prefill?: PaymentPrefill | null;
  onClose: () => void;
}

function overpayText(pending: PendingConfirmation | null): string {
  if (pending?.excess === null || pending?.excess === undefined) return PAYMENT_MESSAGES.overpayUnknown;
  return PAYMENT_MESSAGES.overpay(formatCop(pending.excess));
}

function Done({ payment, membership, methodLabel, onAnother }: { payment: PaymentOutView; membership: string | null; methodLabel: string; onAnother: () => void }) {
  const titleId = useId();
  // Revisión S3-F4 (M2): el botón que tenía el foco desaparece; el foco va al título del resumen.
  const titleRef = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    titleRef.current?.focus();
  }, []);
  return (
    <div role="status" aria-labelledby={titleId} className={styles.done}>
      <h3 ref={titleRef} id={titleId} tabIndex={-1} className={styles.doneTitle}>
        Pago registrado
      </h3>
      <dl className={styles.list}>
        <div className={styles.row}>
          <dt>Valor</dt>
          <dd>{formatCop(payment.amount_cop)}</dd>
        </div>
        <div className={styles.row}>
          <dt>Medio</dt>
          <dd>{methodLabel}</dd>
        </div>
        {membership ? (
          <div className={styles.row}>
            <dt>Membresía</dt>
            <dd>{membership}</dd>
          </div>
        ) : null}
      </dl>
      <Button variant="secondary" onClick={onAnother}>
        Registrar otro pago
      </Button>
    </div>
  );
}

export function RegisterPaymentPanel({ target, prefill = null, onClose }: RegisterPaymentPanelProps) {
  const formId = useId();
  const alertRef = useRef<HTMLParagraphElement>(null);
  const state = useRegisterPaymentForm(target, prefill, { alertRef });
  const methods = usePaymentMethodOptions();
  const { form, done } = state;
  // Revisión S3-F4 (M1): sin socio o sin una membresía que reciba pagos no hay nada que registrar.
  const canSubmit = state.member !== null && state.options.length > 0;
  // Revisión S3-F4 (M2): al volver del resumen ("Registrar otro pago") el foco va al valor.
  const wasDone = useRef(false);
  useEffect(() => {
    if (done) wasDone.current = true;
    else if (wasDone.current) {
      wasDone.current = false;
      form.setFocus("amount");
    }
  }, [done, form]);

  const close = (): void => {
    if (!state.submitting) onClose();
  };

  return (
    <>
      <SidePanel
        open
        title={REGISTER_PANEL_TITLE}
        isDirty={!state.submitting && done === null && form.formState.isDirty}
        onClose={close}
        cancelLabel={done ? "Listo" : "Cancelar"}
        footer={
          done ? null : (
            <Button type="submit" form={formId} loading={state.submitting} disabled={!canSubmit}>
              {state.submitting ? "Registrando…" : "Registrar"}
            </Button>
          )
        }
      >
        {done ? (
          <Done
            payment={done}
            membership={state.selected ? membershipText(state.selected) : null}
            methodLabel={methods.methods.find((m) => m.code === done.method)?.label ?? done.method}
            onAnother={state.registerAnother}
          />
        ) : (
          <form id={formId} className={styles.form} noValidate aria-label={REGISTER_PANEL_TITLE} onSubmit={(event) => void form.handleSubmit(state.submit)(event)}>
            {state.alert ? (
              <p ref={alertRef} role="alert" tabIndex={-1} className={styles.alert}>
                {state.alert}
              </p>
            ) : null}
            {state.membershipFromUrl && !state.member ? (
              <MembershipFromUrlState query={state.membershipFromUrl} />
            ) : (
              <PaymentMemberPicker member={state.member} canChange={state.memberPicked} onSelect={state.selectMember} onClear={state.clearMember} />
            )}
            {state.member ? (
              <>
                <MembershipSelect form={form} memberId={state.member.id} memberships={state.memberships} options={state.options} balance={state.balance} />
                <PaymentFields form={form} methods={methods} onAmountEdit={state.onAmountEdit} />
              </>
            ) : null}
          </form>
        )}
      </SidePanel>
      <ConfirmModal
        open={state.overpay !== null}
        title={PAYMENT_MESSAGES.overpayTitle}
        consequence={overpayText(state.overpay)}
        confirmLabel="Registrar pago"
        tone="primary"
        onConfirm={state.confirmOverpay}
        onClose={state.closeOverpay}
      />
      <ConfirmModal
        open={state.duplicate !== null}
        title={PAYMENT_MESSAGES.duplicateTitle}
        consequence={PAYMENT_MESSAGES.duplicate}
        confirmLabel="Sí, registrar otro"
        tone="primary"
        onConfirm={state.confirmDuplicate}
        onClose={state.closeDuplicate}
      />
    </>
  );
}


/**
 * Revisión S3-F4 (H1): con `?pago=<membresía>` el socio sale de esa membresía. Mientras llega se dice;
 * si falla (enlace viejo, 404, red), se explica con Reintentar en vez de ofrecer un buscador inútil.
 */
function MembershipFromUrlState({ query }: { query: UseQueryResult<MembershipRowView> }) {
  if (!query.isError) return <p className={styles.note}>Cargando la membresía…</p>;
  return (
    <div className={styles.section}>
      <p role="alert" className={styles.fieldError}>
        {PAYMENT_MESSAGES.membershipFromUrlFailed}
      </p>
      <Button
        variant="secondary"
        loading={query.isFetching}
        onClick={() => {
          void query.refetch();
        }}
      >
        Reintentar
      </Button>
    </div>
  );
}
