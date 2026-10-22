// S2-F4a · US-045: lógica común del cambio de contraseña ("Mi cuenta" y /cambiar-clave).
// React Hook Form + Zod (adaptador propio, S2-D22) sobre useChangePassword.
// - Un 422 con `field` del api se marca en su campo y le da el foco.
// - Cualquier otro error queda como mensaje general ("qué pasó y qué hacer").
// - Al terminar limpia el formulario y la mutación (las contraseñas no quedan en memoria) y
//   avisa con onSuccess.
import { useState, type BaseSyntheticEvent } from "react";
import { useForm, type UseFormReturn } from "react-hook-form";
import { zodResolver } from "../../../shared/lib/zodResolver";
import { passwordErrorMessage, passwordFieldError, useChangePassword } from "../api";
import { changePasswordSchema, type ChangePasswordForm } from "../schemas";

const EMPTY: ChangePasswordForm = { currentPassword: "", newPassword: "", confirmPassword: "" };

export interface ChangePasswordFormApi {
  form: UseFormReturn<ChangePasswordForm>;
  submit: (event?: BaseSyntheticEvent) => Promise<void>;
  pending: boolean;
  generalError: string | null;
  /** Vacía los campos, el error y la mutación (al cerrar el panel). */
  reset: () => void;
}

export function useChangePasswordForm(onSuccess: () => void): ChangePasswordFormApi {
  const mutation = useChangePassword();
  const form = useForm<ChangePasswordForm>({ resolver: zodResolver(changePasswordSchema), defaultValues: EMPTY });
  const [generalError, setGeneralError] = useState<string | null>(null);

  const reset = (): void => {
    form.reset(EMPTY);
    mutation.reset();
    setGeneralError(null);
  };

  const submit = form.handleSubmit(async (values) => {
    setGeneralError(null);
    try {
      await mutation.mutateAsync({ currentPassword: values.currentPassword, newPassword: values.newPassword });
    } catch (error) {
      const fieldError = passwordFieldError(error);
      if (fieldError) {
        form.setError(fieldError.field, { type: "server", message: fieldError.message }, { shouldFocus: true });
        return;
      }
      setGeneralError(passwordErrorMessage(error));
      return;
    }
    reset();
    onSuccess();
  });

  return { form, submit, pending: mutation.isPending, generalError, reset };
}
