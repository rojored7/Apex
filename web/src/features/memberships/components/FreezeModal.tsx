// S3-F5 · US-089 (front): congelar una membresía (Membresias.html, "Modal · Congelar membresía de …";
// DESIGN.md regla 3: congelar es un modal con confirmación). Admin y coach (`memberships.freeze`, Q7);
// el api vuelve a verificar.
// - React Hook Form + Zod (freezeFormSchema): "Desde" (hoy en Bogotá por defecto) y "Hasta"; "Hasta"
//   no puede ser anterior a "Desde". Bajo las fechas, la vista previa en vivo "Son N días; la
//   membresía terminará el …" (freezePreview, RN-07) y la nota de Configuración del diseño.
// - Un solo envío a la vez ("Congelando…"); mientras tanto no se cierra (ni con Escape).
// - 409 de estado y de límites como aviso del modal (freezeAlert; `freeze_days_exceeded` dice los
//   días que quedan, del mensaje del api); 422 bajo su fecha y con foco (freezeFieldError).
// - Al salir bien avisa al padre con el fin nuevo del 200 (manda el servidor). La mutación lleva
//   fechas: `gcTime: 0`, `reset()` al terminar y al cerrar (S3-D52).
// DESIGN-GAP: el diseño dibuja un campo "Motivo" (Viaje, lesión…); FreezeIn no lo recibe (D14), así
// que no se pinta.
import { useId, useRef, useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { useCan } from "../../../core/auth/useCan";
import { todayBogota } from "../../../core/i18n/format";
import { zodResolver } from "../../../shared/lib/zodResolver";
import { Button } from "../../../shared/ui/Button";
import { Field } from "../../../shared/ui/Field";
import { Modal } from "../../../shared/ui/Modal";
import { useFreezeMembership } from "../api";
import { freezePreview } from "../lib/rules";
import { freezeAlert, freezeFieldError } from "../membershipErrors";
import { freezeFormSchema, toFreezeBody, type FreezeFormValues } from "../schemas";
import styles from "./MembershipModals.module.css";

export interface FreezeTarget {
  id: string;
  member_name: string;
  /** Fin actual de la membresía ("AAAA-MM-DD"), para la vista previa. */
  end_date: string;
}

export interface FreezeModalProps {
  /** La membresía a congelar; null cierra el modal. */
  membership: FreezeTarget | null;
  onClose: () => void;
  /** La membresía quedó congelada; `newEndDate` es el fin que devolvió el api. */
  onFrozen: (target: FreezeTarget, newEndDate: string) => void;
}

export const FREEZE_NOTE = "La fecha de fin se corre los mismos días. Máximo de días congelados por membresía: lo define Configuración.";

const resolver = zodResolver(freezeFormSchema);

export const freezeTitle = (memberName: string): string => `Congelar la membresía de ${memberName}`;

function FreezeForm({ target, onClose, onFrozen }: { target: FreezeTarget; onClose: () => void; onFrozen: FreezeModalProps["onFrozen"] }) {
  const formId = useId();
  const { freeze, isPending, reset } = useFreezeMembership();
  const form = useForm<FreezeFormValues>({ resolver, defaultValues: { frozenFrom: todayBogota(), frozenTo: "" } });
  const {
    register,
    control,
    formState: { errors },
  } = form;
  // useWatch y no form.watch: el compilador de React no puede memorizar watch() (react-hooks).
  const frozenFrom = useWatch({ control, name: "frozenFrom" });
  const frozenTo = useWatch({ control, name: "frozenTo" });
  const preview = freezePreview(frozenFrom, frozenTo, target.end_date);
  const [alert, setAlert] = useState<string | null>(null);
  // Un segundo envío (doble clic o Enter) mientras el primero sigue en curso no sale.
  const inFlight = useRef(false);

  // Revisión S3-F5 (M3): el aviso de un intento anterior se quita al corregir una fecha.
  const clearAlert = (): void => {
    setAlert(null);
  };

  const close = (): void => {
    if (inFlight.current) return;
    reset();
    onClose();
  };

  const save = async (values: FreezeFormValues): Promise<void> => {
    if (inFlight.current) return;
    inFlight.current = true;
    setAlert(null);
    try {
      const frozen = await freeze({ id: target.id, ...toFreezeBody(values) });
      onFrozen(target, frozen.end_date);
    } catch (error) {
      const field = freezeFieldError(error);
      if (field) form.setError(field.path, { type: "server", message: field.message }, { shouldFocus: true });
      else setAlert(freezeAlert(error));
    } finally {
      inFlight.current = false;
    }
  };

  return (
    <Modal
      open
      title={freezeTitle(target.member_name)}
      busy={isPending}
      onClose={close}
      actions={
        <>
          <Button variant="secondary" onClick={close} disabled={isPending}>
            Volver
          </Button>
          <Button type="submit" form={formId} loading={isPending}>
            {isPending ? "Congelando…" : "Congelar"}
          </Button>
        </>
      }
    >
      <form id={formId} className={styles.form} noValidate aria-label={freezeTitle(target.member_name)} onSubmit={(event) => void form.handleSubmit(save)(event)}>
        <div className={styles.dates}>
          <Field label="Desde" type="date" required error={errors.frozenFrom?.message} {...register("frozenFrom", { onChange: clearAlert })} />
          <Field label="Hasta" type="date" required {...(frozenFrom ? { min: frozenFrom } : {})} error={errors.frozenTo?.message} {...register("frozenTo", { onChange: clearAlert })} />
        </div>
        <p className={styles.preview} aria-live="polite">
          {preview ? preview.text : ""}
        </p>
        <p className={styles.note}>{FREEZE_NOTE}</p>
        {alert ? (
          <p role="alert" className={styles.error}>
            {alert}
          </p>
        ) : null}
      </form>
    </Modal>
  );
}

export function FreezeModal({ membership, onClose, onFrozen }: FreezeModalProps) {
  const canFreeze = useCan("memberships.freeze");
  if (!canFreeze || membership === null) return null;
  // La clave monta un formulario nuevo por membresía: cada apertura empieza limpia.
  return <FreezeForm key={membership.id} target={membership} onClose={onClose} onFrozen={onFrozen} />;
}
