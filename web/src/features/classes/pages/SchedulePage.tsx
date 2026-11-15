// S7-F2 · US-155 y US-158 (front): /clases/horario (Horario.html), solo admin (`classes.schedule`).
// - PageHeader «Clases» con «+ Franja horaria»; pestañas de Clases; nota «El horario es la plantilla».
// - DataTable de franjas (paginada en el servidor): Hora, Días «L M X J V», Coach («Open box · sin coach»), Cupo,
//   Duración, Estado («Activa» o «Pausada», siempre con texto) y Acciones (Editar, Cancelar sesiones futuras).
// - Editar y «+ Franja horaria» abren SlotPanel; «Cancelar sesiones futuras» abre CancelFutureModal y, al terminar,
//   un aviso dice cuántas sesiones se cancelaron.
// - Estados: carga, vacío (guía a crear la primera), error con Reintentar, 403 y permiso denegado (el coach no ve el
//   Horario: la ruta es solo admin y la página no pide nada si llega otro rol).
// DESIGN-GAP: Horario.html trae un aviso «Al guardar se regeneran las sesiones futuras» (BRECHAS 15.5, Q23): un cambio
// nunca toca sesiones ya generadas; el aviso del panel lo dice con otras palabras.
import { useState } from "react";
import { useCan } from "../../../core/auth/useCan";
import { formatCount } from "../../../core/i18n/format";
import { useListParams } from "../../../shared/hooks/useListParams";
import { Button } from "../../../shared/ui/Button";
import { DataTable, type Column } from "../../../shared/ui/DataTable";
import { MessagePage } from "../../../shared/ui/MessagePage";
import { StatusTag } from "../../../shared/ui/StatusTag";
import { PageHeader } from "../../../shared/ui/PageHeader";
import { Pagination } from "../../../shared/ui/Pagination";
import { useSlots, type SlotView } from "../api";
import { slotsListError } from "../classErrors";
import { CancelFutureModal } from "../components/CancelFutureModal";
import { CLASSES_PATH, ClassesTabs } from "../components/ClassesTabs";
import { SlotPanel } from "../components/SlotPanel";
import { weekdaysText } from "../schemas";
import styles from "./SchedulePage.module.css";

export const SCHEDULE_EMPTY = "Todavía no hay franjas. El horario semanal es la plantilla de las sesiones.";
export const SCHEDULE_PAST_END = "Esta página ya no tiene franjas.";
export const SCHEDULE_NOTE = "El horario es la plantilla. Cada franja dice qué días se repite, a qué hora, con qué coach y con qué cupo. De aquí salen las sesiones automáticamente.";
export const OPEN_BOX = "Open box · sin coach";

interface RowActionsProps {
  slot: SlotView;
  onEdit: (slot: SlotView) => void;
  onCancelFuture: (slot: SlotView) => void;
}

function RowActions({ slot, onEdit, onCancelFuture }: RowActionsProps) {
  return (
    <span className={styles.actions}>
      <Button
        variant="ghost"
        aria-label={`Editar la franja de las ${slot.start_time}`}
        onClick={() => {
          onEdit(slot);
        }}
      >
        Editar
      </Button>
      <Button
        variant="ghost"
        aria-label={`Cancelar sesiones futuras de la franja de las ${slot.start_time}`}
        onClick={() => {
          onCancelFuture(slot);
        }}
      >
        Cancelar sesiones futuras
      </Button>
    </span>
  );
}

export function cancelledNotice(time: string, count: number): string {
  if (count === 0) return `La franja de las ${time} no tenía sesiones futuras por cancelar.`;
  const sessions = count === 1 ? "1 sesión futura" : `${formatCount(count)} sesiones futuras`;
  return `Se cancelaron ${sessions} de la franja de las ${time}. La franja sigue activa.`;
}

