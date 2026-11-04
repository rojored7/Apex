// S4B-F1 (S4B-D51; deuda de S4A-F2, "Barra Tabs a 1440 px y contraste de 'automático (aviso)'")
// contra `vite preview`: la pestaña Historial de la ficha con el api simulado por page.route. En v0.1
// ninguna ruta produce un `reveal` con `purpose` (CONTACT_CALLERS vacío), así que la entrada se
// simula aquí: "Sistema mostró el teléfono" con purpose "notify" lleva la etiqueta "automático
// (aviso)". axe-core la evalúa en claro y oscuro: no solo "sin violaciones" (en S4A el axe general no
// la encontró) sino que la regla color-contrast la haya revisado y aprobado (nodo en `passes`, nunca
// en `incomplete`). La variante contra el stack, con datos reales, es stack/member-history.spec.ts.
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { json, mockSession } from "./helpers/session";

const TAGS = ["wcag2a", "wcag2aa", "wcag21aa"];
const LABEL = "automático (aviso)";
const ADMIN = { id: "11111111-1111-4111-8111-111111111111", email: "admin@apex.test", role: "admin" } as const;
const SYSTEM_ID = "00000000-0000-0000-0000-000000000001";
const MEMBER_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";

const DETAIL = {
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
  membership_end_date: "2026-12-01",
  created_at: "2026-03-12T15:00:00Z",
  updated_at: "2026-10-20T15:00:00Z",
  warnings: [],
};

const HISTORY = [
  { seq: 903, at: "2026-10-20T19:10:00Z", user_id: SYSTEM_ID, user_name: "Sistema", action: "reveal", table_name: "members.members", record_id: MEMBER_ID, fields: ["phone"], purpose: "notify" },
  { seq: 902, at: "2026-10-20T15:00:00Z", user_id: ADMIN.id, user_name: "admin", action: "update", table_name: "members.members", record_id: MEMBER_ID, fields: ["phone"], purpose: null },
  { seq: 901, at: "2026-03-12T15:00:00Z", user_id: ADMIN.id, user_name: "admin", action: "insert", table_name: "members.members", record_id: MEMBER_ID, fields: [], purpose: null },
];

async function fakeApi(page: Page): Promise<void> {
  await mockSession(page, ADMIN);
  await page.route(`**/api/v1/members/${MEMBER_ID}`, (route) => json(route, 200, DETAIL));
  await page.route(new RegExp(`/api/v1/members/${MEMBER_ID}/audit(\\?.*)?$`), (route) => json(route, 200, { items: HISTORY, total: HISTORY.length, limit: 25, offset: 0 }));
}

async function setTheme(page: Page, theme: "light" | "dark"): Promise<void> {
  await page.emulateMedia({ colorScheme: theme });
  await page.addInitScript((value) => {
    try {
      localStorage.setItem("apex.theme", value);
    } catch {
      // Sin almacenamiento la página queda en claro; la comprobación de data-theme lo detectaría.
    }
  }, theme);
}

async function settle(page: Page): Promise<void> {
  await page.evaluate(async () => {
    await Promise.all(document.getAnimations().map((animation) => animation.finished.catch(() => undefined)));
  });
}

for (const theme of ["light", "dark"] as const) {
  test(`la etiqueta '${LABEL}' del historial tiene contraste suficiente en ${theme}`, async ({ page }) => {
    await fakeApi(page);
    await setTheme(page, theme);
    await page.setViewportSize({ width: 1440, height: 900 });

    await page.goto(`/socios/${MEMBER_ID}/historial`);

    await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
    const historial = page.getByRole("tabpanel").getByRole("complementary", { name: "Historial" });
    await expect(historial.getByText("Sistema mostró el teléfono")).toBeVisible();
    // Solo la entrada con propósito lleva la etiqueta.
    await expect(historial.getByText(LABEL)).toHaveCount(1);
    await expect(historial.getByText(LABEL)).toBeVisible();
    await settle(page);

    const contrast = await new AxeBuilder({ page }).withRules(["color-contrast"]).analyze();
    expect(contrast.violations.map((v) => `${v.id}: ${v.nodes.map((n) => `${n.target.join(" ")} ${n.failureSummary ?? ""}`).join(", ")}`)).toEqual([]);
    const reviewed = contrast.passes.flatMap((p) => p.nodes).filter((n) => n.html.includes(LABEL));
    const unresolved = contrast.incomplete.flatMap((p) => p.nodes).filter((n) => n.html.includes(LABEL));
    expect(unresolved, "axe no pudo calcular el contraste de la etiqueta").toEqual([]);
    expect(reviewed, "axe revisó el contraste de la etiqueta y lo aprobó").toHaveLength(1);

    const general = await new AxeBuilder({ page }).withTags(TAGS).analyze();
    expect(general.violations.map((v) => `${v.id}: ${v.help} -> ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`)).toEqual([]);
    await page.screenshot({ path: `test-results/captures/ficha-historial-aviso-${theme}-1440.png`, fullPage: true });
  });
}
