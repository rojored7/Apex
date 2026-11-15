// S7-F4 · S7-D24 (H-2): salir del modo tablet exige la contraseña de la cuenta del dispositivo.
// La verificación la hace quien monta el layout (verifyPassword devuelve el mensaje de error o null); aquí solo se
// pide, se muestra el error y se avisa al padre cuando la contraseña es la correcta.
// S7-V7f (M-8): React Hook Form + Zod como el resto de formularios (regla 6 de la UI). El botón no se deshabilita con el
// campo vacío: enviarlo vacío dice «Escribe la contraseña.» bajo el campo.
import { useId, useRef, useState, type SyntheticEvent } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "../shared/lib/zodResolver";
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

export const PASSWORD_REQUIRED_MESSAGE = "Escribe la contraseña.";

const leaveSchema = z.object({
  password: z.string().min(1, PASSWORD_REQUIRED_MESSAGE),
});
type LeaveForm = z.infer<typeof leaveSchema>;

function LeaveContent({
  verifyPassword,
  onConfirmed,
  onClose,
}: Omit<LeaveTabletDialogProps, "open">) {
  const formId = useId();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false);
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<LeaveForm>({
    resolver: zodResolver(leaveSchema),
    defaultValues: { password: "" },
  });

  const onValid = async ({ password }: LeaveForm) => {
    setBusy(true);
    setError(null);
    try {
      const failure = await verifyPassword(password);
      if (failure === null) onConfirmed();
      else setError(failure);
    } finally {
      setBusy(false);
    }
  };

  // El candado de doble envío vive en el manejador del evento (no en el render): un segundo submit
  // mientras viaja la verificación no hace nada.
  const onSubmit = (event: SyntheticEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (inFlight.current) return;
    inFlight.current = true;
    void handleSubmit(onValid)(event).finally(() => {
      inFlight.current = false;
    });
  };

  return (
    <Modal
      open
      title="¿Salir del modo tablet?"
      busy={busy}
      onClose={onClose}
      actions={
        <>
          <Button
            variant="secondary"
            size="lg"
            onClick={onClose}
            disabled={busy}
          >
            Volver
          </Button>
          <Button type="submit" form={formId} size="lg" loading={busy}>
            Salir del modo tablet
          </Button>
        </>
      }
    >
      <form id={formId} noValidate onSubmit={onSubmit}>
        <p className={styles.dialogText}>
          Escribe la contraseña de esta cuenta para volver al panel. Mientras
          tanto la tablet solo registra llegadas.
        </p>
        <Field
          label="Contraseña"
          type="password"
          size="lg"
          required
          autoComplete="off"
          error={errors.password?.message}
          {...register("password")}
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
