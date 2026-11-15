// S8-F6 · US-177 (S8-D19, S8-D20, S8-D32, L-4): /tv, la pantalla de la pared del box (TV.html), dentro de TvLayout (1920 × 1080, oscura,
// sin cursor ni interacción). Sin usuario: abre con el enlace `/tv#token=<token>` que da Configuración.
// - Al montar: lee el token (consumeTvToken: solo el fragmento #token=, guardado en el navegador de la TV; un ?token= se descarta) y deja la URL en /tv ANTES de la
//   primera petición; y llama POST /auth/logout (L-4) para que la TV no quede con una sesión de panel abierta.
// - Pide GET /tv/today solo con X-Device-Token (core/api/tvClient) y refresca cada `refresh_seconds`.
// - Estados: cargando, WOD + ranking, `wod: null` (logo y «Sin WOD publicado»), 401 («Token inválido. Pide un enlace nuevo en
//   Configuración», con reintento cada 5 minutos), sin token en la URL ni guardado, y red caída, 429 o 5xx («Sin conexión» sobre lo último).
// DESIGN-GAP (S8-D19): TV.html agrupa el ranking por sexo y nivel, rota entre tres grupos y muestra la diferencia con la vez anterior,
// «PR» y el escalado sugerido; aquí hay UN solo ranking «Todos» sin sexo, 15 filas por página que rotan (el contrato de la TV no trae
// sexo ni historial, EP-24). El pie «Próxima clase 18:00 · Coach María · 0 / 12» tampoco: el tablero no trae clases.
import { QueryClientProvider } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { createQueryClient } from "../../../core/api/queryClient";
import { logout } from "../../../core/auth";
import { formatLongDate, formatTime24 } from "../../../core/i18n/format";
import { TvRequestError } from "../../../core/api/tvClient";
import { useTvBoard } from "../api";
import { TvLeaderboard } from "../components/TvLeaderboard";
import { TvWod } from "../components/TvWod";
import { consumeTvToken } from "../tvToken";
import styles from "./TvPage.module.css";

const LOGO_DARK = "/brand/apex-logo-dark-bg.png";
const LOGO_ALT = "APEX Hybrid Training";
const CLOCK_TICK_MS = 15_000;

export const TV_MESSAGES = {
  invalid: "Token inválido. Pide un enlace nuevo en Configuración",
  missing: "Falta el enlace de la pantalla. Pide un enlace nuevo en Configuración.",
  loading: "Cargando la pantalla…",
  offline: "Sin conexión",
  noWod: "Sin WOD publicado",
  privacy: "Solo nombre y puntaje: nunca datos personales en la TV",
} as const;

function useClock(): string {
  const [now, setNow] = useState(() => new Date().toISOString());
  useEffect(() => {
    const timer = setInterval(() => {
      setNow(new Date().toISOString());
    }, CLOCK_TICK_MS);
    return () => {
      clearInterval(timer);
    };
  }, []);
  return formatTime24(now);
}

function Message({ text, role }: { text: string; role: "alert" | "status" }) {
  return (
    <div className={styles.message}>
      <img className={styles.logo} src={LOGO_DARK} alt={LOGO_ALT} />
      <p role={role} className={styles.messageText}>
        {text}
      </p>
    </div>
  );
}

function TvScreen() {
  const [token] = useState(consumeTvToken);
  const clock = useClock();
  const board = useTvBoard(token);

  // L-4: la TV no deja una sesión de panel abierta en este navegador.
  useEffect(() => {
    void logout();
  }, []);

  const failure = board.error instanceof TvRequestError ? board.error.failure : null;
  if (token === null) return <Message text={TV_MESSAGES.missing} role="alert" />;
  if (failure === "invalid_token") return <Message text={TV_MESSAGES.invalid} role="alert" />;
  const data = board.data;
  if (data === undefined) {
    return failure === null ? <Message text={TV_MESSAGES.loading} role="status" /> : <Message text={TV_MESSAGES.offline} role="status" />;
  }

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <img className={styles.logo} src={LOGO_DARK} alt={LOGO_ALT} />
        <span className={styles.date}>{formatLongDate(data.date)}</span>
        {failure === null ? null : (
          <span role="status" className={styles.offline}>
            {TV_MESSAGES.offline}
          </span>
        )}
        <span className={styles.clock}>{clock}</span>
      </header>
      {data.wod === null ? (
        <div className={styles.empty}>
          <img className={styles.emptyLogo} src={LOGO_DARK} alt="" />
          <p className={styles.messageText}>{TV_MESSAGES.noWod}</p>
        </div>
      ) : (
        <div className={styles.body}>
          <TvWod wod={data.wod} />
          {data.show_leaderboard ? <TvLeaderboard rows={data.leaderboard} scoreType={data.wod.score_type} /> : null}
        </div>
      )}
      <footer className={styles.footer}>
        <span>{TV_MESSAGES.privacy}</span>
      </footer>
    </div>
  );
}

/**
 * La TV tiene su PROPIO QueryClient (S8-F6b, M-1): al montar cierra la sesión del panel (L-4) y clearSession vacía el cliente global;
 * con el global, el GET /tv/today en vuelo se perdía y la pantalla quedaba en «Cargando…».
 */
export default function TvPage() {
  const [tvQueryClient] = useState(createQueryClient);
  return (
    <QueryClientProvider client={tvQueryClient}>
      <TvScreen />
    </QueryClientProvider>
  );
}
