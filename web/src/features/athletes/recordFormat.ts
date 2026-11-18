// S9-F1 (US-184): un récord del api (SummaryRecordOut) en palabras de la pantalla.
// - recordTitle: «Back Squat 1RM» (RM) o «Helen (benchmark)».
// - recordValue: «85 kg» (RM) o la marca con su nivel: «11:42 RX», «DNF · 18 reps RX+», «14 + 3 Escalado», «102,5 kg RX».
import { LEVEL_LABELS } from "../../shared/data/results";
import { formatLoadKg, formatScore, isScoreKind } from "../../shared/data/score";
import type { SummaryRecordView } from "./schemas";

const EMPTY = "—";

export function recordTitle(record: SummaryRecordView): string {
  if (record.kind === "rm") return `${record.movement_name ?? EMPTY} 1RM`;
  return `${record.benchmark_name ?? EMPTY} (benchmark)`;
}

export function recordValue(record: SummaryRecordView): string {
  if (record.kind === "rm") return record.value_g === null ? EMPTY : formatLoadKg(record.value_g);
  const score = formatScore(isScoreKind(record.score_type) ? record.score_type : "none", record);
  return record.level === null ? score : `${score} ${LEVEL_LABELS[record.level]}`;
}
