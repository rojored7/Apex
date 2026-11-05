// S5-F2: errores del api de reglas, plantillas e historial en palabras de la pantalla ("qué pasó y qué
// hacer").
// - Listas: 403, 429 con la espera, 5xx, red y respuesta inválida (las pinta DataTable).
// - Escrituras: un 422 con `field` va bajo su campo con el mensaje del api (ya viene en español); un 409
//   se muestra tal cual como aviso; 404, 403, 429 y 5xx tienen texto propio.
import type { FieldPath } from "react-hook-form";
import { isApiError, type ApiError } from "../../core/api/errors";
import { HTTP_CONFLICT, HTTP_FORBIDDEN, HTTP_TOO_MANY, HTTP_UNPROCESSABLE } from "../../core/api/status";
import { connectionMessage, statusMessage, toScreenError, waitText, type StatusMessages } from "../../shared/lib/apiMessages";
import type { RuleFormValues, TemplateFormValues } from "./adminSchemas";

function listMessages(what: string, forbidden: string): (e: ApiError) => string {
  return (e) => (e.status === HTTP_FORBIDDEN ? forbidden : e.status === HTTP_TOO_MANY ? `Hiciste muchas consultas seguidas. Espera ${waitText(e.retryAfterS)} e intenta de nuevo.` : `No pudimos cargar ${what}. Intenta de nuevo en un momento.`);
}

export function rulesListError(error: unknown): ApiError | null {
  return toScreenError(
    error,
    listMessages("las reglas", "No tienes permiso para ver las reglas de aviso. Si lo necesitas, pídeselo a un administrador."),
    "No pudimos cargar las reglas. Intenta de nuevo en un momento.",
  );
}

export function templatesListError(error: unknown): ApiError | null {
  return toScreenError(
    error,
    listMessages("las plantillas", "No tienes permiso para ver las plantillas de aviso. Si lo necesitas, pídeselo a un administrador."),
    "No pudimos cargar las plantillas. Intenta de nuevo en un momento.",
  );
}

export function historyError(error: unknown): ApiError | null {
  return toScreenError(
    error,
    listMessages("el historial", "No tienes permiso para ver el historial de envíos. Si lo necesitas, pídeselo a un administrador."),
    "No pudimos cargar el historial. Intenta de nuevo en un momento.",
  );
}

export interface FieldProblem<P extends string> {
  path: P;
  message: string;
}

const RULE_FIELDS: Readonly<Record<string, FieldPath<RuleFormValues>>> = {
  name: "name",
  trigger: "trigger",
  offset_days: "days",
  channel: "channel",
  template_id: "template_id",
};

const TEMPLATE_FIELDS: Readonly<Record<string, FieldPath<TemplateFormValues>>> = { name: "name", subject: "subject", body: "body" };

function fieldProblem<P extends string>(error: unknown, fields: Readonly<Record<string, P>>): FieldProblem<P> | null {
  if (!isApiError(error) || error.status !== HTTP_UNPROCESSABLE || !error.field) return null;
  const path = fields[error.field];
  return path === undefined ? null : { path, message: error.message };
}

export const ruleFieldProblem = (error: unknown): FieldProblem<FieldPath<RuleFormValues>> | null => fieldProblem(error, RULE_FIELDS);
export const templateFieldProblem = (error: unknown): FieldProblem<FieldPath<TemplateFormValues>> | null => fieldProblem(error, TEMPLATE_FIELDS);

function writeMessage(error: unknown, messages: StatusMessages): string {
  if (!isApiError(error)) return messages.generic;
  const connection = connectionMessage(error);
  if (connection) return connection;
  if (error.status === HTTP_CONFLICT && error.message.trim() !== "") return error.message;
  return statusMessage(error, messages);
}

const RULE_WRITE: StatusMessages = {
  notFound: "Esta regla ya no existe. Cierra el panel; la lista se actualiza sola.",
  forbidden: "Solo un administrador puede cambiar las reglas. Si lo necesitas, pídeselo a uno.",
  tooMany: (wait) => `Hiciste muchos cambios seguidos. Espera ${wait} e intenta de nuevo.`,
  server: "No pudimos guardar la regla. Intenta de nuevo en un momento.",
  generic: "No pudimos guardar la regla. Intenta de nuevo en un momento.",
};

const TEMPLATE_WRITE: StatusMessages = {
  notFound: "Esta plantilla ya no existe. Cierra el panel; la lista se actualiza sola.",
  forbidden: "Solo un administrador puede cambiar las plantillas. Si lo necesitas, pídeselo a uno.",
  tooMany: (wait) => `Hiciste muchos cambios seguidos. Espera ${wait} e intenta de nuevo.`,
  server: "No pudimos guardar la plantilla. Intenta de nuevo en un momento.",
  generic: "No pudimos guardar la plantilla. Intenta de nuevo en un momento.",
};

const PREVIEW: StatusMessages = {
  forbidden: "Solo un administrador puede ver la vista previa. Si lo necesitas, pídeselo a uno.",
  tooMany: (wait) => `Hiciste muchas vistas previas seguidas. Espera ${wait} e intenta de nuevo.`,
  server: "No pudimos generar la vista previa. Intenta de nuevo en un momento.",
  generic: "No pudimos generar la vista previa. Revisa el texto e intenta de nuevo.",
};

export const ruleWriteMessage = (error: unknown): string => writeMessage(error, RULE_WRITE);
export const templateWriteMessage = (error: unknown): string => writeMessage(error, TEMPLATE_WRITE);
export const previewMessage = (error: unknown): string => writeMessage(error, PREVIEW);
