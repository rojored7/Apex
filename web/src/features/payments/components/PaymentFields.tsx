// S3-F4 · medio, valor, referencia y fecha del pago en el panel "Registrar pago" (Pagos.html: tres
// medios grandes, "Valor *" y "Referencia *").
// - Medios con la etiqueta de GET /payments/methods (D24); si no cargan, las de siempre con un aviso.
// - Valor formateado al escribir ("$ 60.000"); escribir en él deja de seguir al saldo.
// - Referencia solo con Nequi y Bre-B, con el aviso M-7 (S3-D50) y el patrón de comprobante.
// - Fecha y hora del pago en hora de Bogotá; se envía en UTC (schemas.ts).
import { Controller, useWatch, type UseFormReturn } from "react-hook-form";
import type { PaymentMethodOptions } from "../../../shared/data/paymentMethods";
import { METHODS_WITH_REFERENCE, REFERENCE_MAX, SENSITIVE_TEXT_WARNING } from "../../../shared/data/schemas/payment";
import { moneyInputText } from "../../../shared/lib/moneyInput";
import { Button } from "../../../shared/ui/Button";
import { Field } from "../../../shared/ui/Field";
import { PAYMENT_MESSAGES } from "../paymentErrors";
import type { RegisterPaymentFormValues } from "../schemas";
import styles from "./Payments.module.css";

export interface PaymentFieldsProps {
  form: UseFormReturn<RegisterPaymentFormValues>;
  methods: PaymentMethodOptions;
  /** El usuario escribió en el valor: deja de seguir al saldo. */
  onAmountEdit: () => void;
}

export function PaymentFields({ form, methods, onAmountEdit }: PaymentFieldsProps) {
  const { register, control, formState } = form;
  const { errors } = formState;
  const method = useWatch({ control, name: "method" });
  return (
    <>
      <fieldset className={styles.fieldset}>
        <legend className={styles.srOnly}>Medio de pago</legend>
        <div className={styles.methods}>
          {methods.methods.map((option) => (
            <label key={option.code} className={styles.method}>
              <input {...register("method")} className={styles.methodRadio} type="radio" value={option.code} />
              {option.label}
            </label>
          ))}
        </div>
      </fieldset>
      {methods.failed ? (
        <p className={styles.note}>
          {PAYMENT_MESSAGES.methodsFailed}{" "}
          <Button variant="ghost" onClick={methods.retry}>
            Reintentar
          </Button>
        </p>
      ) : null}
      <div className={styles.grid2}>
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
      </div>
      <Field label="Fecha y hora del pago" required type="datetime-local" error={errors.paidAt?.message} {...register("paidAt")} />
    </>
  );
}
