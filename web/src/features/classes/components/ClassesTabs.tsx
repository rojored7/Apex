// S7-F2 y S7-F3 (front): las pestañas de Clases (Horario.html y Sesiones.html): Sesiones, Horario semanal y Asistencia
// por socio. Cada una es una ruta (`/clases`, `/clases/horario`, `/clases/asistencia`), así que la pestaña activa sale
// de la ruta (Tabs en modo `segment`).
// - «Horario semanal» solo la ve quien puede editar el horario (`classes.schedule`, admin); el coach no la tiene.
// - «Asistencia por socio» llega con S7-F5: hasta entonces se ve deshabilitada y lo dice.
import type { ReactNode } from "react";
import { useCan } from "../../../core/auth/useCan";
import { Tabs, type TabItem } from "../../../shared/ui/Tabs";

export const CLASSES_PATH = "/clases";

export interface ClassesTabsProps {
  /** El contenido de la pestaña activa (cada página pinta el suyo). */
  children: ReactNode;
}

export function ClassesTabs({ children }: ClassesTabsProps) {
  const canSchedule = useCan("classes.schedule");
  const tabs: TabItem[] = [
    { id: "sesiones", label: "Sesiones" },
    ...(canSchedule ? [{ id: "horario", label: "Horario semanal" }] : []),
    { id: "asistencia", label: "Asistencia por socio", disabledNote: "Próximamente" },
  ];
  return (
    <Tabs label="Secciones de Clases" tabs={tabs} urlMode="segment" basePath={CLASSES_PATH} indexId="sesiones">
      {() => children}
    </Tabs>
  );
}
