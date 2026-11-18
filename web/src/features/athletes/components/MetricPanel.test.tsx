// S9-F1 · US-178, H-1 (S9-D29), L-7 (S9-D36): panel lateral para registrar medidas (POST /athletes/{id}/metrics).
// - Zod en el cliente: fecha civil (2000-01-01 a hoy), peso en kg con UN decimal (20 a 400), altura entera (50 a 250), % de grasa entero
//   (1 a 75), notas de hasta 500 caracteres; al menos una de las tres medidas numéricas (como el api, `validate_metric`).
// - El peso se escribe en kg y viaja en gramos enteros (61,2 kg son 61200 g, S9-D3).
// - 422 del api bajo su campo; 409 `consent_required` con el mensaje y el enlace a la ficha; con la ficha diciendo que falta la
//   autorización, el botón nace deshabilitado (H-1).
// - reset() al cerrar y tras guardar: ningún valor se queda entre una apertura y la siguiente ni en la caché de mutaciones (L-7).
// DESIGN-GAP (código): «Cintura» y las medidas configurables no están en el contrato (MetricIn solo trae peso, altura, grasa y notas).
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { axe } from "vitest-axe";
import { todayBogota } from "../../../core/i18n/format";
import { apiError, cacheText, MEMBER_ID, METRICS_PATH, metric, renderAthlete } from "../../../test/athletes";
import { testQueryClient, type MockHandler } from "../../../test/server";
import { signInAs, signOutForTests } from "../../../test/session";
import { MetricPanel, type MetricPanelProps } from "./MetricPanel";

/** Todo lo que hay en localStorage y sessionStorage, como texto. */
function storageText(): string {
  const dump = (storage: Storage): string[] => Array.from({ length: storage.length }, (_, i) => `${storage.key(i) ?? ""}=${storage.getItem(storage.key(i) ?? "") ?? ""}`);
  return [...dump(localStorage), ...dump(sessionStorage)].join("\n");
}

const POST = `POST ${METRICS_PATH}`;
const TODAY = todayBogota();
const CREATED = { status: 201, body: metric(1) };
const CONSENT_MESSAGE = "Falta la autorización de datos del socio. Regístrala en su ficha para guardar medidas.";

type PanelOverrides = Partial<Pick<MetricPanelProps, "consentMissing" | "open">>;