export default function SchedulePage() {
  const canSchedule = useCan("classes.schedule");
  const list = useListParams({ localQuery: true });
  const { limit, offset } = list.params;
  const slots = useSlots({ limit, offset }, canSchedule);
  const [editing, setEditing] = useState<SlotView | null>(null);
  const [creating, setCreating] = useState(false);
  const [cancelling, setCancelling] = useState<SlotView | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  if (!canSchedule) {
    return (
      <MessagePage
        title="No tienes permiso para ver el horario"
        message="El horario semanal solo lo ve un administrador. Si lo necesitas, pídeselo a uno."
        linkLabel="Ir a Clases"
        linkTo={CLASSES_PATH}
      />
    );
  }

  const page = slots.data;
  const settled = slots.isPlaceholderData ? undefined : page;
  const isPastEnd = settled !== undefined && settled.total > 0 && settled.items.length === 0;
  const openNew = (): void => {
    setCreating(true);
  };

  const columns: Column<SlotView>[] = [
    { key: "start_time", header: "Hora", render: (row) => <b className={styles.number}>{row.start_time}</b> },
    { key: "weekdays", header: "Días", render: (row) => weekdaysText(row.weekdays) },
    { key: "coach", header: "Coach", render: (row) => row.coach_name ?? OPEN_BOX },
    { key: "capacity", header: "Cupo", render: (row) => <span className={styles.number}>{formatCount(row.capacity)}</span> },
    { key: "duration_min", header: "Duración", render: (row) => <span className={styles.number}>{`${String(row.duration_min)} min`}</span> },
    { key: "is_active", header: "Estado", render: (row) => <StatusTag slot={row.is_active ? "active" : "paused"} /> },
    {
      key: "actions",
      header: "Acción",
      align: "end",
      wide: true,
      render: (row) => <RowActions slot={row} onEdit={setEditing} onCancelFuture={setCancelling} />,
    },
  ];

  return (
    <div className={styles.page}>
      <PageHeader title="Clases" actions={[{ id: "new-slot", label: "+ Franja horaria", variant: "primary", onClick: openNew }]} />
      <ClassesTabs>
        <div className={styles.content}>
          <p className={styles.note}>{SCHEDULE_NOTE}</p>
          {notice ? (
            <p className={styles.notice} role="status">
              {notice}
            </p>
          ) : null}
          <DataTable
            caption="Horario semanal"
            columns={columns}
            rows={page?.items}
            total={page?.total}
            limit={limit}
            rowKey={(row) => row.id}
            isLoading={slots.isLoading || slots.isPlaceholderData}
            error={slotsListError(slots.error)}
            onRetry={() => {
              void slots.refetch();
            }}
            emptyMessage={isPastEnd ? SCHEDULE_PAST_END : SCHEDULE_EMPTY}
            emptyAction={
              isPastEnd ? (
                <Button
                  variant="secondary"
                  onClick={() => {
                    list.setPage(1);
                  }}
                >
                  Ir a la primera página
                </Button>
              ) : (
                <Button onClick={openNew}>Crear la primera franja</Button>
              )
            }
          />
          {page && page.total > 0 ? <Pagination total={page.total} limit={limit} offset={offset} onPageChange={list.setPage} onLimitChange={list.setLimit} /> : null}
        </div>
      </ClassesTabs>
      <SlotPanel
        key="new"
        open={creating}
        slot={null}
        onClose={() => {
          setCreating(false);
        }}
        onSaved={(slot) => {
          setNotice(`Franja de las ${slot.start_time} creada.`);
        }}
      />
      {editing ? (
        <SlotPanel
          key={editing.id}
          open
          slot={editing}
          onClose={() => {
            setEditing(null);
          }}
          onSaved={(slot) => {
            setNotice(`Franja de las ${slot.start_time} guardada.`);
          }}
          onCancelFuture={(slot) => {
            setEditing(null);
            setCancelling(slot);
          }}
        />
      ) : null}
      <CancelFutureModal
        slot={cancelling}
        onClose={() => {
          setCancelling(null);
        }}
        onDone={(slot, count) => {
          setNotice(cancelledNotice(slot.start_time, count));
        }}
      />
    </div>
  );
}
