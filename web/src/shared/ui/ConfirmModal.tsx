// US-065 T3: modal de confirmación (Pagos.html "Anular pago", Llaves.html "Rotar llave").
// Pregunta en el título, consecuencia en una frase, motivo opcional u obligatorio, texto
// tecleado opcional (ROTAR, REENVOLVER), "Volver" y la acción con texto explícito.
// Un solo envío por confirmación (bandera en useRef además del estado) y el error del api
// se queda dentro del modal: bajo el motivo si field = "reason", si no en una alerta.
import { useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { isApiError } from "../../core/api/errors";
import { useFocusTrap } from "../hooks/useFocusTrap";
import { Button } from "./Button";
import styles from "./ConfirmModal.module.css";
import { Field } from "./Field";

export interface ConfirmModalProps {
  open: boolean;
  /** La pregunta: "¿Anular este pago?". */
  title: string;
  /** La consecuencia en una frase. */
  consequence: string;
  /** Texto explícito de la acción: "Anular pago", "Dar de baja". */
  confirmLabel: string;
  tone?: "danger" | "primary";
  cancelLabel?: string;
  reasonRequired?: boolean;
  /** Muestra el campo Motivo aunque no sea obligatorio. */
  showReason?: boolean;
  reasonLabel?: string;
  /** Mínimo de caracteres no vacíos del motivo obligatorio (el api solo pide "no vacío"). */
  minReasonLength?: number;
  /** Texto que hay que teclear exacto para habilitar la acción. */
  confirmText?: string;
  /** Hace la mutación; si rechaza, el modal sigue abierto con el error. */
  onConfirm: (reason: string | undefined) => Promise<void> | void;
  onClose: () => void;
}

export const CONFIRM_GENERIC_ERROR = "No se pudo completar la acción. Intenta de nuevo.";

function ConfirmContent({
  title,
  consequence,
  confirmLabel,
  tone = "danger",
  cancelLabel = "Volver",
  reasonRequired = false,
  showReason = reasonRequired,
  reasonLabel = "Motivo",
  minReasonLength = 3,
  confirmText,
  onConfirm,
  onClose,
}: Omit<ConfirmModalProps, "open">) {
  const baseId = useId();
  const titleId = `${baseId}-title`;
  const descriptionId = `${baseId}-description`;
  const [reason, setReason] = useState("");
  const [typed, setTyped] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [reasonError, setReasonError] = useState<string | undefined>(undefined);
  const [formError, setFormError] = useState<string | undefined>(undefined);
  const busy = useRef(false);

  const cancel = (): void => {
    if (!busy.current) onClose();
  };
  const dialogRef = useFocusTrap<HTMLDivElement>(true, { onEscape: cancel });

  const reasonOk = !reasonRequired || reason.trim().length >= minReasonLength;
  const typedOk = confirmText === undefined || typed === confirmText;

  const confirm = async (): Promise<void> => {
    if (busy.current || !reasonOk || !typedOk) return;
    busy.current = true;
    setSubmitting(true);
    setReasonError(undefined);
    setFormError(undefined);
    try {
      await onConfirm(showReason && reason.trim() !== "" ? reason : undefined);
      onClose();
    } catch (error) {
      if (isApiError(error) && error.field === "reason" && showReason) setReasonError(error.message);
      else setFormError(isApiError(error) ? error.message : CONFIRM_GENERIC_ERROR);
    } finally {
      busy.current = false;
      setSubmitting(false);
    }
  };

  return (
    <div className={styles.backdrop}>
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={descriptionId}
        aria-busy={submitting ? true : undefined}
        tabIndex={-1}
        className={styles.modal}
      >
        <h2 id={titleId} className={styles.title}>
          {title}
        </h2>
        <p id={descriptionId} className={styles.consequence}>
          {consequence}
        </p>
        {showReason ? (
          <Field
            label={reasonLabel}
            name="reason"
            required={reasonRequired}
            {...(reasonError ? { error: reasonError } : {})}
          >
            {(control) => (
              <textarea
                {...control}
                rows={3}
                value={reason}
                onChange={(event) => {
                  setReason(event.target.value);
                }}
              />
            )}
          </Field>
        ) : null}
        {confirmText !== undefined ? (
          <Field
            label={`Escribe ${confirmText} para confirmar`}
            name="confirm-text"
            required
            autoComplete="off"
            spellCheck={false}
            value={typed}
            onChange={(event) => {
              setTyped(event.target.value);
            }}
          />
        ) : null}
        {formError ? (
          <p role="alert" className={styles.error}>
            {formError}
          </p>
        ) : null}
        <div className={styles.actions}>
          <Button variant="secondary" onClick={cancel} disabled={submitting}>
            {cancelLabel}
          </Button>
          <Button
            variant={tone === "danger" ? "danger" : "primary"}
            loading={submitting}
            disabled={!reasonOk || !typedOk}
            onClick={() => {
              void confirm();
            }}
          >
            {confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  );
}

export function ConfirmModal({ open, ...props }: ConfirmModalProps) {
  // El contenido se monta al abrir, así cada apertura empieza limpia.
  return open ? createPortal(<ConfirmContent {...props} />, document.body) : null;
}
