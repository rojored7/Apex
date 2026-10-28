// S3-F3 · US-084, US-085 y US-088 (front): /membresias/vender (Membresia_Vender.html), admin y
// coach (`memberships.sell`).
// - Los tres pasos del diseño en una página (socio, plan y fechas, pago) más el resumen; React Hook
//   Form y Zod (useSellForm). POST /members/{id}/memberships con `first_payment` opcional; vender y
//   renovar usan el mismo endpoint (regla 9 de CLAUDE.md).
// - `?socio=<id>` fija el socio; `&renovar=1` renueva: `renew: true`, sin `start_date`, y la fecha
//   de inicio la calcula el servidor (vista previa, Q1). El formulario se monta de nuevo al cambiar
//   el socio o la renovación de la URL (por ejemplo al pulsar "Renovar" en el aviso de
//   `membership_conflict`) y al pulsar "Vender otra membresía"; abrir el panel de pagos (`?pago=`) no
//   lo toca (Fase 4 L4).
// - Pendiente 3 de V1 (S3-D103): las migas enlazan "Membresías" a /membresias. "Cancelar" y el enlace
//   de la venta registrada llevan a la ficha del socio si se llegó con `?socio=` (desde su ficha o
//   para renovar), y a /membresias si no.
import { useRef, useState } from "react";
import { useWatch } from "react-hook-form";
import { Link, useLocation } from "react-router";
import { formatCop, parseCop } from "../../../core/i18n/format";
import { useMemberName } from "../../../shared/data/members";
import { ConfirmModal } from "../../../shared/ui/ConfirmModal";
import { PageHeader } from "../../../shared/ui/PageHeader";
import { cx } from "../../../shared/ui/cx";
import { FirstPaymentSection, usePaymentMethodOptions } from "../components/FirstPaymentSection";
import { MemberStep, UNNAMED_MEMBER } from "../components/MemberStep";
import { PlanStep } from "../components/PlanStep";
import styles from "../components/Sell.module.css";
import { SellDone, SellSummary } from "../components/SellSummary";
import { memberHref, MEMBERSHIPS_PATH, memberNameFromState, readSellParams, type SellLocationState, type SellParams } from "../membershipLinks";
import { useSellForm, type Overpayment } from "./useSellForm";
import page from "./SellPage.module.css";

export const SELL_TITLE = "Vender membresía";
export const RENEW_TITLE = "Renovar membresía";

const OVERPAY_TITLE = "¿Registrar un pago mayor al precio?";
const NO_CREDIT = "La diferencia no queda como saldo a favor.";

/** S3-D103: a dónde vuelve la venta (Cancelar y tras vender). */
export interface SellExit {
  href: string;
  text: string;
}

export function sellExitOf(params: SellParams): SellExit {
  return params.memberId ? { href: memberHref(params.memberId), text: "Ir a la ficha del socio" } : { href: MEMBERSHIPS_PATH, text: "Ir a Membresías" };
}

function overpayText(overpay: Overpayment | null): string {
  if (overpay?.excess === null || overpay === null) return `Este pago supera el saldo de la membresía. ${NO_CREDIT}`;
  return `Este pago supera el precio del plan en ${formatCop(overpay.excess)}. ${NO_CREDIT}`;
}

function Steps({ memberDone, planDone }: { memberDone: boolean; planDone: boolean }) {
  const steps = [
    { label: "Socio", done: memberDone },
    { label: "Plan y fechas", done: planDone },
    { label: "Pago", done: false },
  ];
  return (
    <ol className={styles.steps} aria-label="Pasos de la venta">
      {steps.map((step, index) => (
        <li key={step.label} className={cx(styles.step, step.done && styles.stepDone)}>
          <span className={styles.stepNumber} aria-hidden="true">
            {index + 1}
          </span>
          {step.label}
        </li>
      ))}
    </ol>
  );
}

interface SellFormProps {
  params: SellParams;
  initialMemberName: string | null;
  /** S3-F7: el nombre que llegó de GET /members/{id} cuando la navegación no lo trajo. */
  fallbackName: string | null;
  onSellAnother: () => void;
}

