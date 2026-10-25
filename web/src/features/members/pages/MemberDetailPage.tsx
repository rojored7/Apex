// S3-F1 · US-073 y US-076 (front): /socios/:id (Socio_Ficha.html), admin y coach (members.view).
// - GET /members/{id} con useMember: la ficha trae los cinco sensibles enmascarados (N-01) y el
//   estado, plan y fin de la membresía que decide (B9b).
// - PageHeader con el nombre, el StatusTag de la membresía (y "Dado de baja"), la línea "Socio desde
//   … · plan · vence …" y las migas Socios › nombre. Acciones por rol con useCan (el api vuelve a
//   verificar, RN-15): Vender membresía (memberships.sell) y Editar (members.update) en un socio
//   vivo; Dar de baja (members.delete, solo admin); en un dado de baja solo Reactivar
//   (members.reactivate, solo admin): su ficha es de solo lectura (N-20) y se puede revelar.
// - Las pestañas son rutas hijas (S3-D65, E3, E14): la página pinta la activa en su <Outlet /> y le
//   pasa la ficha por el contexto (MemberOutletContext, que cumple MemberTabContext de shared/data).
//   "Datos" es la hija índice (MemberDataTab); Membresías y Pagos son hijas de sus features (S3-F7;
//   se ven deshabilitadas si su ruta no abre una página para el rol, memberTabs); Historial llega
//   con US-106 (deshabilitada con su versión); las demás, con la suya.
// - Estados: cargando, 404 "Socio no encontrado", error con "Reintentar", aviso de autorización
//   faltante (Q16), avisos de "Cambios guardados", "Socio dado de baja" y "Socio reactivado", y el
//   409 de documento al reactivar con enlace al socio vivo.
// DESIGN-GAP:
// - Sin foto (v0.3) ni las cuatro tarjetas de resumen (Membresía, Asistencia, Último WOD, Avisos):
//   la de Membresía es la tarjeta de la vigente en la pestaña Membresías (S3-F7) y las demás llegan
//   con v0.2 a v0.5. "Renovar" y "Registrar pago" no van en el encabezado sino en las pestañas
//   Membresías (Renovar, Registrar saldo) y Pagos (Registrar pago); "Vender membresía" siempre
//   lleva a la venta (un 409 de la venta ofrece "Renovar").
// - El menú "Más" (WhatsApp, enlace al portal) no existe todavía: "Dar de baja" va como botón.
// - Aviso "Sin autorización de datos registrada" (Q16) y el estado "Dado de baja" con "Reactivar":
//   el diseño no los dibuja (BRECHAS §10).
import { useEffect, useRef, useState } from "react";
import { Link, Outlet, useLocation, useNavigate, useParams } from "react-router";
import { formatDate } from "../../../core/i18n/format";
import type { Role } from "../../../core/auth/permissions";
import { isPageAvailable } from "../../../core/auth/routeAccess";
import { useCan, useRole } from "../../../core/auth/useCan";
import { Button } from "../../../shared/ui/Button";
import { MessagePage } from "../../../shared/ui/MessagePage";
import { PageHeader, type PageAction } from "../../../shared/ui/PageHeader";
import { StatusTag } from "../../../shared/ui/StatusTag";
import { Tabs, type TabItem } from "../../../shared/ui/Tabs";
import { useMember } from "../api";
import type { MemberOutletContext } from "../memberOutlet";
import { DeactivateMemberModal, ReactivateMemberModal } from "../components/DeactivateMemberModal";
import { membershipDetail, membershipStatusOf } from "../lib/memberRow";
import { DETAIL_MESSAGES, detailErrorOf, STATUS_CHANGE_MESSAGES } from "../memberErrors";
import { editMemberHref, isMemberId, memberHref, MEMBERS_PATH, readUpdatedNotice, sellHref } from "../memberLinks";
import type { MemberDetailView } from "../schemas";
import styles from "./MemberDetailPage.module.css";

