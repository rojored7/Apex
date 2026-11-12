// S6-F1 · US-142 (S6-D3, D34, D62, D81): estado de la firma de la cadena en Auditoría. El contrato
// trae `state`, `is_late`, `latest` y `last_valid`; el front no reimplementa la regla. Cuatro estados
// con StatusTag de texto (Íntegra, Alterada, Firma atrasada, Sin firmas); sin «no verificable»: la
// verificación no depende del custodio (D81). Claro y oscuro con axe; sin colores literales.
import { readFileSync } from "node:fs";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "vitest-axe";
import { signatureInfo, signaturesLatest } from "../../../test/audit";
import { mockApi, renderWithProviders } from "../../../test/server";
import { SignatureStatus } from "./SignatureStatus";

const SOURCES = [readFileSync("src/features/system/components/SignatureStatus.tsx", "utf8"), readFileSync("src/features/system/components/SignatureStatus.module.css", "utf8")];

afterEach(() => {
  delete document.documentElement.dataset.theme;
  vi.unstubAllGlobals();
});

function renderStatus(body: unknown, status = 200) {
  const mock = mockApi({ "GET /audit/signatures/latest": { status, body } });
  return { mock, ...renderWithProviders(<SignatureStatus />) };
}

describe("SignatureStatus · los cuatro estados", () => {
  it("Íntegra: línea con seq, fecha de Bogotá y Ed25519", async () => {
    renderStatus(signaturesLatest());

    expect(await screen.findByText("Íntegra")).toBeInTheDocument();
    expect(screen.getByText("Última firma válida: seq 88412 · 21 oct 2026, 7:00 a. m. · Ed25519")).toBeInTheDocument();
  });

  it("Alterada: state invalid, con la última firma que sí fue válida", async () => {
    renderStatus(signaturesLatest({ state: "invalid", last_valid: signatureInfo({ through_seq: 88000 }) }));

    expect(await screen.findByText("Alterada")).toBeInTheDocument();
    expect(screen.getByText("Última firma válida: seq 88000 · 21 oct 2026, 7:00 a. m. · Ed25519")).toBeInTheDocument();
    expect(screen.queryByText("Íntegra")).not.toBeInTheDocument();
  });

  it("Alterada sin ninguna firma válida lo dice", async () => {
    renderStatus(signaturesLatest({ state: "invalid", last_valid: null }));

    expect(await screen.findByText("Alterada")).toBeInTheDocument();
    expect(screen.getByText("Ninguna firma verificó correctamente.")).toBeInTheDocument();
  });

  it("Firma atrasada: is_late con la verificación al día", async () => {
    renderStatus(signaturesLatest({ is_late: true }));

    expect(await screen.findByText("Firma atrasada")).toBeInTheDocument();
    expect(screen.queryByText("Íntegra")).not.toBeInTheDocument();
    expect(screen.getByText(/Última firma válida: seq 88412/)).toBeInTheDocument();
  });

  it("Sin firmas: latest nulo, sin línea de última firma", async () => {
    renderStatus(signaturesLatest({ latest: null, last_valid: null, state: "none", verified_at: null }));

    expect(await screen.findByText("Sin firmas")).toBeInTheDocument();
    expect(screen.getByText("Todavía no se ha firmado la cadena.")).toBeInTheDocument();
    expect(screen.queryByText(/Última firma válida/)).not.toBeInTheDocument();
  });

  it("firma registrada pero sin verificar: no afirma que es íntegra", async () => {
    renderStatus(signaturesLatest({ state: "none", last_valid: null, verified_at: null }));

    expect(await screen.findByText(/Última firma registrada: seq 88412/)).toBeInTheDocument();
    expect(screen.getByText(/Pulsa «Verificar ahora»/)).toBeInTheDocument();
    expect(screen.queryByText("Íntegra")).not.toBeInTheDocument();
    expect(screen.queryByText("Alterada")).not.toBeInTheDocument();
  });

  it("nunca dice «no verificable» ni «parcial» (la verificación no depende del custodio, D81)", async () => {
    const { container } = renderStatus(signaturesLatest());
    await screen.findByText("Íntegra");

    expect(container.textContent).not.toMatch(/no verificable|parcial|sellado/i);
  });
});

describe("SignatureStatus · carga y error", () => {
  it("muestra la carga mientras llega", () => {
    renderStatus(signaturesLatest());

    expect(screen.getByText("Consultando el estado de la firma…")).toBeInTheDocument();
  });

  it("un error del api se explica y Reintentar vuelve a pedir", async () => {
    const mock = mockApi({ "GET /audit/signatures/latest": { status: 500, body: { error: { code: "internal", message: "x" } } } });
    const user = userEvent.setup();
    renderWithProviders(<SignatureStatus />);

    expect(await screen.findByText("No pudimos consultar el estado de la firma; vuelve a intentarlo.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Reintentar" }));

    expect(mock.callsTo("GET /audit/signatures/latest").length).toBeGreaterThanOrEqual(2);
  });

  it("un 403 dice que no hay permiso", async () => {
    renderStatus({ error: { code: "forbidden", message: "x" } }, 403);

    expect(await screen.findByText("No tienes permiso para ver el estado de la firma.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Reintentar" })).not.toBeInTheDocument();
  });

  it("un 429 dice que espere y no ofrece Reintentar (cubeta staff-read)", async () => {
    renderStatus({ error: { code: "rate_limited", message: "x" } }, 429);

    expect(await screen.findByText(/Demasiadas consultas seguidas; espera/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Reintentar" })).not.toBeInTheDocument();
  });

  it("otro error es genérico y sí ofrece Reintentar", async () => {
    renderStatus({ error: { code: "internal", message: "x" } }, 500);

    expect(await screen.findByText("No pudimos consultar el estado de la firma; vuelve a intentarlo.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reintentar" })).toBeInTheDocument();
  });
});

describe("SignatureStatus · diseño", () => {
  it.each([
    ["claro", null],
    ["oscuro", "dark"],
  ])("sin violaciones de accesibilidad en tema %s", async (_name, theme) => {
    if (theme) document.documentElement.dataset.theme = theme;
    const { container } = renderStatus(signaturesLatest({ is_late: true }));
    await screen.findByText("Firma atrasada");

    expect(await axe(container)).toHaveNoViolations();
  });

  it("el bloque es una región con nombre", async () => {
    renderStatus(signaturesLatest());
    await screen.findByText("Íntegra");

    expect(screen.getByRole("region", { name: "Firma de la cadena" })).toBeInTheDocument();
  });

  it("solo usa tokens: ni colores literales ni fuentes literales", () => {
    const code = SOURCES.join("\n");

    expect(code).not.toMatch(/#[0-9a-fA-F]{3,8}\b/);
    expect(code).not.toMatch(/\b(rgb|rgba|hsl|hsla|oklch)\(/);
    expect(code).not.toMatch(/font-family\s*:\s*(?!var\()/);
  });
});
