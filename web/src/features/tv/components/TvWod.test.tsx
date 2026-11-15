// S8-F6 · US-177 (front): el WOD del día en la TV. Cargas en gramos enteros del contrato (S8-D41) mostradas con formatLoadKg.
import { render, screen, within } from "@testing-library/react";
import { tvWod } from "../../../test/tv";
import { TvWod } from "./TvWod";

describe("TvWod", () => {
  it("muestra el título, las píldoras (Benchmark, tipo y límite) y la descripción", () => {
    render(<TvWod wod={tvWod()} />);

    expect(screen.getByRole("heading", { name: "Helen" })).toBeInTheDocument();
    expect(screen.getByText("Benchmark")).toBeInTheDocument();
    expect(screen.getByText("Por tiempo")).toBeInTheDocument();
    expect(screen.getByText("Límite 20:00")).toBeInTheDocument();
    expect(screen.getByText("3 rondas por tiempo")).toBeInTheDocument();
  });

  it("lista los movimientos con sus repeticiones y la carga Rx en kg desde gramos (24000 g es «24 / 16 kg»)", () => {
    render(<TvWod wod={tvWod()} />);

    const list = screen.getByRole("list", { name: "Movimientos" });
    const items = within(list).getAllByRole("listitem");
    expect(items.map((item) => item.textContent)).toEqual(["1 Run 400 m", "21 Kettlebell swing · 24 / 16 kg", "12 Pull-up"]);
  });

  it("una carga con decimales usa coma: 102500 g es «102,5 kg»; una sola carga se muestra sola", () => {
    const wod = tvWod({
      movements: [
        { name: "Back squat", reps: "5", load_rx_m_g: 102500, load_rx_f_g: null },
        { name: "Press", reps: "5", load_rx_m_g: null, load_rx_f_g: 40000 },
      ],
    });
    render(<TvWod wod={wod} />);

    const items = within(screen.getByRole("list", { name: "Movimientos" })).getAllByRole("listitem");
    expect(items.map((item) => item.textContent)).toEqual(["5 Back squat · 102,5 kg", "5 Press · 40 kg"]);
  });

  it("sin límite de tiempo ni benchmark no dibuja esas píldoras; un WOD sin marca no dice «Por tiempo»", () => {
    render(<TvWod wod={tvWod({ time_cap_s: null, is_benchmark: false, score_type: "none" })} />);

    expect(screen.queryByText(/^Límite/)).not.toBeInTheDocument();
    expect(screen.queryByText("Benchmark")).not.toBeInTheDocument();
    expect(screen.queryByText("Por tiempo")).not.toBeInTheDocument();
  });

  it("el texto del WOD se pinta como texto, nunca como HTML", () => {
    render(<TvWod wod={tvWod({ title: "<img src=x onerror=alert(1)>", description: "<b>negrita</b>" })} />);

    expect(screen.getByText("<b>negrita</b>")).toBeInTheDocument();
    expect(document.querySelector("img")).toBeNull();
  });
});
