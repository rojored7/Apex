// S3-F2 · US-072 (front): /socios en el celular (Socios_Movil.html), con `matchMedia` simulado a
// 390 px. La lista se vuelve tarjetas (D39) con nombre, StatusTag, plan y "vence"; la tarjeta
// entera es un enlace de al menos 44 px; "Cargar más" acumula (useInfiniteQuery) hasta el total
// o hasta 20 páginas (M-9, S3-D52); un error de la página siguiente conserva las tarjetas y
// ofrece "Reintentar"; "Nuevo socio" es un botón flotante con `members.create`; los chips se
// desplazan dentro de su caja. Nada enmascarado ni sensible (N-01).
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { focusManager, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, renderHook, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { axe } from "vitest-axe";
import { apiError, listCalls, memberPage, memberRows, pagedMemberPage, renderMembers, type MemberRowFixture } from "../../../test/members";
import { setViewportWidth, type RecordedCall } from "../../../test/server";
import { signInAs, signOutForTests } from "../../../test/session";
import { useCreateMember } from "../api";

const cardList = () => screen.getByRole("list", { name: "Socios" });
const cards = () => within(cardList()).getAllByRole("listitem");
const loadMore = () => screen.getByRole("button", { name: "Cargar más" });
const SIXTY = memberRows(60);

function cssRule(file: string, selector: RegExp): string {
  const css = readFileSync(fileURLToPath(new URL(file, import.meta.url)), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
  return [...css.matchAll(/([^{}]+)\{([^{}]*)\}/g)]
    .filter((rule) => selector.test((rule[1] ?? "").trim()))
    .map((rule) => rule[2] ?? "")
    .join(";");
}

const paged = (rows: MemberRowFixture[]) => ({ "GET /members": (call: RecordedCall) => pagedMemberPage(call, rows) });

beforeEach(() => {
  setViewportWidth(390);
  signInAs("admin");
});

afterEach(() => {
  cleanup();
  signOutForTests();
  vi.unstubAllGlobals();
});

describe("MemberCardList · tarjetas (Socios_Movil.html)", () => {
  it("en el celular la lista son tarjetas y no hay tabla", async () => {
    renderMembers("/socios", { handlers: paged(SIXTY) });

    await waitFor(() => {
      expect(cards()).toHaveLength(25);
    });
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("cada tarjeta es un enlace a la ficha con el nombre, el plan, el vencimiento y el estado", async () => {
    renderMembers("/socios", { handlers: paged(SIXTY) });

    const laura = await screen.findByRole("link", { name: "Laura Gómez" });
    expect(laura).toHaveAttribute("href", `/socios/${SIXTY[0]?.id ?? ""}`);
    expect(laura).toHaveTextContent("Mensual · vence 27 nov 2026");
    expect(within(laura).getByText("Al día")).toHaveAttribute("data-status", "active");
    const other = screen.getByRole("link", { name: "Socio 02 Prueba" });
    expect(other).toHaveTextContent("12 clases · venció 15 oct 2026");
    expect(within(other).getByText("Vencido")).toHaveAttribute("data-status", "expired");
  });

  it("sin membresía la tarjeta lo dice; un dado de baja y un inactivo llevan su etiqueta", async () => {
    renderMembers();

    const laura = await screen.findByRole("link", { name: "Laura Gómez" });
    expect(laura).toHaveTextContent("Sin membresía");
    const elena = screen.getByRole("link", { name: "Elena Vargas" });
    expect(within(elena).getByText("Dado de baja")).toHaveAttribute("data-account", "deleted");
    const andres = screen.getByRole("link", { name: "Andrés Ruiz" });
    expect(within(andres).getByText("Inactivo")).toHaveAttribute("data-account", "inactive");
    expect(within(laura).queryByText("Activo")).not.toBeInTheDocument();
  });

  it("la tarjeta entera es el enlace y mide al menos 44 px (--control)", async () => {
    renderMembers();

    const laura = await screen.findByRole("link", { name: "Laura Gómez" });
    expect(laura).toHaveClass("card");
    expect(laura.closest("li")).not.toBeNull();
    expect(cssRule("./MemberCardList.module.css", /^\.card$/)).toMatch(/min-height\s*:\s*var\(--control\)/);
  });

  it("nada enmascarado ni sensible en las tarjetas (N-01)", async () => {
    renderMembers();
    await screen.findByRole("link", { name: "Laura Gómez" });

    expect(cardList().textContent).not.toContain("•");
  });

  it("los chips se desplazan dentro de su caja (overflow-x: auto)", async () => {
    renderMembers();
    await screen.findByRole("link", { name: "Laura Gómez" });

    expect(screen.getByRole("group", { name: "Estado" })).toHaveClass("chips");
    expect(cssRule("../../../shared/ui/Chips.module.css", /^\.chips$/)).toMatch(/overflow-x\s*:\s*auto/);
  });

  it("no tiene violaciones de accesibilidad", async () => {
    const { container } = renderMembers("/socios", { handlers: paged(SIXTY) });
    await waitFor(() => {
      expect(cards()).toHaveLength(25);
    });

    expect(await axe(container)).toHaveNoViolations();
  });
});

describe("MemberCardList · Cargar más", () => {
  it("acumula las páginas y desaparece al llegar al total", async () => {
    const { mock, user } = renderMembers("/socios", { handlers: paged(SIXTY) });
    await waitFor(() => {
      expect(cards()).toHaveLength(25);
    });
    expect(screen.getByText("Mostrando 25 de 60")).toBeInTheDocument();

    await user.click(loadMore());
    await waitFor(() => {
      expect(cards()).toHaveLength(50);
    });
    await user.click(loadMore());
    await waitFor(() => {
      expect(cards()).toHaveLength(60);
    });

    expect(screen.queryByRole("button", { name: "Cargar más" })).not.toBeInTheDocument();
    expect(screen.getByText("Mostrando 60 de 60")).toBeInTheDocument();
    expect(listCalls(mock).map((p) => p.toString())).toEqual(["limit=25&offset=0", "limit=25&offset=25", "limit=25&offset=50"]);
  });

  it("con todo en la primera página no ofrece 'Cargar más'", async () => {
    renderMembers();
    await screen.findByRole("link", { name: "Laura Gómez" });

    expect(screen.queryByRole("button", { name: "Cargar más" })).not.toBeInTheDocument();
  });

  it("mientras trae la página siguiente lo dice y no deja pedirla dos veces", async () => {
    let release: (() => void) | null = null;
    const { mock, user } = renderMembers("/socios", {
      handlers: {
        "GET /members": (call) =>
          new URL(call.url, "http://apex.test").searchParams.get("offset") === "25"
            ? new Promise((resolve) => {
                release = () => {
                  resolve(pagedMemberPage(call, SIXTY));
                };
              })
            : pagedMemberPage(call, SIXTY),
      },
    });
    await waitFor(() => {
      expect(cards()).toHaveLength(25);
    });

    await user.click(loadMore());

    const busy = await screen.findByRole("button", { name: "Cargando…" });
    expect(busy).toHaveAttribute("aria-disabled", "true");
    // Revisión S3-F2 (M1): el mismo botón conserva el foco mientras carga.
    expect(busy).toHaveFocus();
    await user.click(busy);
    expect(listCalls(mock).filter((p) => p.get("offset") === "25")).toHaveLength(1);
    (release as (() => void) | null)?.();
    await waitFor(() => {
      expect(cards()).toHaveLength(50);
    });
  });

  it("si la página siguiente falla conserva las tarjetas y ofrece 'Reintentar'", async () => {
    let failSecond = true;
    const { user } = renderMembers("/socios", {
      handlers: {
        "GET /members": (call) =>
          failSecond && new URL(call.url, "http://apex.test").searchParams.get("offset") === "25" ? apiError(500, "internal") : pagedMemberPage(call, SIXTY),
      },
    });
    await waitFor(() => {
      expect(cards()).toHaveLength(25);
    });

    await user.click(loadMore());

    expect(await screen.findByRole("alert")).toHaveTextContent("No pudimos cargar más socios. Intenta de nuevo.");
    expect(cards()).toHaveLength(25);
    failSecond = false;
    await user.click(screen.getByRole("button", { name: "Reintentar" }));

    await waitFor(() => {
      expect(cards()).toHaveLength(50);
    });
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("no pide más de 20 páginas (M-9): la 21 no se pide y se sugiere filtrar", async () => {
    const rows = memberRows(50);
    const { mock, user } = renderMembers("/socios?limit=2", { handlers: paged(rows) });
    await waitFor(() => {
      expect(cards()).toHaveLength(2);
    });

    for (let page = 2; page <= 20; page += 1) {
      await user.click(loadMore());
      await waitFor(() => {
        expect(cards()).toHaveLength(page * 2);
      });
    }

    expect(screen.queryByRole("button", { name: "Cargar más" })).not.toBeInTheDocument();
    expect(screen.getByText("Se muestran los primeros 40 socios. Usa la búsqueda o los filtros para encontrar a los demás.")).toBeInTheDocument();
    expect(listCalls(mock).some((p) => p.get("offset") === "40")).toBe(false);
    expect(listCalls(mock)).toHaveLength(20);
  });

  it("cambiar de chip vuelve a empezar desde la primera página", async () => {
    const { mock, user } = renderMembers("/socios", { handlers: paged(SIXTY) });
    await waitFor(() => {
      expect(cards()).toHaveLength(25);
    });
    await user.click(loadMore());
    await waitFor(() => {
      expect(cards()).toHaveLength(50);
    });

    await user.click(within(screen.getByRole("group", { name: "Estado" })).getByRole("button", { name: /^Vencidos/ }));

    await waitFor(() => {
      expect(listCalls(mock).at(-1)?.toString()).toBe("limit=25&offset=0&membership_status=expired");
    });
    await waitFor(() => {
      expect(cards()).toHaveLength(25);
    });
  });

  it("buscar va al api sin offset en la URL y no deja la búsqueda en la caché", async () => {
    const { mock, queryClient, router, user } = renderMembers("/socios", { handlers: paged(SIXTY) });
    await waitFor(() => {
      expect(cards()).toHaveLength(25);
    });

    await user.type(screen.getByRole("searchbox", { name: "Buscar" }), "laura");
    await waitFor(() => {
      expect(listCalls(mock).at(-1)?.toString()).toBe("limit=25&offset=0&q=laura");
    });
    expect(router.state.location.search).not.toContain("laura");
    await user.click(screen.getByRole("button", { name: "Limpiar" }));

    await waitFor(() => {
      expect(JSON.stringify(queryClient.getQueryCache().findAll({ queryKey: ["members"] }).map((query) => query.queryKey))).not.toContain("laura");
    });
  });
});

describe("MemberCardList · Nuevo socio y estados", () => {
  it("con members.create 'Nuevo socio' es un botón flotante (uno solo en la pantalla)", async () => {
    renderMembers();
    await screen.findByRole("link", { name: "Laura Gómez" });

    const links = screen.getAllByRole("link", { name: "Nuevo socio" });
    expect(links).toHaveLength(1);
    expect(links[0]).toHaveAttribute("href", "/socios/nuevo");
    expect(links[0]).toHaveClass("fab");
    expect(cssRule("./MemberCardList.module.css", /^\.fab$/)).toMatch(/position\s*:\s*fixed/);
  });

  it("el coach también tiene el botón flotante", async () => {
    signInAs("coach");
    renderMembers();
    await screen.findByRole("link", { name: "Laura Gómez" });

    expect(screen.getByRole("link", { name: "Nuevo socio" })).toHaveClass("fab");
  });

  it("sin members.create no hay botón flotante", async () => {
    signInAs("member");
    renderMembers();
    await screen.findByRole("link", { name: "Laura Gómez" });

    expect(screen.queryByRole("link", { name: "Nuevo socio" })).not.toBeInTheDocument();
  });

  it("mientras carga la primera página lo anuncia y pinta cajas grises", () => {
    renderMembers("/socios", { handlers: { "GET /members": () => new Promise(() => undefined) } });

    expect(screen.getByText("Cargando socios…").closest('[role="status"]')).not.toBeNull();
    expect(screen.getAllByTestId("card-skeleton")).toHaveLength(4);
    // Revisión S3-F2 (L2): las cajas no son un segundo landmark "Socios".
    expect(screen.queryByRole("region", { name: "Socios" })).not.toBeInTheDocument();
  });

  it("sin socios todavía guía a registrar el primero", async () => {
    renderMembers("/socios", { rows: [] });

    expect(await screen.findByText("Todavía no hay socios registrados.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Registrar el primer socio" })).toHaveAttribute("href", "/socios/nuevo");
  });

  it("sin resultados con un chip guía a limpiar los filtros", async () => {
    const { router, user } = renderMembers("/socios?membership_status=frozen", {
      handlers: { "GET /members": (call) => (new URL(call.url, "http://apex.test").searchParams.has("membership_status") ? memberPage(call, [], 0) : memberPage(call)) },
    });

    expect(await screen.findByText("No hay socios que coincidan con la búsqueda")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Limpiar filtros" }));

    await waitFor(() => {
      expect(router.state.location.search).toBe("");
    });
    expect(await screen.findByRole("link", { name: "Laura Gómez" })).toBeInTheDocument();
  });

  it("un error de la primera página se explica y se puede reintentar", async () => {
    let fail = true;
    const { user } = renderMembers("/socios", { handlers: { "GET /members": (call) => (fail ? apiError(500, "internal") : memberPage(call)) } });

    expect(await screen.findByRole("alert")).toHaveTextContent("No pudimos cargar los socios. Intenta de nuevo en un momento.");
    fail = false;
    await user.click(screen.getByRole("button", { name: "Reintentar" }));

    expect(await screen.findByRole("link", { name: "Laura Gómez" })).toBeInTheDocument();
  });

  it("anuncia cuántos socios muestra en una región de estado", async () => {
    renderMembers();
    await screen.findByRole("link", { name: "Laura Gómez" });

    expect(screen.getByText("Mostrando 3 de 3").closest('[role="status"]')).not.toBeNull();
  });
});

describe("MemberCardList · revisión S3-F2", () => {
  it("M1: al traer la última página el botón desaparece y el foco va a la primera tarjeta nueva", async () => {
    const { user } = renderMembers("/socios", { handlers: paged(memberRows(30)) });
    await waitFor(() => {
      expect(cards()).toHaveLength(25);
    });

    await user.click(loadMore());

    await waitFor(() => {
      expect(cards()).toHaveLength(30);
    });
    expect(screen.queryByRole("button", { name: "Cargar más" })).not.toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByRole("link", { name: "Socio 26 Prueba" })).toHaveFocus();
    });
  });

  it("M1: si quedan páginas el foco se queda en 'Cargar más'", async () => {
    const { user } = renderMembers("/socios", { handlers: paged(SIXTY) });
    await waitFor(() => {
      expect(cards()).toHaveLength(25);
    });

    await user.click(loadMore());

    await waitFor(() => {
      expect(cards()).toHaveLength(50);
    });
    expect(loadMore()).toHaveFocus();
  });

  it("M2: un socio repetido entre dos páginas (el offset se corrió) sale una sola vez", async () => {
    const rows = memberRows(30);
    const { user } = renderMembers("/socios", {
      handlers: {
        "GET /members": (call) => {
          const offset = Number(new URL(call.url, "http://apex.test").searchParams.get("offset"));
          // Una baja entre las dos cargas: la segunda página empieza una fila antes.
          return offset === 25 ? { status: 200, body: { items: rows.slice(24), total: 30, limit: 25, offset: 25 } } : pagedMemberPage(call, rows);
        },
      },
    });
    await waitFor(() => {
      expect(cards()).toHaveLength(25);
    });

    await user.click(loadMore());

    await waitFor(() => {
      expect(screen.getByText("Mostrando 30 de 30")).toBeInTheDocument();
    });
    expect(cards()).toHaveLength(30);
    expect(screen.getAllByRole("link", { name: "Socio 25 Prueba" })).toHaveLength(1);
  });

  it("M3: volver a la ventana no relee en serie las páginas cargadas", async () => {
    const { mock, user } = renderMembers("/socios", { handlers: paged(SIXTY) });
    await waitFor(() => {
      expect(cards()).toHaveLength(25);
    });
    await user.click(loadMore());
    await waitFor(() => {
      expect(cards()).toHaveLength(50);
    });
    const before = listCalls(mock).length;

    act(() => {
      focusManager.setFocused(false);
      focusManager.setFocused(true);
    });

    expect(listCalls(mock)).toHaveLength(before);
    focusManager.setFocused(undefined);
  });

  it("M3: tras un alta las tarjetas vuelven a la primera página en vez de releer todas", async () => {
    const { mock, queryClient, user } = renderMembers("/socios", { handlers: paged(SIXTY) });
    await waitFor(() => {
      expect(cards()).toHaveLength(25);
    });
    await user.click(loadMore());
    await waitFor(() => {
      expect(cards()).toHaveLength(50);
    });
    const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
    const { result } = renderHook(() => useCreateMember(), { wrapper });

    await act(async () => {
      await result.current.mutateAsync({ first_name: "Sara", last_name: "Mejía", document_type: "CC", document: "5566779988", data_consent: true });
    });

    await waitFor(() => {
      expect(cards()).toHaveLength(25);
    });
    expect(listCalls(mock).filter((p) => p.get("offset") === "25")).toHaveLength(1);
  });

  it("M4: si una relectura falla, las tarjetas quedan con un aviso y 'Reintentar'", async () => {
    let fail = false;
    const { queryClient, user } = renderMembers("/socios", {
      handlers: { "GET /members": (call) => (fail ? apiError(500, "internal") : pagedMemberPage(call, SIXTY)) },
    });
    await waitFor(() => {
      expect(cards()).toHaveLength(25);
    });

    fail = true;
    await act(async () => {
      await queryClient.refetchQueries({ queryKey: ["members", "infinite"] });
    });

    expect(await screen.findByRole("alert")).toHaveTextContent("No pudimos actualizar la lista de socios.");
    expect(cards()).toHaveLength(25);
    fail = false;
    await user.click(screen.getByRole("button", { name: "Reintentar" }));

    await waitFor(() => {
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    });
  });
});
