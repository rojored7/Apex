// S5-F1 · US-127 y US-128 (front): /avisos/hoy (PorAvisarHoy.html), admin y coach.
// - Título con la fecha de Bogotá, nota con el total, "Historial" y "Regenerar lista".
// - Chips de canal ("Pendientes de WhatsApp", "Correo por enviar", "Todos") en la URL como `canal`;
//   filtran la página cargada. Los conteos de los dos primeros solo se muestran cuando la lista cabe
//   en una página (si no, no serían ciertos).
// - Lista de tarjetas (TodayRow), paginada en el servidor. Estados: carga, vacío con guía, fuera de
//   rango, filtro sin filas, error con Reintentar (403, 429, 5xx, respuesta inválida).
// - "Abrir WhatsApp" y "Omitir" confirman con un aviso que se puede cerrar.
// DESIGN-GAP:
// - "Regenerar lista": no hay endpoint, el job `notify` genera la lista cada mañana. El botón se ve
//   deshabilitado con su explicación.
// - "Ya avisados": GET /notifications/today solo trae pendientes y fallidos (S5-D219); lo ya enviado
//   se ve en el historial. Sin filas en gris ni "Reenviar" y sin el chip.
// - Los chips "Vence hoy", "Vence en 3 días", "Vencidos" y "Sin entrenar 10+ días" necesitan filtros
//   del api que no existen en v0.2.
// - El diseño abre en "Pendientes de WhatsApp"; aquí se abre en "Todos" porque el api no filtra por
//   canal y una página filtrada puede dejar fuera avisos que sí existen.
// - "Lista generada a las 7:00": el api no dice a qué hora se generó.
import { useState } from "react";
import { Link } from "react-router";
import { formatCount, formatLongDate, todayBogota } from "../../../core/i18n/format";
import { useListParams } from "../../../shared/hooks/useListParams";
import { Button } from "../../../shared/ui/Button";
import { Chips, type ChipOption } from "../../../shared/ui/Chips";
import { PageHeader, type PageAction } from "../../../shared/ui/PageHeader";
import { Pagination } from "../../../shared/ui/Pagination";
import { useToday } from "../api";
import { SkipModal, type SkipTarget } from "../components/SkipModal";
import { TodayRow } from "../components/TodayRow";
import { todayError } from "../noticeErrors";
import { CANAL_FILTERS, type CanalFilter, type NotificationRowView } from "../schemas";
import styles from "./TodayPage.module.css";

const FILTERS = ["canal"] as const;

const CANAL_LABELS: Readonly<Record<Exclude<CanalFilter, "todos">, string>> = { whatsapp: "Pendientes de WhatsApp", correo: "Correo por enviar" };
const CANAL_EMPTY: Readonly<Record<Exclude<CanalFilter, "todos">, string>> = {
  whatsapp: "No hay avisos de WhatsApp en esta página.",
  correo: "No hay avisos de correo en esta página.",
};

export const TODAY_EMPTY = "Nadie por avisar hoy";
export const TODAY_PAST_END = "Esta página ya no tiene avisos.";

const HEADER_ACTIONS: PageAction[] = [
  { id: "regenerate", label: "Regenerar lista", disabled: true },
  { id: "history", label: "Historial", href: "/avisos/historial" },
];

function pickCanal(values: readonly string[]): CanalFilter {
  return CANAL_FILTERS.find((value) => value === values[0]) ?? "todos";
}

const isWhatsapp = (row: NotificationRowView): boolean => row.channel === "whatsapp_link";

function noteText(total: number, items: readonly NotificationRowView[]): string {
  if (items.length < total) return `${formatCount(total)} por atender.`;
  const whatsapp = items.filter(isWhatsapp).length;
  const mail = items.length - whatsapp;
  return `${formatCount(total)} por atender: ${formatCount(whatsapp)} esperan WhatsApp, ${formatCount(mail)} ${mail === 1 ? "es" : "son"} de correo.`;
}

