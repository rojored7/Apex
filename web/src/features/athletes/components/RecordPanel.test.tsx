// S9-F2 · US-180 (Atleta_Perfil.html «+ Registrar RM»): panel lateral para registrar un récord manual (POST /athletes/{id}/records).
// - Segmented «Tipo de récord»: RM (movimiento activo que se mide en kg, carga en kg) o Benchmark (benchmark, nivel y la marca del
//   `score_type`: tiempo mm:ss, rondas + repeticiones, repeticiones o carga). Sin «No terminó»: no hay `capped` manual (S9-D8).
// - Las cargas viajan en gramos enteros (S9-D41; 102,5 kg son 102500 g, tope 1.000 kg); la fecha es la civil de Bogotá, hasta hoy.
// - 422 bajo su campo; 409 record_duplicate; 403, 404, 429 y 5xx explicados. Un récord no es dato de salud: no pide la autorización de datos.
// - reset() al cerrar y tras guardar: ningún valor queda para la próxima apertura ni en la caché de mutaciones.
// DESIGN-GAP: 3RM, 5RM, «máx. reps» y la unidad preferida del diseño; «editar» un récord (se invalida y se registra otro, S9-D13).
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { axe } from "vitest-axe";
import { todayBogota } from "../../../core/i18n/format";
import { apiError, benchmarkId, CATALOG_BENCHMARKS, CATALOG_HANDLERS, CATALOG_MOVEMENTS, pageReply, MEMBER_ID, movementId, record, RECORDS_PATH, renderAthlete } from "../../../test/athletes";
import { testQueryClient, type MockHandler } from "../../../test/server";
import { signInAs, signOutForTests } from "../../../test/session";
import { RecordPanel } from "./RecordPanel";

const POST = `POST ${RECORDS_PATH}`;
const TODAY = todayBogota();
const CREATED = { status: 201, body: record(9) };

function renderPanel(handlers: Record<string, MockHandler> = {}, queryClient = testQueryClient()) {
  const onClose = vi.fn();
  const onSaved = vi.fn();
  const view = renderAthlete(<RecordPanel open memberId={MEMBER_ID} onClose={onClose} onSaved={onSaved} />, { handlers: { ...CATALOG_HANDLERS, [POST]: CREATED, ...handlers }, queryClient });
  return { ...view, onClose, onSaved };
}

/** Un anfitrión que abre y cierra el panel como la pestaña (el panel se desmonta al cerrar). */
function Host({ onSaved }: { onSaved: () => void }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button
        type="button"
        onClick={() => {
          setOpen(true);
        }}
      >
        Abrir panel
      </button>
      <RecordPanel
        open={open}
        memberId={MEMBER_ID}
        onClose={() => {
          setOpen(false);
        }}
        onSaved={() => {
          onSaved();
          setOpen(false);
        }}
      />
    </>
  );
}

const save = () => screen.getByRole("button", { name: "Guardar récord" });
const movement = () => screen.getByLabelText(/^Movimiento/);
const load = () => screen.getByLabelText(/^Carga \(kg\)/);
const date = () => screen.getByLabelText(/^Fecha del récord/);
const benchmark = () => screen.getByLabelText(/^Benchmark$/);
const kindRadio = (name: "RM" | "Benchmark") => screen.getByRole("radio", { name });

/** Elige un movimiento del select cuando el catálogo ya llegó. */
async function pickMovement(user: ReturnType<typeof userEvent.setup>, name: string) {
  await screen.findByRole("option", { name });
  await user.selectOptions(movement(), name);
}

async function toBenchmark(user: ReturnType<typeof userEvent.setup>, name?: string) {
  await user.click(kindRadio("Benchmark"));
  if (name === undefined) return;
  await screen.findByRole("option", { name });
  await user.selectOptions(benchmark(), name);
}

beforeEach(() => {
  signInAs("coach");
});

