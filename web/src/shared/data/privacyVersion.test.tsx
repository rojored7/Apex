// S6-F4 · US-149: la versión vigente de la política de privacidad, solo lectura, para el formulario del socio.
import { waitFor } from "@testing-library/react";
import { renderHook } from "@testing-library/react";
import { createElement, type ReactNode } from "react";
import { QueryClientProvider } from "@tanstack/react-query";
import { mockApi, testQueryClient } from "../../test/server";
import { usePrivacyVersion } from "./privacyVersion";

const section = (policy_version: string | null) => ({
  status: 200,
  body: { key: "privacy", value: { policy_version, policy_text: policy_version ? "Texto" : null, retention_years: 5, consent_required_from: null }, version: 1, updated_at: null, updated_by: null },
});

function setup(enabled = true) {
  const client = testQueryClient();
  const wrapper = ({ children }: { children: ReactNode }) => createElement(QueryClientProvider, { client }, children);
  return renderHook(() => usePrivacyVersion(enabled), { wrapper });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("usePrivacyVersion", () => {
  it("devuelve la versión publicada", async () => {
    mockApi({ "GET /settings/privacy": section("2026-10") });
    const { result } = setup();
    await waitFor(() => {
      expect(result.current).toEqual({ status: "ready", version: "2026-10" });
    });
  });

  it("sin política publicada la versión es null (versión no registrada)", async () => {
    mockApi({ "GET /settings/privacy": section(null) });
    const { result } = setup();
    await waitFor(() => {
      expect(result.current).toEqual({ status: "ready", version: null });
    });
  });

  it("el 403 de un coach no rompe: estado unavailable", async () => {
    mockApi({ "GET /settings/privacy": { status: 403, body: { error: { code: "forbidden", message: "x" } } } });
    const { result } = setup();
    await waitFor(() => {
      expect(result.current.status).toBe("unavailable");
    });
  });

  it("una respuesta con otra forma es unavailable", async () => {
    mockApi({ "GET /settings/privacy": { status: 200, body: { nada: true } } });
    const { result } = setup();
    await waitFor(() => {
      expect(result.current.status).toBe("unavailable");
    });
  });

  it("deshabilitado no pide nada al api", async () => {
    const mock = mockApi({ "GET /settings/privacy": section("2026-10") });
    const { result } = setup(false);
    await new Promise((resolve) => setTimeout(resolve, 30));
    expect(mock.callsTo("GET /settings/privacy")).toHaveLength(0);
    expect(result.current.status).toBe("loading");
  });

  it("mientras llega, loading", () => {
    mockApi({ "GET /settings/privacy": section("2026-10") });
    expect(setup().result.current.status).toBe("loading");
  });
});
