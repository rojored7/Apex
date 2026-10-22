// S2-F4a · US-045 y S2-D18: /cambiar-clave, con sesión y cualquier rol (RequireAuth lleva aquí
// mientras must_change_password sea verdadero). Misma tarjeta de acceso que ResetPage, pero
// con la contraseña actual: POST /auth/me/password. Al terminar, la sesión ya tiene el access
// nuevo con must_change_password en falso y la página va al inicio del rol (homeFor).
// "Cerrar sesión" sirve a quien no conoce la contraseña inicial.
// DESIGN-GAP: sin pantalla propia en docs/design/screens/; usa la tarjeta "Nueva contraseña"
// de Login.html con el campo de la contraseña actual.
import { useState } from "react";
import { useNavigate } from "react-router";
import { homeFor, LOGIN_PATH } from "../../../core/auth/routeAccess";
import { getSession, logout, useSession } from "../../../core/auth/session";
import { Button } from "../../../shared/ui/Button";
import styles from "../components/AccessCard.module.css";
import { ChangePasswordFields } from "../components/ChangePasswordFields";
import { useChangePasswordForm } from "../components/useChangePasswordForm";

export default function ChangePasswordPage() {
  const { user } = useSession();
  const navigate = useNavigate();
  // Se decide al llegar: tras guardar, la sesión ya no lo exige y la página se va.
  const [required] = useState(() => getSession().user?.mustChangePassword === true);
  const [leaving, setLeaving] = useState(false);
  const { form, submit, pending, generalError } = useChangePasswordForm(() => {
    const role = getSession().user?.role;
    void navigate(role ? homeFor(role) : LOGIN_PATH, { replace: true });
  });

  return (
    <form className={styles.form} noValidate aria-labelledby="change-title" onSubmit={(event) => void submit(event)}>
      <h1 id="change-title" className={styles.title}>
        Cambia tu contraseña
      </h1>
      {required ? (
        <p className={styles.notice} role="status">
          Antes de seguir, cambia la contraseña inicial de tu cuenta.
        </p>
      ) : null}
      {user ? (
        <p className={styles.lead}>
          Cuenta: <strong>{user.email}</strong>
        </p>
      ) : null}
      {generalError ? (
        <p className={styles.error} role="alert">
          {generalError}
        </p>
      ) : null}
      <ChangePasswordFields form={form} autoFocus />
      <Button type="submit" className={styles.submit} loading={pending}>
        {pending ? "Guardando…" : "Cambiar contraseña"}
      </Button>
      <Button
        variant="secondary"
        className={styles.submit}
        loading={leaving}
        onClick={() => {
          setLeaving(true);
          void logout();
        }}
      >
        {leaving ? "Cerrando sesión…" : "Cerrar sesión"}
      </Button>
    </form>
  );
}
