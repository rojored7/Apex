// S4A-F2 · US-106 (front): pestaña Historial de la ficha (/socios/:id/historial; S4A-D30, S4A-D32),
// admin y coach (members.history.view). Socio_Ficha.html dibuja la pestaña y DESIGN.md pide que sea la
// última; la lista es HistoryAside (shared/ui) con las entradas de GET /members/{id}/audit.
// - useMemberHistory: páginas de 25 por `offset` en el orden del api (seq descendente). "Cargar más"
//   suma la siguiente; en el tope de MEMBER_HISTORY_MAX_PAGES deja de ofrecerse y se avisa.
// - Cada entrada es una frase con quien actuó (historyPhrase), la entidad y la hora de Bogotá; un
//   reveal automático lleva "automático (aviso)". Nunca hay valores: el api solo manda nombres de
//   campo y el esquema rechaza cualquier otra clave (memberHistoryItemSchema estricto).
// - Estados: cargando, vacío ("Sin cambios registrados"), error con "Reintentar" (429 de staff-read:
//   "Demasiadas consultas; espera un momento"), fallo al cargar más (las entradas se conservan).
// DESIGN-GAP: Socio_Ficha.html no dibuja la pestaña Historial abierta (su enlace va a Auditoria.html,
// que es la pantalla del admin); se usa HistoryAside a todo el ancho de la pestaña, sin filtros ni
// búsqueda (el api acepta `q` por usuario; la pantalla no la ofrece todavía).
import { useParams } from "react-router";
import { HistoryAside } from "../../../shared/ui/HistoryAside";
import { MEMBER_HISTORY_MAX_PAGES, MEMBER_HISTORY_PAGE_SIZE, useMemberHistory } from "../api";
import { uniqueHistoryEntries } from "../lib/historyEntries";
import { HISTORY_MESSAGES, historyError, historyNotFoundError } from "../memberErrors";
import { isMemberId } from "../memberLinks";
import styles from "./MemberHistoryTab.module.css";

const CAP_ENTRIES = MEMBER_HISTORY_MAX_PAGES * MEMBER_HISTORY_PAGE_SIZE;

/** M-9 (como la lista de socios en el celular): el tope de "Cargar más". */
export const HISTORY_CAP_NOTICE = `Se muestran las ${String(CAP_ENTRIES)} entradas más recientes. Las anteriores están en Auditoría (solo administradores).`;

export default function MemberHistoryTab() {
  const { id = "" } = useParams();
  const history = useMemberHistory(id);
  const pages = history.data?.pages ?? [];
  const entries = uniqueHistoryEntries(pages.flatMap((page) => page.items));
  const atCap = pages.length >= MEMBER_HISTORY_MAX_PAGES && history.hasNextPage;
  const nextFailed = history.isFetchNextPageError;
  const canLoadMore = (history.hasNextPage && !atCap) || nextFailed;
  const firstError = history.isError && history.data === undefined ? historyError(history.error) : null;
  // Revisión S4A-F2 (LOW-1): con un `:id` sin forma de UUID la consulta no sale (enabled: false) y
  // quedaría "cargando" para siempre; la pestaña dice que el socio no existe, sin petición.
  if (!isMemberId(id)) {
    return (
      <div className={styles.tab}>
        <HistoryAside title="Historial" entries={[]} total={0} error={historyNotFoundError()} onLoadMore={() => undefined} />
      </div>
    );
  }

  return (
    <div className={styles.tab}>
      <HistoryAside
        title="Historial"
        entries={entries}
        // HistoryAside ofrece el botón mientras las entradas sean menos que el total: aquí lo decide
        // la página siguiente del api y el tope (las repetidas por un offset corrido no cuentan).
        total={canLoadMore ? entries.length + 1 : entries.length}
        isLoading={history.isPending || history.isFetchingNextPage}
        error={firstError ?? undefined}
        onRetry={() => {
          void history.refetch();
        }}
        moreLabel="Cargar más"
        onLoadMore={() => {
          if (!history.isFetchingNextPage) void history.fetchNextPage();
        }}
        footer={
          <>
            {nextFailed && entries.length > 0 ? (
              <p role="alert" className={styles.error}>
                {HISTORY_MESSAGES.loadMoreFailed}
              </p>
            ) : null}
            {atCap ? <p className={styles.note}>{HISTORY_CAP_NOTICE}</p> : null}
          </>
        }
      />
    </div>
  );
}
