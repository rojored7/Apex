// S3-F3 · US-085 (front): paso "3 · Pago" de Membresia_Vender.html, el primer pago de la venta.
// - "Registrar el pago ahora" (marcado): sin pago la membresía queda "Pendiente de pago" (Q3) y el
//   botón dice "Vender".
// - Medios con la etiqueta de GET /payments/methods (usePaymentMethods de shared/data, D24); si no
//   cargan se muestran las etiquetas de siempre (los tres medios son fijos) con un aviso.
// - Valor recibido: se precarga con el precio y se formatea al escribir ("$ 120.000").
// - Referencia solo con Nequi y Bre-B, con el aviso M-7 (S3-D50) y el patrón de comprobante.
//   DESIGN-GAP: el diseño no dice si la referencia es obligatoria; el api la acepta opcional en los
//   tres medios (D17), así que es opcional.
// - Fecha y hora del pago: por defecto ahora, en hora de Bogotá; se envía en UTC (schemas.ts).
//   DESIGN-GAP: el diseño pide solo la fecha; el api guarda un instante (`paid_at`), así que se pide
//   fecha y hora.
// - DESIGN-GAP: el diseño dice "Recibo por correo si el socio tiene correo"; los recibos llegan con
//   v0.2 y no se menciona.
import { Controller, useWatch, type Control, type FieldErrors, type UseFormRegister } from "react-hook-form";
import { usePaymentMethods, type PaymentMethodView } from "../../../shared/data/paymentMethods";
import { METHODS_WITH_REFERENCE, PAYMENT_METHOD_CODES, REFERENCE_MAX, SENSITIVE_TEXT_WARNING, type PaymentMethodCode } from "../../../shared/data/schemas/payment";
import { moneyInputText } from "../../../shared/lib/moneyInput";
import { Button } from "../../../shared/ui/Button";
import { Field } from "../../../shared/ui/Field";
import { SELL_MESSAGES } from "../membershipErrors";
import type { SellFormValues } from "../schemas";
import styles from "./Sell.module.css";

/** Las etiquetas por defecto de los tres medios (D24), si GET /payments/methods no responde. */
const DEFAULT_LABELS: Readonly<Record<PaymentMethodCode, string>> = { cash: "Efectivo", nequi: "Nequi", breb: "Bre-B" };

export const DEFAULT_PAYMENT_METHODS: readonly PaymentMethodView[] = PAYMENT_METHOD_CODES.map((code) => ({ code, label: DEFAULT_LABELS[code], hint: "" }));

export interface FirstPaymentSectionProps {
  control: Control<SellFormValues>;
  register: UseFormRegister<SellFormValues>;
  errors: FieldErrors<SellFormValues>;
  /** Los medios que se muestran (los del api o los de siempre). */
  methods: readonly PaymentMethodView[];
  methodsFailed: boolean;
  onRetryMethods: () => void;
  /** El usuario escribió en el valor: deja de seguir al precio. */
  onAmountEdit: () => void;
}

/** Los medios del api, o los de siempre mientras cargan o si fallan. */
export function usePaymentMethodOptions(): { methods: readonly PaymentMethodView[]; failed: boolean; retry: () => void } {
  const query = usePaymentMethods();
  return {
    methods: query.data ?? DEFAULT_PAYMENT_METHODS,
    failed: query.isError,
    retry: () => {
      void query.refetch();
    },
  };
}

function MethodOptions({ methods, register }: { methods: readonly PaymentMethodView[]; register: UseFormRegister<SellFormValues> }) {
  return (
    <fieldset className={styles.fieldset}>
      <legend className={styles.srOnly}>Medio de pago</legend>
      <div className={styles.methods}>
        {methods.map((method) => (
          <label key={method.code} className={styles.method}>
            <input {...register("method")} className={styles.methodRadio} type="radio" value={method.code} />
            {method.label}
          </label>
        ))}
      </div>
    </fieldset>
  );
}

export function FirstPaymentSection({ control, register, errors, methods, methodsFailed, onRetryMethods, onAmountEdit }: FirstPaymentSectionProps) {
  const withPayment = useWatch({ control, name: "withPayment" });
  const method = useWatch({ control, name: "method" });
  return (
    <section className={styles.box} aria-labelledby="sell-payment-title">
      <h2 id="sell-payment-title" className={styles.h2}>
        3 · Pago
      </h2>
      <label className={styles.toggle}>
        <input {...register("withPayment")} className={styles.checkbox} type="checkbox" />
        Registrar el pago ahora
      </label>
      {withPayment ? (
        <>
          <MethodOptions methods={methods} register={register} />
          {methodsFailed ? (
            <p className={styles.note}>
              {SELL_MESSAGES.methodsFailed}{" "}
              <Button variant="ghost" onClick={onRetryMethods}>
                Reintentar
              </Button>
            </p>
          ) : null}
          <div className={styles.grid3}>
            <Controller
              control={control}
              name="amount"
              render={({ field }) => (
                <Field
                  label="Valor recibido"
                  required
                  inputMode="numeric"
                  autoComplete="off"
                  name={field.name}
                  ref={field.ref}
                  value={field.value}
                  error={errors.amount?.message}
                  onBlur={field.onBlur}
                  onChange={(event) => {
                    onAmountEdit();
                    field.onChange(moneyInputText(event.target.value, field.value));
                  }}
                />
              )}
            />
            {METHODS_WITH_REFERENCE.has(method) ? (
              <Field
                label="Referencia"
                placeholder="N.º de transacción"
                autoComplete="off"
                maxLength={REFERENCE_MAX * 2}
                hint={SENSITIVE_TEXT_WARNING}
                error={errors.reference?.message}
                {...register("reference")}
              />
            ) : null}
            <Field label="Fecha y hora del pago" required type="datetime-local" error={errors.paidAt?.message} {...register("paidAt")} />
          </div>
          <p className={styles.note}>Si el valor es menor al precio, queda como abono y la membresía muestra el saldo pendiente.</p>
        </>
      ) : (
        <p className={styles.note}>La membresía queda Pendiente de pago hasta que registres un pago.</p>
      )}
    </section>
  );
}
