// S8-F6 · US-177 (front): el ranking «Todos» de la TV. 15 filas por página que rotan; marcas con formatScore (S8-D19, S8-D41).
import { act, render, screen } from "@testing-library/react";
import { tvRow, tvRows } from "../../../test/tv";
import { TvLeaderboard, TV_PAGE_ROWS, TV_ROTATE_MS } from "./TvLeaderboard";

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

const names = (): string[] => screen.getAllByRole("row").slice(1).map((row) => row.querySelectorAll("td")[1]?.textContent ?? "");

describe("TvLeaderboard", () => {
  it("muestra posición, nombre con inicial, marca y nivel", () => {
    render(<TvLeaderboard rows={[tvRow(1, "Ana P.", 702), tvRow(2, "Luis M.", 800, { level: "rx_plus" }), tvRow(3, "Sara N.", null, { level: "scaled", score: { capped: true, load_g: null, reps: 15, rounds: 2, seconds: null } })]} scoreType="time" />);

    expect(screen.getByRole("table", { name: "Ranking del WOD" })).toBeInTheDocument();
    expect(screen.getByText("Ana P.")).toBeInTheDocument();
    expect(screen.getByText("11:42")).toBeInTheDocument();
    expect(screen.getByText("RX+")).toBeInTheDocument();
    expect(screen.getByText("DNF · 2 + 15")).toBeInTheDocument();
    expect(screen.getByText("Escalado")).toBeInTheDocument();
  });

  it("una carga llega en gramos y se ve en kg (102500 g es «102,5 kg»)", () => {
    render(<TvLeaderboard rows={[tvRow(1, "Ana P.", null, { score: { capped: false, load_g: 102500, reps: null, rounds: null, seconds: null } })]} scoreType="load" />);

    expect(screen.getByText("102,5 kg")).toBeInTheDocument();
  });

  it("sin resultados guía a registrar con el coach y no dibuja la tabla", () => {
    render(<TvLeaderboard rows={[]} scoreType="time" />);

    expect(screen.getByText("Registra tu resultado con el coach")).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("hasta 15 filas no rota", () => {
    render(<TvLeaderboard rows={tvRows(TV_PAGE_ROWS)} scoreType="time" />);

    expect(names()).toHaveLength(TV_PAGE_ROWS);
    act(() => {
      vi.advanceTimersByTime(TV_ROTATE_MS * 3);
    });
    expect(names()).toHaveLength(TV_PAGE_ROWS);
    expect(names()[0]).toBe("Atleta 1 X.");
  });

  it("con más de 15 filas muestra 15 por página, rota cada 12 s y da la vuelta", () => {
    render(<TvLeaderboard rows={tvRows(20)} scoreType="time" />);

    expect(names()).toHaveLength(15);
    expect(names()[0]).toBe("Atleta 1 X.");
    expect(screen.getByText("Página 1 de 2")).toBeInTheDocument();

    act(() => {
      vi.advanceTimersByTime(TV_ROTATE_MS);
    });
    expect(names()).toEqual(["Atleta 16 X.", "Atleta 17 X.", "Atleta 18 X.", "Atleta 19 X.", "Atleta 20 X."]);
    expect(screen.getByText("Página 2 de 2")).toBeInTheDocument();

    act(() => {
      vi.advanceTimersByTime(TV_ROTATE_MS);
    });
    expect(names()[0]).toBe("Atleta 1 X.");
  });

  it("si el ranking se acorta mientras se ve la última página, vuelve a una página que existe", () => {
    const { rerender } = render(<TvLeaderboard rows={tvRows(20)} scoreType="time" />);
    act(() => {
      vi.advanceTimersByTime(TV_ROTATE_MS);
    });
    expect(names()[0]).toBe("Atleta 16 X.");

    rerender(<TvLeaderboard rows={tvRows(8)} scoreType="time" />);

    expect(names()).toHaveLength(8);
    expect(names()[0]).toBe("Atleta 1 X.");
  });

  it("el nombre se pinta como texto, nunca como HTML", () => {
    render(<TvLeaderboard rows={[tvRow(1, "<img src=x onerror=alert(1)> P.", 600)]} scoreType="time" />);

    expect(screen.getByText("<img src=x onerror=alert(1)> P.")).toBeInTheDocument();
    expect(document.querySelector("img")).toBeNull();
  });
});