afterEach(() => {
  cleanup();
  signOutForTests();
  vi.unstubAllGlobals();
});

describe("RecordPanel · formulario", () => {
  it("abre como «Registrar récord» con el tipo RM elegido, la fecha de hoy en Bogotá y la carga vacía", () => {
    renderPanel();

    expect(screen.getByRole("dialog", { name: "Registrar récord" })).toBeInTheDocument();
    expect(screen.getByRole("radiogroup", { name: "Tipo de récord" })).toBeInTheDocument();
    expect(kindRadio("RM")).toHaveAttribute("aria-checked", "true");
    expect(kindRadio("Benchmark")).toHaveAttribute("aria-checked", "false");
    expect(date()).toHaveValue(TODAY);
    expect(load()).toHaveValue("");
    expect(screen.queryByLabelText(/^Benchmark$/)).not.toBeInTheDocument();
  });

  it("ofrece solo los movimientos activos que se miden en kg (no repeticiones, no inactivos)", async () => {
    renderPanel();

    await screen.findByRole("option", { name: "Back Squat" });
    const names = within(movement()).getAllByRole("option").map((option) => option.textContent);
    expect(names).toEqual(expect.arrayContaining(["Back Squat", "Deadlift"]));
    expect(names).not.toContain("Pull-up");
    expect(names).not.toContain("Clean viejo");
    expect(names).not.toContain("Sled Push");
  });

  it("pasar a Benchmark cambia los campos: elige el benchmark y el nivel, y no hay movimiento ni carga todavía", async () => {
    const { user } = renderPanel();

    await toBenchmark(user);

    expect(kindRadio("Benchmark")).toHaveAttribute("aria-checked", "true");
    expect(benchmark()).toBeInTheDocument();
    expect(screen.getByRole("radiogroup", { name: "Nivel" })).toBeInTheDocument();
    for (const level of ["RX", "RX+", "Escalado"]) expect(screen.getByRole("radio", { name: level })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "RX" })).toHaveAttribute("aria-checked", "true");
    expect(screen.queryByLabelText(/^Movimiento/)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/^Carga \(kg\)/)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/^Tiempo/)).not.toBeInTheDocument();
  });

  it.each([
    ["Fran", ["Tiempo (mm:ss)"], ["Rondas", "Repeticiones", "Carga (kg)"]],
    ["Cindy", ["Rondas", "Repeticiones"], ["Tiempo (mm:ss)", "Carga (kg)"]],
    ["Max Pull-ups", ["Repeticiones"], ["Tiempo (mm:ss)", "Rondas", "Carga (kg)"]],
    ["Max Clean", ["Carga (kg)"], ["Tiempo (mm:ss)", "Rondas", "Repeticiones"]],
  ])("el benchmark %s pide solo los campos de su tipo de marca", async (name, shown, hidden) => {
    const { user } = renderPanel();

    await toBenchmark(user, name);

    for (const label of shown) expect(screen.getByLabelText(new RegExp(`^${label.replace(/[()]/g, "\\$&")}`))).toBeInTheDocument();
    for (const label of hidden) expect(screen.queryByLabelText(new RegExp(`^${label.replace(/[()]/g, "\\$&")}`))).not.toBeInTheDocument();
  });

  it("nunca ofrece «No terminó»: un récord manual no se corta por tiempo", async () => {
    const { user } = renderPanel();
    await toBenchmark(user, "Fran");

    expect(screen.queryByText(/No terminó/)).not.toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
  });

  it("no pide la autorización de datos: un récord no es dato de salud", () => {
    renderPanel();

    expect(screen.queryByText(/autorización de datos/)).not.toBeInTheDocument();
    expect(save()).toBeEnabled();
  });

  it("no tiene violaciones de axe", async () => {
    renderPanel();
    await screen.findByRole("option", { name: "Back Squat" });

    expect(await axe(screen.getByRole("dialog"))).toHaveNoViolations();
  });
});

