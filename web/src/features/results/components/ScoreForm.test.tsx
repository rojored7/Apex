// S8-F4 · US-169 y US-170 (S8-D41): el formulario de marca por `score_type`. Tiempo mm:ss, «No terminó» solo con tiempo y time cap,
// rondas + reps, reps, carga en kg (hasta dos decimales, 0 a 1.000) enviada en gramos enteros; nivel con Segmented y chips de lo escalado.
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "vitest-axe";
import { MOV_PULL, resultOut, scoringWod } from "../../../test/results";
import type { ScoreValues } from "../schemas";
import { ScoreForm } from "./ScoreForm";

type WodType = "time" | "rounds_reps" | "reps" | "load";

function setup(scoreType: WodType = "time", props: Partial<Parameters<typeof ScoreForm>[0]> = {}) {
  const onSubmit = vi.fn<(values: ScoreValues) => void>();
  const onSkip = vi.fn();
  const wod = scoringWod({ score_type: scoreType, time_cap_s: scoreType === "time" ? 1200 : null });
  render(<ScoreForm wod={wod} memberName="Laura Gómez" initial={null} pending={false} error={null} onSubmit={onSubmit} onSkip={onSkip} {...props} />);
  return { onSubmit, onSkip, user: userEvent.setup() };
}

const save = () => screen.getByRole("button", { name: /Guardar y siguiente/ });

afterEach(cleanup);

