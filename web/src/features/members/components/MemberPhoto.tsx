// S6-F3 · US-148 (front): miniatura de la foto del socio en el encabezado de la ficha (lg) y en la
// lista (sm). Con `photo_attachment_id` baja la foto en memoria (useMemberPhoto) y la pinta con un alt
// fijo (nunca el nombre del socio); sin foto, cargando o con error muestra un marcador decorativo.
import { User } from "lucide-react";
import { useMemberPhoto } from "../../../shared/data/memberPhoto";
import styles from "./MemberPhoto.module.css";

export const PHOTO_ALT = "Foto del socio";

export interface MemberPhotoProps {
  photoAttachmentId: string | null | undefined;
  size: "sm" | "lg";
}

export function MemberPhoto({ photoAttachmentId, size }: MemberPhotoProps) {
  const { url } = useMemberPhoto(photoAttachmentId);
  return (
    <span className={styles.photo} data-size={size} data-testid="member-photo">
      {url !== null ? (
        <img className={styles.image} src={url} alt={PHOTO_ALT} />
      ) : (
        <span className={styles.placeholder} data-testid="member-photo-placeholder" aria-hidden="true">
          <User size="100%" />
        </span>
      )}
    </span>
  );
}
