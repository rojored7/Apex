// S2-F4a · US-045: "Mi cuenta" del TopBar (PanelShell lo monta y lo abre).
// - SidePanel con los datos de la cuenta (GET /auth/me, solo mientras está abierto) y el
//   cambio de contraseña (useChangePasswordForm).
// - El éxito cierra el panel y deja el aviso "Contraseña actualizada" fuera de él (la página
//   sigue a la vista); el aviso se puede cerrar y desaparece al volver a abrir el panel.
// - Cerrar (✕, Cancelar, Escape) descarta lo escrito; con cambios, SidePanel pregunta antes.
// DESIGN-GAP: no hay pantalla "Mi cuenta" en docs/design/screens/; se arma con SidePanel y
// Field del kit, como los paneles de Usuarios.html.
import { X } from "lucide-react";
import { useId, useState } from "react";
import { ROLE_LABELS } from "../../../core/auth/permissions";
import { Button } from "../../../shared/ui/Button";
import { SidePanel } from "../../../shared/ui/SidePanel";
import { useMe, type MeView } from "../api";
import styles from "./AccessCard.module.css";
import { ChangePasswordFields } from "./ChangePasswordFields";
import { useChangePasswordForm } from "./useChangePasswordForm";

export interface ChangePasswordPanelProps {
  open: boolean;
  onClose: () => void;
}

export const PASSWORD_UPDATED = "Contraseña actualizada";

function AccountSummary({ me, isLoading, isError }: { me: MeView | undefined; isLoading: boolean; isError: boolean }) {
  if (me) {
    return (
      <ul className={styles.account} aria-label="Datos de tu cuenta">
        <li>
          <span className={styles.accountLabel}>Correo</span>
          <span className={styles.accountValue}>{me.email}</span>
        </li>
        <li>
          <span className={styles.accountLabel}>Rol</span>
          <span className={styles.accountValue}>{ROLE_LABELS[me.role]}</span>
        </li>
        <li>
          <span className={styles.accountLabel}>Gimnasio</span>
          <span className={styles.accountValue}>{me.gym_name}</span>
        </li>
      </ul>
    );
  }
  if (isError) return <p className={styles.lead}>No pudimos cargar los datos de tu cuenta. Cierra el panel y vuelve a abrirlo.</p>;
  return <p className={styles.lead}>{isLoading ? "Cargando los datos de tu cuenta…" : null}</p>;
}

export function ChangePasswordPanel({ open, onClose }: ChangePasswordPanelProps) {
  const formId = useId();
  const [updated, setUpdated] = useState(false);
  const [wasOpen, setWasOpen] = useState(open);
  // Al volver a abrir, el aviso anterior ya no aplica.
  if (open !== wasOpen) {
    setWasOpen(open);
    if (open) setUpdated(false);
  }
  const me = useMe({ enabled: open });
  const { form, submit, pending, generalError, reset } = useChangePasswordForm(() => {
    setUpdated(true);
    onClose();
  });

  // Mientras se guarda no se cierra: un error tardío pintaría el formulario ya vaciado.
  const close = (): void => {
    if (pending) return;
    reset();
    onClose();
  };

  return (
    <>
      {/* La región viva existe siempre: así el lector de pantalla anuncia el aviso al llenarse. */}
      <div role="status">
        {updated ? (
          <div className={styles.success}>
            <div className={styles.actions}>
              <span>{PASSWORD_UPDATED}</span>
              <button
                type="button"
                className={styles.dismiss}
                aria-label="Cerrar aviso"
                onClick={() => {
                  setUpdated(false);
                }}
              >
                <X size={20} aria-hidden="true" />
              </button>
            </div>
          </div>
        ) : null}
      </div>
      <SidePanel
        open={open}
        title="Mi cuenta"
        isDirty={!pending && form.formState.isDirty}
        onClose={close}
        footer={
          <Button type="submit" form={formId} loading={pending}>
            {pending ? "Guardando…" : "Cambiar contraseña"}
          </Button>
        }
      >
        <AccountSummary me={me.data} isLoading={me.isLoading} isError={me.isError} />
        <form id={formId} className={styles.form} noValidate aria-labelledby={`${formId}-title`} onSubmit={(event) => void submit(event)}>
          <h3 id={`${formId}-title`} className={styles.section}>
            Cambiar contraseña
          </h3>
          {generalError ? (
            <p className={styles.error} role="alert">
              {generalError}
            </p>
          ) : null}
          <ChangePasswordFields form={form} />
        </form>
      </SidePanel>
    </>
  );
}
