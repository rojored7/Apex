// S2-F5 (blueprint F5): useSettingsSection lee GET /settings/{key}, guarda con PATCH
// { value, version } usando la versión leída, actualiza solo la caché de su clave, marca el
// 409 version_conflict sin reintentar y recarga con reload().
import { QueryClientProvider, type QueryClient } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import type { components } from "../../core/api/types";
import { mockApi, testQueryClient } from "../../test/server";
import { CONFLICT_REPLY, gymSection, privacySection } from "../../test/settings";
import { signaturesLatest, signedVerifyResult, verifyResult } from "../../test/audit";
import { CONFLICT_MESSAGE, SIGNATURE_LATEST_KEY, isVersionConflict, settingsQueryKey, useLatestSignature, useSettingsSection, useVerifyChain, type GymSettings, type MembershipsSettings, type PrivacyInput } from "./api";

type Schemas = components["schemas"];

function wrapperFor(client: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("useSettingsSection", () => {
  it("los tipos del front encajan en el contrato del api", () => {
    expectTypeOf<GymSettings>().toExtend<Schemas["GymSettings"]>();
    expectTypeOf<PrivacyInput>().toExtend<Schemas["PrivacySettings"]>();
    expectTypeOf<MembershipsSettings>().toExtend<Schemas["MembershipsSettings"]>();
  });

  it("lee la sección con la clave de caché [settings, key]", async () => {
    const mock = mockApi({ "GET /settings/gym": { status: 200, body: gymSection({ name: "Box Norte" }, 3) } });
    const client = testQueryClient();

    const { result } = renderHook(() => useSettingsSection("gym"), { wrapper: wrapperFor(client) });

    await waitFor(() => {
      expect(result.current.query.data?.value.name).toBe("Box Norte");
    });
    expect(mock.callsTo("GET /settings/gym")).toHaveLength(1);
    expect(client.getQueryData(settingsQueryKey("gym"))).toEqual(gymSection({ name: "Box Norte" }, 3));
    expect(settingsQueryKey("privacy")).toEqual(["settings", "privacy"]);
  });

  it("guarda con la versión leída y actualiza solo la caché de su clave", async () => {
    const saved = gymSection({ name: "Box Sur" }, 4);
    const mock = mockApi({
      "GET /settings/gym": { status: 200, body: gymSection({}, 3) },
      "PATCH /settings/gym": { status: 200, body: saved },
    });
    const client = testQueryClient();
    const otherSection = privacySection({}, 0);
    client.setQueryData(settingsQueryKey("privacy"), otherSection);
    const { result } = renderHook(() => useSettingsSection("gym"), { wrapper: wrapperFor(client) });
    await waitFor(() => {
      expect(result.current.query.data).toBeDefined();
    });

    let returned: unknown;
    await act(async () => {
      returned = await result.current.save({ ...gymSection().value, name: "Box Sur" });
    });

    expect(mock.callsTo("PATCH /settings/gym")[0]?.body).toEqual({ value: { ...gymSection().value, name: "Box Sur" }, version: 3 });
    expect(returned).toEqual(saved);
    expect(client.getQueryData(settingsQueryKey("gym"))).toEqual(saved);
    expect(client.getQueryData(settingsQueryKey("privacy"))).toBe(otherSection);
    expect(mock.callsTo("GET /settings/gym")).toHaveLength(1);
  });

  it("guarda con la versión que se le da (la del formulario) aunque la caché tenga otra", async () => {
    const mock = mockApi({
      "GET /settings/gym": { status: 200, body: gymSection({}, 7) },
      "PATCH /settings/gym": CONFLICT_REPLY,
    });
    const { result } = renderHook(() => useSettingsSection("gym"), { wrapper: wrapperFor(testQueryClient()) });
    await waitFor(() => {
      expect(result.current.query.data).toBeDefined();
    });

    await act(async () => {
      await result.current.save(gymSection().value, 5).catch(() => undefined);
    });

    expect(mock.callsTo("PATCH /settings/gym")[0]?.body).toMatchObject({ version: 5 });
  });

  it("un 409 version_conflict marca isConflict, no reintenta y reload lo limpia y vuelve a leer", async () => {
    let reads = 0;
    const mock = mockApi({
      "GET /settings/gym": () => {
        reads += 1;
        return { status: 200, body: gymSection({ name: reads === 1 ? "APEX" : "Otro nombre" }, reads) };
      },
      "PATCH /settings/gym": CONFLICT_REPLY,
    });
    const { result } = renderHook(() => useSettingsSection("gym"), { wrapper: wrapperFor(testQueryClient()) });
    await waitFor(() => {
      expect(result.current.query.data).toBeDefined();
    });

    await act(async () => {
      await result.current.save(gymSection().value).catch(() => undefined);
    });

    await waitFor(() => {
      expect(result.current.isConflict).toBe(true);
    });
    expect(mock.callsTo("PATCH /settings/gym")).toHaveLength(1);

    let fresh: unknown;
    await act(async () => {
      fresh = await result.current.reload();
    });

    await waitFor(() => {
      expect(result.current.isConflict).toBe(false);
    });
    expect(result.current.query.data?.value.name).toBe("Otro nombre");
    expect(fresh).toEqual(gymSection({ name: "Otro nombre" }, 2));
  });

  it("si la recarga falla, reload no devuelve datos viejos y el conflicto sigue", async () => {
    let reads = 0;
    mockApi({
      "GET /settings/gym": () => {
        reads += 1;
        return reads === 1 ? { status: 200, body: gymSection() } : { status: 500, body: { error: { code: "internal_error", message: "x" } } };
      },
      "PATCH /settings/gym": CONFLICT_REPLY,
    });
    const { result } = renderHook(() => useSettingsSection("gym"), { wrapper: wrapperFor(testQueryClient()) });
    await waitFor(() => {
      expect(result.current.query.data).toBeDefined();
    });
    await act(async () => {
      await result.current.save(gymSection().value).catch(() => undefined);
    });

    let fresh: unknown = "sin llamar";
    await act(async () => {
      fresh = await result.current.reload();
    });

    expect(fresh).toBeUndefined();
    expect(result.current.isConflict).toBe(true);
  });

  it("marca isSaving mientras el PATCH está en curso", async () => {
    let release: () => void = () => undefined;
    mockApi({
      "GET /settings/memberships": { status: 200, body: { key: "memberships", value: { expiring_days: 7, max_freeze_days_per_membership: 30, max_freezes_per_membership: 2, max_retroactive_days: 7 }, version: 0, updated_at: null, updated_by: null } },
      "PATCH /settings/memberships": () =>
        new Promise((resolve) => {
          release = () => {
            resolve({ status: 200, body: { key: "memberships", value: { expiring_days: 8, max_freeze_days_per_membership: 30, max_freezes_per_membership: 2, max_retroactive_days: 7 }, version: 1, updated_at: "2026-10-21T15:00:00Z", updated_by: null } });
          };
        }),
    });
    const { result } = renderHook(() => useSettingsSection("memberships"), { wrapper: wrapperFor(testQueryClient()) });
    await waitFor(() => {
      expect(result.current.query.data).toBeDefined();
    });

    let saving: Promise<unknown> = Promise.resolve();
    act(() => {
      saving = result.current.save({ expiring_days: 8, max_freeze_days_per_membership: 30, max_freezes_per_membership: 2, max_retroactive_days: 7 });
    });
    await waitFor(() => {
      expect(result.current.isSaving).toBe(true);
    });
    await act(async () => {
      release();
      await saving;
    });

    await waitFor(() => {
      expect(result.current.isSaving).toBe(false);
    });
    expect(result.current.query.data?.value.expiring_days).toBe(8);
  });

  it("una respuesta con otra forma es un error de la consulta, no datos", async () => {
    mockApi({ "GET /settings/privacy": { status: 200, body: { key: "privacy", value: { retention_years: "cinco" }, version: 0 } } });
    const { result } = renderHook(() => useSettingsSection("privacy"), { wrapper: wrapperFor(testQueryClient()) });

    await waitFor(() => {
      expect(result.current.query.isError).toBe(true);
    });
    expect(result.current.query.error).toMatchObject({ code: "invalid_response" });
    expect(result.current.query.data).toBeUndefined();
  });

  it("guardar antes de leer la sección se rechaza sin llamar al api", async () => {
    const mock = mockApi({ "GET /settings/gym": () => new Promise(() => undefined) });
    const { result } = renderHook(() => useSettingsSection("gym"), { wrapper: wrapperFor(testQueryClient()) });

    await expect(result.current.save(gymSection().value)).rejects.toMatchObject({ code: "not_loaded" });
    expect(mock.callsTo("PATCH /settings/gym")).toHaveLength(0);
  });
});

describe("isVersionConflict", () => {
  it("solo el 409 version_conflict es conflicto", async () => {
    const { ApiError } = await import("../../core/api/errors");

    expect(isVersionConflict(new ApiError({ status: 409, code: "version_conflict", message: CONFLICT_MESSAGE }))).toBe(true);
    expect(isVersionConflict(new ApiError({ status: 409, code: "otro", message: "x" }))).toBe(false);
    expect(isVersionConflict(new ApiError({ status: 422, code: "version_conflict", message: "x" }))).toBe(false);
    expect(isVersionConflict(new Error("x"))).toBe(false);
    expect(CONFLICT_MESSAGE).toBe("Otra persona cambió esta sección. Recarga para ver los cambios.");
  });
});

// S6-F1 · US-142: estado de la firma (S6-D10) y verificación con firmas (S6-A3).
describe("useLatestSignature (S6-F1)", () => {
  it("lee GET /audit/signatures/latest con la clave [audit, signatures, latest]", async () => {
    const mock = mockApi({ "GET /audit/signatures/latest": { status: 200, body: signaturesLatest() } });
    const client = testQueryClient();

    const { result } = renderHook(() => useLatestSignature(), { wrapper: wrapperFor(client) });

    await waitFor(() => {
      expect(result.current.data?.state).toBe("ok");
    });
    expect(mock.callsTo("GET /audit/signatures/latest")).toHaveLength(1);
    expect(result.current.data?.latest?.through_seq).toBe(88412);
    expect(result.current.data?.last_valid?.algorithm).toBe("Ed25519");
    expect(client.getQueryData(SIGNATURE_LATEST_KEY)).toBeDefined();
    expect(SIGNATURE_LATEST_KEY).toEqual(["audit", "signatures", "latest"]);
  });

  it("sin firmas: latest y last_valid vienen nulos", async () => {
    mockApi({ "GET /audit/signatures/latest": { status: 200, body: signaturesLatest({ latest: null, last_valid: null, state: "none", verified_at: null }) } });

    const { result } = renderHook(() => useLatestSignature(), { wrapper: wrapperFor(testQueryClient()) });

    await waitFor(() => {
      expect(result.current.data?.state).toBe("none");
    });
    expect(result.current.data?.latest).toBeNull();
  });

  it("una respuesta con un estado desconocido se rechaza", async () => {
    mockApi({ "GET /audit/signatures/latest": { status: 200, body: signaturesLatest({ state: "partial" }) } });

    const { result } = renderHook(() => useLatestSignature(), { wrapper: wrapperFor(testQueryClient()) });

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
  });
});

describe("useVerifyChain con firmas (S6-F1)", () => {
  it("devuelve signatures_checked, signatures_valid y first_invalid_signature_seq", async () => {
    mockApi({ "POST /audit/verify": { status: 200, body: signedVerifyResult({ signatures_valid: 364, first_invalid_signature_seq: 88000, ok: false }) } });

    const { result } = renderHook(() => useVerifyChain(), { wrapper: wrapperFor(testQueryClient()) });
    let outcome: Awaited<ReturnType<typeof result.current.mutateAsync>> | undefined;
    await act(async () => {
      outcome = await result.current.mutateAsync();
    });

    expect(outcome?.kind).toBe("done");
    if (outcome?.kind !== "done") throw new Error("se esperaba 200");
    expect(outcome.result.signatures_checked).toBe(365);
    expect(outcome.result.signatures_valid).toBe(364);
    expect(outcome.result.first_invalid_signature_seq).toBe(88000);
    expect(outcome.result.last_valid_signature_algorithm).toBe("Ed25519");
  });

  it("una verificación sin los campos de firmas (api anterior) sigue válida", async () => {
    mockApi({ "POST /audit/verify": { status: 200, body: verifyResult() } });

    const { result } = renderHook(() => useVerifyChain(), { wrapper: wrapperFor(testQueryClient()) });
    await act(async () => {
      await result.current.mutateAsync();
    });

    expect(result.current.isSuccess || result.current.isIdle).toBe(true);
  });

  it("no invalida la firma por su cuenta: lo hace VerifyChainButton al terminar (también tras un sondeo)", async () => {
    const client = testQueryClient();
    client.setQueryData(SIGNATURE_LATEST_KEY, signaturesLatest());
    mockApi({ "POST /audit/verify": { status: 200, body: signedVerifyResult() } });

    const { result } = renderHook(() => useVerifyChain(), { wrapper: wrapperFor(client) });
    await act(async () => {
      await result.current.mutateAsync();
    });

    expect(client.getQueryState(SIGNATURE_LATEST_KEY)?.isInvalidated).toBe(false);
  });
});
