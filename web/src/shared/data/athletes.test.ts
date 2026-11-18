// S9-F1 (US-178, US-184): invalidateAthleteViews relee todo lo que muestra datos del atleta, y guardar o anular un
// resultado (invalidateResultViews) la llama: un RM derivado aparece sin recargar la ficha.
import { QueryClient } from "@tanstack/react-query";
import { invalidateAthleteViews } from "./athletes";
import { invalidateResultViews } from "./results";

const ATHLETE_KEYS = [["athlete-summary"], ["athlete-metrics"], ["athlete-rms"], ["athlete-records"], ["athlete-benchmarks"]] as const;

function seeded(): QueryClient {
  const client = new QueryClient();
  for (const key of ATHLETE_KEYS) client.setQueryData([...key, "m1"], { ok: true });
  client.setQueryData(["members", "list"], { ok: true });
  return client;
}

const isStale = (client: QueryClient, key: readonly string[]): boolean => client.getQueryCache().find({ queryKey: [...key, "m1"] })?.state.isInvalidated === true;

describe("invalidateAthleteViews", () => {
  it("invalida resumen, medidas, RMs, récords y benchmarks, y nada más", () => {
    const client = seeded();

    invalidateAthleteViews(client);

    for (const key of ATHLETE_KEYS) expect(isStale(client, key), key[0]).toBe(true);
    expect(client.getQueryCache().find({ queryKey: ["members", "list"] })?.state.isInvalidated).toBe(false);
  });
});

describe("invalidateResultViews (S9-F1)", () => {
  it("también invalida las vistas del atleta", () => {
    const client = seeded();

    invalidateResultViews(client);

    for (const key of ATHLETE_KEYS) expect(isStale(client, key), key[0]).toBe(true);
  });
});