describe("RecordPanel · validación en el cliente (Zod)", () => {
  it("RM sin movimiento no envía y pide elegirlo", async () => {
    const { user, mock } = renderPanel();
    await user.type(load(), "100");

    await user.click(save());

    expect(await screen.findByText("Elige el movimiento.")).toBeInTheDocument();
    expect(mock.callsTo(POST)).toHaveLength(0);
  });

  it.each([[""], ["0"], ["abc"], ["-5"], ["1,234"], ["1000,01"], ["1001"]])("la carga «%s» no se envía y se explica bajo el campo", async (text) => {
    const { user, mock } = renderPanel();
    await pickMovement(user, "Back Squat");
    if (text !== "") await user.type(load(), text);

    await user.click(save());

    expect(await screen.findByText("Escribe la carga en kg, de 0,01 a 1.000, con hasta dos decimales.")).toBeInTheDocument();
    expect(load()).toHaveAccessibleDescription(expect.stringContaining("de 0,01 a 1.000") as string);
    expect(load()).toBeInvalid();
    expect(mock.callsTo(POST)).toHaveLength(0);
  });

  it.each([["2099-01-01"], ["1999-12-31"]])("la fecha %s (futura o anterior al 2000) no se envía", async (value) => {
    const { user, mock } = renderPanel();
    await pickMovement(user, "Back Squat");
    await user.type(load(), "100");
    fireEvent.change(date(), { target: { value } });

    await user.click(save());

    expect(await screen.findByText("La fecha debe estar entre el 1 ene 2000 y hoy.")).toBeInTheDocument();
    expect(mock.callsTo(POST)).toHaveLength(0);
  });

  it("Benchmark sin elegir benchmark no envía", async () => {
    const { user, mock } = renderPanel();
    await toBenchmark(user);

    await user.click(save());

    expect(await screen.findByText("Elige el benchmark.")).toBeInTheDocument();
    expect(mock.callsTo(POST)).toHaveLength(0);
  });

  it.each([["1142"], ["11:7"], ["11:75"], ["abc"], ["0:00"], [""]])("el tiempo «%s» no se envía", async (text) => {
    const { user, mock } = renderPanel();
    await toBenchmark(user, "Fran");
    if (text !== "") await user.type(screen.getByLabelText(/^Tiempo/), text);

    await user.click(save());

    expect(await screen.findByText("Escribe el tiempo como mm:ss, por ejemplo 11:42.")).toBeInTheDocument();
    expect(mock.callsTo(POST)).toHaveLength(0);
  });

  it("rondas + repeticiones: sin rondas o con repeticiones de más no se envía", async () => {
    const { user, mock } = renderPanel();
    await toBenchmark(user, "Cindy");
    await user.type(screen.getByLabelText(/^Repeticiones/), "12");

    await user.click(save());

    expect(await screen.findByText("Escribe las rondas completas, de 0 a 1.000.")).toBeInTheDocument();
    await user.type(screen.getByLabelText(/^Rondas/), "5");
    await user.clear(screen.getByLabelText(/^Repeticiones/));
    await user.type(screen.getByLabelText(/^Repeticiones/), "100001");
    await user.click(save());
    expect(await screen.findByText("Escribe las repeticiones, de 0 a 100.000.")).toBeInTheDocument();
    expect(mock.callsTo(POST)).toHaveLength(0);
  });
});

