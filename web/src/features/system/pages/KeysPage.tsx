// S6-F2 · US-143 a US-146 (Llaves.html, solo admin): /sistema/llaves. Una sola meta: ver y rotar las llaves.
// - PageHeader «Llaves de cifrado»; «Exportar CBOM» queda junto al encabezado (ExportCbomButton necesita su
//   propio aviso de error, que una PageAction no puede llevar).
// - Resumen (KeysSummaryCards): llaves activas, «Rotación vencida (30 días)» (DESIGN-GAP, ver el componente),
//   recifrados en curso, operaciones hoy y «Proveedor activo».
// - Tres pestañas con la elegida en la URL (`?tab=`): Inventario (KeysInventory, con «Rotar»), Bitácora
//   (CryptoOpsLog) y Trabajos (CryptoJobs, con refresco mientras haya uno en curso). Rotar salta a Trabajos.
// - Sin permiso: la ruta es de `crypto.manage` (solo admin) y cada endpoint vuelve a verificarlo; un 403 se
//   explica en cada pestaña.
// DESIGN-GAP: «Verificar estado del proveedor» (Llaves.html) no tiene endpoint propio: el estado del proveedor
//   llega en `summary.provider` con cada lectura y el aviso global de custodio (CustodyNotice) cubre el sellado.
// DESIGN-GAP: las pestañas se llaman Inventario, Bitácora y Trabajos (el diseño: «Bitácora de operaciones» y
//   «Tareas de recifrado»); los nombres cortos caben en celular y coinciden con las tablas.
import { PageHeader } from "../../../shared/ui/PageHeader";
import { Tabs, type TabItem } from "../../../shared/ui/Tabs";
import { CryptoJobs } from "../components/CryptoJobs";
import { CryptoOpsLog } from "../components/CryptoOpsLog";
import { ExportCbomButton } from "../components/ExportCbomButton";
import { KeysInventory } from "../components/KeysInventory";
import { KeysSummaryCards } from "../components/KeysSummaryCards";
import styles from "./KeysPage.module.css";

const TABS: TabItem[] = [
  { id: "inventario", label: "Inventario" },
  { id: "bitacora", label: "Bitácora" },
  { id: "trabajos", label: "Trabajos" },
];

function Panel({ tab }: { tab: string }) {
  if (tab === "bitacora") return <CryptoOpsLog />;
  if (tab === "trabajos") return <CryptoJobs />;
  return <KeysInventory />;
}

export default function KeysPage() {
  return (
    <div className={styles.page}>
      <PageHeader title="Llaves de cifrado" />
      <div className={styles.toolbar}>
        <p className={styles.note}>Este inventario es el CBOM del sistema: la lista de algoritmos y llaves que protegen los datos.</p>
        <ExportCbomButton />
      </div>
      <KeysSummaryCards />
      <Tabs label="Secciones de llaves" tabs={TABS}>
        {(active) => <Panel tab={active} />}
      </Tabs>
    </div>
  );
}
