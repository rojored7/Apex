// S3-F1 · US-073 a US-076: datos y montaje de prueba de la ficha (/socios/:id con su pestaña índice
// "Datos"), la edición (/socios/:id/editar) y un campo sensible con "Mostrar" conectado a
// POST /members/{id}/reveal (useRevealField, S3-D52).
// - memberDetailBody imita MemberDetailOut de GET /members/{id} (B9b): los cinco sensibles llegan
//   enmascarados con el texto del api; nunca hay un dato en claro en la ficha.
// - REVEALED son los valores en claro que devuelve el reveal simulado; las pruebas comprueban que
//   no quedan en el DOM, el almacenamiento, la consola ni la caché de TanStack Query.
import { QueryClientProvider, type QueryClient } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { createMemoryRouter, RouterProvider, useLocation } from "react-router";
import { SessionRoleProvider } from "../core/auth";
import MemberDataTab from "../features/members/components/MemberDataTab";
import MemberHistoryTab from "../features/members/components/MemberHistoryTab";
import MemberMembershipsTab from "../features/memberships/components/MemberMembershipsTab";
import MemberPaymentsTab from "../features/payments/components/MemberPaymentsTab";
import { MemberSensitiveField, type MemberSensitiveFieldProps } from "../features/members/components/MemberSensitiveField";
import MemberDetailPage from "../features/members/pages/MemberDetailPage";
import MemberFormPage from "../features/members/pages/MemberFormPage";
import { mockApi, testQueryClient, type MockHandler, type MockReply, type RecordedCall } from "./server";

export const MEMBER_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
export const DUPLICATE_ID = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee";
export const DETAIL_PATH = `/members/${MEMBER_ID}`;
export const REVEAL_PATH = `/members/${MEMBER_ID}/reveal`;

/** Valores en claro del socio de prueba (solo los devuelve el reveal simulado). */
export const REVEALED = {
  document: "1020304417",
  phone: "3001234567",
  email: "laura@correo.co",
  birth_date: "1991-03-12",
  emergency_contact: { name: "Marta Gómez", phone: "3110000008", relationship: "Madre" },
} as const;

export interface MemberDetailFixture {
  id: string;
  first_name: string;
  last_name: string;
  sex: "f" | "m" | "x" | null;
  status: "active" | "inactive";
  document_type: "CC" | "CE" | "TI" | "PA";
  document: string | null;
  phone: string | null;
  email: string | null;
  birth_date: string | null;
  emergency_contact: string | null;
  data_consent_at: string | null;
  data_consent_version: string | null;
  deleted_at: string | null;
  membership_status: string | null;
  plan_name: string | null;
  membership_end_date: string | null;
  created_at: string;
  updated_at: string;
  warnings: string[];
}

/** MemberDetailOut de Laura Gómez: al día con Mensual, vence el 28 oct 2026, con autorización. */
export function memberDetailBody(overrides: Partial<MemberDetailFixture> = {}): MemberDetailFixture {
  return {
    id: MEMBER_ID,
    first_name: "Laura",
    last_name: "Gómez",
    sex: "f",
    status: "active",
    document_type: "CC",
    document: "CC •••• 4417",
    phone: "••• ••• 4567",
    email: "l•••@•••.co",
    birth_date: "••/••/1991",
    emergency_contact: "Registrado",
    data_consent_at: "2026-03-12T15:00:00Z",
    data_consent_version: "2026-03",
    deleted_at: null,
    membership_status: "active",
    plan_name: "Mensual",
    membership_end_date: "2026-10-28",
    created_at: "2026-03-12T15:00:00Z",
    updated_at: "2026-10-20T15:00:00Z",
    warnings: [],
    ...overrides,
  };
}

/** El mismo socio dado de baja el 20 oct 2026 (N-20: la ficha sigue visible). */
export const DELETED_OVERRIDES: Partial<MemberDetailFixture> = { deleted_at: "2026-10-20T15:00:00Z", status: "inactive" };

export const ok = (body: unknown, status = 200): MockReply => ({ status, body });

export const apiError = (status: number, code: string, extra: Record<string, unknown> = {}, headers?: Record<string, string>): MockReply => ({
  status,
  body: { error: { code, message: "Mensaje del api.", ...extra } },
  ...(headers ? { headers } : {}),
});

