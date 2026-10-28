// Fase 4 del Sprint 3 (L9): la sesión simulada de los E2E contra `vite preview`. Antes cada spec
// repetía el mock de POST /auth/refresh y GET /auth/me. La app restaura la sesión al cargar (refresh +
// me, igual que tras un F5); aquí los dos responden con el usuario de la prueba.
import type { Page, Route } from "@playwright/test";

export interface E2eUser {
  id: string;
  email: string;
  role: "admin" | "coach" | "member";
}

export interface MockSessionOptions {
  /** El `gym_name` de /auth/me ("Box Norte" por defecto). */
  gymName?: string;
  /** Si devuelve falso, el refresh responde 401 (la sesión terminó). */
  isActive?: () => boolean;
}

/** Responde una ruta con JSON (o sin cuerpo). */
export const json = (route: Route, status: number, body?: unknown): Promise<void> =>
  route.fulfill({ status, contentType: "application/json", body: body === undefined ? "" : JSON.stringify(body) });

/** POST /auth/refresh y GET /auth/me con `user` (sin socio, sin cambio de contraseña pendiente). */
export async function mockSession(page: Page, user: E2eUser, { gymName = "Box Norte", isActive = () => true }: MockSessionOptions = {}): Promise<void> {
  await page.route("**/api/v1/auth/refresh", (route) =>
    isActive() ? json(route, 200, { access_token: `e2e-${user.role}`, token_type: "bearer", expires_in: 900 }) : json(route, 401, { error: { code: "invalid_refresh", message: "x" } }),
  );
  await page.route("**/api/v1/auth/me", (route) => json(route, 200, { ...user, member_id: null, gym_name: gymName, must_change_password: false }));
}
