// S4A-F1 · US-104 (front; S4A-D31, S4A-D35, S4A-D58): "Verificar ahora" y la última verificación.
// - La línea de estado dice cuándo terminó la última verificación (hora de Bogotá) y cómo salió.
// - POST /audit/verify por useVerifyChain (useSensitiveMutation): 200 da el resultado; 202 deja la
//   verificación en segundo plano y la pantalla sondea GET /audit/verify/last cada VERIFY_POLL_MS
//   hasta que `finished_at` cambia, con tope de VERIFY_MAX_MS (900 s del api): después dice que no
//   terminó y deja de preguntar. Un 409 (otra verificación en curso) también espera su resultado.
// - Cadena rota: "Cadena rota en el registro seq X" con enlace a `?seq=X` sin perder los filtros.
// - S6-F1 · US-142: la verificación suma las firmas (Ed25519, S6-D62): "Firmas verificadas: N de M válidas",
//   la última firma válida y, si una falla, "Firma alterada en el registro seq X" con enlace. La
//   verificación no depende del custodio (S6-D81): con el custodio sellado sigue completa y solo el
//   aviso global (CustodyNotice) informa del sellado.
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { Link, useLocation } from "react-router";
import { formatCount, formatDateTime } from "../../../core/i18n/format";
import { Button } from "../../../shared/ui/Button";
import { SIGNATURE_LATEST_KEY, VERIFY_MAX_MS, lastVerificationPollLimit, useLastVerification, useVerifyChain } from "../api";
import { AUDIT_MESSAGES, isVerificationRunning, verifyErrorMessage } from "../auditErrors";
import { SEQ_PARAM } from "../auditFilters";
import type { VerifyResultView } from "../schemas";
import { signatureDetail } from "./SignatureStatus";
import styles from "./VerifyChainButton.module.css";

export const VERIFY_TIMEOUT_MESSAGE = "La verificación no terminó; vuelve a intentarlo.";
export const VERIFY_RUNNING_MESSAGE = "Verificando la cadena en segundo plano…";
export const VERIFY_POLL_FAILED_MESSAGE = "No pudimos consultar el resultado de la verificación; vuelve a intentarlo en un momento.";
const FIRST_VERIFICATION_NOTE = "Sin verificación anterior que comparar.";

type Phase =
  | { kind: "idle" }
  | { kind: "polling"; baseline: string | null; maxUpdates: number; message: string }
  | { kind: "done"; result: VerifyResultView; first: boolean }
  | { kind: "failed"; message: string };

type SignedResult = VerifyResultView & { signatures_checked: number; signatures_valid: number };

function hasSignatures(result: VerifyResultView): result is SignedResult {
  return typeof result.signatures_checked === "number" && typeof result.signatures_valid === "number";
}

function lastLine(last: VerifyResultView | null | undefined, failed: boolean): string {
  if (failed) return "No pudimos consultar la última verificación; puedes verificar ahora.";
  if (last === undefined) return "Consultando la última verificación…";
  if (last === null) return "Todavía no se ha verificado la cadena.";
  const outcome = last.ok ? `íntegra, ${formatCount(last.rows_checked)} filas` : `rota en el registro seq ${String(last.broken_at_seq ?? "")}`;
  const signatures = hasSignatures(last) ? ` · firmas ${String(last.signatures_valid)} de ${String(last.signatures_checked)}` : "";
  return `Última verificación: ${formatDateTime(last.finished_at)} · ${outcome}${signatures}`;
}

function seqHref(search: string, seq: number): string {
  const next = new URLSearchParams(search);
  next.set(SEQ_PARAM, String(seq));
  return `?${next.toString()}`;
}

function SignaturesText({ result, search }: { result: VerifyResultView; search: string }) {
  const invalid = result.first_invalid_signature_seq ?? null;
  const validAt = result.last_valid_signature_seq != null && result.last_valid_signature_at && result.last_valid_signature_algorithm;
  return (
    <>
      {hasSignatures(result) ? (
        <p className={invalid === null ? styles.ok : styles.broken}>{`Firmas verificadas: ${String(result.signatures_valid)} de ${String(result.signatures_checked)} válidas`}</p>
      ) : null}
      {invalid !== null ? (
        <p className={styles.broken}>
          Firma alterada en el registro seq {String(invalid)}. <Link to={seqHref(search, invalid)}>Ver el registro {String(invalid)}</Link>
        </p>
      ) : null}
      {validAt ? (
        <p className={styles.note}>
          Última firma válida: {signatureDetail(result.last_valid_signature_seq ?? 0, result.last_valid_signature_at ?? "", result.last_valid_signature_algorithm ?? "")}
        </p>
      ) : null}
    </>
  );
}