/** Pestañas de Socio_Ficha.html; Historial siempre la última (DESIGN.md, Tabs). */
export const MEMBER_TABS: readonly TabItem[] = [
  { id: "datos", label: "Datos" },
  { id: "membresias", label: "Membresías" },
  { id: "pagos", label: "Pagos" },
  { id: "asistencia", label: "Asistencia", disabledUntil: "v0.4" },
  { id: "resultados", label: "Resultados", disabledUntil: "v0.5" },
  { id: "atleta", label: "Atleta", disabledUntil: "v0.6" },
  { id: "avisos", label: "Avisos", disabledUntil: "v0.2" },
  { id: "adjuntos", label: "Adjuntos", disabledUntil: "v0.3" },
  { id: "historial", label: "Historial", disabledUntil: "v0.1" },
];
const INDEX_TAB = "datos";

export const TAB_UNAVAILABLE = "No disponible";

/** S3-F7: pestañas que son rutas hijas de otras features (Membresías, Pagos). */
const CHILD_TABS: ReadonlySet<string> = new Set(["membresias", "pagos"]);

/**
 * Las pestañas con su estado para este rol: una hija cuya ruta no abre una página (su feature
 * deshabilitada o un rol sin acceso; isPageAvailable) se ve deshabilitada en lugar de dar 404.
 */
export function memberTabs(memberId: string, role: Role | null): TabItem[] {
  return MEMBER_TABS.map((tab) => (CHILD_TABS.has(tab.id) && !isPageAvailable(role, `${memberHref(memberId)}/${tab.id}`) ? { ...tab, disabledNote: TAB_UNAVAILABLE } : tab));
}

export const DETAIL_NOTICES = {
  updated: "Cambios guardados",
  deactivated: "Socio dado de baja",
  reactivated: "Socio reactivado",
} as const;

type Modal = "deactivate" | "reactivate" | null;

function useDetailActions(member: MemberDetailView, open: (modal: Modal) => void): PageAction[] {
  const canSell = useCan("memberships.sell");
  const canUpdate = useCan("members.update");
  const canDelete = useCan("members.delete");
  const canReactivate = useCan("members.reactivate");
  if (member.deleted_at !== null) {
    return canReactivate ? [{ id: "reactivate", label: "Reactivar", variant: "primary", onClick: () => { open("reactivate"); } }] : [];
  }
  const sell: PageAction = { id: "sell", label: "Vender membresía", href: sellHref(member.id), variant: "primary" };
  const edit: PageAction = { id: "edit", label: "Editar", href: editMemberHref(member.id) };
  const deactivate: PageAction = { id: "deactivate", label: "Dar de baja", tone: "danger", onClick: () => { open("deactivate"); } };
  return [...(canSell ? [sell] : []), ...(canUpdate ? [edit] : []), ...(canDelete ? [deactivate] : [])];
}

