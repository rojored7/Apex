// S2-F4a · US-048 (criterio 10): /recuperar (Login.html, tarjeta "Olvidé mi contraseña").
// Envía POST /auth/forgot y, pase lo que pase (204 exista o no el correo, 429, 5xx o red),
// muestra el mismo mensaje: la pantalla nunca dice si la cuenta existe.
// DESIGN-GAP: Login.html anuncia "Si el correo está registrado, recibirás un enlace", pero en
// v0.1 forgot no envía correos (H-2, S2-D36; el emisor llega con US-131): el enlace lo da el
// administrador (POST /users/{id}/resend-link), y el mensaje fijo lo dice así.
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link } from "react-router";
import { LOGIN_PATH } from "../../../core/auth/routeAccess";
import { zodResolver } from "../../../shared/lib/zodResolver";
import { Button } from "../../../shared/ui/Button";
import { Field } from "../../../shared/ui/Field";
import { useForgotPassword } from "../api";
import styles from "../components/AccessCard.module.css";
import { forgotSchema, type ForgotForm } from "../schemas";

export const FORGOT_DONE = "Pídele al administrador tu enlace de recuperación.";


export default function ForgotPage() {
  const forgot = useForgotPassword();
  const [done, setDone] = useState(false);
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<ForgotForm>({ resolver: zodResolver(forgotSchema), defaultValues: { email: "" } });

  const submit = handleSubmit(async (values) => {
    try {
      await forgot.mutateAsync(values);
    } catch {
      // H-2: el resultado no cambia el mensaje (ni revela si la cuenta existe).
    }
    forgot.reset();
    setDone(true);
  });

  if (done) {
    return (
      <div className={styles.form}>
        <h1 className={styles.title}>Olvidé mi contraseña</h1>
        <p className={styles.success} role="status">
          {FORGOT_DONE}
        </p>
        <Link className={styles.link} to={LOGIN_PATH}>
          Volver a iniciar sesión
        </Link>
      </div>
    );
  }

  return (
    <form className={styles.form} noValidate aria-labelledby="forgot-title" onSubmit={(event) => void submit(event)}>
      <h1 id="forgot-title" className={styles.title}>
        Olvidé mi contraseña
      </h1>
      <p className={styles.lead}>En esta versión el enlace no llega por correo: te lo entrega el administrador del gimnasio.</p>
      <Field label="Correo" type="email" autoComplete="username" inputMode="email" autoFocus error={errors.email?.message} {...register("email")} />
      <Button type="submit" className={styles.submit} loading={forgot.isPending}>
        {forgot.isPending ? "Enviando…" : "Enviar enlace"}
      </Button>
      <Link className={styles.link} to={LOGIN_PATH}>
        Volver a iniciar sesión
      </Link>
    </form>
  );
}