/** Una página vacía con el limit y el offset pedidos (pestañas de S3-F7). */
export function emptyPage(call: RecordedCall): MockReply {
  const url = new URL(call.url, "http://apex.test");
  return ok({ items: [], total: 0, limit: Number(url.searchParams.get("limit")), offset: Number(url.searchParams.get("offset")) });
}

/** Respuesta del reveal simulado: el valor en claro del campo pedido. */
export function revealReply(call: RecordedCall): MockReply {
  const field = (call.body as { field: keyof typeof REVEALED }).field;
  return ok({ field, value: REVEALED[field] });
}

function Location() {
  const location = useLocation();
  return <span data-testid="location">{`${location.pathname}${location.search}`}</span>;
}

export interface RenderDetailOptions {
  handlers?: Record<string, MockHandler>;
  queryClient?: QueryClient;
  /** Estado de la navegación inicial (el aviso de "Cambios guardados"). */
  state?: unknown;
}

const shell = (page: ReactNode) => (
  <>
    <nav aria-label="Menú principal">
      <a href="/">Inicio</a>
    </nav>
    <main>{page}</main>
    <Location />
  </>
);

/** Monta la ficha, la edición y destinos marcadores con el router real (y su Outlet). */
export function renderMemberDetail(entry = `/socios/${MEMBER_ID}`, { handlers = {}, queryClient = testQueryClient(), state }: RenderDetailOptions = {}) {
  const mock = mockApi({
    [`GET ${DETAIL_PATH}`]: ok(memberDetailBody()),
    [`POST ${REVEAL_PATH}`]: revealReply,
    // S3-F7: las pestañas Membresías y Pagos (rutas hijas) piden lo suyo; por defecto, vacías.
    [`GET ${DETAIL_PATH}/memberships`]: emptyPage,
    [`GET ${DETAIL_PATH}/payments`]: emptyPage,
    // S4A-F2: la caja "Historial reciente" de Datos y la pestaña Historial; por defecto, vacías.
    [`GET ${DETAIL_PATH}/audit`]: emptyPage,
    "GET /payments/methods": ok({ items: [] }),
    ...handlers,
  });
  const router = createMemoryRouter(
    [
      { path: "/socios", element: shell(<h1>Lista de socios</h1>) },
      {
        path: "/socios/:id",
        element: shell(<MemberDetailPage />),
        children: [
          { index: true, element: <MemberDataTab /> },
          { path: "/socios/:id/membresias", element: <MemberMembershipsTab /> },
          { path: "/socios/:id/pagos", element: <MemberPaymentsTab /> },
          { path: "/socios/:id/historial", element: <MemberHistoryTab /> },
        ],
      },
      { path: "/socios/:id/editar", element: shell(<MemberFormPage />) },
      { path: "/membresias/vender", element: shell(<h1>Vender membresía</h1>) },
    ],
    { initialEntries: [state === undefined ? entry : { pathname: entry, state }] },
  );
  const view = render(
    <QueryClientProvider client={queryClient}>
      <SessionRoleProvider>
        <RouterProvider router={router} />
      </SessionRoleProvider>
    </QueryClientProvider>,
  );
  return { mock, router, queryClient, user: userEvent.setup(), ...view };
}

export interface RenderFieldOptions {
  handlers?: Record<string, MockHandler>;
  queryClient?: QueryClient;
  /** Envuelve el campo (por ejemplo en un ErrorBoundary de prueba). */
  wrap?: (field: ReactNode) => ReactNode;
}

/** Un campo sensible de la ficha (MaskedValue con useRevealField), sin el resto de la página. */
export function renderSensitiveField(props: Partial<MemberSensitiveFieldProps> = {}, { handlers = {}, queryClient = testQueryClient(), wrap = (field) => field }: RenderFieldOptions = {}) {
  const mock = mockApi({ [`POST ${REVEAL_PATH}`]: revealReply, ...handlers });
  const field = <MemberSensitiveField memberId={MEMBER_ID} field="document" label="Documento" masked="CC •••• 4417" {...props} />;
  const view = render(
    <QueryClientProvider client={queryClient}>
      <SessionRoleProvider>{wrap(field)}</SessionRoleProvider>
    </QueryClientProvider>,
  );
  return { mock, queryClient, ...view };
}

/** Cuerpos de cada PATCH /members/{id}, en orden. */
export const patchBodies = (mock: { callsTo: (key: string) => RecordedCall[] }): unknown[] => mock.callsTo(`PATCH ${DETAIL_PATH}`).map((c) => c.body);