function renderPanel(handlers: Record<string, MockHandler> = {}, overrides: PanelOverrides = {}, queryClient = testQueryClient()) {
  const onClose = vi.fn();
  const onSaved = vi.fn();
  const view = renderAthlete(<MetricPanel open memberId={MEMBER_ID} onClose={onClose} onSaved={onSaved} {...overrides} />, { handlers: { [POST]: CREATED, ...handlers }, queryClient });
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
      <MetricPanel
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

const weight = () => screen.getByLabelText(/^Peso/);
const height = () => screen.getByLabelText(/^Altura/);
const fat = () => screen.getByLabelText(/^% grasa/);
const notes = () => screen.getByLabelText(/^Notas/);
const date = () => screen.getByLabelText(/^Fecha de la medición/);
const save = () => screen.getByRole("button", { name: "Guardar medidas" });

beforeEach(() => {
  signInAs("coach");
});

afterEach(() => {
  cleanup();
  signOutForTests();
  vi.unstubAllGlobals();
  localStorage.clear();
  sessionStorage.clear();
});

describe("MetricPanel · formulario", () => {
  it("abre con el título, la fecha de hoy en Bogotá y los cuatro campos del contrato vacíos", () => {
    renderPanel();

    expect(screen.getByRole("dialog", { name: "Registrar medidas" })).toBeInTheDocument();
    expect(date()).toHaveValue(TODAY);
    expect(weight()).toHaveValue("");
    expect(height()).toHaveValue("");
    expect(fat()).toHaveValue("");
    expect(notes()).toHaveValue("");
    expect(save()).toBeEnabled();
  });

  it("no ofrece «Cintura» ni medidas extra: el contrato solo trae peso, altura, grasa y notas", () => {
    renderPanel();

    expect(weight()).toBeInTheDocument();
    expect(screen.queryByLabelText(/Cintura/)).not.toBeInTheDocument();
  });

  it("no tiene violaciones de axe", async () => {
    renderPanel();

    expect(await axe(screen.getByRole("dialog"))).toHaveNoViolations();
  });
});

describe("MetricPanel · validación en el cliente (Zod)", () => {
  it("sin ninguna medida no envía y pide al menos una", async () => {
    const { user, mock } = renderPanel();

    await user.click(save());

    expect(await screen.findByText("Registra al menos una medida: peso, altura o % de grasa.")).toBeInTheDocument();
    expect(mock.callsTo(POST)).toHaveLength(0);
  });

  it("solo notas tampoco basta (el api exige una medida numérica)", async () => {
    const { user, mock } = renderPanel();
    await user.type(notes(), "Se pesó en ayunas");

    await user.click(save());

    expect(await screen.findByText("Registra al menos una medida: peso, altura o % de grasa.")).toBeInTheDocument();
    expect(mock.callsTo(POST)).toHaveLength(0);
  });

  it.each([
    ["61,25", "dos decimales"],
    ["19,9", "menos de 20 kg"],
    ["400,1", "más de 400 kg"],
    ["abc", "texto"],
    ["-5", "negativo"],
  ])("el peso «%s» (%s) no se envía y se explica bajo el campo", async (text) => {
    const { user, mock } = renderPanel();
    await user.type(weight(), text);

    await user.click(save());

    expect(await screen.findByText("Escribe el peso en kg con un decimal, de 20 a 400.")).toBeInTheDocument();
    expect(weight()).toHaveAccessibleDescription(expect.stringContaining("de 20 a 400") as string);
    expect(weight()).toBeInvalid();
    expect(mock.callsTo(POST)).toHaveLength(0);
  });

  it.each([["49"], ["251"], ["165,5"], ["x"]])("la altura «%s» no se envía", async (text) => {
    const { user, mock } = renderPanel();
    await user.type(height(), text);

    await user.click(save());

    expect(await screen.findByText("Escribe la altura en cm, un número entero de 50 a 250.")).toBeInTheDocument();
    expect(mock.callsTo(POST)).toHaveLength(0);
  });

  it.each([["0"], ["76"], ["22,5"], ["x"]])("el % de grasa «%s» no se envía", async (text) => {
    const { user, mock } = renderPanel();
    await user.type(fat(), text);

    await user.click(save());

    expect(await screen.findByText("Escribe el % de grasa como número entero, de 1 a 75.")).toBeInTheDocument();
    expect(mock.callsTo(POST)).toHaveLength(0);
  });

  it("notas de más de 500 caracteres no se envían", async () => {
    const { user, mock } = renderPanel();
    await user.type(weight(), "61,2");
    fireEvent.change(notes(), { target: { value: "a".repeat(501) } });

    await user.click(save());

    expect(await screen.findByText("Las notas admiten hasta 500 caracteres.")).toBeInTheDocument();
    expect(mock.callsTo(POST)).toHaveLength(0);
  });

  it.each([["2099-01-01"], ["1999-12-31"]])("la fecha %s (futura o anterior al 2000) no se envía", async (value) => {
    const { user, mock } = renderPanel();
    await user.type(weight(), "61,2");
    fireEvent.change(date(), { target: { value } });

    await user.click(save());

    expect(await screen.findByText("La fecha debe estar entre el 1 ene 2000 y hoy.")).toBeInTheDocument();
    expect(mock.callsTo(POST)).toHaveLength(0);
  });
});

describe("MetricPanel · envío", () => {
  it("el peso en kg con coma viaja en gramos enteros y solo con lo que se llenó", async () => {
    const { user, mock, onSaved } = renderPanel();
    await user.type(weight(), "61,2");

    await user.click(save());

    await waitFor(() => {
      expect(onSaved).toHaveBeenCalledTimes(1);
    });
    expect(mock.callsTo(POST)).toHaveLength(1);
    expect(mock.callsTo(POST)[0]?.body).toEqual({ measured_on: TODAY, weight_g: 61200 });
    expect(mock.callsTo(POST)[0]?.path).toBe(`/athletes/${MEMBER_ID}/metrics`);
  });

  it("el punto decimal también vale: 61.2 kg son 61200 g y 62 kg son 62000 g", async () => {
    const first = renderPanel();
    await first.user.type(weight(), "61.2");
    await first.user.click(save());
    await waitFor(() => {
      expect(first.onSaved).toHaveBeenCalledTimes(1);
    });
    expect(first.mock.callsTo(POST)[0]?.body).toMatchObject({ weight_g: 61200 });
    cleanup();

    const second = renderPanel();
    await second.user.type(weight(), "62");
    await second.user.click(save());
    await waitFor(() => {
      expect(second.onSaved).toHaveBeenCalledTimes(1);
    });
    expect(second.mock.callsTo(POST)[0]?.body).toMatchObject({ weight_g: 62000 });
  });

  it("los límites 20 kg y 400 kg se aceptan y viajan como 20000 y 400000 g", async () => {
    for (const [kg, grams] of [
      ["20", 20000],
      ["400", 400000],
    ] as const) {
      const { user, mock, onSaved } = renderPanel();
      await user.type(weight(), kg);
      await user.click(save());
      await waitFor(() => {
        expect(onSaved).toHaveBeenCalledTimes(1);
      });
      expect(mock.callsTo(POST)[0]?.body).toMatchObject({ weight_g: grams });
      cleanup();
    }
  });

  it("envía fecha, peso, altura, grasa y notas recortadas, cada uno con su tipo", async () => {
    const { user, mock, onSaved } = renderPanel();
    fireEvent.change(date(), { target: { value: "2026-10-01" } });
    await user.type(weight(), "61,2");
    await user.type(height(), "165");
    await user.type(fat(), "22");
    await user.type(notes(), "  Tras la pausa de septiembre  ");

    await user.click(save());

    await waitFor(() => {
      expect(onSaved).toHaveBeenCalledTimes(1);
    });
    expect(mock.callsTo(POST)[0]?.body).toEqual({ measured_on: "2026-10-01", weight_g: 61200, height_cm: 165, body_fat_pct: 22, notes: "Tras la pausa de septiembre" });
  });

  it("mientras guarda, el botón no permite un segundo envío", async () => {
    let release: (reply: typeof CREATED) => void = () => undefined;
    const pending = new Promise<typeof CREATED>((resolve) => {
      release = resolve;
    });
    const { user, mock, onSaved } = renderPanel({ [POST]: () => pending });
    await user.type(weight(), "61,2");

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

describe("MetricPanel · errores del api", () => {
  it.each([
    ["weight_g", /^Peso/, "Revisa el peso: el servidor no lo aceptó. Corrígelo y vuelve a guardar."],
    ["height_cm", /^Altura/, "Revisa la altura: el servidor no la aceptó. Corrígela y vuelve a guardar."],
    ["body_fat_pct", /^% grasa/, "Revisa el % de grasa: el servidor no lo aceptó. Corrígelo y vuelve a guardar."],
    ["notes", /^Notas/, "Revisa las notas: el servidor no las aceptó. Corrígelas y vuelve a guardar."],
    ["measured_on", /^Fecha de la medición/, "Revisa la fecha: el servidor no la aceptó. Corrígela y vuelve a guardar."],
  ] as const)("422 con field %s va bajo su campo y no cierra el panel", async (field, label, message) => {
    const { user, onSaved } = renderPanel({ [POST]: apiError(422, "validation_error", { field }) });
    await user.type(screen.getByLabelText(/^Peso/), "61,2");

    await user.click(save());

    expect(await screen.findByText(message)).toBeInTheDocument();
    expect(screen.getByLabelText(label)).toHaveAccessibleDescription(expect.stringContaining(message) as string);
    expect(onSaved).not.toHaveBeenCalled();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("409 consent_required muestra el mensaje con el enlace a la ficha y no cierra ni guarda", async () => {
    const { user, onSaved } = renderPanel({ [POST]: apiError(409, "consent_required") });
    await user.type(weight(), "61,2");

    await user.click(save());

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(CONSENT_MESSAGE);
    expect(within(alert).getByRole("link", { name: "Ir a la ficha del socio" })).toHaveAttribute("href", `/socios/${MEMBER_ID}`);
    expect(onSaved).not.toHaveBeenCalled();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("403 dice que no tiene permiso para registrar medidas", async () => {
    const { user } = renderPanel({ [POST]: apiError(403, "forbidden") });
    await user.type(weight(), "61,2");

    await user.click(save());

    expect(await screen.findByRole("alert")).toHaveTextContent("No tienes permiso para registrar medidas. Si lo necesitas, pídeselo a un administrador.");
  });

  it("404 member_not_found dice que el socio ya no existe o está dado de baja", async () => {
    const { user } = renderPanel({ [POST]: apiError(404, "member_not_found") });
    await user.type(weight(), "61,2");

    await user.click(save());

    expect(await screen.findByRole("alert")).toHaveTextContent("El socio ya no existe o está dado de baja: no se pueden registrar medidas.");
  });

  it("429 dice cuánto esperar", async () => {
    const { user } = renderPanel({ [POST]: apiError(429, "rate_limited", {}, { "Retry-After": "30" }) });
    await user.type(weight(), "61,2");

    await user.click(save());

    expect(await screen.findByRole("alert")).toHaveTextContent("Guardaste muchas medidas seguidas. Espera 30 segundos e intenta de nuevo.");
  });

  it("503 crypto_unavailable y 500 dicen qué hacer, sin el texto técnico", async () => {
    const first = renderPanel({ [POST]: apiError(503, "crypto_unavailable", {}, { "Retry-After": "30" }) });
    await first.user.type(weight(), "61,2");
    await first.user.click(save());
    expect(await screen.findByRole("alert")).toHaveTextContent("No pudimos guardar las medidas. Intenta de nuevo en un momento.");
    cleanup();

    const second = renderPanel({ [POST]: apiError(500, "internal_error") });
    await second.user.type(weight(), "61,2");
    await second.user.click(save());
    expect(await screen.findByRole("alert")).toHaveTextContent("No pudimos guardar las medidas. Intenta de nuevo en un momento.");
    expect(screen.queryByText("Mensaje del api.")).not.toBeInTheDocument();
  });
});

describe("MetricPanel · autorización de datos (H-1, S9-D29)", () => {
  it("si la ficha ya dice que falta la autorización, el botón nace deshabilitado con el mensaje y el enlace a la ficha", async () => {
    const { user, mock } = renderPanel({}, { consentMissing: true });

    expect(save()).toBeDisabled();
    const notice = screen.getByText(CONSENT_MESSAGE);
    expect(notice).toBeInTheDocument();
    expect(within(notice.closest("div, p") as HTMLElement).getByRole("link", { name: "Ir a la ficha del socio" })).toHaveAttribute("href", `/socios/${MEMBER_ID}`);
    await user.type(weight(), "61,2");
    await user.click(save());
    expect(mock.callsTo(POST)).toHaveLength(0);
  });

  it("con la autorización registrada no hay aviso y el botón se puede usar", () => {
    renderPanel({}, { consentMissing: false });

    expect(screen.queryByText(CONSENT_MESSAGE)).not.toBeInTheDocument();
    expect(save()).toBeEnabled();
  });

  it("si la ficha no trae el dato (undefined), el botón queda habilitado y decide el 409 del api", () => {
    renderPanel();

    expect(save()).toBeEnabled();
    expect(screen.queryByText(CONSENT_MESSAGE)).not.toBeInTheDocument();
  });
});

describe("MetricPanel · reset al cerrar y tras guardar (L-7)", () => {
  it("cerrar con cambios pide confirmación; al descartar y reabrir, los campos vuelven vacíos", async () => {
    const user = userEvent.setup();
    renderAthlete(<Host onSaved={vi.fn()} />, { handlers: { [POST]: CREATED } });
    await user.click(screen.getByRole("button", { name: "Abrir panel" }));
    await user.type(weight(), "61,2");
    await user.type(notes(), "Texto de salud");

    await user.click(screen.getByRole("button", { name: "Cancelar" }));
    expect(await screen.findByText("¿Descartar los cambios?")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Descartar cambios" }));
    expect(screen.queryByRole("dialog", { name: "Registrar medidas" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Abrir panel" }));

    expect(weight()).toHaveValue("");
    expect(notes()).toHaveValue("");
    expect(date()).toHaveValue(TODAY);
    expect(document.body).not.toHaveTextContent("Texto de salud");
  });

  it("tras guardar y volver a abrir el panel está vacío y la mutación no deja valores en la caché ni en el almacenamiento", async () => {
    const user = userEvent.setup();
    const onSaved = vi.fn();
    const queryClient = testQueryClient();
    renderAthlete(<Host onSaved={onSaved} />, { handlers: { [POST]: CREATED }, queryClient });
    await user.click(screen.getByRole("button", { name: "Abrir panel" }));
    await user.type(weight(), "61,2");
    await user.type(height(), "165");
    await user.type(notes(), "Texto de salud");

    await user.click(save());
    await waitFor(() => {
      expect(onSaved).toHaveBeenCalledTimes(1);
    });
    await waitFor(() => {
      expect(queryClient.getMutationCache().getAll()).toHaveLength(0);
    });
    await user.click(screen.getByRole("button", { name: "Abrir panel" }));

    expect(weight()).toHaveValue("");
    expect(height()).toHaveValue("");
    expect(notes()).toHaveValue("");
    for (const text of ["61200", "61,2", "Texto de salud"]) {
      expect(cacheText(queryClient)).not.toContain(text);
      expect(storageText()).not.toContain(text);
    }
    expect(screen.getByTestId("where").textContent).not.toMatch(/61|Texto/);
  });

  it("un error del api tampoco deja el valor en la caché de mutaciones", async () => {
    const queryClient = testQueryClient();
    const { user } = renderPanel({ [POST]: apiError(500, "internal_error") }, {}, queryClient);
    await user.type(weight(), "61,2");

    await user.click(save());
    await screen.findByRole("alert");

    await waitFor(() => {
      expect(queryClient.getMutationCache().getAll()).toHaveLength(0);
    });
    expect(cacheText(queryClient)).not.toContain("61200");
  });
});

// S9-F1 (revisión, seguridad L5): con la autorización faltando, ni un Enter dentro del campo envía.
describe("MetricPanel · sin autorización, el envío por teclado tampoco sale (revisión L5)", () => {
  it("Enter en el peso no hace POST cuando la ficha dice que falta la autorización", async () => {
    const { user, mock } = renderPanel({}, { consentMissing: true });
    await user.type(weight(), "61,2{Enter}");

    expect(mock.callsTo(POST)).toHaveLength(0);
  });
});
