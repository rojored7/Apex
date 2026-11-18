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
import { useParams, useSearchParams } from "react-router";
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

// Filtros propios de cada subpestaña: no pasan a la siguiente (`bm` es de Benchmarks).
const SUBTAB_PARAMS = ["kind", "invalidated", "bm"] as const;

export const SAVED_NOTICE = "Medidas guardadas.";
export const RECORD_SAVED_NOTICE = "Récord guardado.";
export const METRIC_VOIDED_NOTICE = "Medición anulada.";
export const RECORD_INVALIDATED_NOTICE = "Récord invalidado.";
const DEFAULT_SUBTAB = ATHLETE_SUBTABS[0]?.id ?? "";

interface SubtabProps {
  active: string;
  memberId: string;
  memberDeleted: boolean;
  memberUnknown: boolean;
  onNotice: (text: string) => void;
}

function Subtab({ active, memberId, memberDeleted, memberUnknown, onNotice }: SubtabProps) {
  if (active === "medidas") {
    return (
      <MetricsTab
        memberId={memberId}
        memberDeleted={memberDeleted}
        memberUnknown={memberUnknown}
        onVoided={() => {
          onNotice(METRIC_VOIDED_NOTICE);
        }}
      />
    );
  }
  if (active === "resumen") return <SummaryCards memberId={memberId} />;
  if (active === "rms") return <RmsTab memberId={memberId} />;
  if (active === "records") {
    return (
      <RecordsTab
        memberId={memberId}
        memberDeleted={memberDeleted}
        onInvalidated={() => {
          onNotice(RECORD_INVALIDATED_NOTICE);
        }}
      />
    );
  }
  return <BenchmarksTab memberId={memberId} />;
}

function AthleteTabContent({ memberId, member }: { memberId: string; member: MemberTabMember | null }) {
  // Sin la ficha cargada no se sabe si el socio está de baja: solo lectura (revisión S9-F2, seguridad L3).
  const memberDeleted = member === null || member.deleted_at !== null;
  const canWrite = useCan("athletes.write");
  const [panel, setPanel] = useState<"metric" | "record" | null>(null);
  // El aviso nace en una subpestaña y se va al cambiar de ella; el siguiente lo reemplaza (V7, M9).
  const [searchParams] = useSearchParams();
  const currentTab = searchParams.get("tab") ?? DEFAULT_SUBTAB;
  const [raised, setRaised] = useState<{ text: string; tab: string } | null>(null);
  const notice = raised !== null && raised.tab === currentTab ? raised.text : null;
  const setNotice = (text: string | null): void => {
    setRaised(text === null ? null : { text, tab: currentTab });
  };

  return (
    <div className={styles.tab}>
      <p role="status" aria-label="Avisos del atleta" className={notice === null ? styles.noticeSlot : styles.saved}>
        {notice}
      </p>
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
        {(active) => <Subtab active={active} memberId={memberId} memberDeleted={memberDeleted} memberUnknown={member === null} onNotice={setNotice} />}
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
