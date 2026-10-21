import { forwardRef, type InputHTMLAttributes, type ReactNode } from "react";

export interface FieldErrorAction {
  href: string;
  text: string;
}

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
  size?: "md" | "lg";
  children?: (control: FieldControlProps) => ReactNode;
}

export const Field = forwardRef<HTMLInputElement, FieldProps>(function Field(_props, _ref) {
  return null;
});