export default function TodayPage() {
  const list = useListParams<(typeof FILTERS)[number]>({ filters: FILTERS });
  const { limit, offset } = list.params;
  const canal = pickCanal(list.filters.canal);
  const today = useToday({ limit, offset });
  const [notice, setNotice] = useState<string | null>(null);
  const [skipping, setSkipping] = useState<SkipTarget | null>(null);

  const page = today.data;
  const settled = today.isPlaceholderData ? undefined : page;
  const error = todayError(today.error);
  const isLoading = today.isLoading || today.isPlaceholderData;
  const items = settled?.items ?? [];
  // Los conteos por canal solo son ciertos si la lista entera está en esta página.
  const isComplete = settled !== undefined && offset === 0 && items.length === settled.total;
  const whatsappCount = items.filter(isWhatsapp).length;
  const shown = canal === "todos" ? items : items.filter((row) => (canal === "whatsapp") === isWhatsapp(row));
  const isPastEnd = settled !== undefined && settled.total > 0 && items.length === 0;

  const chipOptions: ChipOption[] = [
    { value: "whatsapp", label: CANAL_LABELS.whatsapp, ...(isComplete ? { count: whatsappCount } : {}) },
    { value: "correo", label: CANAL_LABELS.correo, ...(isComplete ? { count: items.length - whatsappCount } : {}) },
    { value: "todos", label: "Todos", ...(settled ? { count: settled.total } : {}) },
  ];

  return (
    <div className={styles.page}>
      <PageHeader title={`Por avisar hoy · ${formatLongDate(todayBogota())}`} actions={HEADER_ACTIONS} />
      <p className={styles.note}>La lista la genera el sistema cada mañana.</p>
      <p className={styles.note}>Si no se abre WhatsApp, permite las ventanas emergentes de este sitio.</p>
      {settled && settled.total > 0 ? <p className={styles.note}>{noteText(settled.total, items)}</p> : null}
      {notice ? (
        <div role="status" className={styles.notice}>
          <span>{notice}</span>
          <Button
            variant="ghost"
            aria-label="Cerrar aviso"
            onClick={() => {
              setNotice(null);
            }}
          >
            Cerrar
          </Button>
        </div>
      ) : null}
      {settled && settled.total > 0 ? (
        <Chips
          label="Canal"
          mode="single"
          options={chipOptions}
          value={[canal]}
          onChange={(value) => {
            const next = value[0];
            if (next !== undefined) list.setFilter("canal", next === "todos" ? undefined : next);
          }}
        />
      ) : null}
      {error ? (
        <div role="alert" className={styles.problem}>
          <p>{error.message}</p>
          <Button
            variant="secondary"
            onClick={() => {
              void today.refetch();
            }}
          >
            Reintentar
          </Button>
        </div>
      ) : isLoading ? (
        <p role="status" aria-busy="true" className={styles.state}>
          Cargando avisos…
        </p>
      ) : settled && settled.total === 0 ? (
        <div className={styles.empty}>
          <h2 className={styles.emptyTitle}>{TODAY_EMPTY}</h2>
          <p>El sistema genera los avisos cada mañana. Cuando un socio tenga algo que avisar, aparecerá aquí con el mensaje ya escrito.</p>
          <Link to="/avisos/historial">Ver el historial de envíos</Link>
        </div>
      ) : isPastEnd ? (
        <div className={styles.empty}>
          <p>{TODAY_PAST_END}</p>
          <Button
            variant="secondary"
            onClick={() => {
              list.setPage(1);
            }}
          >
            Ir a la primera página
          </Button>
        </div>
      ) : shown.length === 0 && canal !== "todos" ? (
        <div className={styles.empty}>
          <p>{CANAL_EMPTY[canal]}</p>
          <Button
            variant="secondary"
            onClick={() => {
              list.setFilter("canal", undefined);
            }}
          >
            Ver todos
          </Button>
        </div>
      ) : (
        <ul aria-label="Avisos de hoy" className={styles.list}>
          {shown.map((row) => (
            <TodayRow
              key={row.id}
              row={row}
              onOpened={(name) => {
                setNotice(`WhatsApp abierto para ${name}. El aviso quedó marcado como enviado.`);
              }}
              onSkip={(target) => {
                setSkipping({ id: target.id, member_name: target.member_name });
              }}
            />
          ))}
        </ul>
      )}
      {settled && settled.total > 0 ? (
        <Pagination total={settled.total} limit={limit} offset={offset} onPageChange={list.setPage} onLimitChange={list.setLimit} />
      ) : null}
      <aside className={styles.how}>
        <p>
          <b>Cómo funciona.</b> «Abrir WhatsApp» lanza wa.me con el mensaje ya escrito; al tocarlo, el aviso queda marcado como «enviado por WhatsApp» con hora y usuario y sale de esta lista. «Omitir» pide
          un motivo corto (ya pagó, no contactar) y también queda en el historial. En celular cada fila es una tarjeta y el botón de WhatsApp ocupa todo el ancho. El teléfono nunca se muestra completo: el
          enlace lo arma el servidor.
        </p>
      </aside>
      <SkipModal
        target={skipping}
        onClose={() => {
          setSkipping(null);
        }}
        onSkipped={(name) => {
          setNotice(`Aviso de ${name} omitido. Quedó en el historial con tu motivo.`);
        }}
      />
    </div>
  );
}
