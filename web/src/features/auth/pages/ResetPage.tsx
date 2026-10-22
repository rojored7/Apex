// S2-F4a · US-048: /restablecer/:token (Login.html, tarjeta "Nueva contraseña · Activar
// cuenta"). El mismo enlace activa una cuenta nueva o recupera el acceso (S2-D18).
// - Al llegar, history.replaceState saca el token de la barra (no queda en el historial ni
//   en capturas); el token sigue en memoria de esta pantalla. Recargar ya no lo tiene: hay
//   que volver a abrir el enlace.
// - Zod: de 12 a 128 caracteres y la repetición igual. POST /auth/reset { token,
//   new_password } (204, no inicia sesión): va a /login con el aviso de contraseña guardada.
// - 400 invalid_token (usado, vencido, inexistente o de una cuenta bloqueada) y un token mal
//   formado: "El enlace ya no es válido. Pide uno nuevo al administrador."
// DESIGN-GAP: Login.html dice "Guardar y entrar", pero el restablecimiento no abre la sesión
// (S2-D18): el botón dice "Guardar contraseña" y luego se entra desde /login.
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useNavigate, useParams } from "react-router";
import { LOGIN_PATH } from "../../../core/auth/routeAccess";
import { zodResolver } from "../../../shared/lib/zodResolver";
import { Button } from "../../../shared/ui/Button";
import { Field } from "../../../shared/ui/Field";
import { isInvalidLink, passwordErrorMessage, passwordFieldError, PASSWORD_ERRORS, useResetPassword } from "../api";
import styles from "../components/AccessCard.module.css";
import { PASSWORD_MESSAGES, resetSchema, type ResetForm } from "../schemas";
import { LOGIN_NOTICE_PASSWORD_SET } from "../loginNotice";

/** Forma del token del enlace (base64url, de 20 a 200 caracteres como ResetIn del api). */
const TOKEN_PATTERN = /^[A-Za-z0-9_-]{20,200}$/;
const RESET_PREFIX = "/restablecer/";
/** Lo que queda en la barra tras sacar el token. */
export const RESET_BARE_PATH = "/restablecer";


function InvalidLink() {
  return (
    <div className={styles.form}>
      <h1 className={styles.title}>Nueva contraseña</h1>
      <p className={styles.error} role="alert">
        {PASSWORD_ERRORS.invalidLink}
      </p>
      <Link className={styles.link} to={LOGIN_PATH}>
        Ir a iniciar sesión
      </Link>
    </div>
  );
}

export default function ResetPage() {
  const params = useParams();
  const [token] = useState(() => params.token ?? "");
  const [invalid, setInvalid] = useState(() => !TOKEN_PATTERN.test(token));
  const [generalError, setGeneralError] = useState<string | null>(null);
  const navigate = useNavigate();
  const reset = useResetPassword();
  const form = useForm<ResetForm>({ resolver: zodResolver(resetSchema), defaultValues: { newPassword: "", confirmPassword: "" } });
  const {
    register,
    formState: { errors },
  } = form;

  useEffect(() => {
    if (window.location.pathname.startsWith(RESET_PREFIX)) {
      window.history.replaceState(window.history.state, "", RESET_BARE_PATH);
    }
  }, []);

  if (invalid) return <InvalidLink />;

  const submit = form.handleSubmit(async (values) => {
    setGeneralError(null);
    try {
      await reset.mutateAsync({ token, newPassword: values.newPassword });
    } catch (error) {
      if (isInvalidLink(error)) {
        setInvalid(true);
        return;
      }
      const field = passwordFieldError(error);
      if (field?.field === "newPassword") {
        form.setError("newPassword", { type: "server", message: field.message }, { shouldFocus: true });
        return;
      }
      setGeneralError(passwordErrorMessage(error));
      return;
    }
    reset.reset();
    void navigate(LOGIN_PATH, { replace: true, state: { notice: LOGIN_NOTICE_PASSWORD_SET } });
  });

  return (
    <form className={styles.form} noValidate aria-labelledby="reset-title" onSubmit={(event) => void submit(event)}>
      <h1 id="reset-title" className={styles.title}>
        Nueva contraseña
      </h1>
      <p className={styles.lead}>Sirve para activar tu cuenta o para recuperar el acceso.</p>
      {generalError ? (
        <p className={styles.error} role="alert">
          {generalError}
        </p>
      ) : null}
      <Field
        label="Contraseña nueva"
        type="password"
        autoComplete="new-password"
        required
        autoFocus
        hint={PASSWORD_MESSAGES.policy}
        error={errors.newPassword?.message}
        {...register("newPassword")}
      />
      <Field
        label="Repite la contraseña nueva"
        type="password"
        autoComplete="new-password"
        required
        error={errors.confirmPassword?.message}
        {...register("confirmPassword")}
      />
      <Button type="submit" className={styles.submit} loading={reset.isPending}>
        {reset.isPending ? "Guardando…" : "Guardar contraseña"}
      </Button>
      <Link className={styles.link} to={LOGIN_PATH}>
        Volver a iniciar sesión
      </Link>
    </form>
  );
}
