// S6-F4 · US-149: «4 · Autorización de datos (Ley 1581)» del alta y la edición del socio.
// - La casilla (la registra quien monta la sección con register("data_consent")): nunca empieza marcada.
// - Con la casilla marcada: la fecha de aceptación «ahora» en hora de Bogotá y la versión vigente de la
//   política, las dos de SOLO LECTURA. No viajan: las fija el api (data_consent_at y la versión que copia
//   de settings/privacy, S6-C3). La versión sale de GET /settings/privacy (solo admin): publicada, «versión
//   no registrada» si no hay política, o un texto neutro si no se puede leer (coach).
// - Documento firmado opcional (PDF, JPEG o PNG, 5 MB): el formulario lo sube como kind=consent tras guardar.
// - Con la autorización ya registrada (edición) muestra su texto en lugar de la casilla.
import { useEffect, useMemo, useRef, useState, type ChangeEvent } from "react";
import type { UseFormRegisterReturn } from "react-hook-form";
import { formatDateTime } from "../../../core/i18n/format";
import { usePrivacyVersion } from "../../../shared/data/privacyVersion";
import { Button } from "../../../shared/ui/Button";
import { Field } from "../../../shared/ui/Field";
import { CONSENT_FILE_TYPES, fileError } from "../schemas";
import styles from "./ConsentSection.module.css";

export const CONSENT_LEGEND = "4 · Autorización de datos (Ley 1581)";
export const VERSION_NOT_REGISTERED = "versión no registrada";
export const VERSION_ON_SAVE = "Se registra la versión vigente al guardar";
const FILE_HINT = "PDF, JPEG o PNG, hasta 5 MB. Se sube al guardar.";
const CHECK_HINT_ID = "member-consent-hint";
const CHECK_ERROR_ID = "member-consent-error";

export interface ConsentSectionProps {
  /** register("data_consent") del formulario. */
  checkbox: UseFormRegisterReturn;
  /** Estado actual de la casilla (watch). */
  accepted: boolean;
  /** Edición con la autorización ya registrada: su texto reemplaza a la casilla. */
  registeredText: string | null;
  checkboxLabel: string;
  checkboxHint: string;
  /** Error bajo la casilla (por ejemplo el 422 de data_consent_at). */
  checkboxError?: string | undefined;
  file: File | null;
  onFileChange: (file: File | null) => void;
  /** Error de Zod del archivo. */
  fileErrorText?: string | undefined;
}

export function ConsentSection({ checkbox, accepted, registeredText, checkboxLabel, checkboxHint, checkboxError, file, onFileChange, fileErrorText }: ConsentSectionProps) {
  const privacy = usePrivacyVersion(accepted && registeredText === null);
  const [localError, setLocalError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const checkRef = useRef<HTMLInputElement | null>(null);
  // Un error del servidor bajo la casilla (el 422 de data_consent_at) lleva el foco: el formulario es largo.
  useEffect(() => {
    if (checkboxError) checkRef.current?.focus();
  }, [checkboxError]);
  // «Ahora» se toma al marcar la casilla y queda fijo mientras siga marcada (no corre un reloj).
  const acceptedAt = useMemo(() => (accepted ? formatDateTime(new Date().toISOString()) : ""), [accepted]);

  const versionText = privacy.status === "ready" ? (privacy.version ?? VERSION_NOT_REGISTERED) : privacy.status === "unavailable" ? VERSION_ON_SAVE : "Consultando…";

  const handleFile = (event: ChangeEvent<HTMLInputElement>): void => {
    const picked = event.target.files?.[0] ?? null;
    if (picked === null) {
      setLocalError(null);
      onFileChange(null);
      return;
    }
    const problem = fileError("consent", picked);
    setLocalError(problem);
    onFileChange(problem === null ? picked : null);
  };

  const removeFile = (): void => {
    setLocalError(null);
    if (inputRef.current) inputRef.current.value = "";
    onFileChange(null);
  };

  const describedBy = checkboxError ? `${CHECK_HINT_ID} ${CHECK_ERROR_ID}` : CHECK_HINT_ID;
  return (
    <fieldset className={styles.section}>
      <legend className={styles.legend}>{CONSENT_LEGEND}</legend>
      {registeredText ? (
        <p className={styles.registered}>{registeredText}</p>
      ) : (
        <>
          <label className={styles.check}>
            <input type="checkbox" className={styles.checkbox} aria-describedby={describedBy} aria-invalid={checkboxError ? true : undefined} {...checkbox}
              ref={(element) => {
                checkRef.current = element;
                checkbox.ref(element);
              }}
            />
            <span>{checkboxLabel}</span>
          </label>
          <p id={CHECK_HINT_ID} className={styles.note}>
            {checkboxHint}
          </p>
          {checkboxError ? (
            <p id={CHECK_ERROR_ID} className={styles.error}>
              {checkboxError}
            </p>
          ) : null}
          {accepted ? (
            <div className={styles.grid}>
              <Field label="Fecha de aceptación" name="consent_at_preview" readOnly value={acceptedAt} hint="Hora de Bogotá; la registra el sistema al guardar." />
              <Field label="Versión de la política" name="consent_version_preview" readOnly value={versionText} hint="La fija el sistema; no se edita aquí." />
            </div>
          ) : null}
        </>
      )}
      <div className={styles.file}>
        <Field label="Documento firmado (opcional)" name="consent_file" hint={FILE_HINT} error={localError ?? fileErrorText}>
          {(control) => <input {...control} ref={inputRef} type="file" accept={CONSENT_FILE_TYPES.join(",")} onChange={handleFile} />}
        </Field>
        {file !== null ? (
          <Button variant="secondary" className={styles.remove} onClick={removeFile}>
            Quitar documento
          </Button>
        ) : null}
      </div>
    </fieldset>
  );
}