function MemberDetail({ member, refreshError }: { member: MemberDetailView; refreshError: string | null }) {
  const location = useLocation();
  const navigate = useNavigate();
  const [modal, setModal] = useState<Modal>(null);
  const [notice, setNotice] = useState<string | null>(() => (readUpdatedNotice(location.state) ? DETAIL_NOTICES.updated : null));
  const [duplicateId, setDuplicateId] = useState<string | null>(null);
  // Tras dar de baja o reactivar, el botón que abrió el modal ya no existe: el foco va al aviso.
  const [focusNotice, setFocusNotice] = useState(false);
  const noticeRef = useRef<HTMLParagraphElement>(null);
  const alertRef = useRef<HTMLDivElement>(null);
  const actions = useDetailActions(member, setModal);
  const role = useRole();

  useEffect(() => {
    if (focusNotice) noticeRef.current?.focus();
  }, [focusNotice, notice]);
  useEffect(() => {
    if (duplicateId !== null) alertRef.current?.focus();
  }, [duplicateId]);
  // Revisión S3-F1 (LOW-6): el aviso de la edición se lee una vez; recargar no lo repite.
  useEffect(() => {
    if (readUpdatedNotice(location.state)) void navigate(`${location.pathname}${location.search}`, { replace: true, state: null });
  }, [location, navigate]);

  const name = `${member.first_name} ${member.last_name}`;
  const deleted = member.deleted_at !== null;
  const target = { id: member.id, name };
  const done = (text: string) => (): void => {
    setDuplicateId(null);
    setNotice(text);
    setFocusNotice(true);
  };

  return (
    <div className={styles.page}>
      <PageHeader
        title={name}
        badge={
          <span className={styles.badges}>
            <StatusTag status={membershipStatusOf(member) ?? "none"} />
            {deleted ? <StatusTag account="deleted" /> : null}
          </span>
        }
        description={`Socio desde ${formatDate(member.created_at)} · ${membershipDetail(member)}`}
        breadcrumbs={[{ label: "Socios", href: MEMBERS_PATH }, { label: name }]}
        actions={actions}
      />
      {refreshError ? (
        <p className={styles.alert} role="alert">
          {refreshError}
        </p>
      ) : null}
      {notice ? (
        <p ref={noticeRef} className={styles.notice} role="status" tabIndex={-1}>
          {notice}
        </p>
      ) : null}
      {duplicateId !== null ? (
        <div ref={alertRef} className={styles.alert} role="alert" tabIndex={-1}>
          <span>{STATUS_CHANGE_MESSAGES.duplicated}</span>{" "}
          <Link className={styles.link} to={memberHref(duplicateId)}>
            Ver el socio con ese documento
          </Link>
        </div>
      ) : null}
      {deleted && member.deleted_at !== null ? (
        <p className={styles.deleted}>
          {`Dado de baja el ${formatDate(member.deleted_at)}. Su ficha es de solo lectura; sus membresías, pagos e historial se conservan.`}
        </p>
      ) : null}
      {member.data_consent_at === null ? (
        <div className={styles.consent}>
          <strong className={styles.consentTitle}>Sin autorización de datos registrada</strong>
          <span>{'Edita el socio y marca "Registrar autorización" cuando el socio la acepte (Ley 1581).'}</span>
        </div>
      ) : null}
      <Tabs label="Secciones del socio" urlMode="segment" basePath={memberHref(member.id)} indexId={INDEX_TAB} tabs={memberTabs(member.id, role)}>
        {() => <Outlet context={{ member } satisfies MemberOutletContext} />}
      </Tabs>
      <DeactivateMemberModal
        open={modal === "deactivate"}
        member={target}
        onClose={() => {
          setModal(null);
        }}
        onDone={done(DETAIL_NOTICES.deactivated)}
      />
      <ReactivateMemberModal
        open={modal === "reactivate"}
        member={target}
        onClose={() => {
          setModal(null);
        }}
        onDone={done(DETAIL_NOTICES.reactivated)}
        onDuplicate={setDuplicateId}
      />
    </div>
  );
}

export default function MemberDetailPage() {
  const { id = "" } = useParams();
  const query = useMember(id);

  // Revisión S3-F1 (LOW-3): un `:id` sin forma de UUID no se pide al api.
  if (!isMemberId(id)) return <MessagePage title={DETAIL_MESSAGES.notFound} message={DETAIL_MESSAGES.notFoundHint} linkLabel="Ir a Socios" linkTo={MEMBERS_PATH} />;
  // Revisión S3-F1 (TS MEDIUM-1): una relectura fallida con la ficha ya cargada no la quita de la
  // pantalla; solo avisa (refreshError).
  if (query.data !== undefined) {
    const refreshError = query.isError ? DETAIL_MESSAGES.refreshFailed : null;
    return <MemberDetail key={query.data.id} member={query.data} refreshError={refreshError} />;
  }
  if (query.isError) {
    const failure = detailErrorOf(query.error);
    if (failure.notFound) return <MessagePage title={DETAIL_MESSAGES.notFound} message={failure.message} linkLabel="Ir a Socios" linkTo={MEMBERS_PATH} />;
    return (
      <div className={styles.failure}>
        <p className={styles.alert} role="alert">
          {failure.message}
        </p>
        <Button
          variant="secondary"
          loading={query.isFetching}
          onClick={() => {
            void query.refetch();
          }}
        >
          Reintentar
        </Button>
      </div>
    );
  }
  return (
    <p className={styles.loading} role="status">
      Cargando la ficha del socio…
    </p>
  );
}
