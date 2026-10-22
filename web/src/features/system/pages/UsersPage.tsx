// S2-F4a · US-046 y US-047 (front): /sistema/usuarios (Usuarios.html), solo admin.
// - PageHeader "Usuarios del sistema" con el total y "Nuevo usuario del equipo" (NewUserPanel).
// - FilterBar: búsqueda por correo, rol y estado. S2-D41 (M-8): la búsqueda vive en estado
//   local con la espera de 300 ms de FilterBar y nunca en la URL; en la URL quedan rol,
//   estado, limit y offset (useListParams con localQuery). Un valor de filtro desconocido en
//   la URL no viaja al api.
// - DataTable: correo (enlace), rol, StatusTag de cuenta, último acceso en hora de Bogotá y
//   sesiones abiertas. Estados de carga, vacío, error (con Reintentar) y sin permiso (403).
// DESIGN-GAP:
// - Usuarios.html tiene columna "Usuario" con el nombre: auth.users no tiene nombre (S2-D17),
//   la tabla empieza por el correo hasta US-110.
// - El rol va como texto: el kit no tiene la píldora de rol (`w-tag`) de la pantalla.
// - La columna "Acción" (Editar) y el panel de edición llegan con S2-F4b; el enlace del correo
//   ya apunta a `?usuario=<id>`, que es donde F4b abre ese panel.
// - El filtro "Equipo (admin y coach)" no existe en el api (`role` es un solo valor).
// - El orden es el del api (correo ascendente, US-046 criterio 8): GET /users no acepta `sort`.
import { useMemo, useState } from "react";
import { ApiError, GENERIC_MESSAGES, isApiError } from "../../../core/api/errors";
import { ROLE_LABELS, ROLES, type Role } from "../../../core/auth/permissions";
import { formatCount, formatDateTime } from "../../../core/i18n/format";
import { useListParams } from "../../../shared/hooks/useListParams";
import { Button } from "../../../shared/ui/Button";
import { DataTable, type Column } from "../../../shared/ui/DataTable";
import { FilterBar } from "../../../shared/ui/FilterBar";
import { PageHeader } from "../../../shared/ui/PageHeader";
import { Pagination } from "../../../shared/ui/Pagination";
import { ACCOUNT_LABELS, type AccountStatusView } from "../../../shared/ui/statusLabel";
import { StatusTag } from "../../../shared/ui/StatusTag";
import { useUsers, type UsersParams } from "../api";
import { NewUserPanel } from "../components/NewUserPanel";
import { ACCOUNT_STATUSES, type UserRowView } from "../schemas";
import { userHref } from "../userLinks";
import styles from "./UsersPage.module.css";

const FILTERS = ["role", "status"] as const;
type UsersFilter = (typeof FILTERS)[number];

export const USERS_EMPTY = "No hay usuarios con estos filtros";
export const USERS_MESSAGES = {
  forbidden: "No tienes permiso para ver los usuarios. Si lo necesitas, pídeselo a un administrador.",
  failed: "No pudimos cargar los usuarios. Intenta de nuevo en un momento.",
} as const;

const HTTP_FORBIDDEN = 403;


/** El primer valor de la URL si es uno de los permitidos; si no, ninguno. */
function pickOne<T extends string>(values: readonly string[], allowed: readonly T[]): T | undefined {
  const [first] = values;
  return allowed.find((value) => value === first);
}

/** El error de la lista en palabras de la pantalla ("qué pasó y qué hacer"). */
function listError(error: unknown): ApiError | null {
  if (!error) return null;
  if (!isApiError(error)) return new ApiError({ status: 0, code: "unknown", message: USERS_MESSAGES.failed });
  if (error.code === "invalid_response") return error;
  if (error.status === 0) return new ApiError({ status: 0, code: error.code, message: error.code === "timeout" ? GENERIC_MESSAGES.timeout : GENERIC_MESSAGES.network_error });
  const message = error.status === HTTP_FORBIDDEN ? USERS_MESSAGES.forbidden : USERS_MESSAGES.failed;
  return new ApiError({ status: error.status, code: error.code, message });
}

