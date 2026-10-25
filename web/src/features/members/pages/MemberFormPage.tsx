// S2-F6 · US-069 (front): /socios/nuevo (Socio_Form.html), admin y coach (`members.create`).
// - React Hook Form + Zod con las reglas de MemberCreate (memberFormSchema); POST /members con
//   useCreateMember. El formulario vive solo en memoria: nada en localStorage ni sessionStorage.
// - M-4: la casilla envía `data_consent: true` (o false); el servidor fija la fecha. M-5: no hay
//   campo de notas.
// - 422 con `field` (incluido L-3) y 409 `member_document_duplicated` bajo su campo, con foco; el
//   409 enlaza a /socios/{existing_id} con "Ver socio existente" sin recargar (S2-D34). 403, 429
//   (con la espera de Retry-After), 5xx, red y respuesta inválida como aviso general.
// - 201: vuelve a /socios con el aviso "Socio registrado" y, si el api devolvió
//   `data_consent_missing`, "Falta la autorización de tratamiento de datos" (DECISIÓN 34).
// DESIGN-GAP:
// - Sin "Guardar y vender membresía". Tras guardar el alta vuelve a la lista con un aviso, no a la
//   ficha (S2-F6; la ficha existe desde S3-F1). S3-F1: con `:id` la ruta es la edición (MemberEditView).
// - Las secciones que faltan (foto, firma, archivo, portal, cargas, observaciones de salud) están
//   anotadas en MemberFormFields.tsx.
import { useEffect, useMemo, useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useNavigate, useParams } from "react-router";
import { zodResolver } from "../../../shared/lib/zodResolver";
import { Button } from "../../../shared/ui/Button";
import { PageHeader } from "../../../shared/ui/PageHeader";
import { useCreateMember } from "../api";
import { MemberFormFields } from "../components/MemberFormFields";
import { createErrorMessage, fieldErrorOf } from "../memberErrors";
import { MEMBERS_PATH, type MemberCreatedState } from "../memberLinks";
import { EMPTY_MEMBER_FORM, memberFormSchema, toMemberCreate, type MemberFormValues } from "../schemas";
import styles from "./MemberFormPage.module.css";
import { MemberEditView } from "./MemberEditView";

export const NEW_MEMBER_TITLE = "Nuevo socio";

function MemberCreateForm() {
  const navigate = useNavigate();
  const create = useCreateMember();
  const resolver = useMemo(() => zodResolver(memberFormSchema()), []);
  const form = useForm<MemberFormValues>({ resolver, defaultValues: EMPTY_MEMBER_FORM });
  const [existingId, setExistingId] = useState<string | null>(null);
  const [generalError, setGeneralError] = useState<string | null>(null);
  // Un segundo envío (Enter o clic) mientras el primero sigue en curso no sale.
  const inFlight = useRef(false);
  // El aviso general queda arriba de un formulario largo y Guardar está al final: el foco (y con
  // él el desplazamiento) va al aviso para que también lo vea quien no usa lector de pantalla.
  const errorRef = useRef<HTMLParagraphElement>(null);
  useEffect(() => {
    if (generalError) errorRef.current?.focus();
  }, [generalError]);

  const save = async (values: MemberFormValues): Promise<void> => {
    if (inFlight.current) return;
    inFlight.current = true;
    setExistingId(null);
    setGeneralError(null);
    try {
      const created = await create.mutateAsync(toMemberCreate(values));
      const state: MemberCreatedState = { memberCreated: { name: `${created.firstName} ${created.lastName}`, consentMissing: created.consentMissing } };
      void navigate(MEMBERS_PATH, { state });
    } catch (error) {
      const target = fieldErrorOf(error);
      if (target) {
        setExistingId(target.existingId);
        form.setError(target.path, { type: "server", message: target.message }, { shouldFocus: true });
      } else {
        setGeneralError(createErrorMessage(error));
      }
    } finally {
      inFlight.current = false;
    }
  };

  const goToExisting = (href: string): void => {
    void navigate(href);
  };

  return (
    <div className={styles.page}>
      <PageHeader title={NEW_MEMBER_TITLE} breadcrumbs={[{ label: "Socios", href: MEMBERS_PATH }, { label: NEW_MEMBER_TITLE }]} />
      <form className={styles.form} noValidate aria-label={NEW_MEMBER_TITLE} onSubmit={(event) => void form.handleSubmit(save)(event)}>
        {generalError ? (
          <p ref={errorRef} className={styles.error} role="alert" tabIndex={-1}>
            {generalError}
          </p>
        ) : null}
        <MemberFormFields form={form} existingId={existingId} onNavigate={goToExisting} />
        <div className={styles.actions}>
          <span className={styles.note}>* obligatorio</span>
          <span className={styles.spacer} />
          <Link className={styles.cancel} to={MEMBERS_PATH}>
            Cancelar
          </Link>
          <Button type="submit" loading={create.isPending}>
            {create.isPending ? "Guardando…" : "Guardar"}
          </Button>
        </div>
      </form>
    </div>
  );
}

/** /socios/nuevo (alta) o, con `:id`, /socios/:id/editar (S3-F1, US-075; MemberEditView). */
export default function MemberFormPage() {
  const { id } = useParams();
  return id ? <MemberEditView id={id} /> : <MemberCreateForm />;
}
