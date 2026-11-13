// S6-F4 · US-148 y US-149: sube los archivos pendientes del formulario DESPUÉS de guardar al socio.
// - Orden fijo: foto y luego documento firmado. Un fallo no detiene al otro y no deshace el guardado
//   del socio: cada uno se devuelve con su motivo en palabras de la pantalla para avisarlo.
import { uploadErrorMessage } from "../memberErrors";
import type { MemberFileKind } from "../schemas";

export interface PendingFiles {
  photo: File | null;
  consent: File | null;
}

export interface UploadFailure {
  kind: MemberFileKind;
  reason: string;
}

export type UploadFn = (kind: MemberFileKind, file: File) => Promise<unknown>;

export async function uploadPending(upload: UploadFn, files: PendingFiles): Promise<UploadFailure[]> {
  const queue: readonly (readonly [MemberFileKind, File | null])[] = [
    ["photo", files.photo],
    ["consent", files.consent],
  ];
  const failures: UploadFailure[] = [];
  for (const [kind, file] of queue) {
    if (file === null) continue;
    try {
      await upload(kind, file);
    } catch (error) {
      failures.push({ kind, reason: uploadErrorMessage(kind, error) });
    }
  }
  return failures;
}
