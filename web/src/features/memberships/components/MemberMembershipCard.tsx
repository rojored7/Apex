// S3-F7 · US-093 (front): tarjeta de la membresía vigente o de la futura en la pestaña Membresías de
// la ficha (la caja "Membresía" de Socio_Ficha.html: "Vence en 8 días · Mensual · $120.000 · pagada").
// - Plan, StatusTag, vigencia, días restantes (vigente) o "Empieza el …" (futura), clases si el plan
//   es de clases, precio, pagado, saldo y congelaciones.
// - Acciones que decide membershipActions: Registrar saldo (?pago=<membresía>, S3-D65), Congelar y
//   Anular. Cada una nombra la membresía para el lector de pantalla.
// DESIGN-GAP:
// - La tarjeta de la futura no está dibujada (el diseño solo muestra la vigente; BRECHAS §10).
// - "Pendiente de pago" (Q3) no está dibujado: StatusTag con el tono de "Por vencer" y su texto.
// - La vigencia lleva el año ("29 sept 2026 – 28 oct 2026", DESIGN.md regla 7).
import { useId, type ReactNode } from "react";
import { Link, useLocation } from "react-router";
import { formatCop, formatCount, formatDate } from "../../../core/i18n/format";
import type { FreezeOutView, MembershipOutView } from "../../../shared/data/memberships";
import { paymentPanelHref } from "../../../shared/lib/paymentPanel";
import { Button } from "../../../shared/ui/Button";
import buttonStyles from "../../../shared/ui/Button.module.css";
import { cx } from "../../../shared/ui/cx";
import { StatusTag } from "../../../shared/ui/StatusTag";
import { classesRemainingText, daysLeftText, saldo } from "../lib/rules";
import styles from "./MemberMembershipsTab.module.css";

export type MembershipCardKind = "current" | "future";

export const CARD_TITLES = { current: "Membresía vigente", future: "Próxima membresía" } as const satisfies Record<MembershipCardKind, string>;

export interface MembershipCardActions {
  pay: boolean;
  freeze: boolean;
  cancel: boolean;
}

export interface MemberMembershipCardProps {
  kind: MembershipCardKind;
  membership: MembershipOutView;
  today: string;
  actions: MembershipCardActions;
  onFreeze: (membership: MembershipOutView) => void;
  onCancel: (membership: MembershipOutView) => void;
}

/** "Del 5 oct 2026 al 9 oct 2026 · 5 días". */
export function freezeText(freeze: FreezeOutView): string {
  const days = freeze.days === 1 ? "1 día" : `${formatCount(freeze.days)} días`;
  return `Del ${formatDate(freeze.frozen_from)} al ${formatDate(freeze.frozen_to)} · ${days}`;
}

function Fact({ label, children, wide = false }: { label: string; children: ReactNode; wide?: boolean }) {
  return (
    <div className={cx(styles.fact, wide && styles.factWide)}>
      <dt className={styles.label}>{label}</dt>
      <dd className={styles.value}>{children}</dd>
    </div>
  );
}

function CardActions({ membership, actions, onFreeze, onCancel }: Pick<MemberMembershipCardProps, "membership" | "actions" | "onFreeze" | "onCancel">) {
  const location = useLocation();
  if (!actions.pay && !actions.freeze && !actions.cancel) return null;
  const plan = membership.plan_name;
  return (
    <div className={styles.actions}>
      {actions.pay ? (
        <Link
          className={cx(buttonStyles.button, buttonStyles.primary, buttonStyles.md)}
          to={paymentPanelHref(location, { membershipId: membership.id })}
          aria-label={`Registrar saldo de la membresía ${plan}`}
        >
          Registrar saldo
        </Link>
      ) : null}
      {actions.freeze ? (
        <Button
          variant="secondary"
          aria-label={`Congelar la membresía ${plan}`}
          onClick={() => {
            onFreeze(membership);
          }}
        >
          Congelar
        </Button>
      ) : null}
      {actions.cancel ? (
        <Button
          variant="danger"
          aria-label={`Anular la membresía ${plan}`}
          onClick={() => {
            onCancel(membership);
          }}
        >
          Anular
        </Button>
      ) : null}
    </div>
  );
}

export function MemberMembershipCard({ kind, membership, today, actions, onFreeze, onCancel }: MemberMembershipCardProps) {
  const titleId = useId();
  const m = membership;
  return (
    <section aria-labelledby={titleId} className={cx(styles.card, kind === "current" && styles.current)}>
      <div className={styles.cardHead}>
        <h2 id={titleId} className={styles.cardTitle}>
          {CARD_TITLES[kind]}
        </h2>
        <StatusTag status={m.status} />
      </div>
      <p className={styles.plan}>{m.plan_name}</p>
      <p className={styles.when}>{`${formatDate(m.start_date)} – ${formatDate(m.end_date)}`}</p>
      <p className={styles.days}>{kind === "current" ? daysLeftText(today, m.end_date) : `Empieza el ${formatDate(m.start_date)}`}</p>
      <dl className={styles.facts}>
        {m.classes_total !== null ? <Fact label="Clases">{classesRemainingText(m.classes_remaining, m.classes_total)}</Fact> : null}
        <Fact label="Precio">{formatCop(m.agreed_price_cop)}</Fact>
        <Fact label="Pagado">{formatCop(m.paid_cop)}</Fact>
        <Fact label="Saldo">{formatCop(saldo(m.agreed_price_cop, m.paid_cop))}</Fact>
        <Fact label="Congelaciones" wide>
          {m.freezes.length === 0 ? (
            "Sin congelaciones"
          ) : (
            <ul className={styles.freezes}>
              {m.freezes.map((freeze) => (
                <li key={freeze.id}>{freezeText(freeze)}</li>
              ))}
            </ul>
          )}
        </Fact>
      </dl>
      <CardActions membership={m} actions={actions} onFreeze={onFreeze} onCancel={onCancel} />
    </section>
  );
}
