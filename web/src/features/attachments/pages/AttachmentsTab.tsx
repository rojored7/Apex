// S6-F3 · US-150 (front): pestaña Adjuntos de la ficha (/socios/:id/adjuntos), admin y coach
// (`members.view`). Vive en features/attachments (S3-D65, como Avisos en notifications): es una ruta
// hija de /socios/:id que la ficha pinta en su <Outlet /> y le pasa el socio por el contexto.
// - GET /members/{id}/attachments paginada en el servidor (25, 50 o 100; `offset` en la URL), en el
//   orden del api (`created_at` descendente): tipo (con "Cifrado" si es sensible), fecha de Bogotá,
//   tamaño legible, quién subió (el nombre si el contrato lo trae; si no, el id corto) y "Descargar".
// - "Descargar" usa api.blob y a[download] (L-2). Con rol coach no aparece en `consent` ni `other` (M-6,
//   `attachments.download.restricted`): dice "Solo administradores"; el api vuelve a verificar y su 403 se muestra.
// - Estados: carga, vacío ("Este socio no tiene adjuntos" con "Editar socio" si se puede), error con
//   Reintentar, 404, 403, 429 y errores de descarga en un aviso con role="alert".
// DESIGN-GAP: Socio_Ficha.html solo enlaza la pestaña y dibuja una caja "Adjuntos" dentro de Datos; no
// dibuja la tabla ni la descarga. Se usa el patrón de tabla y paginación de las pestañas Membresías y Pagos.
// No hay botón "Subir archivo" aquí: la subida vive en el alta y la edición del socio (S6-F4).
import { useState } from "react";
import { Link, useParams } from "react-router";
import { useCan } from "../../../core/auth/useCan";
import { formatDateTime } from "../../../core/i18n/format";
import { useMemberTab } from "../../../shared/data/members";
import { useListParams } from "../../../shared/hooks/useListParams";
import buttonStyles from "../../../shared/ui/Button.module.css";
import { cx } from "../../../shared/ui/cx";
import { DataTable, type Column } from "../../../shared/ui/DataTable";
import { Pagination } from "../../../shared/ui/Pagination";
import { useMemberAttachments } from "../api";
import { attachmentsListError } from "../attachmentErrors";
import { AttachmentDownloadButton } from "../components/AttachmentDownloadButton";
import { formatBytes, kindLabel, uploaderText } from "../lib/attachmentText";
import type { AttachmentView } from "../schemas";
import styles from "./AttachmentsTab.module.css";

export { ATTACHMENT_MESSAGES } from "../attachmentErrors";
export const ATTACHMENTS_EMPTY = "Este socio no tiene adjuntos";
export const ATTACHMENTS_LOADING = "Cargando los adjuntos…";
export const RESTRICTED_NOTE = "Solo administradores";
const PAST_END = "Esta página ya no tiene adjuntos.";
const RESTRICTED_KINDS: ReadonlySet<AttachmentView["kind"]> = new Set(["consent", "other"]);

interface ColumnOptions {
  canDownloadRestricted: boolean;
  onError: (message: string | null) => void;
}

function columnsFor({ canDownloadRestricted, onError }: ColumnOptions): Column<AttachmentView>[] {
  return [
    {
      key: "kind",
      header: "Tipo",
      render: (row) => (
        <span className={styles.kind}>
          <span>{kindLabel(row.kind)}</span>
          {row.sensitive ? <span className={styles.sensitive}>Cifrado</span> : null}
        </span>
      ),
    },
    { key: "created_at", header: "Fecha", render: (row) => <span className={styles.nowrap}>{formatDateTime(row.created_at)}</span> },
    { key: "size_bytes", header: "Tamaño", render: (row) => <span className={styles.nowrap}>{formatBytes(row.size_bytes)}</span> },
    { key: "uploaded_by", header: "Subido por", render: (row) => uploaderText(row) },
    {
      key: "actions",
      header: "Acción",
      align: "end",
      render: (row) =>
        RESTRICTED_KINDS.has(row.kind) && !canDownloadRestricted ? <span className={styles.restricted}>{RESTRICTED_NOTE}</span> : <AttachmentDownloadButton attachment={row} onError={onError} />,
    },
  ];
}

export default function AttachmentsTab() {
  const { id = "" } = useParams();
  const member = useMemberTab();
  const list = useListParams({ filters: [] });
  const params = { limit: list.params.limit, offset: list.params.offset };
  const attachments = useMemberAttachments(id === "" ? null : id, params);
  const canDownloadRestricted = useCan("attachments.download.restricted");
  const canEdit = useCan("members.update");
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const columns = columnsFor({ canDownloadRestricted, onError: setDownloadError });

  if (attachments.data === undefined && !attachments.isError) {
    return (
      <p className={styles.loading} role="status">
        {ATTACHMENTS_LOADING}
      </p>
    );
  }
  const data = attachments.data;
  const isPastEnd = data !== undefined && data.total > 0 && data.items.length === 0;
  const showEdit = canEdit && member !== null && member.deleted_at === null;

  return (
    <div className={styles.tab}>
      {downloadError ? (
        <p role="alert" className={styles.alert}>
          {downloadError}
        </p>
      ) : null}
      <DataTable
        caption="Adjuntos del socio"
        columns={columns}
        rows={data?.items}
        total={data?.total}
        limit={params.limit}
        rowKey={(row) => row.id}
        isLoading={attachments.isPlaceholderData}
        error={attachmentsListError(attachments.error)}
        onRetry={() => {
          void attachments.refetch();
        }}
        emptyMessage={isPastEnd ? PAST_END : ATTACHMENTS_EMPTY}
        emptyAction={
          showEdit && !isPastEnd ? (
            <Link className={cx(buttonStyles.button, buttonStyles.secondary, buttonStyles.md)} to={`/socios/${id}/editar`}>
              Editar socio
            </Link>
          ) : undefined
        }
      />
      {data && data.total > 0 ? <Pagination total={data.total} limit={params.limit} offset={params.offset} onPageChange={list.setPage} onLimitChange={list.setLimit} /> : null}
    </div>
  );
}
