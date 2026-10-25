// US-064 T2: pestañas accesibles (patrón tablist/tab/tabpanel con tabindex móvil).
// La pestaña activa vive en la URL (?tab= o un segmento de la ruta; S3-F1: la pestaña `indexId`
// vive en la ruta base, la hija índice), nunca en un estado
// propio duplicado: recargar o volver atrás la conserva. La selección sigue al foco.
import { useId, useRef, type KeyboardEvent, type ReactNode } from "react";
import { useLocation, useNavigate, useSearchParams } from "react-router";
import { cx } from "./cx";
import styles from "./Tabs.module.css";

export interface TabItem {
  id: string;
  label: string;
  /** Versión en la que llega ("v0.4"): la pestaña se ve deshabilitada y lo anuncia. */
  disabledUntil?: string;
  /** S3-F7: deshabilitada por otra razón (su ruta no abre una página para el rol): este texto en lugar de la versión. */
  disabledNote?: string;
}

export interface TabsProps {
  /** Nombre accesible de la lista de pestañas. */
  label: string;
  tabs: TabItem[];
  /** `query`: `?tab=<id>` (por defecto). `segment`: `<basePath>/<id>`. */
  urlMode?: "query" | "segment";
  /** Parámetro de la URL en modo `query`. */
  param?: string;
  /** Ruta base en modo `segment`, sin barra final. */
  basePath?: string;
  /**
   * S3-F1 (E14): en modo `segment`, la pestaña que vive en `basePath` mismo (la ruta hija índice,
   * "Datos" de la ficha): no agrega segmento y es la activa cuando la URL no trae ninguno.
   */
  indexId?: string;
  children: (activeId: string) => ReactNode;
}

function segmentAfter(pathname: string, basePath: string): string | null {
  if (!pathname.startsWith(`${basePath}/`)) return null;
  return pathname.slice(basePath.length + 1).split("/")[0] ?? null;
}

export function Tabs({ label, tabs, urlMode = "query", param = "tab", basePath = "", indexId, children }: TabsProps) {
  const [searchParams, setSearchParams] = useSearchParams();
  const location = useLocation();
  const navigate = useNavigate();
  const baseId = useId();
  const tabRefs = useRef(new Map<string, HTMLButtonElement>());

  const isOff = (tab: TabItem): boolean => Boolean(tab.disabledUntil ?? tab.disabledNote);
  const enabled = tabs.filter((tab) => !isOff(tab));
  const segment = urlMode === "segment" ? segmentAfter(location.pathname, basePath) : null;
  // S3-F1 (E14): sin segmento, la ruta base es la de la pestaña índice.
  const requested = urlMode === "query" ? searchParams.get(param) : (segment ?? indexId ?? null);
  const activeId = enabled.find((tab) => tab.id === requested)?.id ?? enabled[0]?.id ?? "";
  const tabId = (id: string): string => `${baseId}-tab-${id}`;
  const panelId = `${baseId}-panel`;

  const select = (id: string): void => {
    if (urlMode === "query") {
      setSearchParams((previous) => {
        const next = new URLSearchParams(previous);
        next.set(param, id);
        // Una pestaña con su propia lista empieza en la primera página.
        next.delete("offset");
        return next;
      });
    } else {
      // S3-F7: igual que en modo `query`, la pestaña nueva empieza en la primera página de su lista. Los
      // filtros de una lista (`voided`) se conservan: las otras pestañas no los leen (revisión, L6).
      // (la ficha tiene dos listas paginadas, Membresías y Pagos); lo demás de la URL se conserva.
      const next = new URLSearchParams(location.search);
      next.delete("offset");
      const query = next.toString();
      void navigate(`${id === indexId ? basePath : `${basePath}/${id}`}${query === "" ? "" : `?${query}`}`);
    }
    tabRefs.current.get(id)?.focus();
  };

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>): void => {
    const index = enabled.findIndex((tab) => tab.id === activeId);
    const last = enabled.length - 1;
    const targets: Record<string, number> = {
      ArrowRight: index >= last ? 0 : index + 1,
      ArrowLeft: index <= 0 ? last : index - 1,
      Home: 0,
      End: last,
    };
    const target = targets[event.key];
    const next = target === undefined ? undefined : enabled[target];
    if (!next) return;
    event.preventDefault();
    select(next.id);
  };

  return (
    <div className={styles.tabs}>
      <div role="tablist" aria-label={label} className={styles.list} onKeyDown={onKeyDown}>
        {tabs.map((tab) => {
          const isActive = tab.id === activeId;
          const isDisabled = isOff(tab);
          return (
            <button
              key={tab.id}
              ref={(el) => {
                if (el) tabRefs.current.set(tab.id, el);
                else tabRefs.current.delete(tab.id);
              }}
              type="button"
              role="tab"
              id={tabId(tab.id)}
              aria-selected={isActive}
              aria-controls={panelId}
              aria-disabled={isDisabled ? true : undefined}
              tabIndex={isActive ? 0 : -1}
              className={cx(styles.tab, isActive && styles.active, isDisabled && styles.disabled)}
              onClick={() => {
                if (!isDisabled) select(tab.id);
              }}
            >
              {tab.label}
              {isDisabled ? <span className={styles.until}>{tab.disabledNote ?? `Disponible en ${tab.disabledUntil ?? ""}`}</span> : null}
            </button>
          );
        })}
      </div>
      <div role="tabpanel" id={panelId} aria-labelledby={tabId(activeId)} tabIndex={0} className={styles.panel}>
        {children(activeId)}
      </div>
    </div>
  );
}
