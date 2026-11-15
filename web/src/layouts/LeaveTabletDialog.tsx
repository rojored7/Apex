// S7-F4 · S7-D24 (H-2): salir del modo tablet exige la contraseña de la cuenta del dispositivo.
// La verificación la hace quien monta el layout (verifyPassword devuelve el mensaje de error o null); aquí solo se
// pide, se muestra el error y se avisa al padre cuando la contraseña es la correcta.
import { useId, useRef, useState } from "react";
import { Button } from "../shared/ui/Button";
import { Field } from "../shared/ui/Field";
import { Modal } from "../shared/ui/Modal";
import styles from "./GymLayout.module.css";

export interface LeaveTabletDialogProps {
  open: boolean;
  verifyPassword: (password: string) => Promise<string | null>;
  onConfirmed: () => void;
  onClose: () => void;
}

function LeaveContent({ verifyPassword, onConfirmed, onClose }: Omit<LeaveTabletDialogProps, "open">) {
  const formId = useId();
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false);

  const submit = async (): Promise<void> => {
    if (inFlight.current || password === "") return;
    inFlight.current = true;
    setBusy(true);
    setError(null);
    try {
      const failure = await verifyPassword(password);
      if (failure === null) onConfirmed();
      else setError(failure);
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  };

  return (
    <Modal
      open
      title="¿Salir del modo tablet?"
      busy={busy}
      onClose={onClose}
      actions={
        <>
          <Button variant="secondary" size="lg" onClick={onClose} disabled={busy}>
            Volver
          </Button>
          <Button type="submit" form={formId} size="lg" loading={busy} disabled={password === ""}>
            Salir del modo tablet
          </Button>
        </>
      }
    >
      <form
        id={formId}
        onSubmit={(event) => {
          event.preventDefault();
          void submit();
        }}
      >
        <p className={styles.dialogText}>Escribe la contraseña de esta cuenta para volver al panel. Mientras tanto la tablet solo registra llegadas.</p>
        <Field
          label="Contraseña"
          name="tablet-password"
          type="password"
          size="lg"
          required
          autoComplete="off"
          value={password}
          onChange={(event) => {
            setPassword(event.target.value);
          }}
        />
        {error ? (
          <p role="alert" className={styles.dialogError}>
            {error}
          </p>
        ) : null}
      </form>
    </Modal>
  );
}

export function LeaveTabletDialog({ open, ...props }: LeaveTabletDialogProps) {
  // El contenido se monta al abrir: cada apertura empieza con la contraseña vacía.
  return open ? <LeaveContent {...props} /> : null;
}
