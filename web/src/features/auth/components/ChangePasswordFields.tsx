// S2-F4a · US-045: los tres campos del cambio de contraseña (actual, nueva y su repetición),
// con la política a la vista. Los usan "Mi cuenta" (panel) y /cambiar-clave (página).
import type { UseFormReturn } from "react-hook-form";
import { Field } from "../../../shared/ui/Field";
import { PASSWORD_MESSAGES, type ChangePasswordForm } from "../schemas";

export interface ChangePasswordFieldsProps {
  form: UseFormReturn<ChangePasswordForm>;
  /** El foco arranca en la contraseña actual (página); en el panel lo maneja el SidePanel. */
  autoFocus?: boolean;
}

/** `error` solo cuando hay mensaje (exactOptionalPropertyTypes). */
const fieldError = (message: string | undefined): { error?: string } => (message ? { error: message } : {});

export function ChangePasswordFields({ form, autoFocus = false }: ChangePasswordFieldsProps) {
  const {
    register,
    formState: { errors },
  } = form;
  return (
    <>
      <Field
        label="Contraseña actual"
        type="password"
        autoComplete="current-password"
        required
        autoFocus={autoFocus}
        {...fieldError(errors.currentPassword?.message)}
        {...register("currentPassword")}
      />
      <Field
        label="Contraseña nueva"
        type="password"
        autoComplete="new-password"
        required
        hint={PASSWORD_MESSAGES.policy}
        {...fieldError(errors.newPassword?.message)}
        {...register("newPassword")}
      />
      <Field
        label="Repite la contraseña nueva"
        type="password"
        autoComplete="new-password"
        required
        {...fieldError(errors.confirmPassword?.message)}
        {...register("confirmPassword")}
      />
    </>
  );
}
