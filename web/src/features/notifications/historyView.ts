// S5-F2 · US-130 (front): cómo se lee una fila del historial (Notif_Historial.html).
// - detailText: el detalle en palabras: el motivo de un aviso omitido, el error de uno fallido o lo que
//   pasó con uno enviado ("enlace abierto" de WhatsApp, "correo enviado").
// - whoText: "sistema" cuando lo hizo el worker y "Equipo" cuando lo hizo una persona (el api guarda el
//   id de la cuenta, no su nombre).
// - whenOf: el instante que se muestra: el del envío y, si no hubo, el de la creación del aviso.
import { LAST_ERROR_LABELS, type NotificationRowView } from "./schemas";

export function detailText(row: NotificationRowView): string {
  if (row.status === "skipped") return row.skip_reason ? `motivo: ${row.skip_reason}` : "omitido";
  if (row.status === "failed") return LAST_ERROR_LABELS[row.last_error ?? "unknown"] ?? "error desconocido";
  if (row.status === "sent") return row.channel === "whatsapp_link" ? "enlace abierto" : "correo enviado";
  return "esperando envío";
}

export function whoText(row: NotificationRowView): string {
  return row.sent_by ? "Equipo" : "sistema";
}

export function whenOf(row: NotificationRowView): string {
  return row.sent_at ?? row.created_at;
}
