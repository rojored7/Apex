// S3-F6 · US-100 (front): el resumen del mes de /pagos (Pagos.html, la fila de KPI de arriba).
// - Mes elegido con `?mes=AAAA-MM` en la URL (conserva los demás parámetros); sin él, o con uno mal
//   formado, el mes actual de Bogotá (no el del equipo: a las 10 p. m. del 31 de octubre en Bogotá ya
//   es noviembre en UTC). El mes siempre viaja explícito: GET /payments/summary?month=AAAA-MM (D23).
// - KpiCard: total del mes con los pagos válidos, uno por medio con la etiqueta de Configuración
//   (D24) y "$ 0" cuando es cero, y el contador de anulados (no suman al total).
// - Carga y error por tarjeta (KpiCard, con Reintentar); un 422 `month` (fuera de 2020 a 2100) se
//   explica con el rango en vez de tarjetas en error.
// DESIGN-GAP: Pagos.html no dibuja el selector de mes ni la tarjeta de anulados; el título de la
// tarjeta del total lleva el año ("Octubre 2026 · total"; el diseño escribe "Octubre · total").
import { useId, useState } from "react";
import { useSearchParams } from "react-router";
import { formatCount, formatMonth, todayBogota } from "../../../core/i18n/format";
import { usePaymentMethodOptions } from "../../../shared/data/paymentMethods";
import { Field } from "../../../shared/ui/Field";
import { KpiCard } from "../../../shared/ui/KpiCard";
import { usePaymentsSummary } from "../api";
import { isMonthOutOfRange, SUMMARY_MESSAGES } from "../paymentErrors";
import styles from "./MonthSummary.module.css";

export const MONTH_PARAM = "mes";
export const SUMMARY_TITLE = "Resumen del mes";

/** "AAAA-MM" con un mes del 01 al 12; el año lo valida el api (2020 a 2100, D23). */
const MONTH_PATTERN = /^\d{4}-(0[1-9]|1[0-2])$/;

/** El mes actual en Bogotá ("AAAA-MM"). */
export function currentMonthBogota(): string {
  return todayBogota().slice(0, 7);
}

/** El mes de la URL si está bien formado; si no, el actual de Bogotá. */
export function monthFromSearch(search: URLSearchParams): string {
  const raw = search.get(MONTH_PARAM) ?? "";
  return MONTH_PATTERN.test(raw) ? raw : currentMonthBogota();
}

/**
 * Revisión S3-F6 (M3): qué hacer con lo que llega del campo. Donde `type="month"` no existe (Firefox y
 * Safari de escritorio lo pintan como texto) llegan textos a medias: se guardan como borrador sin
 * tocar la URL. Un mes completo se confirma en la URL; el campo vacío vuelve al mes actual.
 */
export type MonthInputChange = { kind: "commit"; month: string } | { kind: "clear" } | { kind: "draft"; text: string };

export function monthInputChange(text: string): MonthInputChange {
  const value = text.trim();
  if (value === "") return { kind: "clear" };
  return MONTH_PATTERN.test(value) ? { kind: "commit", month: value } : { kind: "draft", text };
}

const capitalize = (text: string): string => text.charAt(0).toLocaleUpperCase("es-CO") + text.slice(1);

const validCountText = (count: number): string => (count === 1 ? "1 pago válido" : `${formatCount(count)} pagos válidos`);

export function MonthSummary() {
  const [searchParams, setSearchParams] = useSearchParams();
  const month = monthFromSearch(searchParams);
  const summary = usePaymentsSummary(month);
  const { methods } = usePaymentMethodOptions();
  const headingId = useId();
  const [draft, setDraft] = useState<string | null>(null);
  const { data } = summary;
  const outOfRange = isMonthOutOfRange(summary.error);
  const cardState = {
    isLoading: summary.isLoading,
    error: summary.isError,
    onRetry: () => {
      void summary.refetch();
    },
  };

  return (
    <section aria-labelledby={headingId} className={styles.summary}>
      <div className={styles.header}>
        <h2 id={headingId} className={styles.title}>
          {SUMMARY_TITLE}
        </h2>
        <div className={styles.month}>
          <Field
            label="Mes"
            name={MONTH_PARAM}
            type="month"
            min="2020-01"
            max="2100-12"
            placeholder="AAAA-MM"
            pattern="[0-9]{4}-[0-9]{2}"
            value={draft ?? month}
            onChange={(event) => {
              const change = monthInputChange(event.target.value);
              if (change.kind === "draft") {
                setDraft(change.text);
                return;
              }
              setDraft(null);
              setSearchParams((previous) => {
                const params = new URLSearchParams(previous);
                if (change.kind === "commit") params.set(MONTH_PARAM, change.month);
                else params.delete(MONTH_PARAM);
                return params;
              });
            }}
          />
        </div>
      </div>
      {outOfRange ? (
        <p role="alert" className={styles.error}>
          {SUMMARY_MESSAGES.monthOutOfRange}
        </p>
      ) : (
        <div className={styles.cards}>
          <KpiCard
            label={`${capitalize(formatMonth(month))} · total`}
            kind="money"
            value={data?.total_cop}
            {...(data ? { note: validCountText(data.payments_count) } : {})}
            {...cardState}
          />
          {methods.map((method) => (
            <KpiCard key={method.code} label={method.label} kind="money" value={data?.by_method[method.code]} {...cardState} />
          ))}
          <KpiCard label="Anulados" kind="count" value={data?.voided_count} note="No suman al total" {...cardState} />
        </div>
      )}
    </section>
  );
}
