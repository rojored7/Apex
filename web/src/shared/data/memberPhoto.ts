// S6-F3 · US-148: la foto del socio para la ficha y la lista (ADR-007, S6-D37).
// - useMemberPhoto(photoAttachmentId): GET /attachments/{id} por api.blob (con el token en memoria),
//   un `blob:` creado en memoria con URL.createObjectURL y revocado al desmontar y al cambiar de id.
//   Con id nulo no pide nada.
// - La foto es un dato personal: la consulta sobrevive 60 s a su último observador (gcTime) para no repetir 100 GET al paginar, no se
//   reintenta ni se relee al volver a la ventana, y nada va a localStorage ni a sessionStorage.
// - Un error (404, 403, 429, 503) no rompe la pantalla: `url` queda nulo e `isError` en verdadero, y
//   quien pinta muestra el marcador sin foto.
import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api, UNEXPECTED_CONTENT_MESSAGE } from "../../core/api/client";
import { CLIENT_ERROR_CODES } from "../../core/api/errorCodes";
import { ApiError } from "../../core/api/errors";

export function memberPhotoKey(photoAttachmentId: string): readonly ["attachments", "photo", string] {
  return ["attachments", "photo", photoAttachmentId];
}

export interface MemberPhotoState {
  /** `blob:` en memoria, o null mientras baja, sin foto o con error. */
  url: string | null;
  isLoading: boolean;
  isError: boolean;
}

const PHOTO_STALE_MS = 60_000;

export function useMemberPhoto(photoAttachmentId: string | null | undefined): MemberPhotoState {
  const id = photoAttachmentId ?? null;
  const query = useQuery({
    queryKey: memberPhotoKey(id ?? ""),
    queryFn: async ({ signal }) => {
      const result = await api.blob(`/attachments/${encodeURIComponent(id ?? "")}`, { signal });
      // LOW-1: la foto solo entra en un <img> si el api la entregó como imagen.
      if (!(result.contentType ?? "").trim().toLowerCase().startsWith("image/")) {
        throw new ApiError({ status: 200, code: CLIENT_ERROR_CODES.unexpectedContentType, message: UNEXPECTED_CONTENT_MESSAGE });
      }
      return result.blob;
    },
    enabled: id !== null,
    // MEDIUM-2: el Blob se reutiliza 60 s entre lista y ficha; el blob: se revoca por componente.
    gcTime: PHOTO_STALE_MS,
    staleTime: PHOTO_STALE_MS,
    retry: false,
    refetchOnWindowFocus: false,
  });
  const blob = id === null ? undefined : query.data;
  const [made, setMade] = useState<{ blob: Blob; url: string } | null>(null);

  // El blob: es un recurso externo del navegador: se crea al llegar la foto y se revoca al cambiar o desmontar.
  useEffect(() => {
    if (blob === undefined) return undefined;
    const created = URL.createObjectURL(blob);
    // eslint-disable-next-line react-hooks/set-state-in-effect -- sincroniza el estado con un recurso externo (ObjectURL) recién creado.
    setMade({ blob, url: created });
    return () => {
      URL.revokeObjectURL(created);
    };
  }, [blob]);

  const url = blob !== undefined && made?.blob === blob ? made.url : null;
  return { url, isLoading: id !== null && query.isPending, isError: id !== null && query.isError };
}
