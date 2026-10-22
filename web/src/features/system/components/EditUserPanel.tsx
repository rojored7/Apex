// S2-F4b · US-049 (front): edición de una cuenta en el SidePanel de Usuarios.html.
// - La abre UsersPage con `?usuario=<id>` (enlace del correo, "Editar", el 409 del alta o un
//   enlace compartido). GET /users/{id} (useUser) incluye cuentas dadas de baja: esas se ven,
//   pero no se editan.
// - Correo y rol (Coach o Admin; el rol de un socio no se cambia aquí). React Hook Form + Zod;
//   PATCH /users/{id} solo con lo que cambió; "Guardar" queda deshabilitado sin cambios.
// - 409 email_taken bajo el correo con enlace al existente (abre su edición sin recargar);
//   409 last_admin y 404 como mensaje general; 422 al campo. No se cierra mientras guarda.
// - Si la cuenta es la propia, al guardar se relee la sesión (rol y correo vigentes).
// DESIGN-GAP: Usuarios.html muestra el nombre (auth.users no lo tiene, S2-D17), la tabla de
// permisos por rol y las acciones (enlace, sesiones, bloquear) dentro del panel; aquí las
// acciones van en la fila (blueprint F4b) y la tabla de permisos no se dibuja.
import { useEffect, useId, useState } from "react";
import { useForm } from "react-hook-form";
import { useLocation, useNavigate } from "react-router";
import { API_ERROR_CODES, CLIENT_ERROR_CODES } from "../../../core/api/errorCodes";
import { isApiError } from "../../../core/api/errors";
import { HTTP_CONFLICT, HTTP_NOT_FOUND, HTTP_UNPROCESSABLE } from "../../../core/api/status";
import { ROLE_LABELS, STAFF_ROLES } from "../../../core/auth/permissions";
import { refreshCurrentUser, useSession } from "../../../core/auth/session";
import { zodResolver } from "../../../shared/lib/zodResolver";
import { Button } from "../../../shared/ui/Button";
import { Field } from "../../../shared/ui/Field";
import { SidePanel } from "../../../shared/ui/SidePanel";
import { useUpdateUser, useUser, type UpdateUserChanges } from "../api";
import { editUserSchema, type EditUserForm, type UserView } from "../schemas";
import { userActionMessage } from "../userActions";
import { userHref } from "../userLinks";
import styles from "./EditUserPanel.module.css";

export interface EditUserPanelProps {
  /** La cuenta que se edita (`?usuario=<id>`); null con el panel cerrado. */
  userId: string | null;
  onClose: () => void;
  /** Tras guardar, con el correo de la cuenta (para el aviso de la lista). */
  onSaved?: (email: string) => void;
}

export const EDIT_USER_TITLE = "Editar usuario";

export const EDIT_USER_MESSAGES = {
  loading: "Cargando la cuenta…",
  notFound: "No encontramos esta cuenta. Cierra el panel y búscala en la lista.",
  loadFailed: "No pudimos cargar la cuenta. Intenta de nuevo en un momento.",
  deleted: "Esta cuenta está dada de baja. Su historial se conserva y ya no se puede editar.",
  memberRole: "Socio: su rol no se cambia desde aquí.",
  emailTaken: "Ya existe una cuenta con este correo.",
  emailRejected: "El servidor no aceptó este correo. Revísalo e intenta de nuevo.",
  roleRejected: "El servidor no aceptó este rol. Elige Coach o Admin.",
  lastAdmin: "Debe quedar al menos un administrador activo. Nombra a otro administrador antes de quitarle el rol a esta cuenta.",
} as const;

type UpdateMutation = ReturnType<typeof useUpdateUser>;

/** Solo lo que cambió respecto de la cuenta leída (el correo se compara ya recortado). */
function changesOf(account: UserView, values: EditUserForm): UpdateUserChanges {
  const email = values.email.trim();
  return {
    ...(email !== account.email ? { email } : {}),
    ...(values.role !== account.role ? { role: values.role } : {}),
  };
}

function loadErrorMessage(error: unknown): string {
  if (!isApiError(error)) return EDIT_USER_MESSAGES.loadFailed;
  if (error.status === HTTP_NOT_FOUND) return EDIT_USER_MESSAGES.notFound;
  if (error.code === CLIENT_ERROR_CODES.invalidResponse || error.status === 0) return userActionMessage(error);
  return EDIT_USER_MESSAGES.loadFailed;
}

function saveErrorMessage(error: unknown): string {
  return isApiError(error) && error.code === API_ERROR_CODES.lastAdmin ? EDIT_USER_MESSAGES.lastAdmin : userActionMessage(error);
}

const isStaffRole = (role: UserView["role"]): boolean => (STAFF_ROLES as readonly string[]).includes(role);

interface EditFormProps {
  account: UserView;
  formId: string;
  save: UpdateMutation;
  onDirtyChange: (dirty: boolean) => void;
  onSaved: (account: UserView) => void;
}

