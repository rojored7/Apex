// S3-F3 · paso "2 · Plan y fechas" de Membresia_Vender.html.
// - Planes activos (usePlans de shared/data con `active: true`; el coach no ve /planes pero sí esta
//   lista, S2-D26) como opciones de radio con su duración y precio. Sin planes activos, el admin
//   puede ir a crearlos; el coach debe pedirlo.
// - Inicio: hoy en Bogotá y editable al vender; al renovar, de solo lectura con la fecha que da la
//   vista previa del servidor (Q1): "Empieza el 29 oct 2026, al día siguiente de que termine la
//   actual".
// - DESIGN-GAP (D16): "Fin (calculado)" es de solo lectura y dice "Vale hasta el <fecha>" (fin
//   inclusivo de N-23: 29 oct + 30 días = 28 nov, no el "27 nov" del diseño).
// - DESIGN-GAP (D16): "Precio pactado" es de solo lectura: SellMembershipIn no recibe precio (el
//   servidor copia el del plan); el diseño lo deja ajustar como descuento.
import type { RefObject } from "react";
import type { UseFormRegisterReturn } from "react-hook-form";
import { Link } from "react-router";
import type { UseQueryResult } from "@tanstack/react-query";
import { useCan } from "../../../core/auth";
import { EMPTY_VALUE, formatCop, formatDate } from "../../../core/i18n/format";
import type { Page } from "../../../core/api/page";
import type { PlanRowView } from "../../../shared/data/plans";
import { Button } from "../../../shared/ui/Button";
import { Field } from "../../../shared/ui/Field";
import { planTermsText, untilText } from "../lib/rules";
import { SELL_MESSAGES } from "../membershipErrors";
import { PLANS_PATH } from "../membershipLinks";
import type { RenewalPreviewView } from "../schemas";
import styles from "./Sell.module.css";

export interface PlanStepDates {
  start: string | null;
  end: string | null;
  price: number | null;
}

export interface PlanStepProps {
  plans: UseQueryResult<Page<PlanRowView>>;
  planField: UseFormRegisterReturn<"planId">;
  startField: UseFormRegisterReturn<"startDate">;
  planError?: string | undefined;
  startError?: string | undefined;
  renew: boolean;
  /** La vista previa de la renovación (solo al renovar con plan elegido). */
  preview: UseQueryResult<RenewalPreviewView> | null;
  dates: PlanStepDates;
  /** El fieldset de los planes: el foco de un error de plan va al radio elegido. */
  planGroupRef: RefObject<HTMLFieldSetElement | null>;
}

function PlanOptions({ plans, planField }: Pick<PlanStepProps, "plans" | "planField">) {
  const canManagePlans = useCan("plans.manage");
  if (plans.isError) {
    return (
      <p className={styles.fieldError}>
        {SELL_MESSAGES.plansFailed}{" "}
        <Button variant="ghost" onClick={() => void plans.refetch()}>
          Reintentar
        </Button>
      </p>
    );
  }
  if (plans.isPending) return <p className={styles.note}>Cargando planes…</p>;
  if (plans.data.items.length === 0) {
    return (
      <div>
        <p className={styles.note}>No hay planes activos para vender.</p>
        {canManagePlans ? (
          <Link className={styles.link} to={PLANS_PATH}>
            Crear un plan
          </Link>
        ) : (
          <p className={styles.note}>Pídele a un administrador que active un plan.</p>
        )}
      </div>
    );
  }
  return (
    <div className={styles.planGrid}>
      {plans.data.items.map((plan) => (
        <label key={plan.id} className={styles.planOption}>
          <input {...planField} className={styles.radio} type="radio" value={plan.id} />
          <span className={styles.optionText}>
            <span className={styles.optionName}>{plan.name}</span>{" "}
            <span className={styles.note}>{planTermsText(plan)}</span>
          </span>
        </label>
      ))}
    </div>
  );
}

function renewStartHint(preview: UseQueryResult<RenewalPreviewView> | null): string {
  if (preview === null) return "Se calcula al elegir el plan.";
  if (preview.isPending) return "Calculando fechas…";
  if (!preview.isSuccess) return "";
  const start = formatDate(preview.data.start_date);
  return preview.data.current_end_date === null ? `Empieza el ${start}.` : `Empieza el ${start}, al día siguiente de que termine la actual.`;
}

function PreviewError({ preview }: { preview: UseQueryResult<RenewalPreviewView> | null }) {
  if (preview === null || !preview.isError) return null;
  return (
    <p className={styles.fieldError}>
      {SELL_MESSAGES.previewFailed}{" "}
      <Button variant="ghost" onClick={() => void preview.refetch()}>
        Reintentar
      </Button>
    </p>
  );
}

export function PlanStep({ plans, planField, startField, planError, startError, renew, preview, dates, planGroupRef }: PlanStepProps) {
  const planErrorId = "sell-plan-error";
  const renewHint = renew ? renewStartHint(preview) : "";
  return (
    <section className={styles.box} aria-labelledby="sell-plan-title">
      <h2 id="sell-plan-title" className={styles.h2}>
        2 · Plan y fechas
      </h2>
      <fieldset ref={planGroupRef} className={styles.fieldset} aria-describedby={planError ? planErrorId : undefined}>
        <legend className={styles.srOnly}>Plan</legend>
        <PlanOptions plans={plans} planField={planField} />
      </fieldset>
      {planError ? (
        <p id={planErrorId} className={styles.fieldError}>
          {planError}
        </p>
      ) : null}
      <div className={styles.grid3}>
        {renew ? (
          <Field label="Inicio" name="start-preview" readOnly value={dates.start ? formatDate(dates.start) : EMPTY_VALUE} {...(renewHint ? { hint: renewHint } : {})} />
        ) : (
          <Field label="Inicio" required type="date" error={startError} {...startField} />
        )}
        <Field label="Fin (calculado)" name="end-preview" readOnly value={dates.end ? formatDate(dates.end) : EMPTY_VALUE} {...(dates.end ? { hint: `Vale ${untilText(dates.end)}.` } : {})} />
        <Field label="Precio pactado" name="price-preview" readOnly value={dates.price === null ? EMPTY_VALUE : formatCop(dates.price)} />
      </div>
      <PreviewError preview={preview} />
      <p className={styles.note}>El precio es el del plan y queda guardado en la membresía: si después cambia el plan, lo vendido no cambia.</p>
    </section>
  );
}
