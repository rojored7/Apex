// S3-F4 · estado y envío del panel "Registrar pago" (RegisterPaymentPanel). Separado del panel para que
// cada parte tenga una sola tarea:
// - Socio: fijo por la membresía (`?pago=<membresía>`), por la URL (`?pago=nuevo&socio=`) o elegido
//   en el panel. Sus membresías abiertas salen de useMemberOpenMemberships (shared/data, S3-D66).
//   S3-F7: si vino por la URL y no tiene membresías abiertas, su nombre sale de useMemberName.
// - Formulario (React Hook Form + Zod, registerPaymentSchema): membresía, medio, valor, referencia y
//   fecha y hora del pago (ahora en Bogotá). Con una sola membresía abierta se elige sola. El valor
//   sigue al saldo de la membresía elegida mientras no se edite; una precarga desde una anulación
//   (valor y medio) manda sobre el saldo.
// - Envío: un solo POST a la vez (doble clic, Enter). Si el valor supera el saldo se confirma antes
//   (Q5, S3-D41); un 409 `payment_exceeds_balance` también abre esa confirmación y un 409
//   `payment_possible_duplicate` abre la del duplicado. Cada confirmación se suma a las anteriores.
// - Errores: bajo su campo con foco (registerFieldError) o como aviso general con foco
//   (registerAlert). Un error nunca limpia el formulario (503 `busy` incluido). 409
//   `membership_cancelled` relee las membresías del socio.
import { useQueryClient, type UseQueryResult } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState, type RefObject } from "react";
import { useForm, useWatch, type Resolver, type UseFormReturn } from "react-hook-form";
import { formatCop, nowBogotaInput, parseCop } from "../../../core/i18n/format";
import { useMemberName } from "../../../shared/data/members";
import { openMembershipsKey, useMemberOpenMemberships, useMembershipOption, type MembershipRowView } from "../../../shared/data/memberships";
import type { PaymentPanelTarget, PaymentPrefill } from "../../../shared/lib/paymentPanel";
import { zodResolver } from "../../../shared/lib/zodResolver";
import { useRegisterPayment } from "../api";
import { balanceOf, excessOver } from "../lib/balance";
import { isDuplicateError, isMembershipCancelledError, isOverpaymentError, registerAlert, registerFieldError } from "../paymentErrors";
import { EMPTY_REGISTER_FORM, registerPaymentSchema, toPaymentBody, type PaymentBodyOptions, type PaymentOutView, type RegisterPaymentFormValues } from "../schemas";

export interface PanelMember {
  id: string;
  /** null: vino en la URL y todavía no se sabe el nombre. */
  name: string | null;
}

export interface PendingConfirmation {
  values: RegisterPaymentFormValues;
  confirmations: PaymentBodyOptions;
  /** Cuánto supera al saldo, o null si lo dijo el servidor (409) sin decir cuánto. */
  excess: number | null;
}

export interface RegisterPaymentFormState {
  form: UseFormReturn<RegisterPaymentFormValues>;
  member: PanelMember | null;
  /** El socio lo eligió el usuario en el panel (se puede cambiar). */
  memberPicked: boolean;
  selectMember: (member: PanelMember) => void;
  clearMember: () => void;
  /** Revisión S3-F4 (H1): la membresía de `?pago=<membresía>` (carga y error). */
  membershipFromUrl: UseQueryResult<MembershipRowView> | null;
  memberships: UseQueryResult<MembershipRowView[]>;
  options: MembershipRowView[];
  selected: MembershipRowView | null;
  balance: number | null;
  onAmountEdit: () => void;
  alert: string | null;
  overpay: PendingConfirmation | null;
  duplicate: PendingConfirmation | null;
  closeOverpay: () => void;
  closeDuplicate: () => void;
  confirmOverpay: () => Promise<void>;
  confirmDuplicate: () => Promise<void>;
  submit: (values: RegisterPaymentFormValues) => Promise<void>;
  submitting: boolean;
  done: PaymentOutView | null;
  registerAnother: () => void;
}

function initialValues(target: PaymentPanelTarget, prefill: PaymentPrefill | null): RegisterPaymentFormValues {
  return {
    ...EMPTY_REGISTER_FORM,
    membershipId: target.kind === "membership" ? target.membershipId : "",
    method: prefill?.method ?? EMPTY_REGISTER_FORM.method,
    amount: prefill ? formatCop(prefill.amountCop) : "",
    paidAt: nowBogotaInput(),
  };
}