function ResultText({ result, first, search }: { result: VerifyResultView; first: boolean; search: string }) {
  if (!result.ok && result.broken_at_seq !== null) {
    return (
      <>
        <p className={styles.broken}>
          Cadena rota en el registro seq {String(result.broken_at_seq)}. <Link to={seqHref(search, result.broken_at_seq)}>Ver el registro {String(result.broken_at_seq)}</Link>
        </p>
        <SignaturesText result={result} search={search} />
      </>
    );
  }
  return (
    <>
      {result.ok || result.first_invalid_signature_seq == null ? (
        <p className={styles.ok}>{`Cadena íntegra: ${formatCount(result.rows_checked)} filas verificadas (${formatDateTime(result.finished_at)})`}</p>
      ) : null}
      <SignaturesText result={result} search={search} />
      {first ? <p className={styles.note}>{FIRST_VERIFICATION_NOTE}</p> : null}
    </>
  );
}

function PhaseText({ phase, search }: { phase: Phase; search: string }) {
  if (phase.kind === "polling") return <p className={styles.note}>{phase.message}</p>;
  if (phase.kind === "done") return <ResultText result={phase.result} first={phase.first} search={search} />;
  if (phase.kind === "failed") return <p className={styles.error}>{phase.message}</p>;
  return null;
}

/**
 * Mientras se espera: llega una verificación terminada distinta de la de antes (ese es el resultado),
 * o la consulta falla (revisión de seguridad de F1, MEDIUM 1: el sondeo se frena y se dice).
 */
function resolvePhase(phase: Phase, last: VerifyResultView | null | undefined, lastFailed: boolean): Phase {
  if (phase.kind !== "polling") return phase;
  if (lastFailed) return { kind: "failed", message: VERIFY_POLL_FAILED_MESSAGE };
  if (!last || last.finished_at === phase.baseline) return phase;
  return { kind: "done", result: last, first: phase.baseline === null };
}

export function VerifyChainButton() {
  const [phase, setPhase] = useState<Phase>({ kind: "idle" });
  const queryClient = useQueryClient();
  const waiting = phase.kind === "polling" ? phase : null;
  const last = useLastVerification({ polling: waiting !== null, baseline: waiting?.baseline ?? null, ...(waiting ? { maxUpdates: waiting.maxUpdates } : {}) });
  const shown = resolvePhase(phase, last.data, last.isError);
  const polling = shown.kind === "polling";
  const finished = shown.kind === "done";

  // Una verificación terminada (también la que llega por sondeo) puede cambiar el estado de la firma.
  useEffect(() => {
    if (finished) void queryClient.invalidateQueries({ queryKey: SIGNATURE_LATEST_KEY });
  }, [finished, queryClient]);
  const verify = useVerifyChain();
  const { search } = useLocation();
  const busy = useRef(false);

  // Tope del sondeo (S4A-D58): después de VERIFY_MAX_MS la verificación no terminó y se deja de preguntar.
  useEffect(() => {
    if (!polling) return;
    const timer = setTimeout(() => {
      setPhase({ kind: "failed", message: VERIFY_TIMEOUT_MESSAGE });
    }, VERIFY_MAX_MS);
    return () => {
      clearTimeout(timer);
    };
  }, [polling]);

  const start = async (): Promise<void> => {
    if (busy.current) return;
    busy.current = true;
    const previous = last.data ?? null;
    setPhase({ kind: "idle" });
    try {
      const outcome = await verify.mutateAsync();
      if (outcome.kind === "done") setPhase({ kind: "done", result: outcome.result, first: previous === null });
      else setPhase({ kind: "polling", baseline: outcome.last?.finished_at ?? null, maxUpdates: lastVerificationPollLimit(queryClient), message: VERIFY_RUNNING_MESSAGE });
    } catch (error) {
      setPhase(
        isVerificationRunning(error)
          ? { kind: "polling", baseline: previous?.finished_at ?? null, maxUpdates: lastVerificationPollLimit(queryClient), message: AUDIT_MESSAGES.verifyRunning }
          : { kind: "failed", message: verifyErrorMessage(error) },
      );
    } finally {
      busy.current = false;
    }
  };

  const pending = verify.isPending;
  return (
    <section className={styles.box} aria-label="Integridad de la cadena">
      <p className={styles.note}>{lastLine(last.data, last.isError && last.data === undefined)}</p>
      <div className={styles.row}>
        <Button
          variant="secondary"
          disabled={pending || polling}
          onClick={() => {
            void start();
          }}
        >
          {pending ? "Verificando…" : "Verificar ahora"}
        </Button>
      </div>
      <div role="status" className={styles.result}>
        <PhaseText phase={shown} search={search} />
      </div>
    </section>
  );
}
