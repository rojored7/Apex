// S8-F3 · US-171 y US-172 (front): /wods/:id (WOD_Detalle.html), admin y coach (`wods.view`).
// - «El WOD», las sesiones que lo usan y tres pestañas por `?tab=`: Leaderboard (GET /wods/{id}/leaderboard), Todos los resultados
//   (GET /wods/{id}/results, con «Anular» solo para el admin) e Historial (E5: GET /audit, solo con `audit.view`).
// - Un WOD sin marca (`score_type = none`) no registra resultados: se dice y no hay pestañas.
// - Estados: carga, error con Reintentar, WOD inexistente, permiso denegado.
// DESIGN-GAP: «Ver en TV», «Por validar», «vs. su anterior», «PR» y «Veces hecho en el box» llegan con EP-24, EP-25 y F6.
import { useParams } from "react-router";
import { useCan } from "../../../core/auth/useCan";
import { formatCount, formatLongDate } from "../../../core/i18n/format";
import { Button } from "../../../shared/ui/Button";
import { MessagePage } from "../../../shared/ui/MessagePage";
import { PageHeader } from "../../../shared/ui/PageHeader";
import { Tabs, type TabItem } from "../../../shared/ui/Tabs";
import { AllResults } from "../components/AllResults";
import { Leaderboard } from "../components/Leaderboard";
import { WodHistory } from "../components/WodHistory";
import { WodSessions } from "../components/WodSessions";
import { WodSummary } from "../components/WodSummary";
import { wodLoadError } from "../wodFormErrors";
import { useWod } from "../wodsApi";
import styles from "./WodDetailPage.module.css";

export const NO_SCORE_MESSAGE = "Este WOD no registra resultados: es un WOD sin marca.";

export default function WodDetailPage() {
  const { id = "" } = useParams();
  const canView = useCan("wods.view");
  const canRecord = useCan("results.record");
  const canSeeHistory = useCan("audit.view");
  const query = useWod(canView ? id : undefined);
  const wod = query.data;

  if (!canView) {
    return <MessagePage title="No tienes permiso para ver los WODs" message="Los WODs los ven el administrador y los coaches. Si lo necesitas, pídeselo a un administrador." linkLabel="Ir al inicio" linkTo="/" />;
  }
  if (query.isPending) {
    return (
      <p role="status" className={styles.state}>
        Cargando el WOD…
      </p>
    );
  }
  if (query.isError || !wod) {
    return (
      <div className={styles.state}>
        <p role="alert">{wodLoadError(query.error)?.message}</p>
        <Button
          variant="secondary"
          onClick={() => {
            void query.refetch();
          }}
        >
          Reintentar
        </Button>
      </div>
    );
  }

  const scored = wod.score_type !== "none";
  const tabs: TabItem[] = [
    { id: "leaderboard", label: "Leaderboard" },
    { id: "todos", label: `Todos los resultados (${formatCount(wod.result_count)})` },
    ...(canSeeHistory ? [{ id: "historial", label: "Historial" }] : []),
  ];

  return (
    <div className={styles.page}>
      <PageHeader
        title={wod.title}
        description={`${wod.is_benchmark ? "Benchmark · " : ""}${formatLongDate(wod.date)} · ${formatCount(wod.result_count)} ${wod.result_count === 1 ? "resultado" : "resultados"}`}
        breadcrumbs={[{ label: "WODs", href: "/wods" }, { label: wod.title }]}
        actions={[{ id: "edit", label: "Editar", href: `/wods/${encodeURIComponent(wod.id)}/editar` }]}
      />
      <div className={styles.layout}>
        <div className={styles.side}>
          <WodSummary wod={wod} />
          <WodSessions wodId={wod.id} canRecord={canRecord && scored} />
        </div>
        <div className={styles.main}>
          {scored ? (
            <Tabs label="Resultados del WOD" tabs={tabs}>
              {(active) =>
                active === "todos" ? (
                  <AllResults wodId={wod.id} scoreType={wod.score_type} />
                ) : active === "historial" && canSeeHistory ? (
                  <WodHistory wodId={wod.id} />
                ) : (
                  <Leaderboard wodId={wod.id} scoreType={wod.score_type} />
                )
              }
            </Tabs>
          ) : (
            <p className={styles.note}>{NO_SCORE_MESSAGE}</p>
          )}
        </div>
      </div>
    </div>
  );
}
