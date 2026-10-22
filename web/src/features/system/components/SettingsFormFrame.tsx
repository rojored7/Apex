// S2-F5: lo común a las tres secciones de Configuración (Config.html, una caja por sección).
// - SettingsFormFrame: caja con título, nota, campos, avisos y "Guardar" (con estado de envío).
//   Avisos: "Cambios guardados" en una región role="status" que siempre existe (así el lector
//   de pantalla lo anuncia), el conflicto 409 con "Recargar" (Guardar queda deshabilitado hasta
//   recargar: la versión local ya no sirve) y un error general en role="alert".
// - SectionLoadState: carga, error y "sin permiso" de la lectura de la sección.
import type { UseQueryResult } from "@tanstack/react-query";
import { CircleCheck } from "lucide-react";
import { useId, type SubmitEventHandler, type ReactNode } from "react";
import { isApiError } from "../../../core/api/errors";
import { Button } from "../../../shared/ui/Button";
import { CONFLICT_MESSAGE } from "../api";
import styles from "./SettingsForm.module.css";

export interface SettingsFormProps {
  /** Avisa a la página si el formulario tiene cambios sin guardar. */
  onDirtyChange?: ((dirty: boolean) => void) | undefined;
}

export interface SettingsFormFrameProps {
  title: string;
  description?: string;
  /** Texto bajo el título (por ejemplo la versión vigente de la política). */
  summary?: ReactNode;
  onSubmit: SubmitEventHandler<HTMLFormElement>;
  isSaving: boolean;
  isConflict: boolean;
  isReloading: boolean;
  saved: boolean;
  formError: string | undefined;
  onReload: () => void;
  children: ReactNode;
}

export function SettingsFormFrame({
  title,
  description,
  summary,
  onSubmit,
  isSaving,
  isConflict,
  isReloading,
  saved,
  formError,
  onReload,
  children,
}: SettingsFormFrameProps) {
  const titleId = useId();
  return (
    <section className={styles.card} aria-labelledby={titleId}>
      <header className={styles.head}>
        <h2 id={titleId} className={styles.title}>
          {title}
        </h2>
        {description ? <p className={styles.note}>{description}</p> : null}
        {summary}
      </header>
      <form className={styles.form} noValidate aria-labelledby={titleId} onSubmit={onSubmit}>
        {/* Mientras guarda, los campos quedan de solo lectura: lo que vuelve del servidor
            reemplaza el formulario y no debe pisar algo escrito durante el envío. */}
        <fieldset className={styles.grid} disabled={isSaving}>
          {children}
        </fieldset>
        {isConflict ? (
          <div role="alert" className={styles.conflict}>
            <p className={styles.alertText}>{CONFLICT_MESSAGE}</p>
            <Button variant="secondary" loading={isReloading} onClick={onReload}>
              Recargar
            </Button>
          </div>
        ) : null}
        {formError ? (
          <p role="alert" className={styles.error}>
            {formError}
          </p>
        ) : null}
        <div className={styles.actions}>
          <p role="status" className={styles.saved}>
            {saved ? (
              <>
                <CircleCheck size={20} aria-hidden="true" />
                Cambios guardados
              </>
            ) : null}
          </p>
          <Button type="submit" loading={isSaving} disabled={isConflict}>
            Guardar
          </Button>
        </div>
      </form>
    </section>
  );
}

const FORBIDDEN = 403;

export interface SectionLoadStateProps {
  query: Pick<UseQueryResult, "isError" | "error" | "refetch" | "isFetching">;
}

/** Lo que se ve mientras la sección no tiene datos: cargando o el error de la lectura. */
export function SectionLoadState({ query }: SectionLoadStateProps) {
  if (!query.isError) {
    return (
      <p role="status" className={styles.loading}>
        Cargando la sección…
      </p>
    );
  }
  if (isApiError(query.error) && query.error.status === FORBIDDEN) {
    return (
      <div role="alert" className={styles.loadError}>
        <p className={styles.alertText}>No tienes permiso para ver esta sección. Pide a un administrador que la revise.</p>
      </div>
    );
  }
  return (
    <div role="alert" className={styles.loadError}>
      <p className={styles.alertText}>No pudimos cargar esta sección. Revisa tu conexión e intenta de nuevo.</p>
      <Button
        variant="secondary"
        loading={query.isFetching}
        onClick={() => {
          void query.refetch();
        }}
      >
        Reintentar
      </Button>
    </div>
  );
}
