// S8-F1 · US-165 y US-166 (front): /movimientos (Movimientos.html), admin y coach (`movements.view`).
// - PageHeader «Movimientos» y dos pestañas por `?tab=`: «Movimientos» (por defecto) y «Benchmarks» (S8-D6).
// - Cada pestaña es una lista paginada en el servidor con su panel de alta y edición (MovementsList, BenchmarksList).
// - Permiso denegado: quien no puede ver el catálogo (el socio) no pide nada.
// DESIGN-GAP (S8-D5, S8-D6): alias, «lb», «Tipos de récord» y la pestaña Benchmarks no están en el contrato o en el diseño.
import { useCan } from "../../../core/auth/useCan";
import { MessagePage } from "../../../shared/ui/MessagePage";
import { PageHeader } from "../../../shared/ui/PageHeader";
import { Tabs, type TabItem } from "../../../shared/ui/Tabs";
import { BenchmarksList } from "../components/BenchmarksList";
import { MovementsList } from "../components/MovementsList";
import styles from "./MovementsPage.module.css";

const TABS: TabItem[] = [
  { id: "movimientos", label: "Movimientos" },
  { id: "benchmarks", label: "Benchmarks" },
];

export default function MovementsPage() {
  const canView = useCan("movements.view");

  if (!canView) {
    return <MessagePage title="No tienes permiso para ver los movimientos" message="El catálogo de movimientos lo ven el administrador y los coaches. Si lo necesitas, pídeselo a un administrador." linkLabel="Ir al inicio" linkTo="/" />;
  }

  return (
    <div className={styles.page}>
      <PageHeader title="Movimientos" />
      <Tabs label="Secciones de Movimientos" tabs={TABS}>
        {(activeId) => (activeId === "benchmarks" ? <BenchmarksList /> : <MovementsList />)}
      </Tabs>
    </div>
  );
}
