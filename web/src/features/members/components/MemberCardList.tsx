// S3-F2 · US-072 (front): /socios en el celular (Socios_Movil.html), bajo MOBILE_QUERY (D39).
// - Tarjetas con el nombre, la línea de la membresía ("Mensual · vence 28 oct 2026") y StatusTag
//   (membresía y, si no está activa, la cuenta: "Inactivo" o "Dado de baja"). La tarjeta entera
//   es el enlace a la ficha, de al menos 44 px; su nombre accesible es el del socio y la línea y
//   las etiquetas la describen. Nada cifrado ni enmascarado (N-01).
// - "Cargar más" (useMembersInfinite) suma la página siguiente y desaparece al llegar al total.
//   M-9 (S3-D52): no pasa de MEMBERS_MAX_PAGES páginas; en el tope pide usar búsqueda o filtros.
//   Si la página siguiente falla, las tarjetas se quedan y el aviso ofrece "Reintentar".
// - "Nuevo socio" es un botón flotante con `members.create` (en el celular sustituye al del
//   encabezado). Estados de carga, vacío (con filtros o sin socios), error con Reintentar.
// DESIGN-GAP:
// - Socios_Movil.html pagina con "Anterior" y "Siguiente"; US-072 y D39 piden "Cargar más".
// - Socios_Movil.html pone "+ Nuevo" junto al título; el blueprint F2 pide botón flotante.
// - Sin el círculo de la foto (los adjuntos llegan en v0.3) ni "12 clases · quedan 2" (la fila de
//   GET /members no trae las clases restantes).
import { Plus } from "lucide-react";
import { useEffect, useId, useRef, type ReactNode } from "react";
import { Link } from "react-router";
import { isApiError } from "../../../core/api/errors";
import type { Page } from "../../../core/api/page";
import { HTTP_FORBIDDEN, HTTP_TOO_MANY } from "../../../core/api/status";
import { useCan } from "../../../core/auth/useCan";
import { formatCount } from "../../../core/i18n/format";
import { Button } from "../../../shared/ui/Button";
import { StatusTag } from "../../../shared/ui/StatusTag";
import { MEMBERS_MAX_PAGES, useMembersInfinite, type MembersInfiniteParams } from "../api";
import { accountStatusOf, membershipDetail, membershipStatusOf } from "../lib/memberRow";
import { LIST_MESSAGES, listError } from "../memberErrors";
import { memberHref, NEW_MEMBER_PATH } from "../memberLinks";
import type { MemberRowView } from "../schemas";
import styles from "./MemberCardList.module.css";

export interface MemberCardListProps {
  params: MembersInfiniteParams;
  /** Lo mismo que la tabla: el texto y la acción del vacío los decide la página. */
  emptyMessage: string;
  emptyAction: ReactNode;
}

export const LOAD_MORE_FAILED = "No pudimos cargar más socios. Intenta de nuevo.";
export const REFRESH_FAILED = "No pudimos actualizar la lista de socios. Lo que ves puede estar desactualizado; intenta de nuevo.";
export const LOADING_TEXT = "Cargando socios…";
const SKELETON_CARDS = 4;

export function capNotice(shown: number): string {
  return `Se muestran los primeros ${formatCount(shown)} socios. Usa la búsqueda o los filtros para encontrar a los demás.`;
}

function MemberCard({ row }: { row: MemberRowView }) {
  const id = useId();
  const membership = membershipStatusOf(row);
  const account = accountStatusOf(row);
  return (
    <li>
      <Link to={memberHref(row.id)} className={styles.card} aria-labelledby={`${id}-name`} aria-describedby={`${id}-detail ${id}-tags`}>
        <span className={styles.main}>
          <span id={`${id}-name`} className={styles.name}>{`${row.first_name} ${row.last_name}`}</span>
          <span id={`${id}-detail`} className={styles.detail}>
            {membershipDetail(row)}
          </span>
        </span>
        <span id={`${id}-tags`} className={styles.tags}>
          {membership && membership !== "none" ? <StatusTag status={membership} /> : null}
          {account !== "active" ? <StatusTag account={account} /> : null}
        </span>
      </Link>
    </li>
  );
}

/** El aviso de una página siguiente fallida: la espera de un 429 y el permiso se explican igual que en la lista. */
function loadMoreMessage(error: unknown): string {
  if (isApiError(error) && (error.status === HTTP_TOO_MANY || error.status === HTTP_FORBIDDEN)) return listError(error)?.message ?? LOAD_MORE_FAILED;
  return LOAD_MORE_FAILED;
}

