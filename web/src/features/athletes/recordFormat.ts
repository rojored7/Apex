// S9-F1 (US-184): un récord del api (SummaryRecordOut) en palabras de la pantalla.
// - recordTitle: «Back Squat 1RM» (RM) o «Helen (benchmark)».
// - recordValue: «85 kg» (RM) o la marca con su nivel: «11:42 RX», «DNF · 18 reps RX+», «14 + 3 Escalado», «102,5 kg RX».
import { LEVEL_LABELS } from "../../shared/data/results";
import { formatLoadKg, formatScore } from "../../shared/data/score";
import type { SummaryRecordView } from "./schemas";

const EMPTY = "—";

export function recordTitle(record: SummaryRecordView): string {
  if (record.kind === "rm") return `${record.movement_name ?? EMPTY} 1RM`;
  return `${record.benchmark_name ?? EMPTY} (benchmark)`;
}

export function recordValue(record: SummaryRecordView): string {
  if (record.kind === "rm") return record.value_g === null ? EMPTY : formatLoadKg(record.value_g);
  const score = formatScore(record.score_type ?? "none", record);
  return record.level === null ? score : `${score} ${LEVEL_LABELS[record.level]}`;
}

export interface RecordOrigin {
  source: "manual" | "derived";
  /** Solo la lista de récords lo trae (RecordOut); el resumen y los RMs no. */
  recorded_by_name?: string | null | undefined;
  result_source?: "desk" | "kiosk" | null | undefined;
}

/** El origen con palabras, nunca solo color: «Manual · quien», «Manual», «Automático del WOD» o «Automático (tablet)». Una sola fuente de texto. */
export function originText(record: RecordOrigin): string {
  if (record.source === "manual") return record.recorded_by_name ? `Manual · ${record.recorded_by_name}` : "Manual";
  return record.result_source === "kiosk" ? "Automático (tablet)" : "Automático del WOD";
}
