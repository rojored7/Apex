// S8-F6 · US-177 (front, S8-D19, S8-D20, S8-D32, L-4): /tv, la pantalla de la pared. Sin usuario: el token viaja solo en la cabecera
// X-Device-Token, sin Authorization ni cookies. Lo lee del fragmento (#token=; por compatibilidad también ?token=), lo guarda en el
// navegador de la TV (localStorage, `apex.tv.token`; S8-D32) y limpia la URL ANTES de la primera petición.
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";
import { mockApi, testQueryClient, type MockHandler, type MockReply, type RecordedCall } from "../../../test/server";
import { signOutForTests } from "../../../test/session";
import { tvBoard, tvRows, TV_TOKEN } from "../../../test/tv";
import TvPage from "./TvPage";

const TODAY = "GET /tv/today";
const REFRESH_MS = 30_000;
const INVALID_RETRY_MS = 5 * 60_000;
const INVALID_TEXT = "Token inválido. Pide un enlace nuevo en Configuración";
const OFFLINE = "Sin conexión";

const ok = (board = tvBoard()): MockReply => ({ status: 200, body: board });
const unauthorized: MockReply = { status: 401, body: { error: { code: "unauthorized", message: "No autorizado." } } };
const serverDown: MockReply = { status: 503, body: { error: { code: "busy", message: "x" } } };

function renderTv() {
  const queryClient = testQueryClient();
  const view = render(
    <QueryClientProvider client={queryClient}>
      <TvPage />
    </QueryClientProvider>,
  );
  return { ...view, queryClient };
}

/** El navegador de la TV recién abierto con el enlace. */
function openWith(urlSuffix: string): void {
  window.localStorage.clear();
  window.history.replaceState(null, "", `/tv${urlSuffix}`);
}

const advance = async (ms: number): Promise<void> => {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
};

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  window.localStorage.clear();
});

afterEach(() => {
  cleanup();
  signOutForTests();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  window.localStorage.clear();
  window.history.replaceState(null, "", "/");
});

