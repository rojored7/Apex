// S9-F1 · US-184 (Atleta_Perfil.html): pestaña Atleta de la ficha (/socios/:id/atleta), admin y coach (`athletes.view`). Ruta hija de
// /socios/:id (S3-D65, E3): la ficha la pinta en su <Outlet /> y le pasa el socio por el contexto (useMemberTab, shared/data); esta
// feature no importa features/members y la ficha la carga de forma diferida (lazy en la tabla de rutas).
// - Cinco subpestañas en píldoras con `?tab=`: Resumen (por defecto), Medidas corporales, RMs por movimiento, Récords y Benchmarks.
//   RMs y Récords son de S9-F2; Benchmarks (serie del socio con TrendChart) es de S9-F3.
// - S9-F2: «+ Registrar récord» (athletes.write, socio vivo) abre RecordPanel; un récord no es dato de salud: no exige la autorización de datos.
// - «+ Registrar medidas» (athletes.write) abre el panel; con el socio dado de baja no hay acciones (la ficha es de solo lectura, N-20).
// - H-1: si la ficha trae `data_consent_at: null`, el botón del panel nace deshabilitado con el enlace a la ficha.
// - Abrir la pestaña nunca pide un reveal: los valores se muestran de uno en uno con «Mostrar» (L-7).
// - Guardar avisa «Medidas guardadas.» (role=status, sin ningún valor). Con otro socio en la URL todo se monta de nuevo (key).
// DESIGN-GAP: «Exportar progreso» y «Laura (portal)» del diseño no están en el contrato.
import { useState } from "react";
import { useParams } from "react-router";
import { useCan } from "../../../core/auth/useCan";
import { useMemberTab, type MemberTabMember } from "../../../shared/data/members";
import { Button } from "../../../shared/ui/Button";
import { Tabs, type TabItem } from "../../../shared/ui/Tabs";
import { BenchmarksTab } from "../components/BenchmarksTab";
import { MetricPanel } from "../components/MetricPanel";
import { MetricsTab } from "../components/MetricsTab";
import { RecordPanel } from "../components/RecordPanel";
import { RecordsTab } from "../components/RecordsTab";
import { RmsTab } from "../components/RmsTab";
import { SummaryCards } from "../components/SummaryCards";
import styles from "./AthleteTab.module.css";

export const ATHLETE_SUBTABS: readonly TabItem[] = [
  { id: "resumen", label: "Resumen" },
  { id: "medidas", label: "Medidas corporales" },
  { id: "rms", label: "RMs por movimiento" },
  { id: "records", label: "Récords" },
  { id: "benchmarks", label: "Benchmarks" },
];

// Filtros propios de cada subpestaña: no pasan a la siguiente (`benchmark` es de Benchmarks).
const SUBTAB_PARAMS = ["kind", "invalidated", "benchmark"] as const;

export const SAVED_NOTICE = "Medidas guardadas.";
export const RECORD_SAVED_NOTICE = "Récord guardado.";

interface SubtabProps {
  active: string;
  memberId: string;
  memberDeleted: boolean;
}

function Subtab({ active, memberId, memberDeleted }: SubtabProps) {
  if (active === "medidas") return <MetricsTab memberId={memberId} memberDeleted={memberDeleted} />;
  if (active === "resumen") return <SummaryCards memberId={memberId} />;
  if (active === "rms") return <RmsTab memberId={memberId} />;
  if (active === "records") return <RecordsTab memberId={memberId} memberDeleted={memberDeleted} />;
  return <BenchmarksTab memberId={memberId} />;
}

function AthleteTabContent({ memberId, member }: { memberId: string; member: MemberTabMember | null }) {
  // Sin la ficha cargada no se sabe si el socio está de baja: solo lectura (revisión S9-F2, seguridad L3).
  const memberDeleted = member === null || member.deleted_at !== null;
  const canWrite = useCan("athletes.write");
  const [panel, setPanel] = useState<"metric" | "record" | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  return (
    <div className={styles.tab}>
      {notice ? (
        <p role="status" className={styles.saved}>
          {notice}
        </p>
      ) : null}
      {canWrite && !memberDeleted ? (
        <div className={styles.actions}>
          <Button
            variant="secondary"
            onClick={() => {
              setNotice(null);
              setPanel("record");
            }}
          >
            + Registrar récord
          </Button>
          <Button
            onClick={() => {
              setNotice(null);
              setPanel("metric");
            }}
          >
            + Registrar medidas
          </Button>
        </div>
      ) : null}
      <Tabs label="Secciones del atleta" variant="pills" tabs={[...ATHLETE_SUBTABS]} ownParams={SUBTAB_PARAMS}>
        {(active) => <Subtab active={active} memberId={memberId} memberDeleted={memberDeleted} />}
      </Tabs>
      <MetricPanel
        open={panel === "metric"}
        memberId={memberId}
        consentMissing={member?.data_consent_at === null}
        onClose={() => {
          setPanel(null);
        }}
        onSaved={() => {
          setPanel(null);
          setNotice(SAVED_NOTICE);
        }}
      />
      <RecordPanel
        open={panel === "record"}
        memberId={memberId}
        onClose={() => {
          setPanel(null);
        }}
        onSaved={() => {
          setPanel(null);
          setNotice(RECORD_SAVED_NOTICE);
        }}
      />
    </div>
  );
}

export default function AthleteTab() {
  const member = useMemberTab();
  const { id: routeId = "" } = useParams();
  const memberId = member?.id ?? routeId;
  // key: con otro socio (la URL cambia con la pestaña abierta) se descarta todo el estado: claros, panel y aviso.
  return <AthleteTabContent key={memberId} memberId={memberId} member={member} />;
}
