// S2-F4a/F4b: un enlace de un solo uso (activación o recuperación) en un campo de solo
// lectura con "Copiar". Lo usan el alta (NewUserPanel) y el reenvío (LinkModal). El enlace
// se muestra y se copia, nunca se abre ni se interpreta; al enfocar el campo se selecciona
// para copiarlo a mano si el portapapeles no está disponible.
import { useState } from "react";
import { Button } from "../../../shared/ui/Button";
import { Field } from "../../../shared/ui/Field";
import styles from "./LinkField.module.css";

export interface LinkFieldProps {
  label: string;
  name: string;
  url: string;
  /** Cómo entregarlo; va en una caja de aviso bajo el campo. */
  handoff: string;
}

export const LINK_FIELD_MESSAGES = {
  copied: "Enlace copiado.",
  copyFailed: "No pudimos copiar el enlace. Selecciónalo y cópialo a mano.",
} as const;

type CopyState = "idle" | "copied" | "failed";

export function LinkField({ label, name, url, handoff }: LinkFieldProps) {
  const [copy, setCopy] = useState<CopyState>("idle");
  const onCopy = async (): Promise<void> => {
    try {
      // Sin portapapeles (contexto inseguro) `clipboard` no existe y también cae en el catch.
      await navigator.clipboard.writeText(url);
      setCopy("copied");
    } catch {
      setCopy("failed");
    }
  };
  return (
    <>
      <div className={styles.copyRow}>
        <Field
          label={label}
          name={name}
          readOnly
          value={url}
          onFocus={(event) => {
            event.currentTarget.select();
          }}
        />
        <Button variant="secondary" onClick={() => void onCopy()}>
          Copiar
        </Button>
      </div>
      {copy !== "idle" ? (
        <p className={styles.status} role="status">
          {copy === "copied" ? LINK_FIELD_MESSAGES.copied : LINK_FIELD_MESSAGES.copyFailed}
        </p>
      ) : null}
      <p className={styles.warning}>{handoff}</p>
    </>
  );
}
