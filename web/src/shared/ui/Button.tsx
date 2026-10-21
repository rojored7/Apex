import type { ButtonHTMLAttributes } from "react";
import styles from "./Button.module.css";
import { cx } from "./cx";

export type ButtonVariant = "primary" | "secondary" | "danger" | "ghost";
/** `md` 44 px (`--control`, panel); `lg` 56 px (`--control-gym`, el tamaño `gym` de DESIGN.md). */
export type ButtonSize = "md" | "lg";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  /** Acción en curso: marca `aria-busy`, deshabilita el botón y no conecta `onClick`. */
  loading?: boolean;
}

export function Button({
  variant = "primary",
  size = "md",
  loading = false,
  disabled = false,
  type = "button",
  className,
  onClick,
  children,
  ...rest
}: ButtonProps) {
  return (
    <button
      {...rest}
      type={type}
      className={cx(styles.button, styles[variant], styles[size], loading && styles.loading, className)}
      disabled={disabled || loading}
      aria-busy={loading ? true : undefined}
      onClick={loading ? undefined : onClick}
    >
      {children}
    </button>
  );
}
