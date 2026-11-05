// S5-F2 · US-120 (front): pestaña "Plantillas" de /avisos/reglas (Notif_Reglas.html). Tabla con el nombre,
// el asunto y la fecha del último cambio; el admin crea y edita en TemplateEditor y el coach solo la lee
// ("Ver"). Paginada en el servidor.
import { useState } from "react";
import { formatDate } from "../../../core/i18n/format";
import { useListParams } from "../../../shared/hooks/useListParams";
import { Button } from "../../../shared/ui/Button";
import { DataTable, type Column } from "../../../shared/ui/DataTable";
import { Pagination } from "../../../shared/ui/Pagination";
import { useTemplates } from "../adminApi";
import { templatesListError } from "../adminErrors";
import type { TemplateRowView } from "../adminSchemas";
import styles from "./AdminTabs.module.css";
import { TemplateEditor } from "./TemplateEditor";

export interface TemplatesTabProps {
  canEdit: boolean;
  onNotice: (text: string) => void;
}

export const TEMPLATES_EMPTY = "Todavía no hay plantillas";

export function TemplatesTab({ canEdit, onNotice }: TemplatesTabProps) {
  const list = useListParams({ filters: [] });
  const { limit, offset } = list.params;
  const templates = useTemplates({ limit, offset });
  const [selected, setSelected] = useState<TemplateRowView | null>(null);
  const [creating, setCreating] = useState(false);
  const page = templates.data;
  const settled = templates.isPlaceholderData ? undefined : page;
  const isPastEnd = settled !== undefined && settled.total > 0 && settled.items.length === 0;

  const columns: Column<TemplateRowView>[] = [
    { key: "name", header: "Plantilla", render: (row) => <b>{row.name}</b> },
    { key: "subject", header: "Asunto", render: (row) => row.subject },
    { key: "updated_at", header: "Actualizada", render: (row) => formatDate(row.updated_at) },
    {
      key: "actions",
      header: "Acción",
      align: "end",
      wide: true,
      render: (row) => (
        <Button
          variant="ghost"
          aria-label={canEdit ? `Editar plantilla ${row.name}` : `Ver plantilla ${row.name}`}
          onClick={() => {
            setSelected(row);
          }}
        >
          {canEdit ? "Editar" : "Ver"}
        </Button>
      ),
    },
  ];

  const emptyAction = isPastEnd ? (
    <Button
      variant="secondary"
      onClick={() => {
        list.setPage(1);
      }}
    >
      Ir a la primera página
    </Button>
  ) : canEdit ? (
    <Button
      onClick={() => {
        setCreating(true);
      }}
    >
      Crear la primera plantilla
    </Button>
  ) : null;

  return (
    <div className={styles.tab}>
      {canEdit ? (
        <div className={styles.toolbar}>
          <Button
            onClick={() => {
              setCreating(true);
            }}
          >
            Nueva plantilla
          </Button>
        </div>
      ) : null}
      <DataTable
        caption="Plantillas"
        columns={columns}
        rows={settled?.items}
        total={settled?.total}
        limit={limit}
        rowKey={(row) => row.id}
        isLoading={templates.isLoading || templates.isPlaceholderData}
        error={templatesListError(templates.error)}
        onRetry={() => {
          void templates.refetch();
        }}
        emptyMessage={isPastEnd ? "Esta página ya no tiene plantillas." : TEMPLATES_EMPTY}
        emptyAction={emptyAction}
      />
      {settled && settled.total > 0 ? <Pagination total={settled.total} limit={limit} offset={offset} onPageChange={list.setPage} onLimitChange={list.setLimit} /> : null}
      {canEdit && creating ? (
        <TemplateEditor
          open
          onClose={() => {
            setCreating(false);
          }}
          onSaved={(name) => {
            onNotice(`Plantilla creada: ${name}.`);
          }}
        />
      ) : null}
      {selected ? (
        <TemplateEditor
          key={selected.id}
          open
          template={selected}
          readOnly={!canEdit}
          onClose={() => {
            setSelected(null);
          }}
          onSaved={(name) => {
            onNotice(`Plantilla guardada: ${name}.`);
          }}
        />
      ) : null}
    </div>
  );
}