function CreateButton() {
  return (
    <Link to={NEW_MEMBER_PATH} className={styles.fab}>
      <Plus size={20} aria-hidden="true" />
      Nuevo socio
    </Link>
  );
}

/** Mientras llega la primera página: un aviso para el lector de pantalla y cajas grises. */
function Skeleton() {
  return (
    <div className={styles.list}>
      <p role="status" className={styles.srOnly}>
        {LOADING_TEXT}
      </p>
      {Array.from({ length: SKELETON_CARDS }, (_, index) => (
        <span key={index} className={styles.skeleton} aria-hidden="true" data-testid="card-skeleton" />
      ))}
    </div>
  );
}

function ErrorBox({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className={styles.box}>
      <p role="alert" className={styles.errorText}>
        {message}
      </p>
      <Button variant="secondary" onClick={onRetry}>
        Reintentar
      </Button>
    </div>
  );
}

/** Las filas de todas las páginas sin repetir: un alta o una baja entre dos cargas corre el offset. */
function uniqueRows(pages: readonly Page<MemberRowView>[]): MemberRowView[] {
  const byId = new Map<string, MemberRowView>();
  for (const row of pages.flatMap((page) => page.items)) if (!byId.has(row.id)) byId.set(row.id, row);
  return [...byId.values()];
}

export function MemberCardList({ params, emptyMessage, emptyAction }: MemberCardListProps) {
  const canCreate = useCan("members.create");
  const members = useMembersInfinite(params);
  const pages = members.data?.pages ?? [];
  const rows = uniqueRows(pages);
  const total = pages.at(-1)?.total ?? 0;
  const atCap = pages.length >= MEMBERS_MAX_PAGES && members.hasNextPage;
  const canLoadMore = members.hasNextPage && !atCap;
  const isBusy = members.isFetchingNextPage;
  const nextFailed = members.isFetchNextPageError;
  const listRef = useRef<HTMLUListElement>(null);
  // Revisión S3-F2 (M1): si el botón desaparece al llegar al final, el foco va a la primera tarjeta nueva.
  const focusFrom = useRef<number | null>(null);
  const shown = rows.length;
  useEffect(() => {
    const from = focusFrom.current;
    if (from === null || isBusy || shown <= from) return;
    focusFrom.current = null;
    if (!canLoadMore) listRef.current?.querySelectorAll<HTMLAnchorElement>("a")[from]?.focus();
  }, [shown, isBusy, canLoadMore]);

  const loadMore = () => {
    if (isBusy) return;
    focusFrom.current = shown;
    void members.fetchNextPage();
  };

  return (
    <div className={styles.wrap}>
      {members.isPending ? <Skeleton /> : null}
      {members.isError && !members.data ? (
        <ErrorBox
          message={listError(members.error)?.message ?? LIST_MESSAGES.failed}
          onRetry={() => {
            void members.refetch();
          }}
        />
      ) : null}
      {/* Revisión S3-F2 (M4): una relectura fallida no deja las tarjetas viejas como vigentes sin aviso. */}
      {members.isRefetchError && !nextFailed ? (
        <ErrorBox
          message={REFRESH_FAILED}
          onRetry={() => {
            void members.refetch();
          }}
        />
      ) : null}
      {members.data && rows.length === 0 ? (
        <div className={styles.box}>
          <p className={styles.emptyText}>{emptyMessage}</p>
          {emptyAction}
        </div>
      ) : null}
      {rows.length > 0 ? (
        <ul ref={listRef} aria-label="Socios" className={styles.list}>
          {rows.map((row) => (
            <MemberCard key={row.id} row={row} />
          ))}
        </ul>
      ) : null}
      {/* Revisión S3-F2 (L1): la región existe siempre para que el primer conteo también se anuncie. */}
      <p role="status" className={rows.length > 0 ? styles.count : styles.srOnly}>
        {rows.length > 0 ? `Mostrando ${formatCount(rows.length)} de ${formatCount(total)}` : ""}
      </p>
      {rows.length > 0 && nextFailed ? (
        <p role="alert" className={styles.errorText}>
          {loadMoreMessage(members.error)}
        </p>
      ) : null}
      {/* Un solo botón para "Cargar más", "Cargando…" y "Reintentar": el foco no se pierde al cambiar (M1). */}
      {rows.length > 0 && (canLoadMore || nextFailed) ? (
        <Button variant="secondary" aria-disabled={isBusy} onClick={loadMore}>
          {isBusy ? "Cargando…" : nextFailed ? "Reintentar" : "Cargar más"}
        </Button>
      ) : null}
      {atCap ? <p className={styles.note}>{capNotice(rows.length)}</p> : null}
      {canCreate ? <CreateButton /> : null}
    </div>
  );
}