/** Las membresías que se ofrecen: las abiertas del socio y, si no está entre ellas, la de la URL. */
function optionsOf(open: MembershipRowView[] | undefined, fromUrl: MembershipRowView | undefined): MembershipRowView[] {
  const list = open ?? [];
  return fromUrl && !list.some((m) => m.id === fromUrl.id) ? [...list, fromUrl] : list;
}

/** El socio del panel: el de la membresía de la URL, el de `?socio=` o el que se eligió. */
function usePanelMember(target: PaymentPanelTarget, fromUrl: MembershipRowView | undefined) {
  const [picked, setPicked] = useState<PanelMember | null>(target.kind === "new" && target.memberId ? { id: target.memberId, name: null } : null);
  const member: PanelMember | null = target.kind === "membership" ? (fromUrl ? { id: fromUrl.member_id, name: fromUrl.member_name } : null) : picked;
  return { member, setPicked, memberPicked: target.kind === "new" && target.memberId === null && picked !== null };
}

/** Elementos del panel que el envío enfoca: el aviso general. */
export interface RegisterFocusRefs {
  alertRef: RefObject<HTMLParagraphElement | null>;
}

export function useRegisterPaymentForm(target: PaymentPanelTarget, prefill: PaymentPrefill | null, { alertRef }: RegisterFocusRefs): RegisterPaymentFormState {
  const queryClient = useQueryClient();
  // "Ahora" se lee en cada validación (el panel puede quedar abierto un rato).
  const resolver = useMemo<Resolver<RegisterPaymentFormValues>>(() => async (values, context, options) => zodResolver(registerPaymentSchema())(values, context, options), []);
  const form = useForm<RegisterPaymentFormValues>({ resolver, defaultValues: initialValues(target, prefill) });
  const fromUrl = useMembershipOption(target.kind === "membership" ? target.membershipId : null);
  const { member, setPicked, memberPicked } = usePanelMember(target, fromUrl.data);
  const memberships = useMemberOpenMemberships(member?.id ?? null);
  const options = optionsOf(memberships.data, fromUrl.data);
  const membershipId = useWatch({ control: form.control, name: "membershipId" });
  const selected = options.find((m) => m.id === membershipId) ?? null;
  const balance = selected ? balanceOf(selected) : null;
  const amountEdited = useRef(prefill !== null);

  useOnlyOptionSelected(form, options);
  useAmountFollowsBalance(form, selected?.id ?? null, balance, amountEdited);

  const sender = useSender(form, membershipId === "" ? null : membershipId, alertRef, () => {
    if (member) void queryClient.invalidateQueries({ queryKey: openMembershipsKey(member.id) });
  });

  // S3-F7: un socio de la URL sin membresías abiertas (ni nombre) se nombra con GET /members/{id}.
  const needsName = member !== null && member.name === null && memberships.isSuccess && options.length === 0;
  const fetchedName = useMemberName(needsName ? member.id : null);
  const memberName = member?.name ?? options[0]?.member_name ?? fetchedName.data ?? null;
  return {
    form,
    member: member ? { id: member.id, name: memberName } : null,
    memberPicked,
    selectMember: (chosen) => {
      setPicked(chosen);
      sender.clearAlert();
      form.setValue("membershipId", "");
    },
    clearMember: () => {
      setPicked(null);
      sender.clearAlert();
      form.setValue("membershipId", "");
    },
    membershipFromUrl: target.kind === "membership" ? fromUrl : null,
    memberships,
    options,
    selected,
    balance,
    onAmountEdit: () => {
      amountEdited.current = true;
    },
    ...sender,
    submit: async (values) => {
      const amount = parseCop(values.amount);
      if (balance !== null && amount !== null && amount > balance) {
        sender.askOverpay({ values, confirmations: {}, excess: excessOver(balance, amount) });
        return;
      }
      await sender.send(values, {});
    },
    registerAnother: () => {
      amountEdited.current = false;
      sender.clearDone();
      form.reset({ ...form.getValues(), amount: balance !== null && balance > 0 ? formatCop(balance) : "", reference: "", paidAt: nowBogotaInput() });
    },
  };
}

