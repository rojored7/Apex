// S3-F3 · estado y envío de la venta (SellPage). Separado de la página para que cada parte tenga
// una sola tarea:
// - Formulario (React Hook Form + Zod, sellMembershipSchema): socio, plan, inicio (hoy en Bogotá) y
//   el primer pago (valor, medio, referencia, fecha y hora del pago, ahora en Bogotá).
// - Precio y fechas de la vista previa: al vender salen del plan; al renovar, de la vista previa del
//   servidor (useRenewalPreview). El valor recibido sigue al precio mientras no se edite.
// - Envío: un solo POST a la vez (doble clic, Enter). Si el valor supera el precio, primero se
//   confirma el sobrepago (Q5, S3-D41); un 409 `payment_exceeds_balance` inesperado también abre la
//   confirmación. `confirm_overpayment` solo viaja en verdadero tras confirmar.
// - Errores: bajo su campo con foco (sellFieldError) o como aviso general con foco (sellAlert). Un
//   error nunca limpia el formulario (503 `busy` incluido).
import { useEffect, useMemo, useRef, useState, type RefObject } from "react";
import { useForm, useWatch, type Resolver, type UseFormRegisterReturn, type UseFormReturn } from "react-hook-form";
import type { UseQueryResult } from "@tanstack/react-query";
import { useSession } from "../../../core/auth";
import { formatCop, nowBogotaInput, parseCop, todayBogota } from "../../../core/i18n/format";
import type { Page } from "../../../core/api/page";
import { usePlans, type PlanRowView } from "../../../shared/data/plans";
import { zodResolver } from "../../../shared/lib/zodResolver";
import { useRenewalPreview, useSellMembership } from "../api";
import type { SelectedMember } from "../components/MemberStep";
import { computeEndDate, exceedsBalance, excessOver } from "../lib/rules";
import { isFutureMembershipError, isOverpaymentError, sellAlert, sellFieldError, type SellAlert } from "../membershipErrors";
import type { SellParams } from "../membershipLinks";
import { EMPTY_SELL_FORM, sellMembershipSchema, toSellBody, type RenewalPreviewView, type SellFormValues, type SellMembershipOutView } from "../schemas";

/** Planes activos que se ofrecen (un box tiene pocos; el api admite hasta 200 por página). */
export const SELL_PLANS_LIMIT = 100;

export interface Overpayment {
  values: SellFormValues;
  /** Cuánto supera al precio, o null si lo dijo el servidor (409) sin decir cuánto. */
  excess: number | null;
}

export interface SellDates {
  start: string | null;
  end: string | null;
  price: number | null;
}

export interface SellFormState {
  form: UseFormReturn<SellFormValues>;
  member: SelectedMember | null;
  selectMember: (member: SelectedMember) => void;
  clearMember: () => void;
  plans: UseQueryResult<Page<PlanRowView>>;
  planField: UseFormRegisterReturn<"planId">;
  /** El usuario escribió en el valor recibido: deja de seguir al precio. */
  onAmountEdit: () => void;
  plan: PlanRowView | null;
  preview: UseQueryResult<RenewalPreviewView> | null;
  dates: SellDates;
  alert: SellAlert | null;
  overpay: Overpayment | null;
  closeOverpay: () => void;
  confirmOverpay: () => Promise<void>;
  submit: (values: SellFormValues) => Promise<void>;
  submitting: boolean;
  blocked: boolean;
  sold: SellMembershipOutView | null;
  registeredBy: string | null;
}

function initialValues(params: SellParams): SellFormValues {
  return { ...EMPTY_SELL_FORM, memberId: params.memberId ?? "", renew: params.renew, startDate: todayBogota(), paidAt: nowBogotaInput() };
}

function datesOf(renew: boolean, preview: UseQueryResult<RenewalPreviewView> | null, plan: PlanRowView | null, startDate: string): SellDates {
  if (renew) {
    const data = preview?.data;
    return data ? { start: data.start_date, end: data.end_date, price: data.agreed_price_cop } : { start: null, end: null, price: null };
  }
  if (!plan) return { start: startDate || null, end: null, price: null };
  return { start: startDate || null, end: computeEndDate(startDate, plan.duration_days), price: plan.price_cop };
}

/**
 * El valor recibido sigue al precio (plan o vista previa) hasta que el usuario lo edite (revisión
 * S3-F3, LOW 7: se marca al escribir; un valor borrado a mano tampoco se vuelve a llenar).
 */
function useAmountFollowsPrice(form: UseFormReturn<SellFormValues>, price: number | null, edited: RefObject<boolean>): void {
  useEffect(() => {
    if (price !== null && !edited.current) form.setValue("amount", formatCop(price));
  }, [form, price, edited]);
}

