// S2-F4b (blueprint F4b): hooks de gestión de cuentas. GET /users/{id}, PATCH, DELETE, lock,
// unlock, revoke-sessions y resend-link; respuestas validadas con Zod; todas las mutaciones
// invalidan ["users"] y el reenvío usa gcTime 0 (L-7).
import { QueryClientProvider, type QueryClient } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { isApiError } from "../../core/api/errors";
import type { components } from "../../core/api/types";
import { mockApi, testQueryClient } from "../../test/server";
import { userOut, USERS } from "../../test/users";
import {
  useDeleteUser,
  useLockUser,
  useResendLink,
  useRevokeSessions,
  useUnlockUser,
  useUpdateUser,
  useUser,
  userQueryKey,
  usersQueryKey,
  type UpdateUserChanges,
} from "./api";
import type { UserView } from "./schemas";

type Schemas = components["schemas"];

function wrapperFor(client: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("hooks de cuentas · contrato", () => {
  it("los tipos del front encajan en el contrato del api", () => {
    expectTypeOf<UserView>().toExtend<Schemas["UserOut"]>();
    expectTypeOf<UpdateUserChanges>().toExtend<Schemas["UpdateUserIn"]>();
  });

  it("la clave del detalle vive dentro de [users]", () => {
    expect(userQueryKey("x")).toEqual(["users", "detail", "x"]);
  });
});

describe("useUser", () => {
  it("lee GET /users/{id} y valida la respuesta", async () => {
    const mock = mockApi({ [`GET /users/${USERS.coach.id}`]: { status: 200, body: userOut(USERS.coach) } });

    const { result } = renderHook(() => useUser(USERS.coach.id), { wrapper: wrapperFor(testQueryClient()) });

    await waitFor(() => {
      expect(result.current.data?.email).toBe(USERS.coach.email);
    });
    expect(mock.callsTo(`GET /users/${USERS.coach.id}`)).toHaveLength(1);
  });

  it("no guarda copia en caché: gcTime 0 y un id vacío no pide nada", () => {
    const mock = mockApi({});
    const client = testQueryClient();

    renderHook(() => useUser(""), { wrapper: wrapperFor(client) });

    expect(mock.calls).toHaveLength(0);
    expect(client.getQueryCache().find({ queryKey: userQueryKey("") })?.options.gcTime).toBe(0);
  });

  it("sin id no pide nada", () => {
    const mock = mockApi({});

    const { result } = renderHook(() => useUser(null), { wrapper: wrapperFor(testQueryClient()) });

    expect(result.current.fetchStatus).toBe("idle");
    expect(mock.calls).toHaveLength(0);
  });

  it("escapa el id en la ruta", async () => {
    const mock = mockApi({});

    renderHook(() => useUser("a/b?c"), { wrapper: wrapperFor(testQueryClient()) });

    await waitFor(() => {
      expect(mock.calls).toHaveLength(1);
    });
    expect(mock.calls[0]?.url).toContain("/users/a%2Fb%3Fc");
  });

  it("una forma inesperada es un error invalid_response", async () => {
    mockApi({ [`GET /users/${USERS.coach.id}`]: { status: 200, body: { id: USERS.coach.id } } });

    const { result } = renderHook(() => useUser(USERS.coach.id), { wrapper: wrapperFor(testQueryClient()) });

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
    expect(isApiError(result.current.error) && result.current.error.code).toBe("invalid_response");
  });
});

describe("mutaciones de cuentas", () => {
  async function invalidatesUsers<T>(useHook: () => { mutateAsync: (v: T) => Promise<unknown> }, variables: T, handlers: Parameters<typeof mockApi>[0]) {
    const mock = mockApi(handlers);
    const client = testQueryClient();
    client.setQueryData(usersQueryKey({ limit: 25, offset: 0 }), { items: [], total: 0, limit: 25, offset: 0 });
    const { result } = renderHook(useHook, { wrapper: wrapperFor(client) });
    let value: unknown;
    await act(async () => {
      value = await result.current.mutateAsync(variables);
    });
    await waitFor(() => {
      expect(client.getQueryState(usersQueryKey({ limit: 25, offset: 0 }))?.isInvalidated).toBe(true);
    });
    return { mock, value, client };
  }

  it("useUpdateUser hace PATCH con los cambios y devuelve la cuenta", async () => {
    const { mock, value } = await invalidatesUsers(useUpdateUser, { id: USERS.coach.id, changes: { role: "admin" } }, {
      [`PATCH /users/${USERS.coach.id}`]: { status: 200, body: userOut(USERS.coach, { role: "admin" }) },
    });

    expect(mock.callsTo(`PATCH /users/${USERS.coach.id}`)[0]?.body).toEqual({ role: "admin" });
    expect((value as UserView).role).toBe("admin");
  });

  it("useDeleteUser hace DELETE y no devuelve nada", async () => {
    const { mock, value } = await invalidatesUsers(useDeleteUser, { id: USERS.coach.id }, { [`DELETE /users/${USERS.coach.id}`]: { status: 204 } });

    expect(mock.callsTo(`DELETE /users/${USERS.coach.id}`)).toHaveLength(1);
    expect(value).toBeUndefined();
  });

  it("useLockUser y useUnlockUser hacen POST a lock y unlock", async () => {
    const locked = await invalidatesUsers(useLockUser, { id: USERS.coach.id }, { [`POST /users/${USERS.coach.id}/lock`]: { status: 200, body: userOut(USERS.coach, { status: "locked" }) } });
    expect((locked.value as UserView).status).toBe("locked");

    const unlocked = await invalidatesUsers(useUnlockUser, { id: USERS.locked.id }, { [`POST /users/${USERS.locked.id}/unlock`]: { status: 200, body: userOut(USERS.locked, { status: "active" }) } });
    expect((unlocked.value as UserView).status).toBe("active");
  });

  it("useRevokeSessions devuelve {revoked}", async () => {
    const { value } = await invalidatesUsers(useRevokeSessions, { id: USERS.coach.id }, { [`POST /users/${USERS.coach.id}/revoke-sessions`]: { status: 200, body: { revoked: 2 } } });

    expect(value).toBe(2);
  });

  it("useResendLink devuelve el enlace y usa gcTime 0", async () => {
    const { value, client } = await invalidatesUsers(useResendLink, { id: USERS.coach.id }, {
      [`POST /users/${USERS.coach.id}/resend-link`]: { status: 200, body: { url: "https://apex.test/restablecer/abc", purpose: "reset", expires_at: "2026-10-21T20:30:00Z" } },
    });

    expect(value).toEqual({ url: "https://apex.test/restablecer/abc", purpose: "reset", expiresAt: "2026-10-21T20:30:00Z" });
    expect(client.getMutationCache().getAll()[0]?.options.gcTime).toBe(0);
  });

  it("useResendLink rechaza un propósito desconocido o un vencimiento sin zona", async () => {
    const client = testQueryClient();
    for (const body of [
      { url: "https://apex.test/restablecer/abc", purpose: "login", expires_at: "2026-10-21T20:30:00Z" },
      { url: "https://apex.test/restablecer/abc", purpose: "reset", expires_at: "2026-10-21 20:30" },
    ]) {
      mockApi({ [`POST /users/${USERS.coach.id}/resend-link`]: { status: 200, body } });
      const { result } = renderHook(() => useResendLink(), { wrapper: wrapperFor(client) });
      await act(async () => {
        await expect(result.current.mutateAsync({ id: USERS.coach.id })).rejects.toMatchObject({ code: "invalid_response" });
      });
    }
  });

  it("un 409 o un 404 releen la lista (quedó vieja)", async () => {
    for (const [status, code] of [[409, "already_locked"], [404, "user_not_found"]] as const) {
      mockApi({ [`POST /users/${USERS.coach.id}/lock`]: { status, body: { error: { code, message: "x" } } } });
      const client = testQueryClient();
      client.setQueryData(usersQueryKey({ limit: 25, offset: 0 }), { items: [], total: 0, limit: 25, offset: 0 });
      const { result } = renderHook(() => useLockUser(), { wrapper: wrapperFor(client) });

      await act(async () => {
        await expect(result.current.mutateAsync({ id: USERS.coach.id })).rejects.toMatchObject({ code, status });
      });

      expect(client.getQueryState(usersQueryKey({ limit: 25, offset: 0 }))?.isInvalidated).toBe(true);
    }
  });

  it("un 5xx no invalida la lista", async () => {
    mockApi({ [`POST /users/${USERS.admin.id}/lock`]: { status: 500, body: { error: { code: "internal", message: "x" } } } });
    const client = testQueryClient();
    client.setQueryData(usersQueryKey({ limit: 25, offset: 0 }), { items: [], total: 0, limit: 25, offset: 0 });
    const { result } = renderHook(() => useLockUser(), { wrapper: wrapperFor(client) });

    await act(async () => {
      await expect(result.current.mutateAsync({ id: USERS.admin.id })).rejects.toMatchObject({ code: "internal", status: 500 });
    });

    expect(client.getQueryState(usersQueryKey({ limit: 25, offset: 0 }))?.isInvalidated).toBe(false);
  });
});
