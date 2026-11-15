// S8-F3 · US-171 (front): el leaderboard muestra la posición del servidor tal cual (empates 1-2-2-4) y formatea cada tipo de marca.
import { QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, within } from "@testing-library/react";
import { SessionRoleProvider } from "../../../core/auth";
import { mockApi, testQueryClient } from "../../../test/server";
import { signInAs, signOutForTests } from "../../../test/session";
import { boardPage, boardRow, BOARD_ROWS } from "../../../test/wods";
import { Leaderboard } from "./Leaderboard";

const ID = "f2f2f2f2-0000-4000-8000-000000000001";

function renderBoard(scoreType: "time" | "rounds_reps" | "reps" | "load", reply = boardPage()) {
  mockApi({ [`GET /wods/${ID}/leaderboard`]: reply });
  return render(
    <QueryClientProvider client={testQueryClient()}>
      <SessionRoleProvider>
        <Leaderboard wodId={ID} scoreType={scoreType} />
      </SessionRoleProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  signInAs("admin");
});

afterEach(() => {
  cleanup();
  signOutForTests();
  vi.unstubAllGlobals();
});

describe("Leaderboard", () => {
  it("numera los empates 1, 2, 2, 4 como los manda el servidor", async () => {
    renderBoard("time");
    await screen.findByText("Valentina R.");
    const rows = screen.getAllByRole("row").slice(1);
    expect(rows.map((row) => within(row).getAllByRole("cell")[0]?.textContent)).toEqual(["1", "2", "2", "4"]);
    expect(BOARD_ROWS).toHaveLength(4);
  });

  it("quien no terminó se ve con DNF y sus repeticiones", async () => {
    renderBoard("time", boardPage([boardRow(1, "Sara", 900, { capped: true, reps: 135 })]));
    expect(await screen.findByText("DNF · 135 reps")).toBeInTheDocument();
  });

  it("rondas y repeticiones, repeticiones y carga", async () => {
    renderBoard("rounds_reps", boardPage([boardRow(1, "Ana", null, { rounds: 5, reps: 12 })]));
    expect(await screen.findByText("5 + 12")).toBeInTheDocument();
    cleanup();
    renderBoard("load", boardPage([boardRow(1, "Ana", null, { load_g: 102500 })]));
    expect(await screen.findByText("102,5 kg")).toBeInTheDocument();
  });

  it("un leaderboard demasiado grande se explica y no se trunca", async () => {
    renderBoard("time", { status: 422, body: { error: { code: "leaderboard_too_large", message: "x" } } });
    expect(await screen.findByRole("alert")).toHaveTextContent("demasiados resultados");
  });
});
