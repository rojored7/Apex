// S2-F4a · US-047 (front) y L-7: alta de un usuario del equipo (SidePanel de Usuarios.html).
// - Correo y rol (Coach o Admin, L-2); React Hook Form + Zod; POST /users con useCreateUser.
// - 201: el enlace de activación en un campo de solo lectura, "Copiar" y cómo entregarlo. El
//   enlace viaja una sola vez (US-047, criterio 9): al cerrar el panel se descarta del estado
//   (reset() de la mutación, que además tiene gcTime 0) y ya no se puede volver a ver; para
//   eso está "Reenviar enlace" (S2-F4b).
// - 409 email_taken: bajo el correo, con enlace al usuario existente. 422 al campo; 403, 5xx,
//   429 y red como mensaje general.
// DESIGN-GAP: Usuarios.html dibuja el panel de edición (nombre, correo, rol, tabla de permisos
// y acciones). El alta usa ese mismo panel sin nombre (S2-D17) y sin las acciones, que llegan
// con S2-F4b; tras crear muestra el enlace, que la pantalla no dibuja.
import { useId, useState } from "react";
import { useNavigate } from "react-router";
import { useForm } from "react-hook-form";
import { GENERIC_MESSAGES, isApiError } from "../../../core/api/errors";
import { DEFAULT_STAFF_ROLE, ROLE_LABELS, STAFF_ROLES } from "../../../core/auth/permissions";
import { formatDateTime } from "../../../core/i18n/format";
import { zodResolver } from "../../../shared/lib/zodResolver";
import { Button } from "../../../shared/ui/Button";
import { Field } from "../../../shared/ui/Field";
import { SidePanel } from "../../../shared/ui/SidePanel";
import { useCreateUser, type CreatedUser } from "../api";
import { LinkField } from "./LinkField";
import { userHref } from "../userLinks";
import { createUserSchema, type CreateUserForm } from "../schemas";
import styles from "./NewUserPanel.module.css";

export interface NewUserPanelProps {
  open: boolean;
  onClose: () => void;
}

export const NEW_USER_TITLE = "Nuevo usuario del equipo";
export const LINK_HANDOFF = "Entrega este enlace por un medio seguro; vence en 72 horas.";

const NEW_USER_MESSAGES = {
  emailTaken: "Ya existe una cuenta con este correo.",
  emailRejected: "El servidor no aceptó este correo. Revísalo e intenta de nuevo.",
  roleRejected: "Elige un rol: Coach o Admin.",
  forbidden: "Solo un administrador puede crear usuarios. Si lo necesitas, pídeselo a uno.",
  tooMany: "Demasiados intentos. Espera un momento y vuelve a intentarlo.",
  server: "No pudimos crear el usuario. Intenta de nuevo en un momento.",
  generic: "No pudimos crear el usuario. Revisa los datos e intenta de nuevo.",
} as const;

const DEFAULTS: CreateUserForm = { email: "", role: DEFAULT_STAFF_ROLE };

const HTTP_FORBIDDEN = 403;
const HTTP_CONFLICT = 409;
const HTTP_UNPROCESSABLE = 422;
const HTTP_TOO_MANY = 429;
const HTTP_SERVER_ERROR = 500;

const fieldError = (message: string | undefined): { error?: string } => (message ? { error: message } : {});

function generalMessage(error: unknown): string {
  if (!isApiError(error)) return NEW_USER_MESSAGES.generic;
  if (error.code === "invalid_response") return error.message;
  if (error.status === 0) return error.code === "timeout" ? GENERIC_MESSAGES.timeout : GENERIC_MESSAGES.network_error;
  if (error.status === HTTP_FORBIDDEN) return NEW_USER_MESSAGES.forbidden;
  if (error.status === HTTP_TOO_MANY) return NEW_USER_MESSAGES.tooMany;
  if (error.status >= HTTP_SERVER_ERROR) return NEW_USER_MESSAGES.server;
  return NEW_USER_MESSAGES.generic;
}

