// S8-F4 · US-169 (front): «+ Alguien que no hizo check-in» (Resultados_Registro.html). Busca por nombre (3 letras o más; el quiosco
// del servidor solo busca por nombre, S7-D41), registra la llegada con POST /attendance (con sus banderas y su descuento, S8-D15) y
// deja al socio listo para registrar su resultado. Si ya está en la lista, solo lo elige. Nunca llama /members/{id} ni /reveal.
import { useRef, useState } from "react";
import { useCheckIn } from "../../../shared/data/attendance";
import { memberFullName, memberSearchNote, useMemberSearch } from "../../../shared/data/members";
import { Button } from "../../../shared/ui/Button";
import { MemberSearch, type MemberSearchOption, type MemberSearchStatus } from "../../../shared/ui/MemberSearch";
import { addAttendanceMessage, searchFailedText } from "../resultErrors";
import styles from "./AddWalkIn.module.css";

export const WALKIN_MIN_CHARS = 3;
export const WALKIN_SEARCH_DELAY_MS = 300;

export interface AddWalkInProps {
  sessionId: string;
  /** Los socios que ya están en la lista de la clase. */
  presentIds: ReadonlySet<string>;
  /** El socio quedó en la lista: la pantalla lo elige para registrar su resultado. */
  onReady: (memberId: string) => void;
}

const lettersOf = (text: string): number => text.replace(/\s/g, "").length;

export function AddWalkIn({ sessionId, presentIds, onReady }: AddWalkInProps) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const add = useCheckIn();
  const busy = useRef(false);
  const search = useMemberSearch(text, WALKIN_SEARCH_DELAY_MS, WALKIN_MIN_CHARS);
  const length = lettersOf(text);
  let status: MemberSearchStatus = search.status;
  if (length === 0) status = "idle";
  else if (length < WALKIN_MIN_CHARS) status = "short";
  else if (search.status === "idle") status = "pending";

  const options: MemberSearchOption[] = search.options.map((member) => ({
    id: member.id,
    name: memberFullName(member),
    note: presentIds.has(member.id) ? "Ya está en la lista" : memberSearchNote(member),
  }));

  const pick = async (option: MemberSearchOption): Promise<void> => {
    if (busy.current) return;
    setError(null);
    if (presentIds.has(option.id)) {
      onReady(option.id);
      setOpen(false);
      setText("");
      return;
    }
    busy.current = true;
    try {
      await add.mutateAsync({ sessionId, memberId: option.id });
      onReady(option.id);
      setOpen(false);
      setText("");
    } catch (failure) {
      setError(addAttendanceMessage(failure));
    } finally {
      busy.current = false;
    }
  };

  if (!open) {
    return (
      <Button
        size="lg"
        variant="secondary"
        onClick={() => {
          setOpen(true);
        }}
      >
        + Alguien que no hizo check-in
      </Button>
    );
  }
  return (
    <section className={styles.panel} aria-label="Agregar a alguien que no hizo check-in">
      <MemberSearch
        name="walkin-search"
        size="gym"
        placeholder="Escribe el nombre del socio"
        value={text}
        onChange={setText}
        status={status}
        options={options}
        emptyText="No encontramos a nadie con ese nombre. Revisa cómo está escrito."
        failedText={searchFailedText(search.error)}
        shortText={`Escribe al menos ${String(WALKIN_MIN_CHARS)} letras para buscar.`}
        onSelect={(option) => {
          void pick(option);
        }}
      />
      {error !== null ? (
        <p role="alert" className={styles.error}>
          {error}
        </p>
      ) : null}
      <Button
        size="lg"
        variant="ghost"
        onClick={() => {
          setOpen(false);
          setText("");
          setError(null);
        }}
      >
        Cancelar
      </Button>
    </section>
  );
}
