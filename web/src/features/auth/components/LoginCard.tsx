// S2-F3 · US-042: tarjeta de Login.html (tema claro, dentro de AccessLayout, que pone el
// logo). React Hook Form + Zod con el adaptador propio (S2-D22).
// - Estados: inicial (foco en el correo), enviando (botón "Entrando…" deshabilitado),
//   error sobre los campos (role="alert") y espera tras un 429 (botón bloqueado).
// - Ante un error conserva el correo, limpia la contraseña y le da el foco; un error de un
//   campo (422 con `field`) marca ese campo.
// DESIGN-GAP: Login.html muestra "[NOMBRE DEL GIMNASIO]" bajo el logo, pero gym_name solo
// llega con la sesión abierta (GET /auth/me): aquí se muestra "APEX" (S2-D50).
import { useForm } from "react-hook-form";
import { Link } from "react-router";
import { zodResolver } from "../../../shared/lib/zodResolver";
import { Button } from "../../../shared/ui/Button";
import { Field } from "../../../shared/ui/Field";
import { DEFAULT_GYM_NAME } from "../api";
import { loginSchema, type LoginForm } from "../schemas";
import styles from "./AccessCard.module.css";

export type LoginField = keyof LoginForm;

export type LoginOutcome = { ok: true } | { ok: false; fieldError?: { field: LoginField; message: string } | undefined };

export interface LoginCardProps {
  /** Con `ok: false` la tarjeta limpia la contraseña y da el foco al campo que toca. */
  onSubmit: (values: LoginForm) => Promise<LoginOutcome>;
  pending: boolean;
  /** Error general sobre los campos (credenciales, 429, red, servidor). */
  error: string | null;
  /** Aviso al llegar (cierre no confirmado, sesión vencida). */
  notice?: string | null | undefined;
  /** Segundos que faltan para volver a intentar tras un 429; 0 si no hay espera. */
  waitS: number;
}

/** `error` solo cuando hay mensaje (exactOptionalPropertyTypes). */

export function LoginCard({ onSubmit, pending, error, notice, waitS }: LoginCardProps) {
  const {
    register,
    handleSubmit,
    resetField,
    setError,
    setFocus,
    formState: { errors },
  } = useForm<LoginForm>({ resolver: zodResolver(loginSchema), defaultValues: { email: "", password: "" } });

  const submit = handleSubmit(async (values) => {
    const outcome = await onSubmit(values);
    if (outcome.ok) return;
    resetField("password");
    if (outcome.fieldError) {
      setError(outcome.fieldError.field, { type: "server", message: outcome.fieldError.message });
      setFocus(outcome.fieldError.field);
      return;
    }
    setFocus("password");
  });

  const waiting = waitS > 0;

  return (
    <form className={styles.form} noValidate aria-labelledby="login-title" onSubmit={(event) => void submit(event)}>
      <p className={styles.gym}>{DEFAULT_GYM_NAME}</p>
      <h1 id="login-title" className={styles.title}>
        Iniciar sesión
      </h1>
      {notice ? (
        <p className={styles.notice} role="status">
          {notice}
        </p>
      ) : null}
      {error ? (
        <p className={styles.error} role="alert">
          {error}
        </p>
      ) : null}
      <Field label="Correo" type="email" autoComplete="username" inputMode="email" autoFocus error={errors.email?.message} {...register("email")} />
      <Field label="Contraseña" type="password" autoComplete="current-password" error={errors.password?.message} {...register("password")} />
      <Button type="submit" className={styles.submit} loading={pending} disabled={waiting}>
        {pending ? "Entrando…" : "Entrar"}
      </Button>
      <Link className={styles.link} to="/recuperar">
        Olvidé mi contraseña
      </Link>
      <p className={styles.note}>Si eres socio, entras al portal. Si eres coach o admin, al panel.</p>
    </form>
  );
}