function SellForm({ params, initialMemberName, fallbackName, onSellAnother }: SellFormProps) {
  const alertRef = useRef<HTMLDivElement>(null);
  const planGroupRef = useRef<HTMLFieldSetElement>(null);
  const state = useSellForm(params, initialMemberName, { alertRef, planGroupRef });
  const methods = usePaymentMethodOptions();
  const { form, plan, dates, alert } = state;
  // S3-F7: el socio fijado por la URL sin nombre en la navegación toma el de GET /members/{id}.
  const member = state.member && state.member.name === null && state.member.id === params.memberId && fallbackName !== null ? { ...state.member, name: fallbackName } : state.member;
  const { errors } = form.formState;
  const withPayment = useWatch({ control: form.control, name: "withPayment" });
  const method = useWatch({ control: form.control, name: "method" });
  const amount = parseCop(useWatch({ control: form.control, name: "amount" }));
  const methodLabel = methods.methods.find((m) => m.code === method)?.label ?? "";
  const exit = sellExitOf(params);

  return (
    <>
      <Steps memberDone={member !== null} planDone={plan !== null} />
      {state.sold ? (
        <SellDone sold={state.sold} exit={exit} onSellAnother={onSellAnother} />
      ) : (
        <form className={page.form} noValidate aria-label={params.renew ? RENEW_TITLE : SELL_TITLE} onSubmit={(event) => void form.handleSubmit(state.submit)(event)}>
          {alert ? (
            <div ref={alertRef} className={styles.alert} role="alert" tabIndex={-1}>
              <span>{alert.message}</span>
              {alert.action ? (
                <Link
                  className={styles.link}
                  to={alert.action.href}
                  state={member?.name ? ({ memberName: member.name } satisfies SellLocationState) : undefined}
                >
                  {alert.action.text}
                </Link>
              ) : null}
            </div>
          ) : null}
          <div className={styles.columns}>
            <div className={styles.main}>
              <MemberStep member={member} fixed={params.memberId !== null} error={errors.memberId?.message} onSelect={state.selectMember} onClear={state.clearMember} />
              <PlanStep
                plans={state.plans}
                planField={state.planField}
                startField={form.register("startDate")}
                planError={errors.planId?.message}
                startError={errors.startDate?.message}
                renew={params.renew}
                preview={state.preview}
                dates={dates}
                planGroupRef={planGroupRef}
              />
              <FirstPaymentSection
                control={form.control}
                register={form.register}
                errors={errors}
                methods={methods.methods}
                methodsFailed={methods.failed}
                onRetryMethods={methods.retry}
                onAmountEdit={state.onAmountEdit}
              />
            </div>
            <SellSummary
              memberName={member ? (member.name ?? UNNAMED_MEMBER) : null}
              planName={plan?.name ?? null}
              start={dates.start && plan ? dates.start : null}
              end={dates.end}
              price={dates.price}
              withPayment={withPayment}
              amount={amount}
              methodLabel={methodLabel}
              registeredBy={state.registeredBy}
              submitting={state.submitting}
              submitDisabled={state.blocked}
              cancelHref={exit.href}
            />
          </div>
        </form>
      )}
      <ConfirmModal
        open={state.overpay !== null}
        title={OVERPAY_TITLE}
        consequence={overpayText(state.overpay)}
        confirmLabel="Registrar pago"
        tone="primary"
        onConfirm={state.confirmOverpay}
        onClose={state.closeOverpay}
      />
    </>
  );
}

export default function SellPage() {
  const location = useLocation();
  const params = readSellParams(location.search);
  const memberName = memberNameFromState(location.state);
  // S3-F7 (pendiente de S3-F1): sin el nombre en la navegación (un enlace directo o la ficha) se
  // pide; con él, no.
  const fetchedName = useMemberName(params.memberId !== null && memberName === null ? params.memberId : null);
  // "Vender otra membresía" vuelve a montar el formulario limpio.
  const [round, setRound] = useState(0);
  const title = params.renew ? RENEW_TITLE : SELL_TITLE;
  return (
    <div className={page.page}>
      <PageHeader title={title} breadcrumbs={[{ label: "Membresías", href: MEMBERSHIPS_PATH }, { label: params.renew ? "Renovar" : "Vender" }]} />
      <SellForm
        // L4: la clave es lo que define la venta (socio y renovación), no toda la búsqueda de la URL.
        key={`${params.memberId ?? ""}|${String(params.renew)}#${String(round)}`}
        params={params}
        initialMemberName={memberName}
        fallbackName={fetchedName.data ?? null}
        onSellAnother={() => {
          setRound((value) => value + 1);
        }}
      />
    </div>
  );
}
