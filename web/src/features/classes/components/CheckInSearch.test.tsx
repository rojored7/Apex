// S7-F4 · US-159: el buscador de la tablet: 2 caracteres como mínimo y 300 ms de espera; el 429 dice «Espera un momento».
// Solo trae nombre, estado, plan y foto (N-01); «Llegó» y «Vender» avisan al padre.
import { QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { MemoryRouter } from "react-router";
import { SessionRoleProvider } from "../../../core/auth";
import { apiError, MEMBER_ROWS, membersPage } from "../../../test/classes";
import { mockApi, testQueryClient, type MockHandler } from "../../../test/server";
import { signInAs, signOutForTests } from "../../../test/session";
import { CheckInSearch } from "./CheckInSearch";

function Harness({ onArrive, onSell, pending = false }: { onArrive: (id: string) => void; onSell: (id: string) => void; pending?: boolean }) {
  const [text, setText] = useState("");
  return (
    <CheckInSearch
      text={text}
      onTextChange={setText}
      arrived={new Set()}
      pending={pending}
      onArrive={(option) => {
        onArrive(option.id);
      }}
      onSell={(option) => {
        onSell(option.id);
      }}
    />
  );
}

function renderSearch(handlers: Record<string, MockHandler> = {}, pending = false) {
  const mock = mockApi({ "GET /members": membersPage([MEMBER_ROWS.laura, MEMBER_ROWS.elena]), ...handlers });
  const onArrive = vi.fn();
  const onSell = vi.fn();
  render(
    <QueryClientProvider client={testQueryClient()}>
      <SessionRoleProvider>
        <MemoryRouter>
          <Harness onArrive={onArrive} onSell={onSell} pending={pending} />
        </MemoryRouter>
      </SessionRoleProvider>
    </QueryClientProvider>,
  );
  return { mock, onArrive, onSell, user: userEvent.setup() };
}

const box = () => screen.getByRole("searchbox", { name: "Buscar socio" });

beforeEach(() => {
  signInAs("coach");
});
afterEach(() => {
  cleanup();
  signOutForTests();
  vi.unstubAllGlobals();
});

describe("CheckInSearch · mínimo del servidor (S7-C4c)", () => {
  it("los espacios no cuentan: «l a» no pide nada", async () => {
    const { mock, user } = renderSearch();
    await user.type(box(), "l a ");
    await new Promise((resolve) => setTimeout(resolve, 400));

    expect(mock.callsTo("GET /members")).toHaveLength(0);
    expect(screen.getByText("Escribe al menos 3 letras para buscar.")).toBeInTheDocument();
  });

  it("pide como máximo 20 resultados y nunca manda sort", async () => {
    const { mock, user } = renderSearch();
    await user.type(box(), "lau");
    await screen.findByRole("list", { name: "Socios encontrados" });

    const params = new URL(mock.callsTo("GET /members")[0]?.url ?? "", "http://apex.test").searchParams;
    expect(Number(params.get("limit"))).toBeLessThanOrEqual(20);
    expect(params.has("sort")).toBe(false);
  });
});

describe("CheckInSearch", () => {
  it("con menos de 3 letras no pide nada y dice cuántas escribir", async () => {
    const { mock, user } = renderSearch();
    await user.type(box(), "la");
    await new Promise((resolve) => setTimeout(resolve, 400));

    expect(mock.callsTo("GET /members")).toHaveLength(0);
    expect(screen.getByText("Escribe al menos 3 letras para buscar.")).toBeInTheDocument();
  });

  it("con 3 letras espera 300 ms de calma y hace una sola petición con q", async () => {
    const { mock, user } = renderSearch();
    await user.type(box(), "lau");

    expect(await screen.findByRole("list", { name: "Socios encontrados" })).toBeInTheDocument();
    const calls = mock.callsTo("GET /members");
    expect(calls).toHaveLength(1);
    expect(new URL(calls[0]?.url ?? "", "http://apex.test").searchParams.get("q")).toBe("lau");
  });

  it("sin resultados guía al coach; cada fila trae nombre, nota y estado", async () => {
    const { user } = renderSearch({ "GET /members": membersPage([]) });
    await user.type(box(), "zzz");
    expect(await screen.findByText("No encontramos a nadie con ese nombre. Revisa cómo está escrito.")).toBeInTheDocument();
  });

  it("«Llegó» y «Vender» avisan al padre con el socio elegido", async () => {
    const { user, onArrive, onSell } = renderSearch();
    await user.type(box(), "ele");
    const list = await screen.findByRole("list", { name: "Socios encontrados" });

    await user.click(within(list).getAllByRole("button", { name: "Llegó" })[0] as HTMLElement);
    expect(onArrive).toHaveBeenCalledWith("mem-laura");
    await user.click(within(list).getByRole("button", { name: "Vender" }));
    expect(onSell).toHaveBeenCalledWith("mem-elena");
  });

  it("mientras se registra una llegada los botones quedan deshabilitados", async () => {
    const { user } = renderSearch({}, true);
    await user.type(box(), "lau");
    const list = await screen.findByRole("list", { name: "Socios encontrados" });

    for (const button of within(list).getAllByRole("button")) expect(button).toBeDisabled();
  });

  it("429: «Espera un momento»; otro error: dice que no se pudo buscar", async () => {
    const { user } = renderSearch({ "GET /members": apiError(429, "rate_limited") });
    await user.type(box(), "lau");
    expect(await screen.findByText("Espera un momento y vuelve a buscar.")).toBeInTheDocument();
    cleanup();

    const second = renderSearch({ "GET /members": apiError(500, "internal_error") });
    await second.user.type(box(), "lau");
    expect(await screen.findByText("No pudimos buscar. Intenta de nuevo en un momento.")).toBeInTheDocument();
  });
});
