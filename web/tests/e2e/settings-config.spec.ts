// S2-F5 (US-055, US-057, US-058) contra `vite preview`: la pantalla de Configuración en un
// navegador real con el api simulado por page.route (sesión de admin y las tres secciones en
// memoria con su versión). La variante contra el stack (sesión y base reales) es
// stack/settings-gym.spec.ts. Accesibilidad con @axe-core/playwright en claro y oscuro.
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page, type Route } from "@playwright/test";

const TAGS = ["wcag2a", "wcag2aa", "wcag21aa"];
const PATH = "/sistema/configuracion";

type Key = "gym" | "privacy" | "memberships" | "payment_methods";

interface Section {
  key: Key;
  value: Record<string, unknown>;
  version: number;
  updated_at: string | null;
  updated_by: string | null;
}

interface FakeApi {
  sections: Record<Key, Section>;
  patches: { key: Key; body: unknown }[];
  /** La próxima escritura de esta sección responde 409 (otra persona guardó antes). */
  conflictOn: Set<Key>;
}

function initialSections(): Record<Key, Section> {
  const base = { version: 0, updated_at: null, updated_by: null };
  return {
    gym: { key: "gym", value: { name: "APEX", nit: null, address: null, city: null, phone: null, whatsapp: null, email: null }, ...base },
    privacy: { key: "privacy", value: { policy_version: null, policy_text: null, retention_years: 5, consent_required_from: null }, ...base },
    memberships: { key: "memberships", value: { expiring_days: 7, max_freeze_days_per_membership: 30, max_freezes_per_membership: 2, max_retroactive_days: 7 }, ...base },
    payment_methods: {
      key: "payment_methods",
      value: { cash: { label: "Efectivo", hint: "" }, nequi: { label: "Nequi", hint: "" }, breb: { label: "Bre-B", hint: "" } },
      ...base,
    },
  };
}

const json = (route: Route, status: number, body: unknown) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });

async function fakeApi(page: Page): Promise<FakeApi> {
  const state: FakeApi = { sections: initialSections(), patches: [], conflictOn: new Set() };
  await page.route("**/api/v1/auth/refresh", (route) => json(route, 200, { access_token: "e2e-admin", token_type: "bearer", expires_in: 900 }));
  await page.route("**/api/v1/auth/me", (route) =>
    json(route, 200, {
      id: "11111111-1111-4111-8111-111111111111",
      email: "admin@apex.test",
      role: "admin",
      member_id: null,
      gym_name: "APEX",
      must_change_password: false,
    }),
  );
  await page.route("**/api/v1/settings/*", async (route) => {
    const key = new URL(route.request().url()).pathname.split("/").pop() as Key;
    const current = state.sections[key];
    if (route.request().method() === "GET") return json(route, 200, current);
    const body = route.request().postDataJSON() as { value: Record<string, unknown>; version: number };
    state.patches.push({ key, body });
    if (state.conflictOn.has(key) || body.version !== current.version) {
      state.conflictOn.delete(key);
      state.sections[key] = { ...current, value: { ...current.value, name: "Cambio de otra persona" }, version: current.version + 1 };
      return json(route, 409, { error: { code: "version_conflict", message: "Otra persona cambió esta sección. Recarga para ver los cambios." } });
    }
    const value = key === "gym" && typeof body.value.email === "string" ? { ...body.value, email: body.value.email.toLowerCase() } : body.value;
    state.sections[key] = { key, value, version: current.version + 1, updated_at: "2026-10-21T15:00:00Z", updated_by: "11111111-1111-4111-8111-111111111111" };
    return json(route, 200, state.sections[key]);
  });
  return state;
}

async function axeViolations(page: Page): Promise<string[]> {
  // V4 del Sprint 3: el hover de un botón recién pulsado pasa por colores intermedios; se mide al final.
  await page.evaluate(async () => {
    await Promise.all(document.getAnimations().map((animation) => animation.finished.catch(() => undefined)));
  });
  const result = await new AxeBuilder({ page }).withTags(TAGS).analyze();
  return result.violations.map((v) => `${v.id}: ${v.help} -> ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`);
}

