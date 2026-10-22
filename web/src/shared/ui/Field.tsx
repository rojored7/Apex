import { forwardRef, useId, type InputHTMLAttributes, type ReactNode } from "react";
import { cx } from "./cx";
import styles from "./Field.module.css";

/** Enlace opcional junto al error (p. ej. al socio existente cuando el documento está duplicado). */
export interface FieldErrorAction {
  /** Solo rutas internas que empiezan por "/"; cualquier otra se descarta. */
  href: string;
  text: string;
  /**
   * S2-F4a: navegación dentro de la SPA (p. ej. `useNavigate`). Sin él, el enlace recarga la
   * página, y con ella se pierde el access en memoria y se renueva la sesión.
   */
  onNavigate?: (href: string) => void;
}

/** Atributos que el control propio (children) debe recibir para quedar asociado y accesible. */
export interface FieldControlProps {
  id: string;
  name: string;
  className: string;
  "aria-invalid": boolean;
  "aria-describedby"?: string;
  "aria-required"?: boolean;
}

export interface FieldProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "name" | "size" | "children" | "required"> {
  label: string;
  name: string;
  hint?: string;
  error?: string;
  errorAction?: FieldErrorAction;
  required?: boolean;
  /** `md` 44 px (panel); `lg` 56 px (check-in y registro de resultados). */
  size?: "md" | "lg";
  /** Control propio (select, textarea...). Sin children se usa un `<input>`. */
  children?: (control: FieldControlProps) => ReactNode;
}

/** Ruta interna segura: empieza por una sola "/" y no esconde otro origen ("//x", "/\\x"). */
export function isInternalHref(href: string): boolean {
  return href.startsWith("/") && !href.startsWith("//") && !href.startsWith("/\\");
}

export const Field = forwardRef<HTMLInputElement, FieldProps>(function Field(
  { label, name, hint, error, errorAction, required = false, size = "md", children, id: idProp, className, ...inputProps },
  ref,
) {
  const generatedId = useId();
  const id = idProp ?? `field-${generatedId}`;
  const hintId = `${id}-hint`;
  const errorId = `${id}-error`;
  const hasError = error !== undefined && error.length > 0;
  const describedBy = [hint ? hintId : null, hasError ? errorId : null].filter(Boolean).join(" ");

  const control: FieldControlProps = {
    id,
    name,
    className: cx(styles.control, styles[size], hasError && styles.invalid, className),
    "aria-invalid": hasError,
    ...(describedBy ? { "aria-describedby": describedBy } : {}),
    ...(required ? { "aria-required": true } : {}),
  };

  const action = hasError && errorAction && isInternalHref(errorAction.href) ? errorAction : undefined;

  return (
    <div className={styles.field}>
      <label className={styles.label} htmlFor={id}>
        {label}
        {required ? (
          <span className={styles.required} aria-hidden="true">
            *
          </span>
        ) : null}
      </label>
      {children ? children(control) : <input {...inputProps} {...control} ref={ref} />}
      {hint ? (
        <p id={hintId} className={styles.hint}>
          {hint}
        </p>
      ) : null}
      {hasError ? (
        <p id={errorId} className={styles.error}>
          {error}
          {action ? (
            <>
              {" "}
              <a
                className={styles.errorAction}
                href={action.href}
                onClick={(event) => {
                  if (!action.onNavigate) return;
                  event.preventDefault();
                  action.onNavigate(action.href);
                }}
              >
                {action.text}
              </a>
            </>
          ) : null}
        </p>
      ) : null}
    </div>
  );
});
