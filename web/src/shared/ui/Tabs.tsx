// US-064 T2: pestañas accesibles (patrón tablist/tab/tabpanel con tabindex móvil).
// La pestaña activa vive en la URL (?tab= o un segmento de la ruta), nunca en un estado
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
  children: (activeId: string) => ReactNode;
}

function segmentAfter(pathname: string, basePath: string): string | null {
  if (!pathname.startsWith(`${basePath}/`)) return null;
  return pathname.slice(basePath.length + 1).split("/")[0] ?? null;
}

export function Tabs({ label, tabs, urlMode = "query", param = "tab", basePath = "", children }: TabsProps) {
  const [searchParams, setSearchParams] = useSearchParams();
  const location = useLocation();
  const navigate = useNavigate();
  const baseId = useId();
  const tabRefs = useRef(new Map<string, HTMLButtonElement>());

  const enabled = tabs.filter((tab) => !tab.disabledUntil);
  const requested = urlMode === "query" ? searchParams.get(param) : segmentAfter(location.pathname, basePath);
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
      void navigate(`${basePath}/${id}${location.search}`);
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
          const isDisabled = Boolean(tab.disabledUntil);
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
              {tab.disabledUntil ? <span className={styles.until}>{`Disponible en ${tab.disabledUntil}`}</span> : null}
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
