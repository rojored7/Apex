// S3-F1 · US-075 (front): /socios/:id/editar (Socio_Form.html en modo editar), admin y coach
// (members.update). MemberFormPage lo monta cuando la ruta trae `:id`.
// - GET /members/{id} con useMember (la misma clave que la ficha): cargando, 404, error con
//   "Reintentar" y, si está dado de baja, el aviso sin formulario (editarlo da 409
//   `member_deactivated`; hay que reactivarlo primero).
// - React Hook Form + Zod (memberEditSchema). PATCH /members/{id} con solo lo modificado
//   (toMemberPatch con `dirtyFields` y los modos "Cambiar"/"Quitar"); sin cambios no se envía nada.
//   useUpdateMember: `gcTime: 0` y `reset()` al terminar (S3-D52). Nada en localStorage ni en la URL.
// - Errores bajo su campo con foco (403 `forbidden_field`, 409 de documento con "Ver socio
//   existente", `consent_cannot_be_withdrawn`, 422 con `field`); el resto como aviso general con foco.
// - Al guardar vuelve a la ficha con "Cambios guardados" (estado de la navegación).
import { useEffect, useMemo, useRef, useState } from "react";
import { useForm, type FieldPath } from "react-hook-form";
import { Link, useNavigate } from "react-router";
import { useCan } from "../../../core/auth/useCan";
import { zodResolver } from "../../../shared/lib/zodResolver";
import { Button } from "../../../shared/ui/Button";
import { MessagePage } from "../../../shared/ui/MessagePage";
import { PageHeader } from "../../../shared/ui/PageHeader";
import { useMember, useUpdateMember } from "../api";
import { MemberEditFields } from "../components/MemberEditFields";
import { DETAIL_MESSAGES, detailErrorOf, EDIT_ERROR_MESSAGES, editErrorMessage, editFieldErrorOf } from "../memberErrors";
import { isMemberId, memberHref, MEMBERS_PATH, type MemberUpdatedState } from "../memberLinks";
import { editDefaults, memberEditSchema, SENSITIVE_EDIT_FIELDS, toMemberPatch, type MemberDetailView, type MemberEditValues, type SensitiveEditField } from "../schemas";
import styles from "./MemberFormPage.module.css";

export const EDIT_MEMBER_TITLE = "Editar socio";
export const NO_CHANGES_MESSAGE = "No hay cambios para guardar.";

const crumbs = (member: MemberDetailView) => [
  { label: "Socios", href: MEMBERS_PATH },
  { label: `${member.first_name} ${member.last_name}`, href: memberHref(member.id) },
  { label: "Editar" },
];

const isSensitive = (root: string): root is SensitiveEditField => (SENSITIVE_EDIT_FIELDS as readonly string[]).includes(root);

/**
 * Revisión S3-F1 (TS MEDIUM-2): ¿el control de este campo está en pantalla? Un error del api para un
 * sensible sin "Cambiar", para el tipo de documento del coach o para una autorización ya registrada
 * no tiene dónde mostrarse: va como aviso general.
 */
function isControlShown(path: FieldPath<MemberEditValues>, values: MemberEditValues, member: MemberDetailView, canChangeDocument: boolean): boolean {
  const root = path.split(".")[0] ?? path;
  if (root === "document_type") return canChangeDocument;
  if (root === "data_consent") return member.data_consent_at === null;
  return isSensitive(root) ? values.modes[root] === "change" : true;
}

