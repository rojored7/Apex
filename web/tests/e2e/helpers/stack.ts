// Utilidades de los E2E contra el stack de Compose (proyecto `stack`, S2-W0-1).
// Las capturas cubren los cuatro anchos de US-068 en tema claro y oscuro; el tema lo da
// `prefers-color-scheme` (tokens.css), que Playwright emula con `colorScheme`.
// `loginComo` y `crearCoach` (S2-F5) entran por el api, sin la pantalla de login (S2-F3):
// POST /auth/login deja la cookie HttpOnly del refresh en el contexto del navegador y la app
// restaura la sesión al cargar (POST /auth/refresh + GET /auth/me), igual que tras un F5.
// Necesitan el login real (S2-B2/B3) y los usuarios (B4): solo corren contra el stack.
import type { APIRequestContext, Page } from "@playwright/test";

export type Theme = "light" | "dark";

export interface Credentials {
  email: string;
  password: string;
}

const API = "/api/v1";

/** Admin del seed (V3 del plan): E2E_ADMIN_EMAIL y E2E_ADMIN_PASSWORD. */
export function datosDeBase(): Credentials {
  const email = process.env.E2E_ADMIN_EMAIL;
  const password = process.env.E2E_ADMIN_PASSWORD;
  if (!email || !password) throw new Error("Faltan E2E_ADMIN_EMAIL y E2E_ADMIN_PASSWORD para los E2E contra el stack.");
  return { email, password };
}

interface LoginBody {
  access_token: string;
  must_change_password?: boolean;
}

/**
 * S2-F3: login, refresh y logout exigen `Origin` del front (S2-D38, `require_same_origin`);
 * el APIRequestContext de Playwright no lo envía solo, así que va explícito.
 */
export function sameOriginHeaders(): Record<string, string> {
  const base = process.env.E2E_BASE_URL;
  return base ? { Origin: new URL(base).origin } : {};
}

async function login(request: APIRequestContext, credentials: Credentials): Promise<LoginBody> {
  const response = await request.post(`${API}/auth/login`, { data: credentials, headers: sameOriginHeaders() });
  if (!response.ok()) throw new Error(`El login de ${credentials.email} respondió ${String(response.status())}.`);
  const body = (await response.json()) as LoginBody;
  if (body.must_change_password) throw new Error(`${credentials.email} debe cambiar su contraseña antes de los E2E (V3 del plan).`);
  return body;
}

/** Inicia sesión por el api en el contexto de `page` (la siguiente navegación la restaura) y devuelve el access token. */
export async function loginComo(page: Page, credentials: Credentials = datosDeBase()): Promise<string> {
  return (await login(page.request, credentials)).access_token;
}

/**
 * Crea un coach con correo único por corrida (las specs del stack se corren dos veces, V4) y
 * le pone contraseña con su enlace de activación (POST /users y POST /auth/reset).
 */
export async function crearCoach(page: Page, admin: Credentials = datosDeBase()): Promise<Credentials> {
  const { access_token } = await login(page.request, admin);
  const email = `coach-${Date.now().toString(36)}@apex.test`;
  const created = await page.request.post(`${API}/users`, {
    headers: { Authorization: `Bearer ${access_token}` },
    data: { email, role: "coach" },
  });
  if (!created.ok()) throw new Error(`POST /users respondió ${String(created.status())}.`);
  const token = /\/restablecer\/([A-Za-z0-9_-]+)/.exec(await created.text())?.[1];
  if (!token) throw new Error("POST /users no devolvió el enlace de activación.");
  const password = `Coach-${Date.now().toString(36)}-e2e!`;
  const reset = await page.request.post(`${API}/auth/reset`, { data: { token, new_password: password } });
  if (!reset.ok()) throw new Error(`POST /auth/reset respondió ${String(reset.status())}.`);
  return { email, password };
}

/**
 * V4: espera a que terminen las transiciones y animaciones CSS en curso antes de medir con axe.
 * Tras un clic el puntero queda sobre el botón y su hover (120 ms, Button.module.css) pasa por
 * colores intermedios: axe mide el contraste a mitad de camino (4,22:1) aunque el estado final
 * cumpla. Espera por evento (`Animation.finished`), sin pausas fijas.
 */
export async function esperarTransiciones(page: Page): Promise<void> {
  await page.evaluate(async () => {
    await Promise.all(document.getAnimations().map((animation) => animation.finished.catch(() => undefined)));
  });
}

export const VIEWPORTS: readonly number[] = [320, 768, 1024, 1440];
export const THEMES: readonly Theme[] = ["light", "dark"];
const CAPTURE_HEIGHT = 900;

export function captureName(name: string, theme: Theme, width: number): string {
  return `test-results/captures/${name}-${theme}-${String(width)}.png`;
}

export async function capture(page: Page, name: string, theme: Theme, width: number): Promise<string> {
  const path = captureName(name, theme, width);
  await page.setViewportSize({ width, height: CAPTURE_HEIGHT });
  await page.emulateMedia({ colorScheme: theme });
  await page.screenshot({ path, fullPage: true });
  return path;
}
