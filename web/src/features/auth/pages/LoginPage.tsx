// S2-F3 · US-042: /login (Login.html). Contenedor de LoginCard dentro de AccessLayout.
// - Envía con useLogin; al entrar va a /cambiar-clave si must_change_password, si no a
//   safeNext(next, rol) o a homeFor(rol). Con la sesión ya abierta al llegar, va al inicio.
// - Errores: 401 genérico, 429 con cuenta atrás de Retry-After (botón bloqueado), 422 al campo,
//   403 de Origin, red y 5xx con mensajes "qué pasó y qué hacer".
// - Avisos por la razón del cierre anterior: H-1 (cierre no confirmado) y sesión vencida.
// - S2-F4a: el aviso de contraseña guardada que deja ResetPage (loginNotice.ts) va primero.
// - L5 (revisión del Sprint 2): si la sesión todavía carga (recarga en /login con la cookie
//   vigente), la restaura y muestra "Cargando…"; con sesión va al inicio del rol y sin ella
//   muestra el formulario. La sesión que abre este formulario navega por su cuenta.
import { useEffect, useState } from "react";
import { Navigate, useLocation, useNavigate, useSearchParams } from "react-router";
import { isApiError } from "../../../core/api/errors";
import { HTTP_TOO_MANY, HTTP_UNPROCESSABLE } from "../../../core/api/status";
import { CHANGE_PASSWORD_PATH, homeFor, safeNext } from "../../../core/auth/routeAccess";
import { restoreSession, useSession, type ClearReason, type SessionUser } from "../../../core/auth/session";
import { RouteLoading } from "../../../pages/RouteLoading";
import { LOGIN_MESSAGES, loginErrorMessage, useLogin } from "../api";
import { LoginCard, type LoginField, type LoginOutcome } from "../components/LoginCard";
import { loginNoticeFrom } from "../loginNotice";
import type { LoginForm } from "../schemas";

const TICK_MS = 1_000;

const NOTICES: Partial<Record<ClearReason, string>> = {
  logout_unconfirmed: "No se pudo cerrar la sesión en el servidor. Si usas un equipo compartido, cierra el navegador.",
  expired: "Tu sesión venció. Vuelve a iniciar sesión.",
  unauthorized: "Tu sesión se cerró. Vuelve a iniciar sesión.",
};

const FIELD_MESSAGES: Record<LoginField, string> = {
  email: "Revisa el correo: el servidor no lo aceptó.",
  password: "Revisa la contraseña: el servidor no la aceptó.",
};

type Failure = { kind: "message"; text: string } | { kind: "rate_limited" };

function destinationFor(user: SessionUser, next: string | null): string {
  if (user.mustChangePassword) return CHANGE_PASSWORD_PATH;
  return safeNext(next, user.role) ?? homeFor(user.role);
}

function isLoginField(value: string | undefined): value is LoginField {
  return value === "email" || value === "password";
}

export default function LoginPage() {
  const { status, user: sessionUser, reason } = useSession();
  // La sesión que abre este formulario navega por su cuenta (destinationFor), no al inicio.
  const [submitted, setSubmitted] = useState(false);
  const [params] = useSearchParams();
  // S2-F4a: aviso que deja otra pantalla (ResetPage) en el estado de la navegación.
  const flash = loginNoticeFrom(useLocation().state);
  const navigate = useNavigate();
  const login = useLogin();
  const [failure, setFailure] = useState<Failure | null>(null);
  const [waitS, setWaitS] = useState(0);

  useEffect(() => {
    if (status === "loading") void restoreSession();
  }, [status]);

  useEffect(() => {
    if (waitS <= 0) return undefined;
    const timer = setTimeout(() => {
      setWaitS((value) => value - 1);
    }, TICK_MS);
    return () => {
      clearTimeout(timer);
    };
  }, [waitS]);

  if (status === "loading") return <RouteLoading />;
  if (sessionUser && !submitted) return <Navigate to={homeFor(sessionUser.role)} replace />;

  const onSubmit = async (values: LoginForm): Promise<LoginOutcome> => {
    setFailure(null);
    setSubmitted(true);
    try {
      const user = await login.mutateAsync(values);
      void navigate(destinationFor(user, params.get("next")), { replace: true });
      return { ok: true };
    } catch (error) {
      if (isApiError(error) && error.status === HTTP_TOO_MANY && error.retryAfterS !== undefined && error.retryAfterS > 0) {
        setWaitS(error.retryAfterS);
        setFailure({ kind: "rate_limited" });
        return { ok: false };
      }
      if (isApiError(error) && error.status === HTTP_UNPROCESSABLE && isLoginField(error.field)) {
        return { ok: false, fieldError: { field: error.field, message: FIELD_MESSAGES[error.field] } };
      }
      setFailure({ kind: "message", text: loginErrorMessage(error) });
      return { ok: false };
    }
  };

  const errorText =
    failure === null ? null : failure.kind === "message" ? failure.text : waitS > 0 ? LOGIN_MESSAGES.tooManyWait(waitS) : LOGIN_MESSAGES.canRetry;

  return (
    <LoginCard
      onSubmit={onSubmit}
      pending={login.isPending}
      error={errorText}
      notice={flash ?? (reason ? NOTICES[reason] : undefined)}
      waitS={waitS}
    />
  );
}