describe("TvPage · el token", () => {
  it("lee_el_fragmento_y_limpia_la_url_antes_de_pedir", async () => {
    openWith(`#token=${TV_TOKEN}`);
    const seen: { hash: string; pathname: string; search: string }[] = [];
    const mock = mockApi({
      [TODAY]: () => {
        seen.push({ hash: window.location.hash, pathname: window.location.pathname, search: window.location.search });
        return ok();
      },
      "POST /auth/logout": { status: 204 },
    });

    renderTv();

    await screen.findByRole("heading", { name: "Helen" });
    expect(seen[0]).toEqual({ hash: "", pathname: "/tv", search: "" });
    expect(mock.callsTo(TODAY)[0]?.headers.get("x-device-token")).toBe(TV_TOKEN);
  });

  it("compatibilidad_con_query: un ?token= también se usa y se limpia", async () => {
    openWith(`?token=${TV_TOKEN}`);
    let urlWhenAsked = "";
    const mock = mockApi({
      [TODAY]: () => {
        urlWhenAsked = `${window.location.pathname}${window.location.search}${window.location.hash}`;
        return ok();
      },
      "POST /auth/logout": { status: 204 },
    });

    renderTv();

    await screen.findByRole("heading", { name: "Helen" });
    expect(urlWhenAsked).toBe("/tv");
    expect(mock.callsTo(TODAY)[0]?.headers.get("x-device-token")).toBe(TV_TOKEN);
  });

  it("no_envia_authorization_ni_cookies: solo X-Device-Token y credentials omit", async () => {
    openWith(`#token=${TV_TOKEN}`);
    const mock = mockApi({ [TODAY]: ok(), "POST /auth/logout": { status: 204 } });

    renderTv();

    await screen.findByRole("heading", { name: "Helen" });
    const call: RecordedCall | undefined = mock.callsTo(TODAY)[0];
    expect(call?.credentials).toBe("omit");
    expect(call?.headers.has("authorization")).toBe(false);
    expect(call?.url).not.toContain("token");
  });

  it("guarda el token en el navegador de la TV: tras un reinicio, sin fragmento, sigue funcionando", async () => {
    openWith(`#token=${TV_TOKEN}`);
    mockApi({ [TODAY]: ok(), "POST /auth/logout": { status: 204 } });
    const first = renderTv();
    await screen.findByRole("heading", { name: "Helen" });
    first.unmount();
    vi.unstubAllGlobals();

    const mock = mockApi({ [TODAY]: ok(), "POST /auth/logout": { status: 204 } });
    renderTv();

    await screen.findByRole("heading", { name: "Helen" });
    expect(mock.callsTo(TODAY)[0]?.headers.get("x-device-token")).toBe(TV_TOKEN);
  });

  it("sin token (ni en la URL ni guardado) dice qué hacer y no pide nada", async () => {
    openWith("");
    const mock = mockApi({ [TODAY]: ok(), "POST /auth/logout": { status: 204 } });

    renderTv();

    expect(await screen.findByText("Falta el enlace de la pantalla. Pide un enlace nuevo en Configuración.")).toBeInTheDocument();
    await advance(REFRESH_MS * 2);
    expect(mock.callsTo(TODAY)).toHaveLength(0);
  });

  it("un token con forma inválida se descarta, pero la URL se limpia igual", async () => {
    openWith("#token=<script>alert(1)</script>");
    const mock = mockApi({ [TODAY]: ok(), "POST /auth/logout": { status: 204 } });

    renderTv();

    expect(await screen.findByText(/Falta el enlace de la pantalla/)).toBeInTheDocument();
    expect(window.location.hash).toBe("");
    expect(mock.callsTo(TODAY)).toHaveLength(0);
  });

  it("llama_logout_al_montar: la TV no deja una sesión de panel abierta (L-4)", async () => {
    openWith(`#token=${TV_TOKEN}`);
    const mock = mockApi({ [TODAY]: ok(), "POST /auth/logout": { status: 204 } });

    renderTv();

    await screen.findByRole("heading", { name: "Helen" });
    await waitFor(() => {
      expect(mock.callsTo("POST /auth/logout")).toHaveLength(1);
    });
  });
});