describe("ScoreForm · tiempo", () => {
  it("«11:42» se envía como 702 segundos con nivel RX", async () => {
    const { user, onSubmit } = setup();
    expect(screen.getByRole("heading", { name: "Laura Gómez" })).toBeInTheDocument();
    await user.type(screen.getByLabelText("Tiempo (mm:ss)"), "11:42");
    await user.click(save());
    expect(onSubmit).toHaveBeenCalledWith({ level: "rx", seconds: 702, rounds: null, reps: null, load_g: null, capped: false, scaled_movement_ids: [] });
  });

  it("un tiempo mal escrito o sobre el límite no se envía y explica qué hacer", async () => {
    const { user, onSubmit } = setup();
    const field = screen.getByLabelText("Tiempo (mm:ss)");
    await user.type(field, "1142");
    await user.click(save());
    expect(await screen.findByText("Escribe el tiempo como mm:ss, por ejemplo 11:42.")).toBeInTheDocument();
    await user.clear(field);
    await user.type(field, "25:00");
    await user.click(save());
    expect(await screen.findByText(/supera el límite de 20:00/)).toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("«No terminó» pide las repeticiones, no envía segundos y marca capped", async () => {
    const { user, onSubmit } = setup();
    await user.click(screen.getByRole("button", { name: "No terminó" }));
    expect(screen.queryByLabelText("Tiempo (mm:ss)")).not.toBeInTheDocument();
    await user.type(screen.getByLabelText("Repeticiones completadas"), "135");
    await user.click(save());
    expect(onSubmit).toHaveBeenCalledWith({ level: "rx", seconds: null, rounds: null, reps: 135, load_g: null, capped: true, scaled_movement_ids: [] });
  });

  it("«No terminó» sin repeticiones no se envía", async () => {
    const { user, onSubmit } = setup();
    await user.click(screen.getByRole("button", { name: "No terminó" }));
    await user.click(save());
    expect(await screen.findByText("Escribe cuántas repeticiones completó.")).toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();
  });
});

describe("ScoreForm · otros tipos", () => {
  it("«No terminó» solo existe con tiempo", () => {
    for (const type of ["rounds_reps", "reps", "load"] as const) {
      setup(type);
      expect(screen.queryByRole("button", { name: "No terminó" })).not.toBeInTheDocument();
      cleanup();
    }
  });

  it("rondas y repeticiones", async () => {
    const { user, onSubmit } = setup("rounds_reps");
    await user.type(screen.getByLabelText("Rondas"), "5");
    await user.type(screen.getByLabelText("Repeticiones"), "12");
    await user.click(save());
    expect(onSubmit).toHaveBeenCalledWith({ level: "rx", seconds: null, rounds: 5, reps: 12, load_g: null, capped: false, scaled_movement_ids: [] });
  });

  it("repeticiones", async () => {
    const { user, onSubmit } = setup("reps");
    await user.type(screen.getByLabelText("Repeticiones"), "150");
    await user.click(save());
    expect(onSubmit).toHaveBeenCalledWith({ level: "rx", seconds: null, rounds: null, reps: 150, load_g: null, capped: false, scaled_movement_ids: [] });
  });

  it("«102,5 kg» se envía como load_g: 102500", async () => {
    const { user, onSubmit } = setup("load");
    await user.type(screen.getByLabelText("Carga (kg)"), "102,5");
    await user.click(save());
    expect(onSubmit).toHaveBeenCalledWith({ level: "rx", seconds: null, rounds: null, reps: null, load_g: 102500, capped: false, scaled_movement_ids: [] });
  });

  it.each(["1000,5", "1001", "-5", "abc", ""])("la carga «%s» la rechaza Zod", async (text) => {
    const { user, onSubmit } = setup("load");
    if (text !== "") await user.type(screen.getByLabelText("Carga (kg)"), text);
    await user.click(save());
    expect(await screen.findByText("Escribe la carga en kg, de 0 a 1.000, con hasta dos decimales.")).toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("1.000 kg exactos se aceptan", async () => {
    const { user, onSubmit } = setup("load");
    await user.type(screen.getByLabelText("Carga (kg)"), "1000");
    await user.click(save());
    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({ load_g: 1_000_000 }));
  });
});

describe("ScoreForm · nivel y escalado", () => {
  it("los chips de lo escalado aparecen con Escalado y viajan en scaled_movement_ids", async () => {
    const { user, onSubmit } = setup();
    expect(screen.queryByRole("group", { name: "¿Qué escaló?" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("radio", { name: "Escalado" }));
    await user.click(screen.getByRole("button", { name: "Pull-up" }));
    await user.type(screen.getByLabelText("Tiempo (mm:ss)"), "13:40");
    await user.click(save());
    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({ level: "scaled", seconds: 820, scaled_movement_ids: [MOV_PULL] }));
  });

  it("volver a RX borra lo escalado", async () => {
    const { user, onSubmit } = setup();
    await user.click(screen.getByRole("radio", { name: "Escalado" }));
    await user.click(screen.getByRole("button", { name: "Pull-up" }));
    await user.click(screen.getByRole("radio", { name: "RX+" }));
    await user.type(screen.getByLabelText("Tiempo (mm:ss)"), "9:00");
    await user.click(save());
    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({ level: "rx_plus", scaled_movement_ids: [] }));
  });
});

describe("ScoreForm · prellenado, omitir y estados", () => {
  it("prellena la marca existente (10:58 RX, escalado con sus chips)", () => {
    setup("time", { initial: resultOut("a0a0a0a0-0000-4000-8000-000000000009", { seconds: 658, level: "scaled", scaled_movement_ids: [MOV_PULL] }) });
    expect(screen.getByLabelText("Tiempo (mm:ss)")).toHaveValue("10:58");
    expect(screen.getByRole("radio", { name: "Escalado" })).toBeChecked();
    expect(screen.getByRole("button", { name: "Pull-up" })).toHaveAttribute("aria-pressed", "true");
  });

  it("Omitir no envía nada", async () => {
    const { user, onSkip, onSubmit } = setup();
    await user.click(screen.getByRole("button", { name: "Omitir" }));
    expect(onSkip).toHaveBeenCalledTimes(1);
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("mientras guarda deshabilita el botón y muestra el error recibido", () => {
    setup("time", { pending: true, error: "No pudimos guardar el resultado." });
    expect(screen.getByRole("button", { name: /Guardar y siguiente/ })).toBeDisabled();
    expect(screen.getByRole("alert")).toHaveTextContent("No pudimos guardar el resultado.");
  });

  it("no tiene violaciones de accesibilidad", async () => {
    setup();
    expect(await axe(document.body)).toHaveNoViolations();
  });
});
