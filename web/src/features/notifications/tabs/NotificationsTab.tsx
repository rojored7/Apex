// S5-F3 · US-123 y US-130 (front): pestaña Avisos de la ficha (/socios/:id/avisos), admin y coach
// (`notifications.view`). Ruta hija de /socios/:id (S3-D65, E3): la ficha la pinta en su <Outlet /> y le
// pasa el socio por el contexto (useMemberTab, shared/data); esta feature no importa features/members y la
// ficha la carga de forma diferida (lazy en la tabla de rutas).
// - Canales de aviso (ChannelPreferences): interruptores de correo (opt-in) y WhatsApp manual.
// - Historial de avisos: GET /members/{id}/notifications paginado en el servidor (25, 50 o 100; `offset` en
//   la URL), con "Ver mensaje". Un socio dado de baja (N-20) tiene las preferencias de solo lectura.
// - Estados: carga, vacío ("Este socio todavía no tiene avisos."), error con Reintentar y página fuera de rango.
// DESIGN-GAP: Socio_Ficha.html no dibuja el contenido de la pestaña (solo enlaza a Notif_Historial.html):
// el historial es la misma tabla de /avisos/historial filtrada por socio, sin la columna "Socio".
import { useMemo, useState } from "react";
import { useParams } from "react-router";
import { formatDateTime } from "../../../core/i18n/format";
import { useMemberTab } from "../../../shared/data/members";
import { useListParams } from "../../../shared/hooks/useListParams";
import { Button } from "../../../shared/ui/Button";
import { cx } from "../../../shared/ui/cx";
import { DataTable, type Column } from "../../../shared/ui/DataTable";
import { Pagination } from "../../../shared/ui/Pagination";
import { useRuleOptions } from "../adminApi";
import { CHANNEL_LABELS, STATUS_LABELS } from "../adminSchemas";
import { ChannelPreferences } from "../components/ChannelPreferences";
import { MessagePanel } from "../components/MessagePanel";
import { detailText, whenOf, whoText } from "../historyView";
import { useMemberNotifications } from "../memberApi";
import { memberHistoryError } from "../memberErrors";
import type { NotificationRowView } from "../schemas";
import styles from "./NotificationsTab.module.css";

export const MEMBER_NOTIFICATIONS_EMPTY = "Este socio todavía no tiene avisos.";
const PAST_END = "Esta página ya no tiene avisos.";

export default function NotificationsTab() {
  const member = useMemberTab();
  const { id: routeId = "" } = useParams();
  const memberId = member?.id ?? routeId;
  const readOnly = member?.deleted_at != null;
  const list = useListParams({ filters: [] });
  const { limit, offset } = list.params;
  const history = useMemberNotifications(memberId, { limit, offset });
  const rules = useRuleOptions();
  const [viewing, setViewing] = useState<NotificationRowView | null>(null);
  const page = history.data;
  const settled = history.isPlaceholderData ? undefined : page;
  const isPastEnd = settled !== undefined && settled.total > 0 && settled.items.length === 0;
  const ruleNames = useMemo(() => new Map((rules.data?.items ?? []).map((rule) => [rule.id, rule.name])), [rules.data]);

  const columns: Column<NotificationRowView>[] = [
    { key: "when", header: "Fecha y hora", render: (row) => formatDateTime(whenOf(row)) },
    { key: "rule", header: "Regla", render: (row) => ruleNames.get(row.rule_id) ?? "—" },
    { key: "channel", header: "Canal", render: (row) => CHANNEL_LABELS[row.channel] },
    { key: "status", header: "Resultado", render: (row) => <span className={cx(styles.tag, row.status === "sent" && styles.ok)}>{STATUS_LABELS[row.status]}</span> },
    { key: "detail", header: "Detalle", render: (row) => detailText(row) },
    { key: "who", header: "Quién", render: (row) => whoText(row) },
    {
      key: "actions",
      header: "Acción",
      align: "end",
      wide: true,
      render: (row) => (
        <Button
          variant="ghost"
          aria-label={`Ver mensaje de ${row.member_name}`}
          onClick={() => {
            setViewing(row);
          }}
        >
          Ver mensaje
        </Button>
      ),
    },
  ];

  return (
    <div className={styles.tab}>
      <ChannelPreferences memberId={memberId} readOnly={readOnly} />
      <div className={styles.section}>
        <h2 className={styles.sectionTitle}>Historial de avisos</h2>
        <DataTable
          caption="Historial de avisos del socio"
          columns={columns}
          rows={settled?.items}
          total={settled?.total}
          limit={limit}
          rowKey={(row) => row.id}
          isLoading={history.isLoading || history.isPlaceholderData}
          error={memberHistoryError(history.error)}
          onRetry={() => {
            void history.refetch();
          }}
          emptyMessage={isPastEnd ? PAST_END : MEMBER_NOTIFICATIONS_EMPTY}
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
            ) : null
          }
        />
        {settled && settled.total > 0 ? <Pagination total={settled.total} limit={limit} offset={offset} onPageChange={list.setPage} onLimitChange={list.setLimit} /> : null}
      </div>
      <MessagePanel
        notification={viewing}
        onClose={() => {
          setViewing(null);
        }}
      />
    </div>
  );
}