test.beforeEach(async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
});

test("el admin guarda nombre y NIT, recarga y los ve; el correo vuelve en minúsculas", async ({ page }) => {
  const api = await fakeApi(page);
  await page.goto(PATH);

  const name = page.getByRole("textbox", { name: /Nombre/ });
  await name.fill("APEX CrossFit Bogotá");
  await page.getByRole("textbox", { name: "NIT" }).fill("901234567-8");
  await page.getByRole("textbox", { name: "Correo de contacto" }).fill("Box@APEX.co");
  await page.getByRole("button", { name: "Guardar" }).click();

  await expect(page.getByText("Cambios guardados")).toBeVisible();
  expect(api.patches).toHaveLength(1);
  expect(api.patches[0]?.body).toMatchObject({ version: 0, value: { name: "APEX CrossFit Bogotá", nit: "901234567-8" } });
  // El TopBar toma el nombre guardado sin recargar.
  await expect(page.getByRole("banner")).toContainText("APEX CrossFit Bogotá");

  await page.reload();
  await expect(page.getByRole("textbox", { name: /Nombre/ })).toHaveValue("APEX CrossFit Bogotá");
  await expect(page.getByRole("textbox", { name: "NIT" })).toHaveValue("901234567-8");
  await expect(page.getByRole("textbox", { name: "Correo de contacto" })).toHaveValue("box@apex.co");
});

test("publica la primera versión de la política y luego una nueva con confirmación", async ({ page }) => {
  const api = await fakeApi(page);
  await page.goto(`${PATH}?tab=privacidad`);

  await page.getByRole("textbox", { name: /Versión de la política/ }).fill("2026-10");
  await page.getByRole("textbox", { name: /Texto de la política/ }).fill("Autorizo a APEX el tratamiento de mis datos personales.");
  await page.getByRole("button", { name: "Guardar" }).click();
  await expect(page.getByText("Versión vigente: 2026-10 · vigente desde 21 oct 2026")).toBeVisible();

  await page.getByRole("textbox", { name: /Versión de la política/ }).fill("2026-11");
  await page.getByRole("button", { name: "Guardar" }).click();
  const dialog = page.getByRole("dialog", { name: "¿Publicar la versión 2026-11?" });
  await expect(dialog).toContainText("Los socios que ya aceptaron conservan la versión anterior.");
  await dialog.getByRole("button", { name: "Publicar versión" }).click();

  await expect(page.getByText("Versión vigente: 2026-11 · vigente desde 21 oct 2026")).toBeVisible();
  expect(api.patches.map((p) => p.body)).toMatchObject([{ version: 0 }, { version: 1, value: { policy_version: "2026-11" } }]);
});

test("fija expiring_days = 7 como entero y rechaza un decimal sin llamar al api", async ({ page }) => {
  const api = await fakeApi(page);
  await page.goto(`${PATH}?tab=membresias`);
  const expiring = page.getByRole("spinbutton", { name: /Por vencer/ });

  await expiring.fill("7.5");
  await page.getByRole("button", { name: "Guardar" }).click();
  await expect(page.getByText("Escribe un número entero, sin decimales ni signos.")).toBeVisible();
  expect(api.patches).toHaveLength(0);

  await expiring.fill("7");
  await page.getByRole("button", { name: "Guardar" }).click();
  await expect(page.getByText("Cambios guardados")).toBeVisible();
  expect(api.patches[0]?.body).toEqual({
    value: { expiring_days: 7, max_freeze_days_per_membership: 30, max_freezes_per_membership: 2, max_retroactive_days: 7 },
    version: 0,
  });
});

