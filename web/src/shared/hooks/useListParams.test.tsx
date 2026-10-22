// US-063 T9: los parámetros de una lista viven en la URL (q, filtros, limit, offset, sort).
import { act, render, renderHook, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { MemoryRouter, useLocation, useNavigate } from "react-router";
import { useListParams, type ListParamsApi } from "./useListParams";

const FILTERS = ["status", "plan"] as const;
const SORTS = ["last_name", "end_date"] as const;

function setup(initial: string) {
  let navigateRef: ReturnType<typeof useNavigate> | null = null;
  let search = "";
  function Wrapper({ children }: { children: ReactNode }) {
    return <MemoryRouter initialEntries={[initial]}>{children}</MemoryRouter>;
  }
  const hook = renderHook(
    () => {
      navigateRef = useNavigate();
      search = useLocation().search;
      return useListParams({ filters: FILTERS, sorts: SORTS });
    },
    { wrapper: Wrapper },
  );
  return {
    result: hook.result,
    search: () => search,
    back: () => {
      act(() => {
        void navigateRef?.(-1);
      });
    },
  };
}

function current(api: { current: ListParamsApi<(typeof FILTERS)[number]> }) {
  return api.current;
}

describe("useListParams", () => {
  it("sin parámetros pide la primera página de 25", () => {
    const { result } = setup("/socios");

    expect(current(result).params).toEqual({ limit: 25, offset: 0 });
    expect(current(result).page).toBe(1);
    expect(current(result).q).toBe("");
    expect(current(result).sort).toBeNull();
  });

  it("limit=500 en la URL pide limit=25; limit=0 y texto también", () => {
    expect(setup("/socios?limit=500").result.current.params.limit).toBe(25);
    expect(setup("/socios?limit=0").result.current.params.limit).toBe(25);
    expect(setup("/socios?limit=abc&offset=-3").result.current.params).toEqual({ limit: 25, offset: 0 });
  });

  it("recargar conserva q, filtros, limit, offset y sort, y descarta claves desconocidas", () => {
    const { result } = setup("/socios?q=p%C3%A9rez&status=active&status=expiring&plan=p1&limit=50&offset=100&sort=-end_date&hack=1");

    expect(result.current.params).toEqual({
      q: "pérez",
      status: ["active", "expiring"],
      plan: ["p1"],
      limit: 50,
      offset: 100,
      sort: "-end_date",
    });
    expect(result.current.page).toBe(3);
    expect(result.current.filters.status).toEqual(["active", "expiring"]);
    expect(result.current.sort).toEqual({ field: "end_date", direction: "desc" });
  });

  it("un sort no permitido o mal formado se ignora", () => {
    expect(setup("/socios?sort=password").result.current.params.sort).toBeUndefined();
    expect(setup("/socios?sort=--x").result.current.sort).toBeNull();
  });

  it("cambiar un filtro desde la página 4 vuelve a offset=0", () => {
    const { result, search } = setup("/socios?limit=25&offset=75&status=active");

    act(() => {
      result.current.setFilter("status", ["expired"]);
    });

    expect(result.current.params.offset).toBe(0);
    expect(result.current.params.status).toEqual(["expired"]);
    expect(search()).toBe("?limit=25&status=expired");
  });

  it("quitar un filtro lo borra de la URL", () => {
    const { result } = setup("/socios?status=active&plan=p1");

    act(() => {
      result.current.setFilter("plan", undefined);
    });
    act(() => {
      result.current.setFilter("status", []);
    });

    expect(result.current.params).toEqual({ limit: 25, offset: 0 });
  });

  it("la búsqueda vuelve offset a 0 y una búsqueda vacía la quita", () => {
    const { result, search } = setup("/socios?offset=50");

    act(() => {
      result.current.setQuery("  ana ");
    });
    expect(result.current.params).toEqual({ q: "ana", limit: 25, offset: 0 });
    act(() => {
      result.current.setQuery("");
    });
    expect(search()).toBe("");
  });

  it("página 3 con 50 por página escribe limit=50&offset=100", () => {
    const { result, search } = setup("/socios?limit=50");

    act(() => {
      result.current.setPage(3);
    });

    expect(search()).toBe("?limit=50&offset=100");
    act(() => {
      result.current.setPage(1);
    });
    expect(search()).toBe("?limit=50");
  });

  it("cambiar el tamaño vuelve a la primera página", () => {
    const { result, search } = setup("/socios?offset=100");

    act(() => {
      result.current.setLimit(100);
    });

    expect(search()).toBe("?limit=100");
  });

  it("ordenar escribe campo o -campo y vuelve a la primera página", () => {
    const { result, search } = setup("/socios?offset=25");

    act(() => {
      result.current.setSort({ field: "last_name", direction: "asc" });
    });
    expect(search()).toBe("?sort=last_name");
    act(() => {
      result.current.setSort({ field: "last_name", direction: "desc" });
    });
    expect(result.current.params.sort).toBe("-last_name");
    act(() => {
      result.current.setSort(null);
    });
    expect(search()).toBe("");
  });

  it("limpiar borra búsqueda, filtros, orden y offset y conserva el tamaño", () => {
    const { result, search } = setup("/socios?q=x&status=active&sort=last_name&limit=50&offset=100");

    act(() => {
      result.current.clear();
    });

    expect(search()).toBe("?limit=50");
  });

  it("atrás restaura la vista anterior", () => {
    const { result, back } = setup("/socios?status=active");

    act(() => {
      result.current.setFilter("status", ["expired"]);
    });
    back();

    expect(result.current.params.status).toEqual(["active"]);
  });

  it("params es estable mientras la URL no cambia (sirve de queryKey)", () => {
    const { result } = setup("/socios?status=active");
    const first = result.current.params;

    act(() => {
      result.current.setFilter("status", ["active"]);
    });

    expect(result.current.params).toBe(first);
  });
});

describe("useListParams en una pantalla", () => {
  function Screen() {
    const list = useListParams({ filters: FILTERS });
    return (
      <>
        <output data-testid="params">{JSON.stringify(list.params)}</output>
        <button
          type="button"
          onClick={() => {
            list.setPage(list.page + 1);
          }}
        >
          Siguiente
        </button>
      </>
    );
  }

  it("de la página 2 a la 3 con 50 por página pide offset=100", async () => {
    render(
      <MemoryRouter initialEntries={["/socios?limit=50&offset=50"]}>
        <Screen />
      </MemoryRouter>,
    );

    await userEvent.click(screen.getByRole("button", { name: "Siguiente" }));

    expect(JSON.parse(screen.getByTestId("params").textContent)).toEqual({ limit: 50, offset: 100 });
  });
});

// S2-D41 (M-8): con `localQuery` la búsqueda vive en estado local y nunca en la URL.
describe("useListParams con localQuery", () => {
  function setupLocal(initial: string) {
    let search = "";
    function Wrapper({ children }: { children: ReactNode }) {
      return <MemoryRouter initialEntries={[initial]}>{children}</MemoryRouter>;
    }
    const hook = renderHook(
      () => {
        search = useLocation().search;
        return useListParams({ filters: FILTERS, localQuery: true });
      },
      { wrapper: Wrapper },
    );
    return { result: hook.result, search: () => search };
  }

  it("setQuery pasa q al api, vuelve offset a 0 y no escribe q en la URL", () => {
    const { result, search } = setupLocal("/sistema/usuarios?status=active&offset=50");

    act(() => {
      result.current.setQuery("  ana@apex.test ");
    });

    expect(result.current.q).toBe("ana@apex.test");
    expect(result.current.params).toEqual({ q: "ana@apex.test", status: ["active"], limit: 25, offset: 0 });
    expect(search()).toBe("?status=active");
    expect(search()).not.toContain("q=");
  });

  it("un q que llegue en la URL se ignora (nunca viaja al api)", () => {
    const { result } = setupLocal("/sistema/usuarios?q=7319582046&role=coach");

    expect(result.current.q).toBe("");
    expect(result.current.params).toEqual({ limit: 25, offset: 0 });
  });

  it("una búsqueda vacía quita q de los parámetros", () => {
    const { result } = setupLocal("/sistema/usuarios");

    act(() => {
      result.current.setQuery("ana");
    });
    act(() => {
      result.current.setQuery("   ");
    });

    expect(result.current.params).toEqual({ limit: 25, offset: 0 });
  });

  it("limpiar borra la búsqueda local y los filtros de la URL", () => {
    const { result, search } = setupLocal("/sistema/usuarios?status=locked&limit=50");

    act(() => {
      result.current.setQuery("ana");
    });
    act(() => {
      result.current.clear();
    });

    expect(result.current.q).toBe("");
    expect(result.current.params).toEqual({ limit: 50, offset: 0 });
    expect(search()).toBe("?limit=50");
  });

  it("params es estable mientras ni la URL ni la búsqueda cambian", () => {
    const { result } = setupLocal("/sistema/usuarios");

    act(() => {
      result.current.setQuery("ana");
    });
    const first = result.current.params;
    act(() => {
      result.current.setQuery("ana");
    });

    expect(result.current.params).toBe(first);
  });
});
