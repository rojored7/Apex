// S8-F6b: fetchTvToday respeta una señal que ya llega cancelada (la consulta se canceló antes de salir la petición).
import { fetchTvToday, TvRequestError } from "./tvClient";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("fetchTvToday", () => {
  it("con una señal ya abortada sale abortada y no devuelve datos", async () => {
    const seen: boolean[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn((_url: string, init?: RequestInit) => {
        seen.push(init?.signal?.aborted === true);
        if (init?.signal?.aborted) return Promise.reject(new DOMException("abortada", "AbortError"));
        return Promise.resolve(new Response("{}", { status: 200 }));
      }),
    );
    const controller = new AbortController();
    controller.abort();

    await expect(fetchTvToday("a".repeat(24), controller.signal)).rejects.toBeInstanceOf(TvRequestError);

    expect(seen).toEqual([true]);
  });
});