function MemberEditForm({ member, refreshError }: { member: MemberDetailView; refreshError: string | null }) {
  const navigate = useNavigate();
  const canChangeDocument = useCan("members.document.update");
  const { update, isPending } = useUpdateMember(member.id);
  const resolver = useMemo(() => zodResolver(memberEditSchema()), []);
  const form = useForm<MemberEditValues>({ resolver, defaultValues: editDefaults(member) });
  // Se lee en el render: formState es un Proxy y react-hook-form solo calcula y sigue lo que se lee.
  // `save` usa la de este render: handleSubmit(save) se arma en cada render y cada cambio de
  // dirtyFields vuelve a pintar (revisión S3-F1, LOW-4, aceptado con esta justificación).
  const { dirtyFields } = form.formState;
  const [existingId, setExistingId] = useState<string | null>(null);
  const [generalError, setGeneralError] = useState<string | null>(null);
  const [noChanges, setNoChanges] = useState(false);
  const inFlight = useRef(false);
  const errorRef = useRef<HTMLParagraphElement>(null);
  useEffect(() => {
    if (generalError) errorRef.current?.focus();
  }, [generalError]);

  const save = async (values: MemberEditValues): Promise<void> => {
    if (inFlight.current) return;
    setExistingId(null);
    setGeneralError(null);
    const body = toMemberPatch(values, dirtyFields);
    if (Object.keys(body).length === 0) {
      setNoChanges(true);
      return;
    }
    setNoChanges(false);
    inFlight.current = true;
    try {
      await update(body);
      const state: MemberUpdatedState = { memberUpdated: true };
      void navigate(memberHref(member.id), { state });
    } catch (error) {
      const target = editFieldErrorOf(error);
      if (target && !isControlShown(target.path, values, member, canChangeDocument)) {
        setGeneralError(target.message);
      } else if (target) {
        setExistingId(target.existingId);
        form.setError(target.path, { type: "server", message: target.message }, { shouldFocus: true });
      } else {
        setGeneralError(editErrorMessage(error));
      }
    } finally {
      inFlight.current = false;
    }
  };

  return (
    <div className={styles.page}>
      <PageHeader title={EDIT_MEMBER_TITLE} breadcrumbs={crumbs(member)} />
      {refreshError ? (
        <p className={styles.error} role="alert">
          {refreshError}
        </p>
      ) : null}
      <form
        className={styles.form}
        noValidate
        aria-label={EDIT_MEMBER_TITLE}
        onSubmit={(event) => void form.handleSubmit(save)(event)}
        // Revisión S3-F1 (LOW-3): "No hay cambios" se quita en cuanto se edita algo.
        onChange={() => {
          setNoChanges(false);
        }}
      >
        {generalError ? (
          <p ref={errorRef} className={styles.error} role="alert" tabIndex={-1}>
            {generalError}
          </p>
        ) : null}
        <MemberEditFields
          form={form}
          member={member}
          canChangeDocument={canChangeDocument}
          existingId={existingId}
          onNavigate={(href) => {
            void navigate(href);
          }}
        />
        <div className={styles.actions}>
          <span className={styles.note}>* obligatorio</span>
          {/* Siempre montada: un lector de pantalla anuncia el texto cuando cambia (LOW-3). */}
          <span className={styles.note} role="status">
            {noChanges ? NO_CHANGES_MESSAGE : ""}
          </span>
          <span className={styles.spacer} />
          <Link className={styles.cancel} to={memberHref(member.id)}>
            Cancelar
          </Link>
          <Button type="submit" loading={isPending}>
            {isPending ? "Guardando…" : "Guardar cambios"}
          </Button>
        </div>
      </form>
    </div>
  );
}

function DeactivatedNotice({ member }: { member: MemberDetailView }) {
  return (
    <div className={styles.page}>
      <PageHeader title={EDIT_MEMBER_TITLE} breadcrumbs={crumbs(member)} />
      <p className={styles.error}>{EDIT_ERROR_MESSAGES.deactivated}</p>
      <span>
        <Link className={styles.cancel} to={memberHref(member.id)}>
          Volver a la ficha
        </Link>
      </span>
    </div>
  );
}

export function MemberEditView({ id }: { id: string }) {
  const query = useMember(id);

  // Revisión S3-F1 (LOW-3): un `:id` sin forma de UUID no se pide al api.
  if (!isMemberId(id)) return <MessagePage title={DETAIL_MESSAGES.notFound} message={DETAIL_MESSAGES.notFoundHint} linkLabel="Ir a Socios" linkTo={MEMBERS_PATH} />;
  // Revisión S3-F1 (TS MEDIUM-1): con el socio ya cargado, una relectura fallida no desmonta el
  // formulario (se perdería lo escrito); solo avisa.
  const member = query.data;
  if (member !== undefined) {
    if (member.deleted_at !== null) return <DeactivatedNotice member={member} />;
    return <MemberEditForm key={member.id} member={member} refreshError={query.isError ? DETAIL_MESSAGES.refreshFailed : null} />;
  }
  if (query.isError) {
    const failure = detailErrorOf(query.error);
    if (failure.notFound) return <MessagePage title={DETAIL_MESSAGES.notFound} message={failure.message} linkLabel="Ir a Socios" linkTo={MEMBERS_PATH} />;
    return (
      <div className={styles.page}>
        <p className={styles.error} role="alert">
          {failure.message}
        </p>
        <span>
          <Button
            variant="secondary"
            loading={query.isFetching}
            onClick={() => {
              void query.refetch();
            }}
          >
            Reintentar
          </Button>
        </span>
      </div>
    );
  }
  return (
    <p className={styles.note} role="status">
      Cargando el socio…
    </p>
  );
}
