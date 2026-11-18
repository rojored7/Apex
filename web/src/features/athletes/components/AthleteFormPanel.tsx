// V7 (revisión de Fase 4, L7): el esqueleto que comparten los paneles «Registrar medidas» y «Registrar récord».
// - useSaveFlow: un solo guardado a la vez (un Enter repetido no manda dos POST) y el error general del último intento.
// - AthleteFormPanel: SidePanel con el formulario nombrado, el error general en un `role="alert"` y el botón de guardar en el pie;
//   no se cierra mientras guarda.
import { useRef, useState, type ReactNode, type SyntheticEvent } from "react";
import { Button } from "../../../shared/ui/Button";
import { SidePanel } from "../../../shared/ui/SidePanel";
import styles from "./AthletePanel.module.css";

export interface SaveFlow {
  generalError: string | null;
  setGeneralError: (message: string | null) => void;
  /** Corre un intento de guardado: ignora uno que llega con otro en vuelo, limpia el error general y entrega el fallo a `onFail`. */
  run: (attempt: () => Promise<void>, onFail: (error: unknown) => void) => Promise<void>;
}

export function useSaveFlow(): SaveFlow {
  const inFlight = useRef(false);
  const [generalError, setGeneralError] = useState<string | null>(null);
  const run: SaveFlow["run"] = async (attempt, onFail) => {
    if (inFlight.current) return;
    inFlight.current = true;
    setGeneralError(null);
    try {
      await attempt();
    } catch (error) {
      onFail(error);
    } finally {
      inFlight.current = false;
    }
  };
  return { generalError, setGeneralError, run };
}

export interface AthleteFormPanelProps {
  title: string;
  formId: string;
  submitLabel: string;
  isPending: boolean;
  isDirty: boolean;
  generalError: string | null;
  submitDisabled?: boolean;
  onClose: () => void;
  onSubmit: (event: SyntheticEvent<HTMLFormElement>) => void;
  children: ReactNode;
}

export function AthleteFormPanel({ title, formId, submitLabel, isPending, isDirty, generalError, submitDisabled = false, onClose, onSubmit, children }: AthleteFormPanelProps) {
  return (
    <SidePanel
      open
      title={title}
      isDirty={!isPending && isDirty}
      onClose={() => {
        if (!isPending) onClose();
      }}
      footer={
        <Button type="submit" form={formId} loading={isPending} disabled={submitDisabled}>
          {submitLabel}
        </Button>
      }
    >
      <form id={formId} className={styles.form} noValidate aria-label={title} onSubmit={onSubmit}>
        {generalError ? (
          <p className={styles.error} role="alert">
            {generalError}
          </p>
        ) : null}
        {children}
      </form>
    </SidePanel>
  );
}
