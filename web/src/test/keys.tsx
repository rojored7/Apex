// S6-F2 (US-143 a US-146): datos y montaje de prueba de /sistema/llaves.
// Los objetos imitan CryptoKeyOut, KeysSummary, CryptoOpOut, CryptoJobOut y RotationStartedOut de
// core/crypto/schemas.py (contrato S6-B1 a S6-R1). Ninguno trae material de llave ni referencias.
import { QueryClientProvider, type QueryClient } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactElement } from "react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { mockApi, testQueryClient, type MockHandler, type MockReply, type RecordedCall } from "./server";

export const KEYS_PATH = "/sistema/llaves";
export const KEY_DOC = "11111111-1111-4111-8111-111111111111";
export const KEY_DOC_OLD = "11111111-1111-4111-8111-111111111112";
export const KEY_PHONE = "22222222-2222-4222-8222-222222222222";
export const KEY_BIRTH = "33333333-3333-4333-8333-333333333333";
export const KEY_INDEX = "44444444-4444-4444-8444-444444444444";
export const KEY_SIGN = "55555555-5555-4555-8555-555555555555";
export const KEY_ATTACH = "66666666-6666-4666-8666-666666666666";
export const JOB_ID = "77777777-7777-4777-8777-777777777777";
export const NEW_KEY_ID = "88888888-8888-4888-8888-888888888888";
export const OPS_USER = "99999999-9999-4999-8999-999999999999";
export const SYSTEM_USER = "00000000-0000-0000-0000-000000000001";

export interface KeyFixture {
  id: string;
  purpose: "encrypt" | "index" | "sign";
  data_class: string;
  algorithm: string;
  version: number;
  state: "active" | "decrypt_only" | "retired";
  provider: "local" | "openbao";
  created_at: string;
  rotated_at: string | null;
  age_days: number;
  records_count: number | null;
}

export function cryptoKey(overrides: Partial<KeyFixture> = {}): KeyFixture {
  return {
    id: KEY_DOC,
    purpose: "encrypt",
    data_class: "member.document",
    algorithm: "A256GCM",
    version: 2,
    state: "active",
    provider: "openbao",
    created_at: "2026-03-02T15:00:00Z",
    rotated_at: "2026-10-18T18:00:00Z",
    age_days: 255,
    records_count: 342,
    ...overrides,
  };
}

/** Siete llaves: tres activas de cifrado (con Rotar), una solo descifrar, una retirada, un índice y una firma. */
export const KEYS: KeyFixture[] = [
  cryptoKey(),
  cryptoKey({ id: KEY_DOC_OLD, version: 1, state: "decrypt_only", rotated_at: null, age_days: 255, records_count: 12 }),
  cryptoKey({ id: KEY_PHONE, data_class: "member.phone", version: 1, rotated_at: null, age_days: 40, records_count: 342 }),
  cryptoKey({ id: KEY_BIRTH, data_class: "member.birth_date", version: 1, provider: "local", rotated_at: null, age_days: 12, records_count: 342 }),
  cryptoKey({ id: KEY_INDEX, purpose: "index", data_class: "member.email", algorithm: "HMAC-SHA256", version: 1, rotated_at: null, age_days: 255, records_count: null }),
  cryptoKey({ id: KEY_SIGN, purpose: "sign", data_class: "audit.signature", algorithm: "Ed25519", version: 1, rotated_at: null, age_days: 90, records_count: null }),
  cryptoKey({ id: KEY_ATTACH, data_class: "attachment.sensitive", version: 1, state: "retired", rotated_at: null, age_days: 300, records_count: 0 }),
];

export function keysSummary(overrides: Record<string, unknown> = {}) {
  return { active_count: 5, operations_today: 1204, running_jobs: 1, provider: { names: ["openbao"], state: "ok" }, ...overrides };
}

export function keysReply(call: RecordedCall, items: KeyFixture[] = KEYS, summary: unknown = keysSummary(), total = items.length): MockReply {
  const url = new URL(call.url, "http://apex.test");
  return { status: 200, body: { items, total, limit: Number(url.searchParams.get("limit")), offset: Number(url.searchParams.get("offset")), summary } };
}