describe("RecordPanel · envío", () => {
  it("un RM viaja con kind rm, el movimiento, la carga en gramos enteros (102,5 kg son 102500) y la fecha de hoy", async () => {
    const { user, mock, onSaved } = renderPanel();
    await pickMovement(user, "Back Squat");
    await user.type(load(), "102,5");

    await user.click(save());

    await waitFor(() => {
      expect(onSaved).toHaveBeenCalledTimes(1);
    });
    expect(mock.callsTo(POST)).toHaveLength(1);
    expect(mock.callsTo(POST)[0]?.path).toBe(`/athletes/${MEMBER_ID}/records`);
    expect(mock.callsTo(POST)[0]?.body).toEqual({ kind: "rm", movement_id: movementId(1), value_g: 102_500, achieved_on: TODAY });
  });

  it.each([
    ["100", 100_000],
    ["62.25", 62_250],
    ["0,01", 10],
    ["1000", 1_000_000],
  ])("el RM de %s kg viaja como %s g", async (kg, grams) => {
    const { user, mock, onSaved } = renderPanel();
    await pickMovement(user, "Deadlift");
    await user.type(load(), kg);

    await user.click(save());

    await waitFor(() => {
      expect(onSaved).toHaveBeenCalledTimes(1);
    });
    expect(mock.callsTo(POST)[0]?.body).toMatchObject({ kind: "rm", movement_id: movementId(2), value_g: grams });
  });

  it("la fecha elegida viaja como achieved_on", async () => {
    const { user, mock, onSaved } = renderPanel();
    await pickMovement(user, "Back Squat");
    await user.type(load(), "100");
    fireEvent.change(date(), { target: { value: "2026-09-04" } });

    await user.click(save());

    await waitFor(() => {
      expect(onSaved).toHaveBeenCalledTimes(1);
    });
    expect(mock.callsTo(POST)[0]?.body).toMatchObject({ achieved_on: "2026-09-04" });
  });

  it("un benchmark por tiempo: 11:42 son 702 s, nivel RX por omisión, sin movimiento ni carga ni capped", async () => {
    const { user, mock, onSaved } = renderPanel();
    await toBenchmark(user, "Helen");
    await user.type(screen.getByLabelText(/^Tiempo/), "11:42");

    await user.click(save());

    await waitFor(() => {
      expect(onSaved).toHaveBeenCalledTimes(1);
    });
    expect(mock.callsTo(POST)[0]?.body).toEqual({ kind: "benchmark", benchmark_id: benchmarkId(3), level: "rx", seconds: 702, achieved_on: TODAY });
  });

  it("el nivel Escalado y RX+ viajan como scaled y rx_plus", async () => {
    const first = renderPanel();
    await toBenchmark(first.user, "Fran");
    await first.user.click(screen.getByRole("radio", { name: "Escalado" }));
    await first.user.type(screen.getByLabelText(/^Tiempo/), "13:15");
    await first.user.click(save());
    await waitFor(() => {
      expect(first.onSaved).toHaveBeenCalledTimes(1);
    });
    expect(first.mock.callsTo(POST)[0]?.body).toMatchObject({ level: "scaled", seconds: 795 });
    cleanup();

    const second = renderPanel();
    await toBenchmark(second.user, "Fran");
    await second.user.click(screen.getByRole("radio", { name: "RX+" }));
    await second.user.type(screen.getByLabelText(/^Tiempo/), "9:59");
    await second.user.click(save());
    await waitFor(() => {
      expect(second.onSaved).toHaveBeenCalledTimes(1);
    });
    expect(second.mock.callsTo(POST)[0]?.body).toMatchObject({ level: "rx_plus", seconds: 599 });
  });

  it("rondas + repeticiones, repeticiones y carga viajan en su campo del contrato (la carga en gramos)", async () => {
    const rounds = renderPanel();
    await toBenchmark(rounds.user, "Cindy");
    await rounds.user.type(screen.getByLabelText(/^Rondas/), "18");
    await rounds.user.type(screen.getByLabelText(/^Repeticiones/), "3");
    await rounds.user.click(save());
    await waitFor(() => {
      expect(rounds.onSaved).toHaveBeenCalledTimes(1);
    });
    expect(rounds.mock.callsTo(POST)[0]?.body).toEqual({ kind: "benchmark", benchmark_id: benchmarkId(2), level: "rx", rounds: 18, reps: 3, achieved_on: TODAY });
    cleanup();

    const reps = renderPanel();
    await toBenchmark(reps.user, "Max Pull-ups");
    await reps.user.type(screen.getByLabelText(/^Repeticiones/), "40");
    await reps.user.click(save());
    await waitFor(() => {
      expect(reps.onSaved).toHaveBeenCalledTimes(1);
    });
    expect(reps.mock.callsTo(POST)[0]?.body).toEqual({ kind: "benchmark", benchmark_id: benchmarkId(4), level: "rx", reps: 40, achieved_on: TODAY });
    cleanup();

    const weight = renderPanel();
    await toBenchmark(weight.user, "Max Clean");
    await weight.user.type(screen.getByLabelText(/^Carga \(kg\)/), "92,5");
    await weight.user.click(save());
    await waitFor(() => {
      expect(weight.onSaved).toHaveBeenCalledTimes(1);
    });
    expect(weight.mock.callsTo(POST)[0]?.body).toEqual({ kind: "benchmark", benchmark_id: benchmarkId(5), level: "rx", load_g: 92_500, achieved_on: TODAY });
  });

  it("cambiar de RM a Benchmark no arrastra el movimiento ni la carga escritos", async () => {
    const { user, mock, onSaved } = renderPanel();
    await pickMovement(user, "Back Squat");
    await user.type(load(), "100");
    await toBenchmark(user, "Fran");
    await user.type(screen.getByLabelText(/^Tiempo/), "5:00");

    await user.click(save());

    await waitFor(() => {
      expect(onSaved).toHaveBeenCalledTimes(1);
    });
    const body = mock.callsTo(POST)[0]?.body as Record<string, unknown>;
    expect(body).not.toHaveProperty("movement_id");
    expect(body).not.toHaveProperty("value_g");
    expect(body).not.toHaveProperty("load_g");
  });

  it("mientras guarda, el botón no permite un segundo envío", async () => {
    let release: (reply: typeof CREATED) => void = () => undefined;
    const pending = new Promise<typeof CREATED>((resolve) => {
      release = resolve;
    });
    const { user, mock, onSaved } = renderPanel({ [POST]: () => pending });
    await pickMovement(user, "Back Squat");
    await user.type(load(), "100");

    await user.click(save());
    await user.click(save());

    expect(mock.callsTo(POST)).toHaveLength(1);
    release(CREATED);
    await waitFor(() => {
      expect(onSaved).toHaveBeenCalledTimes(1);
    });
    expect(mock.callsTo(POST)).toHaveLength(1);
  });
});

