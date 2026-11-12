// S6-F3 · US-148 (front): useMemberPhoto(photoAttachmentId) baja la foto del socio con el token por
// api.blob (GET /attachments/{id}), crea un `blob:` en memoria y lo revoca al desmontar y al cambiar de
// id. Con id nulo no pide nada. Nada en localStorage ni sessionStorage; el Blob se reutiliza 60 s (gcTime) entre la lista y la ficha.
import { QueryClientProvider, type QueryClient } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { createElement, type ReactNode } from "react";
import { mockApi, testQueryClient } from "../../test/server";
import { useMemberPhoto } from "./memberPhoto";

const PHOTO_A = "bbbb0001-0000-4000-8000-000000000001";
const PHOTO_B = "bbbb0001-0000-4000-8000-000000000002";
const jpeg = { status: 200, file: { content: "jpeg", contentType: "image/jpeg", filename: "adjunto-bbbb0001.jpg" } };

function wrapper(queryClient: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: queryClient }, children);
  };
}

const created: string[] = [];
const revoked: string[] = [];

beforeEach(() => {
  created.length = 0;
  revoked.length = 0;
  let n = 0;
  vi.stubGlobal(
    "URL",
    Object.assign(URL, {
      createObjectURL: vi.fn(() => {
        n += 1;
        const url = `blob:apex/foto-${String(n)}`;
        created.push(url);
        return url;
      }),
      revokeObjectURL: vi.fn((url: string) => {
        revoked.push(url);
      }),
    }),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("useMemberPhoto", () => {
  it("baja la foto con api.blob y devuelve un blob: en memoria", async () => {
    const mock = mockApi({ [`GET /attachments/${PHOTO_A}`]: jpeg });
    const { result } = renderHook(() => useMemberPhoto(PHOTO_A), { wrapper: wrapper(testQueryClient()) });

    expect(result.current.url).toBeNull();
    await waitFor(() => {
      expect(result.current.url).toBe("blob:apex/foto-1");
    });
    expect(mock.callsTo(`GET /attachments/${PHOTO_A}`)).toHaveLength(1);
    expect(mock.calls[0]?.headers.get("Accept")).toContain("image/jpeg");
  });

  it("con id nulo o indefinido no pide nada", () => {
    const mock = mockApi({});
    const first = renderHook(() => useMemberPhoto(null), { wrapper: wrapper(testQueryClient()) });
    const second = renderHook(() => useMemberPhoto(undefined), { wrapper: wrapper(testQueryClient()) });

    expect(first.result.current).toMatchObject({ url: null, isLoading: false });
    expect(second.result.current.url).toBeNull();
    expect(mock.calls).toHaveLength(0);
  });

  it("revoca el blob: al desmontar", async () => {
    mockApi({ [`GET /attachments/${PHOTO_A}`]: jpeg });
    const { result, unmount } = renderHook(() => useMemberPhoto(PHOTO_A), { wrapper: wrapper(testQueryClient()) });
    await waitFor(() => {
      expect(result.current.url).not.toBeNull();
    });
    unmount();

    expect(revoked).toEqual(["blob:apex/foto-1"]);
  });

  it("revoca el blob: anterior al cambiar de id y pide la foto nueva", async () => {
    const mock = mockApi({ [`GET /attachments/${PHOTO_A}`]: jpeg, [`GET /attachments/${PHOTO_B}`]: jpeg });
    const initialProps: { id: string | null } = { id: PHOTO_A };
    const { result, rerender } = renderHook(({ id }: { id: string | null }) => useMemberPhoto(id), { initialProps, wrapper: wrapper(testQueryClient()) });
    await waitFor(() => {
      expect(result.current.url).toBe("blob:apex/foto-1");
    });
    rerender({ id: PHOTO_B });

    await waitFor(() => {
      expect(result.current.url).toBe("blob:apex/foto-2");
    });
    expect(revoked).toContain("blob:apex/foto-1");
    expect(mock.callsTo(`GET /attachments/${PHOTO_B}`)).toHaveLength(1);
    rerender({ id: null });
    await waitFor(() => {
      expect(result.current.url).toBeNull();
    });
    expect(revoked).toContain("blob:apex/foto-2");
  });

  it("un error (404, 403, 503) deja url nulo y marca isError, sin reintentar", async () => {
    const mock = mockApi({ [`GET /attachments/${PHOTO_A}`]: { status: 404, body: { error: { code: "not_found", message: "x" } } } });
    const { result } = renderHook(() => useMemberPhoto(PHOTO_A), { wrapper: wrapper(testQueryClient()) });

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
    expect(result.current.url).toBeNull();
    expect(mock.callsTo(`GET /attachments/${PHOTO_A}`)).toHaveLength(1);
  });

  it("no escribe en localStorage ni sessionStorage", async () => {
    mockApi({ [`GET /attachments/${PHOTO_A}`]: jpeg });
    const { result } = renderHook(() => useMemberPhoto(PHOTO_A), { wrapper: wrapper(testQueryClient()) });
    await waitFor(() => {
      expect(result.current.url).not.toBeNull();
    });

    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);
  });

  it("reutiliza el Blob entre componentes: al volver a montar dentro de 60 s no vuelve a pedir la foto", async () => {
    const mock = mockApi({ [`GET /attachments/${PHOTO_A}`]: jpeg });
    const queryClient = testQueryClient();
    const first = renderHook(() => useMemberPhoto(PHOTO_A), { wrapper: wrapper(queryClient) });
    await waitFor(() => {
      expect(first.result.current.url).not.toBeNull();
    });
    first.unmount();
    const second = renderHook(() => useMemberPhoto(PHOTO_A), { wrapper: wrapper(queryClient) });

    await waitFor(() => {
      expect(second.result.current.url).not.toBeNull();
    });
    expect(mock.callsTo(`GET /attachments/${PHOTO_A}`)).toHaveLength(1);
    expect(revoked).toContain("blob:apex/foto-1");
  });

  it("una respuesta que no es imagen (PDF) no entra en un <img>: url nulo e isError", async () => {
    mockApi({ [`GET /attachments/${PHOTO_A}`]: { status: 200, file: { content: "%PDF-1.4", contentType: "application/pdf" } } });
    const { result } = renderHook(() => useMemberPhoto(PHOTO_A), { wrapper: wrapper(testQueryClient()) });

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
    expect(result.current.url).toBeNull();
    expect(created).toHaveLength(0);
  });
});
