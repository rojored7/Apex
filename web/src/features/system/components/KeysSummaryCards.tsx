// S6-F2 · US-143 (Llaves.html, cuatro tarjetas y la línea del proveedor): el resumen sale de `summary` de
// GET /crypto/keys (S6-D13) y de las llaves activas del inventario completo (limit 200, corto).
// - Llaves activas, Recifrados en curso y Operaciones hoy: `active_count`, `running_jobs` y `operations_today`.
// - «Proveedor activo: <nombre> · <estado>»; con el custodio sellado o inalcanzable se dice en una alerta de
//   texto (no solo con color) y qué hacer.
// DESIGN-GAP: «Rotación vencida o próxima (30 días)». Nada en el api define el plazo de rotación (no hay
// «Límite»; solo `age_days`), así que no se puede contar qué está vencido: la tarjeta lleva el nombre acordado,
// «Rotación vencida (30 días)», y muestra la antigüedad (`age_days`) de la llave activa más antigua, sin afirmar
// que algo venció (BRECHAS 14.15). Cuando el api publique la política se cambia por el conteo.
import { HTTP_FORBIDDEN, HTTP_TOO_MANY } from "../../../core/api/status";
import { useKeysSummary } from "../api";
import { providerNames, PROVIDER_STATE_LABELS } from "../cryptoLabels";
import { keysListError } from "../keysErrors";
import { KpiCard } from "../../../shared/ui/KpiCard";
import type { KeysPageView } from "../schemas";
import styles from "./KeysSummaryCards.module.css";

const ROTATION_ALERT_DAYS = 30;
export const ROTATION_LABEL = `Rotación vencida (${String(ROTATION_ALERT_DAYS)} días)`;

/** `age_days` de la llave activa más antigua; 0 si no hay activas. */
export function oldestActiveAge(page: KeysPageView): number {
  return page.items.filter((key) => key.state === "active").reduce((oldest, key) => Math.max(oldest, key.age_days), 0);
}

function custodyAlert(state: KeysPageView["summary"]["provider"]["state"]): string | null {
  if (state === "sealed") return "El custodio de llaves está sellado. Los datos cifrados no se pueden leer hasta desellarlo: sigue la guía de OpenBao del RUNBOOK.";
  if (state === "unreachable") return "El custodio de llaves no responde. Revisa que el servicio esté encendido; mientras tanto los datos cifrados no se pueden leer.";
  return null;
}

export function KeysSummaryCards() {
  const query = useKeysSummary();
  const page = query.data;
  const failed = query.isError ? keysListError(query.error) : null;
  const retry = (): void => {
    void query.refetch();
  };
  const loading = query.isLoading;
  const error = failed !== null && page === undefined;
  // Con 403 o 429 reintentar no sirve (falta permiso o hay que esperar): el mensaje lo dice y no se ofrece el botón.
  const retryable = failed !== null && failed.status !== HTTP_FORBIDDEN && failed.status !== HTTP_TOO_MANY;
  const onRetry = retryable ? retry : undefined;
  const alertText = page ? custodyAlert(page.summary.provider.state) : null;

  return (
    <section aria-label="Resumen de llaves" className={styles.root}>
      {page ? (
        <p className={styles.provider}>
          {`Proveedor activo: ${providerNames(page.summary.provider.names)} · ${PROVIDER_STATE_LABELS[page.summary.provider.state]}`}
        </p>
      ) : null}
      {error ? (
        <p role="alert" className={styles.alert}>
          {failed.message}
        </p>
      ) : null}
      {alertText ? (
        <p role="alert" className={styles.alert}>
          {alertText}
        </p>
      ) : null}
      <div className={styles.grid}>
        <KpiCard label="Llaves activas" kind="count" value={page?.summary.active_count} isLoading={loading} error={error} {...(onRetry ? { onRetry } : {})} />
        <KpiCard
          label={ROTATION_LABEL}
          kind="count"
          value={page ? oldestActiveAge(page) : undefined}
          note="días la llave activa más antigua"
          isLoading={loading}
          error={error}
          {...(onRetry ? { onRetry } : {})}
        />
        <KpiCard label="Recifrados en curso" kind="count" value={page?.summary.running_jobs} isLoading={loading} error={error} {...(onRetry ? { onRetry } : {})} />
        <KpiCard label="Operaciones hoy" kind="count" value={page?.summary.operations_today} isLoading={loading} error={error} {...(onRetry ? { onRetry } : {})} />
      </div>
    </section>
  );
}
