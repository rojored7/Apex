// S5-F2 · US-120 y US-121 (front): /avisos/reglas (Notif_Reglas.html), admin y coach. PageHeader "Avisos"
// con el enlace al historial y Tabs con la pestaña en ?tab= (Reglas y Plantillas). El admin crea y edita
// (`notifications.rules.edit`); el coach lee: sin "Nueva regla", sin "Editar" y con la nota de que solo un
// administrador las cambia. El aviso de "creada" o "guardada" se cierra con un botón.
// DESIGN-GAP: Notif_Reglas.html pone "Historial de envíos" como tercera pestaña; es otra pantalla
// (/avisos/historial) y aquí es un enlace del encabezado. Tampoco hay "Pausada" como acción de la fila:
// activar o pausar se hace al editar la regla ("Regla activa").
import { useState } from "react";
import { useCan } from "../../../core/auth/useCan";
import { Button } from "../../../shared/ui/Button";
import { PageHeader, type PageAction } from "../../../shared/ui/PageHeader";
import { Tabs, type TabItem } from "../../../shared/ui/Tabs";
import { RulesTab } from "../components/RulesTab";
import { TemplatesTab } from "../components/TemplatesTab";
import styles from "./RulesPage.module.css";

const TABS: TabItem[] = [
  { id: "reglas", label: "Reglas" },
  { id: "plantillas", label: "Plantillas" },
];

const HEADER_ACTIONS: PageAction[] = [{ id: "history", label: "Historial de envíos", href: "/avisos/historial" }];

export default function RulesPage() {
  const canEdit = useCan("notifications.rules.edit");
  const [notice, setNotice] = useState<string | null>(null);

  return (
    <div className={styles.page}>
      <PageHeader title="Avisos" actions={HEADER_ACTIONS} />
      <p className={styles.note}>
        Una regla dice cuándo avisar y con qué plantilla. El sistema las evalúa cada día a la hora configurada. Los canales que se intentan vienen de Configuración y de lo que cada socio tenga activo.
      </p>
      {canEdit ? null : <p className={styles.note}>Solo un administrador puede cambiar las reglas y las plantillas.</p>}
      {notice ? (
        <div role="status" className={styles.notice}>
          <span>{notice}</span>
          <Button
            variant="ghost"
            aria-label="Cerrar aviso"
            onClick={() => {
              setNotice(null);
            }}
          >
            Cerrar
          </Button>
        </div>
      ) : null}
      <Tabs label="Secciones de avisos" tabs={TABS}>
        {(active) => (active === "plantillas" ? <TemplatesTab canEdit={canEdit} onNotice={setNotice} /> : <RulesTab canEdit={canEdit} onNotice={setNotice} />)}
      </Tabs>
    </div>
  );
}
