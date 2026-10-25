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
  const access_token = await accessToken(page.request, admin);
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

/**
 * S3-F3 (S3-D72): documento de 10 dígitos distinto en cada llamada, para que las specs del stack
 * se puedan correr dos veces seguidas (V4) sin chocar con un 409 de documento duplicado.
 */
export function documentoAleatorio(): string {
  const digits = Array.from(crypto.getRandomValues(new Uint8Array(10)), (byte) => String(byte % 10));
  return `9${digits.slice(1).join("")}`;
}

/**
 * S3-F7 (cierre del front): el access de las altas por el api se reutiliza mientras vale (15 min de
 * vida; se renueva a los 10). El api de desarrollo admite 5 logins por minuto por IP y cada spec del
 * stack daba de alta socio, plan, venta y baja con un login cada uno (429 al correrlas seguidas). Solo
 * se guarda en la memoria del proceso de Playwright; `loginComo` sigue haciendo un login real porque
 * deja la cookie del refresh en el navegador.
 */
const ACCESS_REUSE_MS = 10 * 60 * 1_000;
const accessCache = new Map<string, { token: string; at: number }>();

async function accessToken(request: APIRequestContext, admin: Credentials): Promise<string> {
  const cached = accessCache.get(admin.email);
  if (cached && Date.now() - cached.at < ACCESS_REUSE_MS) return cached.token;
  const { access_token } = await login(request, admin);
  accessCache.set(admin.email, { token: access_token, at: Date.now() });
  return access_token;
}

async function accessDe(page: Page, admin: Credentials): Promise<Record<string, string>> {
  return { Authorization: `Bearer ${await accessToken(page.request, admin)}` };
}

export interface SocioCreado {
  id: string;
  documento: string;
  nombre: string;
}

/** S3-F3: crea un socio activo por el api (POST /members), con documento aleatorio y autorización de datos. */
export async function crearSocio(page: Page, admin: Credentials = datosDeBase()): Promise<SocioCreado> {
  const headers = await accessDe(page, admin);
  const documento = documentoAleatorio();
  const apellido = `Venta${Date.now().toString(36)}`;
  const created = await page.request.post(`${API}/members`, {
    headers,
    data: { first_name: "Sofía", last_name: apellido, document_type: "CC", document: documento, data_consent: true },
  });
  if (!created.ok()) throw new Error(`POST /members respondió ${String(created.status())}.`);
  const body = (await created.json()) as { id: string };
  return { id: body.id, documento, nombre: `Sofía ${apellido}` };
}

export interface PlanCreado {
  id: string;
  nombre: string;
  precio: number;
}

/** S3-F3: crea un plan activo por días con nombre único (POST /plans, solo admin). */
export async function crearPlan(page: Page, precio = 120_000, admin: Credentials = datosDeBase()): Promise<PlanCreado> {
  const headers = await accessDe(page, admin);
  const nombre = `Mensual ${Date.now().toString(36)}`;
  const created = await page.request.post(`${API}/plans`, { headers, data: { name: nombre, price_cop: precio, kind: "days", duration_days: 30 } });
  if (!created.ok()) throw new Error(`POST /plans respondió ${String(created.status())}.`);
  const body = (await created.json()) as { id: string };
  return { id: body.id, nombre, precio };
}

export interface PagoInicial {
  amount_cop: number;
  method: "cash" | "nequi" | "breb";
  reference?: string;
}

/** S3-F3: vende una membresía por el api (POST /members/{id}/memberships), con primer pago opcional. */
export async function venderMembresia(page: Page, socioId: string, planId: string, pago?: PagoInicial, admin: Credentials = datosDeBase()): Promise<{ id: string; status: string }> {
  const headers = await accessDe(page, admin);
  const response = await page.request.post(`${API}/members/${socioId}/memberships`, {
    headers,
    data: { plan_id: planId, ...(pago ? { first_payment: pago } : {}) },
  });
  if (!response.ok()) throw new Error(`POST /members/{id}/memberships respondió ${String(response.status())}.`);
  return (await response.json()) as { id: string; status: string };
}

/** S3-F3: da de baja lógica al socio creado por la spec (DELETE /members/{id}, B10); sin la ruta no hace nada. */
export async function darDeBajaSocio(page: Page, socioId: string, admin: Credentials = datosDeBase()): Promise<void> {
  const headers = await accessDe(page, admin);
  await page.request.delete(`${API}/members/${socioId}`, { headers });
}

/** S3-F5: fecha civil de Bogotá (UTC-5 fijo) desplazada `dias` desde hoy, "AAAA-MM-DD". */
export function fechaBogota(dias = 0): string {
  const BOGOTA_OFFSET_MS = 5 * 60 * 60 * 1_000;
  const DAY_MS = 24 * 60 * 60 * 1_000;
  return new Date(Date.now() - BOGOTA_OFFSET_MS + dias * DAY_MS).toISOString().slice(0, 10);
}

/** S3-F5: vende por el api con una fecha de inicio dada (POST /members/{id}/memberships con start_date). */
export async function venderMembresiaDesde(page: Page, socioId: string, planId: string, inicio: string, pago?: PagoInicial, admin: Credentials = datosDeBase()): Promise<{ id: string; status: string }> {
  const headers = await accessDe(page, admin);
  const response = await page.request.post(`${API}/members/${socioId}/memberships`, {
    headers,
    data: { plan_id: planId, start_date: inicio, ...(pago ? { first_payment: pago } : {}) },
  });
  if (!response.ok()) throw new Error(`POST /members/{id}/memberships respondió ${String(response.status())}.`);
  return (await response.json()) as { id: string; status: string };
}

/** S3-F5: congela por el api (POST /memberships/{id}/freeze); devuelve el código HTTP. */
export async function congelarPorApi(page: Page, membershipId: string, desde: string, hasta: string, admin: Credentials = datosDeBase()): Promise<number> {
  const headers = await accessDe(page, admin);
  const response = await page.request.post(`${API}/memberships/${membershipId}/freeze`, { headers, data: { frozen_from: desde, frozen_to: hasta } });
  return response.status();
}
