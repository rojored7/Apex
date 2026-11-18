// S9-F1 (US-178, US-184): invalidateAthleteViews relee todo lo que muestra datos del atleta, y guardar o anular un
// resultado (invalidateResultViews) la llama: un RM derivado aparece sin recargar la ficha.
import { QueryClient } from "@tanstack/react-query";
import { invalidateAthleteViews, invalidateRecordViews } from "./athletes";
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

// Revisión S9-F2 (seguridad L4): guardar o invalidar un récord relee solo lo que ese cambio mueve, de ESE socio.
describe("invalidateRecordViews", () => {
  it("invalida resumen, RMs, récords y benchmarks del socio, y ni sus medidas ni las de otro socio", () => {
    const client = seeded();
    client.setQueryData(["athlete-rms", "m2"], { ok: true });

    invalidateRecordViews(client, "m1");

    for (const key of [["athlete-summary"], ["athlete-rms"], ["athlete-records"], ["athlete-benchmarks"]] as const) expect(isStale(client, key), key[0]).toBe(true);
    expect(isStale(client, ["athlete-metrics"])).toBe(false);
    expect(client.getQueryCache().find({ queryKey: ["athlete-rms", "m2"] })?.state.isInvalidated).toBe(false);
  });
});