/** Elementos de la página que el envío enfoca: el aviso general y el grupo de planes. */
export interface SellFocusRefs {
  alertRef: RefObject<HTMLDivElement | null>;
  planGroupRef: RefObject<HTMLFieldSetElement | null>;
}

export function useSellForm(params: SellParams, initialMemberName: string | null, { alertRef, planGroupRef }: SellFocusRefs): SellFormState {
  const registeredBy = useSession().user?.email ?? null;
  // Revisión S3-F3 (LOW 6): "hoy" se lee en cada validación (la página puede quedar abierta tras medianoche).
  const resolver = useMemo<Resolver<SellFormValues>>(() => async (values, context, options) => zodResolver(sellMembershipSchema(todayBogota()))(values, context, options), []);
  const form = useForm<SellFormValues>({ resolver, defaultValues: initialValues(params) });
  const [member, setMember] = useState<SelectedMember | null>(params.memberId ? { id: params.memberId, name: initialMemberName } : null);
  const plans = usePlans({ limit: SELL_PLANS_LIMIT, offset: 0, active: true });
  const planId = useWatch({ control: form.control, name: "planId" });
  const startDate = useWatch({ control: form.control, name: "startDate" });
  const plan = plans.data?.items.find((p) => p.id === planId) ?? null;
  const previewQuery = useRenewalPreview(params.renew ? (member?.id ?? null) : null, params.renew && planId !== "" ? planId : null);
  const preview = params.renew && planId !== "" ? previewQuery : null;
  const dates = datesOf(params.renew, preview, plan, startDate);
  const amountEdited = useRef(false);
  useAmountFollowsPrice(form, dates.price, amountEdited);

  const sale = useSellMembership(member?.id ?? null);
  const [alert, setAlert] = useState<SellAlert | null>(null);
  const [overpay, setOverpay] = useState<Overpayment | null>(null);
  const [sold, setSold] = useState<SellMembershipOutView | null>(null);
  const inFlight = useRef(false);
  useEffect(() => {
    if (alert) alertRef.current?.focus();
  }, [alert, alertRef]);

  const context = { memberId: member?.id ?? "", memberName: member?.name ?? null };
  const futureExists = preview !== null && isFutureMembershipError(preview.error);
  const previewAlert = futureExists ? sellAlert(preview.error, context) : null;

  const onError = (error: unknown, values: SellFormValues, confirmed: boolean): void => {
    if (isOverpaymentError(error) && !confirmed) {
      setOverpay({ values, excess: null });
      return;
    }
    const target = sellFieldError(error);
    if (!target) {
      setAlert(sellAlert(error, context));
      return;
    }
    form.setError(target.path, { type: "server", message: target.message }, { shouldFocus: target.path !== "planId" });
    // Un grupo de radios no tiene un ref enfocable en RHF: el foco va al plan elegido.
    if (target.path === "planId") (planGroupRef.current?.querySelector<HTMLInputElement>("input:checked") ?? planGroupRef.current?.querySelector<HTMLInputElement>("input"))?.focus();
  };

  const send = async (values: SellFormValues, confirmed: boolean): Promise<void> => {
    if (inFlight.current) return;
    inFlight.current = true;
    setAlert(null);
    try {
      setSold(await sale.sell(toSellBody(values, { confirmOverpayment: confirmed })));
    } catch (error) {
      onError(error, values, confirmed);
    } finally {
      inFlight.current = false;
    }
  };

  const submit = async (values: SellFormValues): Promise<void> => {
    const amount = parseCop(values.amount);
    if (values.withPayment && dates.price !== null && amount !== null && exceedsBalance(dates.price, 0, amount)) {
      setOverpay({ values, excess: excessOver(dates.price, 0, amount) });
      return;
    }
    await send(values, false);
  };

  return {
    form,
    member,
    selectMember: (selected) => {
      setMember(selected);
      setAlert(null);
      form.setValue("memberId", selected.id);
      form.clearErrors("memberId");
    },
    clearMember: () => {
      setMember(null);
      setAlert(null);
      form.setValue("memberId", "");
    },
    plans,
    // Revisión S3-F3 (LOW 8): cambiar de plan quita el aviso general que ya no aplica.
    planField: form.register("planId", {
      onChange: () => {
        setAlert(null);
      },
    }),
    onAmountEdit: () => {
      amountEdited.current = true;
    },
    plan,
    preview,
    dates,
    alert: alert ?? previewAlert,
    overpay,
    closeOverpay: () => {
      setOverpay(null);
    },
    confirmOverpay: async () => {
      // Revisión S3-F3 (MEDIUM 2): el modal se cierra antes de enviar; así el foco que devuelve no pisa
      // el del campo o el aviso del error.
      const pending = overpay;
      setOverpay(null);
      if (pending) await send(pending.values, true);
    },
    submit,
    submitting: sale.isPending,
    blocked: futureExists,
    sold,
    registeredBy,
  };
}
