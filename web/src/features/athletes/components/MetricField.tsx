// S9-F1 · US-179 y L-7 (S9-D15, S9-D34, S9-D36): un campo de una medición con «Mostrar».
// - «•••» si el api dice `has_*` y «—» si no. La lista nunca trae un valor: «Mostrar» pide UN campo con POST .../reveal.
// - El claro vive solo en el estado de este componente (como texto ya formateado): no pasa por la caché de TanStack Query
//   (useRevealMetric: gcTime 0 y reset()), ni por el almacenamiento, ni por la URL, ni por un aria-label.
// - Se oculta al pulsar «Ocultar», a los 60 s, al perder la visibilidad de la pestaña, al salir de la página, al volver de una suspensión
//   con el plazo vencido (useTimedReveal) y al desmontar; al desmontar también se cancela el POST en vuelo. Si la respuesta llega con
//   la pestaña oculta, no se muestra. Cada «Mostrar» llama una vez (cada vista queda auditada).
// - 403 de un coach con el socio dado de baja: lo explica (solo un administrador, S9-D34).
import { useEffect, useRef, useState } from "react";
import { useCan } from "../../../core/auth/useCan";
import { formatDate } from "../../../core/i18n/format";
import { formatWeightKg } from "../../../shared/data/score";
import { useTimedReveal } from "../../../shared/hooks/useTimedReveal";
import { Button } from "../../../shared/ui/Button";
import { cx } from "../../../shared/ui/cx";
import { useRevealMetric } from "../api";
import { revealMetricError } from "../athleteErrors";
import type { MetricFieldName } from "../schemas";
import styles from "./MetricField.module.css";

export interface MetricFieldProps {
  memberId: string;
  metricId: string;
  field: MetricFieldName;
  /** El api dice si el campo tiene valor (`has_*`): «•••» o «—». */
  has: boolean;
  /** El socio está dado de baja: su `reveal` solo lo hace un administrador (S9-D34). */
  memberDeleted?: boolean;
  /** La fecha de la medición (`YYYY-MM-DD`): el nombre del botón dice de cuál es, sin ningún valor. */
  measuredOn?: string;
  /** Solo falta la ficha (no se sabe si el socio está de baja): el 403 del reveal no dice «dado de baja» (V7, M11). */
  memberUnknown?: boolean;
}

const MASK = "•••";
const EMPTY = "—";
const FIELD_NAMES: Readonly<Record<MetricFieldName, string>> = { weight_g: "peso", height_cm: "altura", body_fat_pct: "% grasa", notes: "notas" };

type RevealState = { status: "masked" } | { status: "loading" } | { status: "revealed"; text: string } | { status: "error"; message: string };

/** El valor en claro como se lee en pantalla: «61,2 kg», «165 cm», «22 %» o la nota tal cual. */
function displayText(field: MetricFieldName, value: number | string | null): string {
  if (value === null) return EMPTY;
  if (field === "notes") return String(value);
  if (typeof value !== "number") return EMPTY;
  if (field === "weight_g") return formatWeightKg(value);
  return field === "height_cm" ? `${String(value)} cm` : `${String(value)} %`;
}

export function MetricField({ memberId, metricId, field, has, memberDeleted = false, measuredOn, memberUnknown = false }: MetricFieldProps) {
  const canReveal = useCan("athletes.reveal");
  const { mutateAsync } = useRevealMetric(memberId);
  const [state, setState] = useState<RevealState>({ status: "masked" });
  const busy = useRef(false);
  const mounted = useRef(true);
  const request = useRef<AbortController | null>(null);
  const revealed = state.status === "revealed";
  const { arm, disarm } = useTimedReveal(revealed, () => {
    setState({ status: "masked" });
  });

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      // Desmontado: el POST en vuelo se cancela y su respuesta nunca llega a nadie.
      request.current?.abort();
    };
  }, []);

  const show = async (): Promise<void> => {
    if (busy.current) return;
    busy.current = true;
    setState({ status: "loading" });
    try {
      const controller = new AbortController();
      request.current = controller;
      const value = await mutateAsync({ metricId, field, signal: controller.signal });
      if (!mounted.current) return;
      if (document.visibilityState === "hidden") {
        setState({ status: "masked" });
        return;
      }
      setState({ status: "revealed", text: displayText(field, value) });
      arm();
    } catch (error) {
      if (mounted.current) setState({ status: "error", message: revealMetricError(error, memberDeleted, memberUnknown) });
    } finally {
      busy.current = false;
    }
  };

  const hide = (): void => {
    disarm();
    setState({ status: "masked" });
  };

  if (!has) return <span className={cx(styles.value, styles.empty)}>{EMPTY}</span>;
  const name = FIELD_NAMES[field];
  return (
    <span className={styles.field}>
      <span className={styles.value} aria-live="polite">
        {state.status === "revealed" ? state.text : MASK}
      </span>
      {canReveal ? (
        <Button
          variant="ghost"
          className={styles.toggle}
          loading={state.status === "loading"}
          aria-label={`${revealed ? "Ocultar" : "Mostrar"} ${name}${measuredOn === undefined ? "" : ` del ${formatDate(measuredOn)}`}`}
          onClick={() => {
            if (revealed) hide();
            else void show();
          }}
        >
          {revealed ? "Ocultar" : "Mostrar"}
        </Button>
      ) : null}
      {state.status === "error" ? (
        <span role="alert" className={styles.error}>
          {state.message}
        </span>
      ) : null}
    </span>
  );
}
