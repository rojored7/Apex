// S6-F4 · US-148: la foto del socio en el alta y la edición.
// DESIGN-GAP: Socio_Form.html no trae el campo de foto (ver docs/BRECHAS.md §14); se coloca arriba de
// "1 · Identificación" con el círculo de la ficha y el control de archivo estándar.
// - Controlado: el formulario guarda el File (value) y lo sube DESPUÉS de guardar al socio.
// - Valida tipo y 5 MB exactos con fileError (la misma regla de Zod). Un archivo inválido no se entrega
//   al formulario (onChange(null)) y el aviso queda bajo el campo: el resto del formulario no se pierde.
// - La vista previa es un blob: en memoria, revocado al cambiar la foto y al desmontar. Nada va a
//   localStorage ni a sessionStorage.
import { User } from "lucide-react";
import { useEffect, useRef, useState, type ChangeEvent } from "react";
import { Button } from "../../../shared/ui/Button";
import { Field } from "../../../shared/ui/Field";
import { fileError, PHOTO_TYPES } from "../schemas";
import { MemberPhoto } from "./MemberPhoto";
import styles from "./PhotoField.module.css";

export const PHOTO_PREVIEW_ALT = "Vista previa de la foto";
const PHOTO_HINT = "JPEG o PNG, hasta 5 MB.";

export interface PhotoFieldProps {
  value: File | null;
  onChange: (file: File | null) => void;
  /** Error del formulario (Zod) para este campo. */
  error?: string | undefined;
  /** Edición: la foto vigente del socio; una nueva la reemplaza. */
  currentPhotoId?: string | null | undefined;
}

export function PhotoField({ value, onChange, error, currentPhotoId = null }: PhotoFieldProps) {
  const [localError, setLocalError] = useState<string | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // El blob: es un recurso externo del navegador: se crea con el archivo y se revoca al cambiar o desmontar.
  useEffect(() => {
    if (value === null) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- sincroniza el estado con un recurso externo (ObjectURL).
      setPreview(null);
      return undefined;
    }
    const url = URL.createObjectURL(value);
    setPreview(url);
    return () => {
      URL.revokeObjectURL(url);
    };
  }, [value]);

  const handleChange = (event: ChangeEvent<HTMLInputElement>): void => {
    const file = event.target.files?.[0] ?? null;
    if (file === null) {
      setLocalError(null);
      onChange(null);
      return;
    }
    const problem = fileError("photo", file);
    setLocalError(problem);
    onChange(problem === null ? file : null);
  };

  const remove = (): void => {
    setLocalError(null);
    if (inputRef.current) inputRef.current.value = "";
    onChange(null);
  };

  const shownError = localError ?? error;
  return (
    <div className={styles.root}>
      <span className={styles.preview} data-testid="photo-field-preview">
        {preview !== null ? (
          <img className={styles.image} src={preview} alt={PHOTO_PREVIEW_ALT} />
        ) : currentPhotoId ? (
          <MemberPhoto photoAttachmentId={currentPhotoId} size="lg" />
        ) : (
          <span className={styles.placeholder} data-testid="photo-field-placeholder" aria-hidden="true">
            <User size="100%" />
          </span>
        )}
      </span>
      <div className={styles.controls}>
        <Field label="Foto del socio (opcional)" name="photo" hint={PHOTO_HINT} error={shownError ?? undefined}>
          {(control) => <input {...control} ref={inputRef} type="file" accept={PHOTO_TYPES.join(",")} onChange={handleChange} />}
        </Field>
        {currentPhotoId && value === null ? <p className={styles.note}>Si eliges una foto nueva, reemplaza a la foto actual del socio.</p> : null}
        {value !== null ? (
          <Button variant="secondary" className={styles.remove} onClick={remove}>
            Quitar foto
          </Button>
        ) : null}
      </div>
    </div>
  );
}