describe("RecordPanel · errores del api", () => {
  it.each([
    ["value_g", /^Carga \(kg\)/, "Revisa la carga: el servidor no la aceptó. Corrígela y vuelve a guardar."],
    ["movement_id", /^Movimiento/, "Revisa el movimiento: el servidor no lo aceptó. Elige otro y vuelve a guardar."],
    ["achieved_on", /^Fecha del récord/, "Revisa la fecha: el servidor no la aceptó. Corrígela y vuelve a guardar."],
  ] as const)("422 con field %s va bajo su campo y no cierra el panel", async (field, label, message) => {
    const { user, onSaved } = renderPanel({ [POST]: apiError(422, "validation_error", { field }) });
    await pickMovement(user, "Back Squat");
    await user.type(load(), "100");

    await user.click(save());

    expect(await screen.findByText(message)).toBeInTheDocument();
    expect(screen.getByLabelText(label)).toHaveAccessibleDescription(expect.stringContaining(message) as string);
    expect(onSaved).not.toHaveBeenCalled();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it.each([
    ["seconds", /^Tiempo/],
    ["benchmark_id", /^Benchmark$/],
  ] as const)("422 de un benchmark con field %s va bajo su campo", async (field, label) => {
    const { user } = renderPanel({ [POST]: apiError(422, "validation_error", { field }) });
    await toBenchmark(user, "Fran");
    await user.type(screen.getByLabelText(/^Tiempo/), "11:42");

    await user.click(save());

    const message = field === "seconds" ? "Revisa la marca: el servidor no la aceptó. Corrígela y vuelve a guardar." : "Revisa el benchmark: el servidor no lo aceptó. Elige otro y vuelve a guardar.";
    expect(await screen.findByText(message)).toBeInTheDocument();
    expect(screen.getByLabelText(label)).toHaveAccessibleDescription(expect.stringContaining(message) as string);
  });

  it("409 record_duplicate dice que ya estaba registrado, sin cerrar el panel", async () => {
    const { user, onSaved } = renderPanel({ [POST]: apiError(409, "record_duplicate") });
    await pickMovement(user, "Back Squat");
    await user.type(load(), "100");

    await user.click(save());

    expect(await screen.findByRole("alert")).toHaveTextContent("Ya registraste ese mismo récord. Revisa la lista antes de guardarlo otra vez.");
    expect(onSaved).not.toHaveBeenCalled();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it.each([
    [403, "forbidden", {}, undefined, "No tienes permiso para registrar récords. Si lo necesitas, pídeselo a un administrador."],
    [404, "member_not_found", {}, undefined, "El socio ya no existe o está dado de baja: no se pueden registrar récords."],
    [429, "rate_limited", {}, { "Retry-After": "30" }, "Guardaste muchos récords seguidos. Espera 30 segundos e intenta de nuevo."],
    [500, "internal_error", {}, undefined, "No pudimos guardar el récord. Intenta de nuevo en un momento."],
  ] as const)("%s %s se explica con palabras de la pantalla, sin el texto técnico", async (status, code, extra, headers, message) => {
    const { user } = renderPanel({ [POST]: apiError(status, code, { ...extra }, headers ? { ...headers } : undefined) });
    await pickMovement(user, "Back Squat");
    await user.type(load(), "100");

    await user.click(save());

    expect(await screen.findByRole("alert")).toHaveTextContent(message);
    expect(screen.queryByText("Mensaje del api.")).not.toBeInTheDocument();
  });
});

describe("RecordPanel · catálogo", () => {
  it("si el catálogo de movimientos falla lo dice con una alerta y no deja guardar un RM sin movimiento", async () => {
    const { user, mock } = renderPanel({ "GET /movements": apiError(500, "internal_error") });

    expect(await screen.findByText("No pudimos cargar los movimientos. Intenta de nuevo en un momento.")).toBeInTheDocument();
    await user.type(load(), "100");
    await user.click(save());
    expect(mock.callsTo(POST)).toHaveLength(0);
  });

  it("si el catálogo de benchmarks falla lo dice en la pestaña Benchmark", async () => {
    const { user } = renderPanel({ "GET /benchmarks": apiError(500, "internal_error") });

    await toBenchmark(user);

    expect(await screen.findByText("No pudimos cargar los benchmarks. Intenta de nuevo en un momento.")).toBeInTheDocument();
  });

  it("sin movimientos en kg lo dice y manda a crearlos en Movimientos", async () => {
    renderPanel({ "GET /movements": (call) => ({ status: 200, body: { items: [], total: 0, limit: Number(new URL(call.url, "http://apex.test").searchParams.get("limit")), offset: 0 } }) });

    expect(await screen.findByText("No hay movimientos activos que se midan en kg. Créalos en Movimientos.")).toBeInTheDocument();
  });
});

describe("RecordPanel · reset al cerrar y tras guardar", () => {
  it("cerrar con cambios pide confirmación; al descartar y reabrir, el tipo vuelve a RM y los campos a vacío", async () => {
    const user = userEvent.setup();
    renderAthlete(<Host onSaved={vi.fn()} />, { handlers: { ...CATALOG_HANDLERS, [POST]: CREATED } });
    await user.click(screen.getByRole("button", { name: "Abrir panel" }));
    await pickMovement(user, "Back Squat");
    await user.type(load(), "100");
    await user.click(kindRadio("Benchmark"));
    await user.click(kindRadio("RM"));

    await user.click(screen.getByRole("button", { name: "Cancelar" }));
    expect(await screen.findByText("¿Descartar los cambios?")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Descartar cambios" }));
    expect(screen.queryByRole("dialog", { name: "Registrar récord" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Abrir panel" }));

    expect(kindRadio("RM")).toHaveAttribute("aria-checked", "true");
    expect(load()).toHaveValue("");
    expect(movement()).toHaveValue("");
    expect(date()).toHaveValue(TODAY);
  });

  it("tras guardar y volver a abrir el panel está vacío y no queda nada en la caché de mutaciones", async () => {
    const user = userEvent.setup();
    const onSaved = vi.fn();
    const queryClient = testQueryClient();
    renderAthlete(<Host onSaved={onSaved} />, { handlers: { ...CATALOG_HANDLERS, [POST]: CREATED }, queryClient });
    await user.click(screen.getByRole("button", { name: "Abrir panel" }));
    await pickMovement(user, "Back Squat");
    await user.type(load(), "100");

    await user.click(save());
    await waitFor(() => {
      expect(onSaved).toHaveBeenCalledTimes(1);
    });
    await waitFor(() => {
      expect(queryClient.getMutationCache().getAll()).toHaveLength(0);
    });
    await user.click(screen.getByRole("button", { name: "Abrir panel" }));

    expect(kindRadio("RM")).toHaveAttribute("aria-checked", "true");
    expect(load()).toHaveValue("");
    expect(movement()).toHaveValue("");
  });
});

// Revisión S9-F2.
describe("RecordPanel · revisión", () => {
  it("si el catálogo de movimientos falla, «Reintentar» vuelve a pedirlo y las opciones aparecen", async () => {
    let calls = 0;
    const { user, mock } = renderPanel({
      "GET /movements": (call) => {
        calls += 1;
        return calls === 1 ? apiError(500, "internal_error") : pageReply(call, CATALOG_MOVEMENTS.filter((m) => m.is_active));
      },
    });
    expect(await screen.findByText("No pudimos cargar los movimientos. Intenta de nuevo en un momento.")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Reintentar" }));

    expect(await screen.findByRole("option", { name: "Back Squat" })).toBeInTheDocument();
    expect(mock.callsTo("GET /movements").length).toBeGreaterThanOrEqual(2);
  });

  it("si el catálogo de benchmarks falla, «Reintentar» vuelve a pedirlo", async () => {
    let calls = 0;
    const { user } = renderPanel({
      "GET /benchmarks": (call) => {
        calls += 1;
        return calls === 1 ? apiError(500, "internal_error") : pageReply(call, CATALOG_BENCHMARKS);
      },
    });
    await toBenchmark(user);
    expect(await screen.findByText("No pudimos cargar los benchmarks. Intenta de nuevo en un momento.")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Reintentar" }));

    expect(await screen.findByRole("option", { name: "Fran" })).toBeInTheDocument();
  });

  it("si el catálogo de movimientos tiene más de lo que cabe, lo avisa con un texto visible", async () => {
    const many = Array.from({ length: 1500 }, (_, i) => ({ ...CATALOG_MOVEMENTS[0], id: `d1d1d1d1-0000-4000-8000-${String(i + 100).padStart(12, "0")}`, name: `Mov ${String(i)}` }));
    renderPanel({
      "GET /movements": (call) => {
        const params = new URL(call.url, "http://apex.test").searchParams;
        const limit = Number(params.get("limit"));
        const offset = Number(params.get("offset"));
        return { status: 200, body: { items: many.slice(offset, offset + limit), total: many.length, limit, offset } };
      },
    });

    expect(await screen.findByText("Hay más movimientos de los que caben en esta lista. Desactiva en Movimientos los que ya no uses.")).toBeInTheDocument();
  });
});
