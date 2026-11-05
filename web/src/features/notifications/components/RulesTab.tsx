// S5-F2 · US-121 (front): pestaña "Reglas" de /avisos/reglas (Notif_Reglas.html). Tabla con la regla, cuándo
// avisa, su plantilla, el canal y el estado; el admin crea y edita en un SidePanel (RuleForm) y el coach solo
// mira (sin "Nueva regla", sin la columna "Acción"). Paginada en el servidor.
import { useMemo, useState } from "react";
import { useListParams } from "../../../shared/hooks/useListParams";
import { Button } from "../../../shared/ui/Button";
import { cx } from "../../../shared/ui/cx";
import { DataTable, type Column } from "../../../shared/ui/DataTable";
import { Pagination } from "../../../shared/ui/Pagination";
import { useRules, useTemplateOptions } from "../adminApi";
import { rulesListError } from "../adminErrors";
import { CHANNEL_LABELS, ruleWhenText, type RuleRowView } from "../adminSchemas";
import styles from "./AdminTabs.module.css";
import { RuleForm } from "./RuleForm";

export interface RulesTabProps {
  canEdit: boolean;
  onNotice: (text: string) => void;
}

export const RULES_EMPTY = "Todavía no hay reglas";

export function RulesTab({ canEdit, onNotice }: RulesTabProps) {
  const list = useListParams({ filters: [] });
  const { limit, offset } = list.params;
  const rules = useRules({ limit, offset });
  const templates = useTemplateOptions();
  const [editing, setEditing] = useState<RuleRowView | null>(null);
  const [creating, setCreating] = useState(false);
  const page = rules.data;
  const settled = rules.isPlaceholderData ? undefined : page;
  const templateItems = useMemo(() => templates.data?.items ?? [], [templates.data]);
  const templateNames = useMemo(() => new Map(templateItems.map((t) => [t.id, t.name])), [templateItems]);
  const isPastEnd = settled !== undefined && settled.total > 0 && settled.items.length === 0;

  const columns: Column<RuleRowView>[] = [
    { key: "name", header: "Regla", render: (row) => <b>{row.name}</b> },
    { key: "when", header: "Cuándo", render: (row) => ruleWhenText(row) },
    { key: "template", header: "Plantilla", render: (row) => templateNames.get(row.template_id) ?? "—" },
    { key: "channel", header: "Canal", render: (row) => CHANNEL_LABELS[row.channel] },
    { key: "is_active", header: "Estado", render: (row) => <span className={cx(styles.tag, !row.is_active && styles.paused)}>{row.is_active ? "Activa" : "Pausada"}</span> },
    ...(canEdit
      ? [
          {
            key: "actions",
            header: "Acción",
            align: "end" as const,
            wide: true,
            render: (row: RuleRowView) => (
              <Button
                variant="ghost"
                aria-label={`Editar regla ${row.name}`}
                onClick={() => {
                  setEditing(row);
                }}
              >
                Editar
              </Button>
            ),
          },
        ]
      : []),
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
      Crear la primera regla
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
            Nueva regla
          </Button>
        </div>
      ) : null}
      <DataTable
        caption="Reglas"
        columns={columns}
        rows={settled?.items}
        total={settled?.total}
        limit={limit}
        rowKey={(row) => row.id}
        isLoading={rules.isLoading || rules.isPlaceholderData}
        error={rulesListError(rules.error)}
        onRetry={() => {
          void rules.refetch();
        }}
        emptyMessage={isPastEnd ? "Esta página ya no tiene reglas." : RULES_EMPTY}
        emptyAction={emptyAction}
      />
      {settled && settled.total > 0 ? <Pagination total={settled.total} limit={limit} offset={offset} onPageChange={list.setPage} onLimitChange={list.setLimit} /> : null}
      {canEdit && creating ? (
        <RuleForm
          open
          templates={templateItems}
          onClose={() => {
            setCreating(false);
          }}
          onSaved={(name) => {
            onNotice(`Regla creada: ${name}.`);
          }}
        />
      ) : null}
      {canEdit && editing ? (
        <RuleForm
          key={editing.id}
          open
          rule={editing}
          templates={templateItems}
          onClose={() => {
            setEditing(null);
          }}
          onSaved={(name) => {
            onNotice(`Regla guardada: ${name}.`);
          }}
        />
      ) : null}
    </div>
  );
}
