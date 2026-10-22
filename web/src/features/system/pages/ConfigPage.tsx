// S2-F5 (US-055, US-057, US-058): /sistema/configuracion (Config.html), solo admin
// (settings.manage; la guarda de la ruta muestra "Sin permiso" a los demás y el api responde
// 403). PageHeader y Tabs con la pestaña en ?tab=; cada pestaña lee y guarda su sección.
// - Salir de una pestaña, o de la pantalla, con cambios sin guardar pide confirmación con
//   ConfirmModal (useBlocker de React Router). Recargar o cerrar la pestaña del navegador usa
//   el aviso del propio navegador (beforeunload).
// - Sin borradores en localStorage: lo no guardado vive solo en el formulario.
// - L4 (revisión del Sprint 2): sin sesión autenticada no se bloquea nada; si la sesión se
//   cierra con cambios sin guardar, el <Navigate> de RequireAuth a /login no queda atrapado.
// DESIGN-GAP: Config.html muestra las ocho secciones como cajas apiladas con un índice
// lateral; el blueprint F5 las pasa a pestañas y el Sprint 2 solo habilita Gimnasio,
// Privacidad y Membresías (S2-D15: horario, medios de pago, canales, clases y TV llegan en
// sus versiones y no se muestran).
import { useCallback, useRef, useState, type ReactNode } from "react";
import { useBeforeUnload, useBlocker, type BlockerFunction } from "react-router";
import { useSession } from "../../../core/auth/session";
import { ConfirmModal } from "../../../shared/ui/ConfirmModal";
import { PageHeader } from "../../../shared/ui/PageHeader";
import { Tabs, type TabItem } from "../../../shared/ui/Tabs";
import { GymSettingsForm } from "../components/GymSettingsForm";
import { MembershipsSettingsForm } from "../components/MembershipsSettingsForm";
import { PrivacySettingsForm } from "../components/PrivacySettingsForm";
import styles from "./ConfigPage.module.css";

const TABS: TabItem[] = [
  { id: "gimnasio", label: "Gimnasio" },
  { id: "privacidad", label: "Privacidad" },
  { id: "membresias", label: "Membresías" },
];

type DirtyHandler = (dirty: boolean) => void;

function sectionFor(id: string, onDirtyChange: DirtyHandler): ReactNode {
  if (id === "privacidad") return <PrivacySettingsForm onDirtyChange={onDirtyChange} />;
  if (id === "membresias") return <MembershipsSettingsForm onDirtyChange={onDirtyChange} />;
  return <GymSettingsForm onDirtyChange={onDirtyChange} />;
}

export default function ConfigPage() {
  const [dirty, setDirty] = useState(false);
  // Se marca al pulsar "Descartar cambios"; ConfirmModal llama a onClose justo después.
  const discard = useRef(false);
  const isSignedIn = useSession().status === "authenticated";

  const shouldBlock = useCallback<BlockerFunction>(
    ({ currentLocation, nextLocation }) =>
      isSignedIn && dirty && (currentLocation.pathname !== nextLocation.pathname || currentLocation.search !== nextLocation.search),
    [dirty, isSignedIn],
  );
  const blocker = useBlocker(shouldBlock);

  useBeforeUnload(
    useCallback(
      (event: BeforeUnloadEvent) => {
        if (dirty) event.preventDefault();
      },
      [dirty],
    ),
  );

  const closeModal = (): void => {
    const confirmed = discard.current;
    discard.current = false;
    if (blocker.state !== "blocked") return;
    if (confirmed) {
      setDirty(false);
      blocker.proceed();
    } else {
      blocker.reset();
    }
  };

  return (
    <div className={styles.page}>
      <PageHeader title="Configuración del gimnasio" description="Cada sección se guarda por separado y queda en auditoría." />
      <Tabs label="Secciones de la configuración" tabs={TABS}>
        {(active) => sectionFor(active, setDirty)}
      </Tabs>
      <ConfirmModal
        open={blocker.state === "blocked"}
        title="Tienes cambios sin guardar. ¿Descartarlos?"
        consequence="Si sigues, se pierden los cambios de esta sección."
        confirmLabel="Descartar cambios"
        cancelLabel="Volver"
        tone="danger"
        onConfirm={() => {
          discard.current = true;
        }}
        onClose={closeModal}
      />
    </div>
  );
}