function EditForm({ account, formId, save, onDirtyChange, onSaved }: EditFormProps) {
  const navigate = useNavigate();
  const location = useLocation();
  const form = useForm<EditUserForm>({ resolver: zodResolver(editUserSchema), defaultValues: { email: account.email, role: account.role } });
  const {
    register,
    formState: { errors, isDirty },
  } = form;
  const [existingId, setExistingId] = useState<string | null>(null);
  const [generalError, setGeneralError] = useState<string | null>(null);

  useEffect(() => {
    onDirtyChange(isDirty);
  }, [isDirty, onDirtyChange]);
  // Al pasar a otra cuenta (o cerrar) este formulario se desmonta: sus cambios no siguen.
  useEffect(
    () => () => {
      onDirtyChange(false);
    },
    [onDirtyChange],
  );

  const submit = form.handleSubmit(async (values) => {
    // Enter en el correo con el guardado en curso no envía otro PATCH.
    if (save.isPending) return;
    setExistingId(null);
    setGeneralError(null);
    const changes = changesOf(account, values);
    if (Object.keys(changes).length === 0) return;
    try {
      onSaved(await save.mutateAsync({ id: account.id, changes }));
    } catch (error) {
      if (isApiError(error) && error.status === HTTP_CONFLICT && error.code === API_ERROR_CODES.emailTaken) {
        setExistingId(error.existingId ?? null);
        form.setError("email", { type: "server", message: EDIT_USER_MESSAGES.emailTaken }, { shouldFocus: true });
        return;
      }
      if (isApiError(error) && error.status === HTTP_UNPROCESSABLE && (error.field === "email" || error.field === "role")) {
        const message = error.field === "email" ? EDIT_USER_MESSAGES.emailRejected : EDIT_USER_MESSAGES.roleRejected;
        form.setError(error.field, { type: "server", message }, { shouldFocus: true });
        return;
      }
      setGeneralError(saveErrorMessage(error));
    }
  });

  const existingAction =
    existingId && errors.email
      ? {
          errorAction: {
            href: userHref(existingId, location.search),
            text: "Ver el usuario existente",
            // Sin recargar: la sesión vive en memoria.
            onNavigate: (href: string) => {
              void navigate(href);
            },
          },
        }
      : {};

  return (
    <form id={formId} className={styles.form} noValidate aria-label={EDIT_USER_TITLE} onSubmit={(event) => void submit(event)}>
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
        error={errors.email?.message}
        {...existingAction}
        {...register("email")}
      />
      {isStaffRole(account.role) ? (
        <Field label="Rol" name="role" required error={errors.role?.message}>
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
      ) : (
        <p className={styles.note}>{EDIT_USER_MESSAGES.memberRole}</p>
      )}
    </form>
  );
}

function DeletedAccount({ account }: { account: UserView }) {
  return (
    <div className={styles.stack}>
      <p className={styles.done}>{account.email}</p>
      <p className={styles.note}>{`Rol: ${ROLE_LABELS[account.role]}`}</p>
      <p className={styles.warning}>{EDIT_USER_MESSAGES.deleted}</p>
    </div>
  );
}

export function EditUserPanel({ userId, onClose, onSaved }: EditUserPanelProps) {
  const formId = useId();
  const session = useSession();
  const account = useUser(userId);
  const save = useUpdateUser();
  const [dirty, setDirty] = useState(false);
  const resetSave = save.reset;
  // Otra cuenta (el enlace "Ver el usuario existente"): el error o el guardado de la anterior
  // no se arrastran.
  useEffect(() => {
    resetSave();
  }, [userId, resetSave]);
  const data = account.data;
  const editable = data !== undefined && data.status !== "deleted";

  const finish = (): void => {
    save.reset();
    setDirty(false);
    onClose();
  };

  /** Mientras guarda no se cierra: el resultado (o su error) debe verse. */
  const close = (): void => {
    if (!save.isPending) finish();
  };

  const saved = (updated: UserView): void => {
    // La propia cuenta: el rol o el correo de la sesión cambian (un admin que pasa a coach deja
    // de ver Usuarios).
    if (updated.id === session.user?.id) void refreshCurrentUser();
    onSaved?.(updated.email);
    finish();
  };

  const renderBody = () => {
    if (account.isPending) {
      return (
        <p className={styles.note} aria-busy="true">
          {EDIT_USER_MESSAGES.loading}
        </p>
      );
    }
    if (account.isError) {
      return (
        <div className={styles.stack}>
          <p className={styles.error} role="alert">
            {loadErrorMessage(account.error)}
          </p>
          <Button
            variant="secondary"
            onClick={() => {
              void account.refetch();
            }}
          >
            Reintentar
          </Button>
        </div>
      );
    }
    if (account.data.status === "deleted") return <DeletedAccount account={account.data} />;
    return <EditForm key={account.data.id} account={account.data} formId={formId} save={save} onDirtyChange={setDirty} onSaved={saved} />;
  };

  return (
    <SidePanel
      open={userId !== null}
      title={EDIT_USER_TITLE}
      isDirty={dirty && !save.isPending}
      onClose={close}
      footer={
        editable ? (
          <Button type="submit" form={formId} loading={save.isPending} disabled={!dirty}>
            {save.isPending ? "Guardando…" : "Guardar"}
          </Button>
        ) : null
      }
    >
      {renderBody()}
    </SidePanel>
  );
}
