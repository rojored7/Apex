// S3-F1 · US-074 (cierra el criterio diferido de US-066): un dato cifrado de la ficha con
// "Mostrar", conectado a POST /members/{id}/reveal.
// - Cada campo tiene su propia mutación (useRevealField): dos "Mostrar" a la vez no se pisan.
// - S3-D52 (M-9): `const out = await mutateAsync(field); const plain = flattenRevealed(field, out.value);
//   reset(); return plain;`. reset() se llama en cuanto llega la respuesta (y también si falla):
//   el claro no queda en `mutation.data` ni en la caché de mutaciones (gcTime 0); vive solo en el
//   estado de MaskedValue, que lo descarta al ocultar, al desmontar o a los 60 s.
// - El error sale como ApiError con el mensaje de la pantalla (revealError): 429 "Demasiadas
//   consultas; espera un momento"; 403 lo traduce MaskedValue. Nunca se registra en consola.
// - Quien lo use en una ficha pasa `key={id del socio}` (MaskedValue).
import { MaskedValue } from "../../../shared/ui/MaskedValue";
import { useRevealField } from "../api";
import { revealError } from "../memberErrors";
import { flattenRevealed, type RevealField } from "../schemas";

export interface MemberSensitiveFieldProps {
  memberId: string;
  field: RevealField;
  label: string;
  /** Texto enmascarado que devolvió el api en la ficha. */
  masked: string | null;
  /** Tipo de documento ("CC") por si el api no lo antepone. */
  documentType?: string;
}

export function MemberSensitiveField({ memberId, field, label, masked, documentType }: MemberSensitiveFieldProps) {
  const { mutateAsync, reset } = useRevealField(memberId);

  const onReveal = async (): Promise<string> => {
    try {
      const out = await mutateAsync(field);
      const plain = flattenRevealed(field, out.value);
      reset();
      return plain;
    } catch (error) {
      reset();
      throw revealError(error);
    }
  };

  return <MaskedValue label={label} masked={masked} kind={field} onReveal={onReveal} {...(documentType ? { documentType } : {})} />;
}