function CreatedLink({ created }: { created: CreatedUser }) {
  return (
    <div className={styles.created}>
      <p className={styles.done}>{`Usuario creado: ${created.email}`}</p>
      <LinkField label="Enlace de activación" name="activation_url" url={created.activationUrl} handoff={LINK_HANDOFF} />
      {/* formatDateTime ya termina en "a. m." o "p. m.": no lleva otro punto. */}
      <p className={styles.note}>{`Vence el ${formatDateTime(created.expiresAt)} Al cerrar este panel ya no se puede volver a ver.`}</p>
    </div>
  );
}

export function NewUserPanel({ open, onClose }: NewUserPanelProps) {
  const formId = useId();
  const create = useCreateUser();
  const navigate = useNavigate();
  const form = useForm<CreateUserForm>({ resolver: zodResolver(createUserSchema), defaultValues: DEFAULTS });
  const {
    register,
    formState: { errors, isDirty },
  } = form;
  const [existingId, setExistingId] = useState<string | null>(null);
  const [generalError, setGeneralError] = useState<string | null>(null);
  const created = create.data;

  /**
   * L-7: al cerrar, el enlace sale del estado y de la caché (reset con gcTime 0). Mientras el
   * alta está en curso no se cierra: si no, el usuario quedaría creado y su enlace, que viaja
   * una sola vez, se perdería.
   */
  const close = (): void => {
    if (create.isPending) return;
    create.reset();
    form.reset(DEFAULTS);
    setExistingId(null);
    setGeneralError(null);
    onClose();
  };

  /** El usuario existente, sin recargar la página (la sesión sigue en memoria). */
  const goToExisting = (href: string): void => {
    close();
    void navigate(href);
  };

  const submit = form.handleSubmit(async (values) => {
    setExistingId(null);
    setGeneralError(null);
    try {
      await create.mutateAsync(values);
    } catch (error) {
      if (isApiError(error) && error.status === HTTP_CONFLICT && (error.field === "email" || error.code === "email_taken")) {
        setExistingId(error.existingId ?? null);
        form.setError("email", { type: "server", message: NEW_USER_MESSAGES.emailTaken }, { shouldFocus: true });
        return;
      }
      if (isApiError(error) && error.status === HTTP_UNPROCESSABLE && (error.field === "email" || error.field === "role")) {
        const message = error.field === "email" ? NEW_USER_MESSAGES.emailRejected : NEW_USER_MESSAGES.roleRejected;
        form.setError(error.field, { type: "server", message }, { shouldFocus: true });
        return;
      }
      setGeneralError(generalMessage(error));
    }
  });

  return (
    <SidePanel
      open={open}
      title={NEW_USER_TITLE}
      isDirty={!created && !create.isPending && isDirty}
      onClose={close}
      cancelLabel={created ? "Listo" : "Cancelar"}
      footer={
        created ? null : (
          <Button type="submit" form={formId} loading={create.isPending}>
            {create.isPending ? "Creando…" : "Crear usuario"}
          </Button>
        )
      }
    >
      {created ? (
        <CreatedLink created={created} />
      ) : (
        <form id={formId} className={styles.form} noValidate aria-label={NEW_USER_TITLE} onSubmit={(event) => void submit(event)}>
          {generalError ? (
            <p className={styles.error} role="alert">
              {generalError}
            </p>
          ) : null}
          <Field
            label="Correo (es el usuario)"
            type="email"
            autoComplete="off"
            inputMode="email"
            required
            {...fieldError(errors.email?.message)}
            {...(existingId && errors.email ? { errorAction: { href: userHref(existingId), text: "Ver el usuario existente", onNavigate: goToExisting } } : {})}
            {...register("email")}
          />
          <Field label="Rol" name="role" required {...fieldError(errors.role?.message)}>
            {(control) => (
              <select {...control} {...register("role")}>
                {STAFF_ROLES.map((role) => (
                  <option key={role} value={role}>
                    {ROLE_LABELS[role]}
                  </option>
                ))}
              </select>
            )}
          </Field>
          <p className={styles.note}>Los socios entran al portal desde su ficha; aquí se crean solo cuentas del equipo.</p>
        </form>
      )}
    </SidePanel>
  );
}
