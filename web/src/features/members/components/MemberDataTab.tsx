// S3-F1 · US-073 y US-074 (front): pestaña "Datos" de la ficha, la ruta hija índice de /socios/:id
// (S3-D65, E14). La ficha llega por el contexto del <Outlet /> de MemberDetailPage (que la pidió y
// pinta la carga y los errores): sin un segundo observador de GET /members/{id}.
// - "Datos de contacto": documento, fecha de nacimiento, teléfono y correo con el enmascarado del api
//   y "Mostrar" (MemberSensitiveField: POST /members/{id}/reveal, auditado; S3-D52), y el sexo en
//   claro (va en el leaderboard).
// - "Contacto de emergencia": el api lo enmascara entero ("Registrado"); "Mostrar" lo trae como
//   "Nombre · Parentesco · Teléfono".
// - "Autorización de datos": la fecha y la versión registradas, o "Sin registrar".
// DESIGN-GAP:
// - Socio_Ficha.html muestra el nombre y el parentesco del contacto en claro y solo enmascara su
//   teléfono; el api cifra y enmascara el contacto completo (v0.1, CLAUDE.md "Campos cifrados").
// - Sin "Unidad preferida" (atleta, v0.6), "Observaciones de salud" (no existen en el modelo, M-5),
//   la caja de "Adjuntos" (v0.3) ni "Historial reciente" (HistoryAside, US-106).
import { formatDate } from "../../../core/i18n/format";
import { useMemberOutlet } from "../memberOutlet";
import { SEX_LABELS, type MemberDetailView, type RevealField } from "../schemas";
import styles from "./MemberDataTab.module.css";
import { MemberSensitiveField } from "./MemberSensitiveField";

const CONTACT_FIELDS: readonly { field: Exclude<RevealField, "emergency_contact">; label: string }[] = [
  { field: "document", label: "Documento" },
  { field: "birth_date", label: "Fecha de nacimiento" },
  { field: "phone", label: "Teléfono (WhatsApp)" },
  { field: "email", label: "Correo" },
];

function consentText(member: MemberDetailView): string {
  if (member.data_consent_at === null) return "Sin registrar";
  const version = member.data_consent_version ? ` · versión ${member.data_consent_version}` : "";
  return `Registrada el ${formatDate(member.data_consent_at)}${version}`;
}

function PlainItem({ label, value }: { label: string; value: string }) {
  return (
    <div className={styles.item}>
      <span className={styles.label}>{label}</span>
      <span className={styles.value}>{value}</span>
    </div>
  );
}

export default function MemberDataTab() {
  const member = useMemberOutlet();
  if (!member) return null;

  return (
    <div className={styles.tab}>
      <section className={styles.box} aria-labelledby="member-contact-title">
        <h2 id="member-contact-title" className={styles.title}>
          Datos de contacto
        </h2>
        <div className={styles.grid}>
          {CONTACT_FIELDS.map(({ field, label }) => (
            <MemberSensitiveField
              key={`${member.id}-${field}`}
              memberId={member.id}
              field={field}
              label={label}
              masked={member[field]}
              {...(field === "document" ? { documentType: member.document_type } : {})}
            />
          ))}
          <PlainItem label="Sexo (para el leaderboard)" value={member.sex ? SEX_LABELS[member.sex] : "Sin indicar"} />
        </div>
      </section>
      <section className={styles.box} aria-labelledby="member-emergency-title">
        <h2 id="member-emergency-title" className={styles.title}>
          Contacto de emergencia
        </h2>
        <div className={styles.grid}>
          <MemberSensitiveField key={`${member.id}-emergency_contact`} memberId={member.id} field="emergency_contact" label="Contacto de emergencia" masked={member.emergency_contact} />
        </div>
      </section>
      <section className={styles.box} aria-labelledby="member-consent-title">
        <h2 id="member-consent-title" className={styles.title}>
          Autorización de datos
        </h2>
        <div className={styles.grid}>
          <PlainItem label="Ley 1581" value={consentText(member)} />
        </div>
      </section>
    </div>
  );
}