/** Con una sola membresía abierta y ninguna elegida, se elige sola. */
function useOnlyOptionSelected(form: UseFormReturn<RegisterPaymentFormValues>, options: MembershipRowView[]): void {
  const only = options.length === 1 ? (options[0]?.id ?? null) : null;
  useEffect(() => {
    if (only !== null && form.getValues("membershipId") === "") form.setValue("membershipId", only);
  }, [form, only]);
}

/** El valor sigue al saldo de la membresía elegida hasta que el usuario lo edite. */
function useAmountFollowsBalance(form: UseFormReturn<RegisterPaymentFormValues>, selectedId: string | null, balance: number | null, edited: RefObject<boolean>): void {
  useEffect(() => {
    if (selectedId === null || balance === null || edited.current) return;
    form.setValue("amount", balance > 0 ? formatCop(balance) : "");
  }, [form, selectedId, balance, edited]);
}

interface Sender {
  alert: string | null;
  overpay: PendingConfirmation | null;
  duplicate: PendingConfirmation | null;
  done: PaymentOutView | null;
  submitting: boolean;
  send: (values: RegisterPaymentFormValues, confirmations: PaymentBodyOptions) => Promise<void>;
  askOverpay: (pending: PendingConfirmation) => void;
  closeOverpay: () => void;
  closeDuplicate: () => void;
  confirmOverpay: () => Promise<void>;
  confirmDuplicate: () => Promise<void>;
  clearAlert: () => void;
  clearDone: () => void;
}

/** Envío, confirmaciones y errores (un solo POST a la vez). */
function useSender(
  form: UseFormReturn<RegisterPaymentFormValues>,
  membershipId: string | null,
  alertRef: RefObject<HTMLParagraphElement | null>,
  onMembershipsStale: () => void,
): Sender {
  const payment = useRegisterPayment(membershipId);
  const [alert, setAlert] = useState<string | null>(null);
  const [overpay, setOverpay] = useState<PendingConfirmation | null>(null);
  const [duplicate, setDuplicate] = useState<PendingConfirmation | null>(null);
  const [done, setDone] = useState<PaymentOutView | null>(null);
  const inFlight = useRef(false);
  useEffect(() => {
    if (alert) alertRef.current?.focus();
  }, [alert, alertRef]);

  const onError = (error: unknown, values: RegisterPaymentFormValues, confirmations: PaymentBodyOptions): void => {
    if (isOverpaymentError(error) && confirmations.confirmOverpayment !== true) {
      setOverpay({ values, confirmations, excess: null });
      return;
    }
    if (isDuplicateError(error) && confirmations.confirmDuplicate !== true) {
      setDuplicate({ values, confirmations, excess: null });
      return;
    }
    if (isMembershipCancelledError(error)) onMembershipsStale();
    const target = registerFieldError(error);
    if (target) form.setError(target.path, { type: "server", message: target.message }, { shouldFocus: true });
    else setAlert(registerAlert(error));
  };

  const send = async (values: RegisterPaymentFormValues, confirmations: PaymentBodyOptions): Promise<void> => {
    if (inFlight.current) return;
    inFlight.current = true;
    setAlert(null);
    try {
      setDone(await payment.register(toPaymentBody(values, confirmations)));
    } catch (error) {
      onError(error, values, confirmations);
    } finally {
      inFlight.current = false;
    }
  };

  // El modal se cierra antes de enviar: así el foco que devuelve no pisa el del campo o el aviso.
  const confirmWith = async (pending: PendingConfirmation | null, extra: PaymentBodyOptions): Promise<void> => {
    setOverpay(null);
    setDuplicate(null);
    if (pending) await send(pending.values, { ...pending.confirmations, ...extra });
  };

  return {
    alert,
    overpay,
    duplicate,
    done,
    submitting: payment.isPending,
    send,
    askOverpay: setOverpay,
    // Cada modal cierra solo el suyo: tras confirmar el sobrepago puede abrirse el del duplicado, y el
    // cierre del primero (que ConfirmModal llama después de onConfirm) no debe borrarlo.
    closeOverpay: () => {
      setOverpay(null);
    },
    closeDuplicate: () => {
      setDuplicate(null);
    },
    confirmOverpay: () => confirmWith(overpay, { confirmOverpayment: true }),
    confirmDuplicate: () => confirmWith(duplicate, { confirmDuplicate: true }),
    clearAlert: () => {
      setAlert(null);
    },
    clearDone: () => {
      setDone(null);
    },
  };
}
