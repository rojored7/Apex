// S6-F1 · US-142 (S6-D3, D34, D62, D81): estado de la firma de la cadena, arriba de «Verificar ahora».
// - GET /audit/signatures/latest por useLatestSignature. El contrato ya trae la decisión (`state`,
//   `is_late`, `latest`, `last_valid`): aquí no se reimplementa la regla de las 48 h ni la de la firma.
// - Cuatro estados con StatusTag de texto: Íntegra, Alterada, Firma atrasada y Sin firmas. No hay
//   «no verificable»: la verificación usa la clave pública guardada y no depende del custodio (D81).
// - «Última firma válida: seq N · <fecha de Bogotá> · Ed25519»; la fecha va en hora de Bogotá.
import { formatDateTime } from "../../../core/i18n/format";
import { Button } from "../../../shared/ui/Button";
import { cx } from "../../../shared/ui/cx";
import { StatusTag } from "../../../shared/ui/StatusTag";
import type { SignatureStateView } from "../../../shared/ui/statusLabel";
import { useLatestSignature } from "../api";
import { signatureError } from "../auditErrors";
import type { SignatureInfoView, SignaturesLatestView } from "../schemas";
import styles from "./SignatureStatus.module.css";

export const SIGNATURE_LOADING = "Consultando el estado de la firma…";
export const SIGNATURE_NONE = "Todavía no se ha firmado la cadena.";
export const SIGNATURE_NONE_VALID = "Ninguna firma verificó correctamente.";
export const SIGNATURE_UNVERIFIED = "Pulsa «Verificar ahora» para comprobarla.";

const ED25519 = "Ed25519";

/** El algoritmo tal como lo escribe el diseño: ed25519 y variantes se muestran como «Ed25519». */
export function algorithmLabel(algorithm: string): string {
  return algorithm.toLowerCase().replace(/[^a-z0-9]/g, "") === "ed25519" ? ED25519 : algorithm;
}

/** «seq N · fecha de Bogotá · Ed25519». */
export function signatureDetail(seq: number, at: string, algorithm: string): string {
  return `seq ${String(seq)} · ${formatDateTime(at)} · ${algorithmLabel(algorithm)}`;
}

/** Del contrato a la etiqueta: sin firma, Sin firmas; la alteración manda sobre el atraso. Null: aún sin verificar. */
export function signatureState(data: SignaturesLatestView): SignatureStateView | null {
  if (data.latest === null) return "none";
  if (data.state === "invalid") return "altered";
  if (data.is_late) return "late";
  return data.state === "ok" ? "intact" : null;
}

function validLine(info: SignatureInfoView | null): string {
  return info ? `Última firma válida: ${signatureDetail(info.through_seq, info.signed_at, info.algorithm)}` : SIGNATURE_NONE_VALID;
}

function lineFor(data: SignaturesLatestView): string {
  if (data.latest === null) return SIGNATURE_NONE;
  if (data.state === "none") return `Última firma registrada: ${signatureDetail(data.latest.through_seq, data.latest.signed_at, data.latest.algorithm)}. ${SIGNATURE_UNVERIFIED}`;
  return validLine(data.last_valid);
}

function Body({ data }: { data: SignaturesLatestView }) {
  const state = signatureState(data);
  return (
    <>
      {state ? <StatusTag signature={state} /> : null}
      <p className={styles.line}>{lineFor(data)}</p>
    </>
  );
}

export function SignatureStatus() {
  const signature = useLatestSignature();
  const failure = signature.isError ? signatureError(signature.error) : null;
  return (
    <section className={styles.box} aria-label="Firma de la cadena">
      <h2 className={styles.title}>Firma de la cadena</h2>
      {signature.isPending ? <p className={styles.line}>{SIGNATURE_LOADING}</p> : null}
      {failure ? (
        <>
          <p role="alert" className={cx(styles.line, styles.error)}>
            {failure.message}
          </p>
          {failure.retryable ? (
            <Button
              variant="secondary"
              onClick={() => {
                void signature.refetch();
              }}
            >
              Reintentar
            </Button>
          ) : null}
        </>
      ) : null}
      {signature.data ? <Body data={signature.data} /> : null}
    </section>
  );
}
