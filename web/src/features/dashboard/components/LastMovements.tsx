// S4A-F3 · US-110 (front): "Últimos movimientos" de Inicio (Inicio.html). Hasta diez frases ya armadas
// por el api (S4A-D28, sin correos ni valores cifrados), en su orden, con la hora relativa de Bogotá
// (la fecha completa en `title` y `dateTime`). La frase de un movimiento con socio enlaza a su ficha
// (/socios/:id); todo va como texto de React, así que una frase con HTML se ve literal.
// Estados: carga, vacío que explica qué aparecerá, y error con el qué pasó y "Reintentar".
// "Ver auditoría" solo para quien puede verla (audit.view; el coach no).
// DESIGN-GAP: "Sistema marcó 3 membresías como vencidas" no aparece: el api excluye al usuario del
// sistema (Q10, US-110) para que el job de vencimientos no tape lo de recepción.
// No es HistoryAside del kit (S4A-D33): este pinta entradas de auditoría con fecha absoluta y sin
// enlaces; aquí cada frase lleva la hora relativa y el enlace a la ficha.
import { Link } from "react-router";
import { Can } from "../../../core/auth";
import { formatDateTime, formatRelativeTime } from "../../../core/i18n/format";
import { isUuid } from "../../../shared/lib/ids";
import { memberHref } from "../../../shared/lib/routes";
import { Button } from "../../../shared/ui/Button";
import { useDashboard } from "../api";
import { movementsErrorMessage } from "../dashboardErrors";
import type { MovementView } from "../schemas";
import styles from "./LastMovements.module.css";

const AUDIT_PATH = "/sistema/auditoria";
export const EMPTY_MOVEMENTS = "Todavía no hay movimientos del equipo. Cuando alguien registre un socio, venda una membresía o reciba un pago, aparece aquí.";

/** Una fila. Revisión de seguridad de F3 (M2): solo un `member_id` con forma de UUID se vuelve enlace. */
export function MovementItem({ movement, nowMs }: { movement: MovementView; nowMs: number }) {
  const phrase = <span data-phrase="">{movement.phrase}</span>;
  return (
    <li className={styles.item}>
      {movement.member_id && isUuid(movement.member_id) ? (
        <Link to={memberHref(movement.member_id)} className={styles.phrase}>
          {phrase}
        </Link>
      ) : (
        <span className={styles.phrase}>{phrase}</span>
      )}
      <time dateTime={movement.at} title={formatDateTime(movement.at)} className={styles.time}>
        {formatRelativeTime(movement.at, nowMs)}
      </time>
    </li>
  );
}

export function LastMovements() {
  const { data, dataUpdatedAt, isPending, isError, error, refetch, isFetching } = useDashboard();
  // La hora relativa se cuenta desde la lectura del tablero (render puro; se renueva con cada lectura).
  const nowMs = dataUpdatedAt;

  let body;
  if (data) {
    body =
      data.last_movements.length === 0 ? (
        <p className={styles.empty}>{EMPTY_MOVEMENTS}</p>
      ) : (
        <ol aria-label="Últimos movimientos" className={styles.list}>
          {data.last_movements.map((movement) => (
            <MovementItem key={movement.seq} movement={movement} nowMs={nowMs} />
          ))}
        </ol>
      );
  } else if (isError) {
    body = (
      <div className={styles.error}>
        <p className={styles.errorText}>{movementsErrorMessage(error)}</p>
        <Button
          variant="secondary"
          loading={isFetching}
          onClick={() => {
            void refetch();
          }}
        >
          Reintentar
        </Button>
      </div>
    );
  } else {
    body = (
      <p role="status" className={styles.empty}>
        Cargando movimientos
      </p>
    );
  }

  return (
    <section aria-labelledby="inicio-movimientos" aria-busy={isPending ? true : undefined} className={styles.box}>
      <div className={styles.head}>
        <h2 id="inicio-movimientos" className={styles.title}>
          Últimos movimientos
        </h2>
        <Can action="audit.view">
          <Link to={AUDIT_PATH} className={styles.more}>
            Ver auditoría
          </Link>
        </Can>
      </div>
      {body}
    </section>
  );
}
