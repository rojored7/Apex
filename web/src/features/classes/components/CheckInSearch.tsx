// S7-F4 · US-159 (front): el buscador de la tablet (CheckIn.html, columna izquierda).
// - Mínimo 2 letras y 300 ms de calma antes de pedir (useMemberSearch con minChars); el 429 dice «Espera un momento».
// - GET /members?q= solo trae nombre, estado de membresía, plan y foto (MemberRowOut, N-01): ningún dato cifrado ni /members/{id}.
// - Cada fila: foto, nombre, nota, estado y la acción. Al día o por vencer: «Llegó». Vencida, congelada, pendiente o sin plan:
//   «Llegó igual» (queda marcado, nunca se bloquea la puerta); sin plan suma «Vender».
// DESIGN-GAP: CheckIn.html busca también por «los últimos 4 del documento»; el documento va cifrado (N-02) y la tablet no lo
// revela, así que solo se busca por nombre.
import type { Ref } from "react";
import { useMemberPhoto } from "../../../shared/data/memberPhoto";
import { memberFullName, memberSearchNote, useMemberSearch, type MemberOption } from "../../../shared/data/members";
import { Button } from "../../../shared/ui/Button";
import { MemberSearch, type MemberSearchOption, type MemberSearchStatus } from "../../../shared/ui/MemberSearch";
import { isMembershipStatusView, type MembershipStatusView } from "../../../shared/ui/statusLabel";
import { StatusTag } from "../../../shared/ui/StatusTag";
import { memberSearchFailedText } from "../classErrors";
import styles from "./CheckInSearch.module.css";

export const CHECKIN_MIN_CHARS = 3;
export const CHECKIN_SEARCH_DELAY_MS = 300;

export interface CheckInSearchProps {
  text: string;
  onTextChange: (text: string) => void;
  /** Los socios que ya llegaron a esta sesión. */
  arrived: ReadonlySet<string>;
  /** Hay un check-in en curso: se espera a que termine para registrar otro. */
  pending: boolean;
  onArrive: (member: MemberOption) => void;
  /** «Vender» (sin plan): sale del modo tablet hacia la venta. */
  onSell: (member: MemberOption) => void;
  /** El buscador de la tablet: la pantalla le devuelve el foco tras cada llegada. */
  inputRef?: Ref<HTMLInputElement> | undefined;
}

function statusOf(member: MemberOption): MembershipStatusView {
  const status = member.membership_status;
  if (status && isMembershipStatusView(status)) return status;
  return "none";
}

const isClean = (status: MembershipStatusView): boolean => status === "active" || status === "expiring";

function Photo({ attachmentId }: { attachmentId: string | null | undefined }) {
  const photo = useMemberPhoto(attachmentId);
  return photo.url ? <img className={styles.photo} src={photo.url} alt="" width={48} height={48} /> : <span className={styles.photo} aria-hidden="true" />;
}

interface RowProps {
  member: MemberOption;
  arrived: boolean;
  pending: boolean;
  onArrive: (member: MemberOption) => void;
  onSell: (member: MemberOption) => void;
}

function Row({ member, arrived, pending, onArrive, onSell }: RowProps) {
  const status = statusOf(member);
  return (
    <div className={styles.row}>
      <Photo attachmentId={member.photo_attachment_id} />
      <div className={styles.text}>
        <b className={styles.name}>{memberFullName(member)}</b>
        <span className={styles.note}>{memberSearchNote(member)}</span>
      </div>
      <StatusTag status={status} />
      {arrived ? (
        <Button size="lg" variant="secondary" disabled>
          Ya llegó
        </Button>
      ) : (
        <>
          <Button
            size="lg"
            variant={isClean(status) ? "primary" : "secondary"}
            disabled={pending}
            onClick={() => {
              onArrive(member);
            }}
          >
            {isClean(status) ? "Llegó" : "Llegó igual"}
          </Button>
          {status === "none" ? (
            <Button
              size="lg"
              variant="secondary"
              disabled={pending}
              onClick={() => {
                onSell(member);
              }}
            >
              Vender
            </Button>
          ) : null}
        </>
      )}
    </div>
  );
}

/** Los caracteres que cuenta el servidor en modo quiosco: sin espacios (S7-C4c). */
const lettersOf = (text: string): number => text.replace(/\s/g, "").length;

export function CheckInSearch({ text, onTextChange, arrived, pending, onArrive, onSell, inputRef }: CheckInSearchProps) {
  const search = useMemberSearch(text, CHECKIN_SEARCH_DELAY_MS, CHECKIN_MIN_CHARS);
  const length = lettersOf(text);
  let status: MemberSearchStatus = search.status;
  if (length === 0) status = "idle";
  else if (length < CHECKIN_MIN_CHARS) status = "short";
  else if (search.status === "idle") status = "pending";

  const byId = new Map(search.options.map((member) => [member.id, member] as const));
  const options: MemberSearchOption[] = search.options.map((member) => ({ id: member.id, name: memberFullName(member), note: memberSearchNote(member) }));
  return (
    <div className={styles.search}>
      <MemberSearch
        name="checkin-search"
        inputRef={inputRef}
        size="gym"
        placeholder="Escribe el nombre del socio"
        value={text}
        onChange={onTextChange}
        status={status}
        options={options}
        emptyText="No encontramos a nadie con ese nombre. Revisa cómo está escrito."
        failedText={memberSearchFailedText(search.error)}
        shortText={`Escribe al menos ${String(CHECKIN_MIN_CHARS)} letras para buscar.`}
        renderOption={(option) => {
          const member = byId.get(option.id);
          return member ? <Row member={member} arrived={arrived.has(member.id)} pending={pending} onArrive={onArrive} onSell={onSell} /> : null;
        }}
      />
    </div>
  );
}