describe("TvPage · el tablero", () => {
  const withLogout = (handler: MockHandler): Record<string, MockHandler> => ({ [TODAY]: handler, "POST /auth/logout": { status: 204 } });

  it("200: muestra el WOD y el ranking «Todos» con «Ana P.»", async () => {
    openWith(`#token=${TV_TOKEN}`);
    mockApi(withLogout(ok()));

    renderTv();

    expect(await screen.findByRole("heading", { name: "Helen" })).toBeInTheDocument();
    expect(screen.getByText("Ana P.")).toBeInTheDocument();
    expect(screen.getByText("9:58")).toBeInTheDocument();
    expect(screen.getByText("Solo nombre y puntaje: nunca datos personales en la TV")).toBeInTheDocument();
    expect(screen.queryByText(OFFLINE)).not.toBeInTheDocument();
  });

  it("pide el tablero de nuevo cada refresh_seconds del servidor", async () => {
    openWith(`#token=${TV_TOKEN}`);
    const mock = mockApi(withLogout(ok(tvBoard({ refresh_seconds: 30 }))));
    renderTv();
    await screen.findByRole("heading", { name: "Helen" });
    expect(mock.callsTo(TODAY)).toHaveLength(1);

    await advance(REFRESH_MS + 500);
    await waitFor(() => {
      expect(mock.callsTo(TODAY)).toHaveLength(2);
    });
  });

  it("wod_null: logo y «Sin WOD publicado», sin ranking", async () => {
    openWith(`#token=${TV_TOKEN}`);
    mockApi(withLogout(ok(tvBoard({ wod: null, leaderboard: [] }))));

    renderTv();

    expect(await screen.findByText("Sin WOD publicado")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "APEX Hybrid Training" })).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("con más de 15 filas el ranking rota por páginas", async () => {
    openWith(`#token=${TV_TOKEN}`);
    mockApi(withLogout(ok(tvBoard({ leaderboard: tvRows(20) }))));
    renderTv();
    expect(await screen.findByText("Página 1 de 2")).toBeInTheDocument();

    await advance(12_000);

    expect(await screen.findByText("Página 2 de 2")).toBeInTheDocument();
  });

  it("401: dice «Token inválido» y reintenta cada 5 minutos; con un token nuevo vuelve a mostrar el tablero", async () => {
    openWith(`#token=${TV_TOKEN}`);
    let calls = 0;
    const mock = mockApi(
      withLogout(() => {
        calls += 1;
        return calls < 3 ? unauthorized : ok();
      }),
    );
    renderTv();

    expect(await screen.findByText(INVALID_TEXT)).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Helen" })).not.toBeInTheDocument();
    expect(mock.callsTo(TODAY)).toHaveLength(1);

    await advance(REFRESH_MS * 2);
    expect(mock.callsTo(TODAY)).toHaveLength(1);

    await advance(INVALID_RETRY_MS);
    await waitFor(() => {
      expect(mock.callsTo(TODAY)).toHaveLength(2);
    });
    expect(screen.getByText(INVALID_TEXT)).toBeInTheDocument();

    await advance(INVALID_RETRY_MS);
    expect(await screen.findByRole("heading", { name: "Helen" })).toBeInTheDocument();
    expect(screen.queryByText(INVALID_TEXT)).not.toBeInTheDocument();
  });

  it("tras rotar el token en pleno servicio (200 y luego 401) deja de mostrar el tablero viejo", async () => {
    openWith(`#token=${TV_TOKEN}`);
    let calls = 0;
    mockApi(
      withLogout(() => {
        calls += 1;
        return calls === 1 ? ok() : unauthorized;
      }),
    );
    renderTv();
    await screen.findByRole("heading", { name: "Helen" });

    await advance(REFRESH_MS + 500);

    expect(await screen.findByText(INVALID_TEXT)).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Helen" })).not.toBeInTheDocument();
  });

  it.each([
    ["red caída", () => Promise.reject(new TypeError("Failed to fetch"))],
    ["5xx", () => serverDown],
  ])("%s: conserva lo último con «Sin conexión» y se recupera sola", async (_name, failure) => {
    openWith(`#token=${TV_TOKEN}`);
    let calls = 0;
    mockApi(
      withLogout(async () => {
        calls += 1;
        if (calls === 2) return failure();
        return ok();
      }),
    );
    renderTv();
    await screen.findByRole("heading", { name: "Helen" });

    await advance(REFRESH_MS + 500);
    expect(await screen.findByText(OFFLINE)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Helen" })).toBeInTheDocument();
    expect(screen.getByText("Ana P.")).toBeInTheDocument();

    await advance(REFRESH_MS + 500);
    await waitFor(() => {
      expect(screen.queryByText(OFFLINE)).not.toBeInTheDocument();
    });
  });

  it("una respuesta con otra forma no se pinta: queda «Sin conexión»", async () => {
    openWith(`#token=${TV_TOKEN}`);
    mockApi(withLogout({ status: 200, body: { date: "hoy", wod: { title: 7 } } }));

    renderTv();

    expect(await screen.findByText(OFFLINE)).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Helen" })).not.toBeInTheDocument();
  });

  it("no_guarda_la_respuesta_en_el_almacenamiento: solo el token vive en localStorage y nada en sessionStorage", async () => {
    openWith(`#token=${TV_TOKEN}`);
    mockApi(withLogout(ok()));
    renderTv();
    await screen.findByRole("heading", { name: "Helen" });

    expect(Object.keys(window.localStorage)).toEqual(["apex.tv.token"]);
    expect(Object.keys(window.sessionStorage)).toEqual([]);
  });
});
