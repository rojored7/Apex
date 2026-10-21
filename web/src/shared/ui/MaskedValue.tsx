// US-066 T4: valor sensible enmascarado con "Mostrar" (Socio_Ficha.html, "CC •••• 4417").
// - Nunca recibe el claro como prop: solo el texto enmascarado del api y onReveal.
// - El claro vive solo en el estado de este componente: no pasa por TanStack Query, ni por
//   el almacenamiento del navegador, ni por la URL; se descarta al ocultar, al desmontar o
//   a los 60 s. Cada pulsación llama a onReveal una vez (cada vista deja una auditoría).
// Criterio diferido: la feature conecta onReveal a POST /members/{id}/reveal en US-074.
import { useEffect, useId, useRef, useState } from "react";
import { isApiError } from "../../core/api/errors";
import type { Action } from "../../core/auth/permissions";
import { useCan } from "../../core/auth/useCan";
import { NO_VALUE_LABEL, maskValue, type SensitiveKind } from "../lib/audit-labels";
import { Button } from "./Button";
import styles from "./MaskedValue.module.css";

/** Tiempo que el dato queda en claro antes de volver a enmascararse. */
export const REVEAL_TTL_MS = 60_000;

export const REVEAL_FORBIDDEN = "No tienes permiso para ver este dato";
export const REVEAL_GENERIC_ERROR = "No se pudo mostrar el dato. Intenta de nuevo.";

export interface MaskedValueProps {
  label: string;
  /** Texto enmascarado que calcula el api al leer la ficha (N-01). */
  masked: string | null;
  /** Pide el dato en claro (queda auditado en el api). */
  onReveal: () => Promise<string>;
  revealAction?: Action;
  kind?: SensitiveKind;
  /** Tipo de documento ("CC") por si el api no lo antepone. */
  documentType?: string;
}

type RevealState =
  | { status: "masked" }
  | { status: "loading" }
  | { status: "revealed"; plain: string }
  | { status: "error"; message: string };

function errorMessage(error: unknown): string {
  if (isApiError(error)) return error.status === 403 ? REVEAL_FORBIDDEN : error.message;
  return REVEAL_GENERIC_ERROR;
}

export function MaskedValue({ label, masked, onReveal, revealAction = "members.reveal", kind = "document", documentType }: MaskedValueProps) {
  const labelId = useId();
  const canReveal = useCan(revealAction);
  const [state, setState] = useState<RevealState>({ status: "masked" });
  const busy = useRef(false);
  const mounted = useRef(true);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clearTimer = (): void => {
    if (timer.current !== null) clearTimeout(timer.current);
    timer.current = null;
  };

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      if (timer.current !== null) clearTimeout(timer.current);
    };
  }, []);

  const shown = maskValue(kind, masked, documentType);
  const hasValue = shown !== NO_VALUE_LABEL;

  const reveal = async (): Promise<void> => {
    if (busy.current) return;
    busy.current = true;
    setState({ status: "loading" });
    try {
      const plain = await onReveal();
      if (!mounted.current) return;
      setState({ status: "revealed", plain });
      clearTimer();
      timer.current = setTimeout(() => {
        setState({ status: "masked" });
      }, REVEAL_TTL_MS);
    } catch (error) {
      if (mounted.current) setState({ status: "error", message: errorMessage(error) });
    } finally {
      busy.current = false;
    }
  };

  const hide = (): void => {
    clearTimer();
    setState({ status: "masked" });
  };

  const isRevealed = state.status === "revealed";

  return (
    <div className={styles.field}>
      <span id={labelId} className={styles.label}>
        {label}
      </span>
      <span className={styles.row}>
        <span className={styles.value} aria-live="polite">
          {isRevealed ? state.plain : shown}
        </span>
        {canReveal && hasValue ? (
          <Button
            variant="ghost"
            className={styles.toggle}
            aria-describedby={labelId}
            loading={state.status === "loading"}
            onClick={() => {
              if (isRevealed) hide();
              else void reveal();
            }}
          >
            {isRevealed ? "Ocultar" : "Mostrar"}
          </Button>
        ) : null}
      </span>
      {state.status === "error" ? (
        <p role="alert" className={styles.error}>
          {state.message}
        </p>
      ) : null}
    </div>
  );
}
