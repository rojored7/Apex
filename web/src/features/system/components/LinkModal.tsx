// S2-F4b · US-052 (front), L-7 y L-13: reenvío del enlace de activación o recuperación desde
// la fila de Usuarios. Es la única forma de volver a obtener un enlace.
// - Primero avisa: el enlace nuevo invalida el anterior. "Generar enlace" hace POST
//   /users/{id}/resend-link (useResendLink); mientras tanto no se cierra ni se pide otro.
// - Con la respuesta: el enlace en un campo de solo lectura con "Copiar", el propósito en
//   texto ("Activación, vence en 72 horas" o "Recuperación, vence en 1 hora"), el vencimiento
//   en hora de Bogotá de `expires_at` y cómo entregarlo.
// - L-7: la mutación tiene gcTime 0 y al cerrar se llama reset(): el enlace sale de la
//   pantalla y de la caché y no se puede volver a ver (para eso se genera otro).
// - 409 user_not_eligible y demás errores, con su mensaje, sin mostrar ningún enlace.
// DESIGN-GAP: Usuarios.html pone "Enviar enlace de nueva contraseña" dentro del panel de
// edición y no dibuja dónde se ve el enlace; aquí es una acción de la fila (blueprint F4b) y un
// diálogo propio (Modal), con el mismo campo y "Copiar" del alta.
import { formatDateTime } from "../../../core/i18n/format";
import { Button } from "../../../shared/ui/Button";
import { Modal } from "../../../shared/ui/Modal";
import { useResendLink, type IssuedLink } from "../api";
import type { LinkPurpose } from "../schemas";
import { userActionMessage } from "../userActions";
import { LinkField } from "./LinkField";
import styles from "./LinkModal.module.css";

export interface LinkTarget {
  id: string;
  email: string;
}

export interface LinkModalProps {
  /** La cuenta a la que se le genera el enlace; null con el modal cerrado. */
  user: LinkTarget | null;
  onClose: () => void;
}

export const LINK_MODAL_TITLE = "Reenviar enlace";
export const RESEND_HANDOFF = "Entrégalo por un medio seguro. Al generar uno nuevo, el anterior deja de servir.";

export const LINK_PURPOSE_TEXT: Readonly<Record<LinkPurpose, string>> = Object.freeze({
  activate: "Activación, vence en 72 horas",
  reset: "Recuperación, vence en 1 hora",
});

function IssuedLinkView({ link }: { link: IssuedLink }) {
  return (
    <>
      <p className={styles.purpose}>{LINK_PURPOSE_TEXT[link.purpose]}</p>
      <LinkField label="Enlace" name="issued_link" url={link.url} handoff={RESEND_HANDOFF} />
      {/* formatDateTime ya termina en "a. m." o "p. m.": no lleva otro punto. */}
      <p className={styles.note}>{`Vence el ${formatDateTime(link.expiresAt)} Al cerrar ya no se puede volver a ver.`}</p>
    </>
  );
}

export function LinkModal({ user, onClose }: LinkModalProps) {
  const resend = useResendLink();
  const link = resend.data;
  const busy = resend.isPending;

  const close = (): void => {
    if (busy) return;
    resend.reset();
    onClose();
  };

  const generate = (): void => {
    if (!user || busy) return;
    resend.mutate({ id: user.id });
  };

  const actions = link ? (
    <Button onClick={close}>Listo</Button>
  ) : (
    <>
      <Button variant="secondary" onClick={close} disabled={busy}>
        Volver
      </Button>
      <Button loading={busy} onClick={generate}>
        {busy ? "Generando…" : "Generar enlace"}
      </Button>
    </>
  );

  return (
    <Modal open={user !== null} title={LINK_MODAL_TITLE} busy={busy} onClose={close} actions={actions}>
      {link ? (
        <IssuedLinkView link={link} />
      ) : (
        <>
          <p className={styles.text}>{`Se genera un enlace nuevo para ${user?.email ?? ""}.`}</p>
          <p className={styles.text}>{RESEND_HANDOFF}</p>
          {resend.isError ? (
            <p className={styles.error} role="alert">
              {userActionMessage(resend.error)}
            </p>
          ) : null}
        </>
      )}
    </Modal>
  );
}