const COLUMNS: Column<UserRowView>[] = [
  { key: "email", header: "Correo", render: (row) => row.email },
  { key: "role", header: "Rol", render: (row) => ROLE_LABELS[row.role] },
  { key: "status", header: "Estado", render: (row) => <StatusTag account={row.status} /> },
  { key: "last_login_at", header: "Último acceso", render: (row) => (row.last_login_at ? formatDateTime(row.last_login_at) : "Nunca") },
  { key: "active_sessions", header: "Sesiones abiertas", align: "end", render: (row) => formatCount(row.active_sessions) },
];

const ROLE_OPTIONS = ROLES.map((role) => ({ value: role, label: ROLE_LABELS[role] }));
const STATUS_OPTIONS = ACCOUNT_STATUSES.map((status) => ({ value: status, label: ACCOUNT_LABELS[status] }));

function isFilter(name: string): name is UsersFilter {
  return (FILTERS as readonly string[]).includes(name);
}

export default function UsersPage() {
  const list = useListParams<UsersFilter>({ filters: FILTERS, localQuery: true });
  const [creating, setCreating] = useState(false);
  const role: Role | undefined = pickOne(list.filters.role, ROLES);
  const status: AccountStatusView | undefined = pickOne(list.filters.status, ACCOUNT_STATUSES);
  const { limit, offset } = list.params;
  const { q } = list;

  const params = useMemo<UsersParams>(
    () => ({ limit, offset, ...(q ? { q } : {}), ...(role ? { role } : {}), ...(status ? { status } : {}) }),
    [limit, offset, q, role, status],
  );
  const users = useUsers(params);
  const page = users.data;

  return (
    <div className={styles.page}>
      <PageHeader
        title="Usuarios del sistema"
        {...(page ? { total: `${formatCount(page.total)} en total` } : {})}
        actions={[
          {
            id: "new-user",
            label: "Nuevo usuario del equipo",
            variant: "primary",
            onClick: () => {
              setCreating(true);
            },
          },
        ]}
      />
      <FilterBar
        query={list.q}
        onQueryChange={list.setQuery}
        onClear={list.clear}
        searchPlaceholder="Correo"
        selects={[
          { name: "role", label: "Rol", value: role ?? "", options: ROLE_OPTIONS, anyLabel: "Todos" },
          { name: "status", label: "Estado", value: status ?? "", options: STATUS_OPTIONS, anyLabel: "Todos menos dados de baja" },
        ]}
        onSelectChange={(name, value) => {
          if (isFilter(name)) list.setFilter(name, value || undefined);
        }}
      />
      <DataTable
        caption="Usuarios"
        columns={COLUMNS}
        rows={page?.items}
        total={page?.total}
        limit={limit}
        rowKey={(row) => row.id}
        rowHref={(row) => userHref(row.id)}
        // Mientras llega la página nueva no se muestran las filas de la anterior como si fueran ella.
        isLoading={users.isLoading || users.isPlaceholderData}
        error={listError(users.error)}
        onRetry={() => {
          void users.refetch();
        }}
        emptyMessage={USERS_EMPTY}
        emptyAction={
          <Button variant="secondary" onClick={list.clear}>
            Limpiar filtros
          </Button>
        }
      />
      {page && page.total > 0 ? <Pagination total={page.total} limit={limit} offset={offset} onPageChange={list.setPage} onLimitChange={list.setLimit} /> : null}
      <p className={styles.note}>
        Los socios con acceso al portal aparecen aquí solo para consulta; su alta se hace desde la ficha del socio.
      </p>
      <NewUserPanel
        open={creating}
        onClose={() => {
          setCreating(false);
        }}
      />
    </div>
  );
}