test("S3-F4: la pestaña Medios de pago guarda las tres etiquetas fijas, sin agregar medios", async ({ page }) => {
  const api = await fakeApi(page);
  await page.goto(PATH);
  await page.getByRole("tab", { name: "Medios de pago" }).click();
  await expect(page).toHaveURL(/\?tab=medios$/);

  const nequi = page.getByRole("group", { name: "Nequi" });
  await expect(page.getByText("Para agregar un medio nuevo se requiere una actualización del sistema.")).toBeVisible();
  await expect(page.getByRole("button", { name: /Agregar/ })).toHaveCount(0);
  await nequi.getByRole("textbox", { name: /Nombre que se muestra/ }).fill("Nequi del box");
  await page.getByRole("button", { name: "Guardar" }).click();

  await expect(page.getByText("Cambios guardados")).toBeVisible();
  expect(api.patches).toEqual([
    {
      key: "payment_methods",
      body: { version: 0, value: { cash: { label: "Efectivo", hint: "" }, nequi: { label: "Nequi del box", hint: "" }, breb: { label: "Bre-B", hint: "" } } },
    },
  ]);

  await page.reload();
  await expect(page.getByRole("group", { name: "Nequi" }).getByRole("textbox", { name: /Nombre que se muestra/ })).toHaveValue("Nequi del box");
});

test("con cambios sin guardar, cambiar de pestaña pide confirmación", async ({ page }) => {
  await fakeApi(page);
  await page.goto(PATH);

  await page.getByRole("textbox", { name: "Ciudad" }).fill("Bogotá");
  await page.getByRole("tab", { name: "Membresías" }).click();
  const dialog = page.getByRole("dialog", { name: "Tienes cambios sin guardar. ¿Descartarlos?" });
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", { name: "Volver" }).click();
  await expect(page.getByRole("textbox", { name: "Ciudad" })).toHaveValue("Bogotá");

  await page.getByRole("tab", { name: "Membresías" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Descartar cambios" }).click();
  await expect(page).toHaveURL(/\?tab=membresias$/);
  await expect(page.getByRole("spinbutton", { name: /Por vencer/ })).toBeVisible();
});

test("un 409 muestra el aviso y Recargar trae lo que guardó la otra persona", async ({ page }) => {
  const api = await fakeApi(page);
  await page.goto(PATH);
  api.conflictOn.add("gym");

  await page.getByRole("textbox", { name: /Nombre/ }).fill("Mi cambio");
  await page.getByRole("button", { name: "Guardar" }).click();
  const alert = page.getByRole("alert");
  await expect(alert).toContainText("Otra persona cambió esta sección. Recarga para ver los cambios.");
  await expect(page.getByRole("button", { name: "Guardar" })).toBeDisabled();

  await alert.getByRole("button", { name: "Recargar" }).click();
  await expect(page.getByRole("textbox", { name: /Nombre/ })).toHaveValue("Cambio de otra persona");
  expect(api.patches).toHaveLength(1);
});

for (const theme of ["light", "dark"] as const) {
  for (const width of [390, 1440]) {
    test(`las cuatro pestañas pasan axe en ${theme} a ${String(width)} px sin desborde`, async ({ page }) => {
      await fakeApi(page);
      await page.emulateMedia({ colorScheme: theme });
      await page.setViewportSize({ width, height: 900 });
      await page.addInitScript((value) => {
        try {
          localStorage.setItem("apex.theme", value);
        } catch {
          // Sin almacenamiento el panel queda en claro; la prueba en oscuro lo detectaría.
        }
      }, theme);

      for (const id of ["gimnasio", "privacidad", "membresias", "medios"]) {
        await page.goto(`${PATH}?tab=${id}`);
        await expect(page.getByRole("button", { name: "Guardar" })).toBeVisible();
        await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
        expect(await axeViolations(page)).toEqual([]);
        const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
        expect(overflow).toBeLessThanOrEqual(0);
        await page.screenshot({ path: `test-results/captures/config-${id}-${theme}-${String(width)}.png`, fullPage: true });
      }
    });
  }
}