export interface OpFixture {
  id: string;
  at: string;
  user_id: string;
  verb: "encrypt" | "decrypt" | "index" | "sign" | "verify" | "wrap" | "unwrap" | "rotate" | "export";
  data_class: string | null;
  key_id: string | null;
  key_version: number | null;
  record_id: string | null;
  purpose: string | null;
  result: "ok" | "error";
  batch_id: string | null;
  count: number;
}

export function cryptoOp(overrides: Partial<OpFixture> = {}): OpFixture {
  return {
    id: "aaaaaaaa-0000-4000-8000-000000000001",
    at: "2026-10-20T15:30:00Z",
    user_id: OPS_USER,
    verb: "decrypt",
    data_class: "member.document",
    key_id: KEY_DOC,
    key_version: 2,
    record_id: "bbbbbbbb-0000-4000-8000-000000000001",
    purpose: "reveal",
    result: "ok",
    batch_id: null,
    count: 1,
    ...overrides,
  };
}

export const OPS: OpFixture[] = [
  cryptoOp(),
  cryptoOp({ id: "aaaaaaaa-0000-4000-8000-000000000002", at: "2026-10-20T12:00:00Z", user_id: SYSTEM_USER, verb: "sign", data_class: "audit.signature", key_version: 1, record_id: null, count: 1 }),
  cryptoOp({ id: "aaaaaaaa-0000-4000-8000-000000000003", at: "2026-10-19T23:00:00Z", verb: "rotate", data_class: "member.phone", key_version: 2, record_id: null, result: "error", count: 0 }),
];

export function opsReply(call: RecordedCall, items: OpFixture[] = OPS, total = items.length): MockReply {
  const url = new URL(call.url, "http://apex.test");
  return { status: 200, body: { items, total, limit: Number(url.searchParams.get("limit")), offset: Number(url.searchParams.get("offset")) } };
}

export interface JobFixture {
  id: string;
  kind: "rotate" | "reencrypt" | "migrate_provider" | "rewrap";
  data_class: string | null;
  status: "pending" | "running" | "done" | "failed";
  total: number;
  done: number;
  percent: number;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
}

export function cryptoJob(overrides: Partial<JobFixture> = {}): JobFixture {
  return {
    id: JOB_ID,
    kind: "rotate",
    data_class: "member.phone",
    status: "running",
    total: 342,
    done: 212,
    percent: 61,
    started_at: "2026-10-20T14:00:00Z",
    finished_at: null,
    created_at: "2026-10-20T13:59:00Z",
    ...overrides,
  };
}

export function jobsReply(call: RecordedCall, items: JobFixture[] = [cryptoJob()], total = items.length): MockReply {
  const url = new URL(call.url, "http://apex.test");
  return { status: 200, body: { items, total, limit: Number(url.searchParams.get("limit")), offset: Number(url.searchParams.get("offset")) } };
}

export const rotationStarted = (): MockReply => ({ status: 202, body: { job_id: JOB_ID, new_key_id: NEW_KEY_ID, previous_key_id: KEY_PHONE } });

export const apiError = (status: number, code: string, message: string, extra: Record<string, unknown> = {}, headers?: Record<string, string>): MockReply => ({
  status,
  body: { error: { code, message, ...extra } },
  ...(headers ? { headers } : {}),
});

/** La URL de una llamada como URLSearchParams. */
export const queryOf = (call: RecordedCall | undefined): URLSearchParams => new URL(call?.url ?? "/", "http://apex.test").searchParams;

/** Los parámetros de la última lectura GET de `path`. */
export const lastGet = (calls: RecordedCall[], path: string): URLSearchParams => queryOf(calls.filter((c) => c.method === "GET" && c.path === path).at(-1));

export interface RenderKeysOptions {
  handlers?: Record<string, MockHandler>;
  queryClient?: QueryClient;
}

/** Monta un elemento en /sistema/llaves con la API simulada de las tres lecturas. */
export function renderKeys(element: ReactElement, entry = KEYS_PATH, { handlers = {}, queryClient = testQueryClient() }: RenderKeysOptions = {}) {
  const mock = mockApi({
    "GET /crypto/keys": (call) => keysReply(call),
    "GET /crypto/ops": (call) => opsReply(call),
    "GET /crypto/jobs": (call) => jobsReply(call),
    ...handlers,
  });
  const router = createMemoryRouter([{ path: KEYS_PATH, element: <main>{element}</main> }], { initialEntries: [entry] });
  const view = render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return { mock, router, queryClient, user: userEvent.setup(), ...view };
}
