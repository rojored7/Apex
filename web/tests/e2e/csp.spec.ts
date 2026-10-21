// US-038 T4: el front carga bajo la CSP exacta de Nginx sin violaciones (criterio 4) y
// un script en línea sin nonce queda bloqueado (criterio 5).
//
// `vite preview` no envía cabeceras ni reemplaza el marcador de nonce, así que la prueba
// intercepta la respuesta HTML y hace lo mismo que Nginx: sustituye `__CSP_NONCE__` por un
// nonce y agrega la cabecera. Con CSP_BASE_URL apuntando al stack real (Nginx) la prueba
// navega sin interceptar y exige que la cabecera venga del servidor.
import { expect, test, type Page } from "@playwright/test";

const MARKER = "__CSP_NONCE__";
const NONCE = "0123456789abcdef0123456789abcdef";
const CSP =
  `default-src 'self'; script-src 'self' 'nonce-${NONCE}'; style-src 'self'; img-src 'self' data:; ` +
  "font-src 'self'; connect-src 'self'; frame-ancestors 'none'; object-src 'none'; base-uri 'self'";

const REAL_BASE = process.env.CSP_BASE_URL;

type Violation = { directive: string; blocked: string };

declare global {
  interface Window {
    __cspViolations: Violation[];
    __inlineRan?: boolean;
  }
}

async function listenViolations(page: Page): Promise<void> {
  await page.addInitScript(() => {
    window.__cspViolations = [];
    document.addEventListener("securitypolicyviolation", (e) => {
      window.__cspViolations.push({ directive: e.violatedDirective, blocked: e.blockedURI });
    });
  });
}

function isHtml(headers: Record<string, string>): boolean {
  return (headers["content-type"] ?? "").includes("text/html");
}

async function serveLikeNginx(page: Page, mutate: (html: string) => string): Promise<void> {
  await page.route("**/*", async (route) => {
    if (route.request().resourceType() !== "document") {
      await route.continue();
      return;
    }
    const response = await route.fetch();
    const headers = response.headers();
    if (!isHtml(headers)) {
      await route.fulfill({ response });
      return;
    }
    const body = mutate((await response.text()).replaceAll(MARKER, NONCE));
    await route.fulfill({
      status: response.status(),
      headers: { ...headers, "content-security-policy": CSP, "cache-control": "no-store" },
      body,
    });
  });
}

test("el front carga sin violaciones de CSP", async ({ page }) => {
  await listenViolations(page);
  if (REAL_BASE === undefined) await serveLikeNginx(page, (html) => html);

  const response = await page.goto(REAL_BASE ?? "/");
  expect(response).not.toBeNull();
  const csp = response?.headers()["content-security-policy"] ?? "";
  expect(csp).toMatch(/script-src 'self' 'nonce-[0-9a-f]{32}'/);
  expect(csp).not.toContain("unsafe-inline");
  expect(csp).not.toContain("unsafe-eval");

  await expect(page.getByRole("heading", { level: 1, name: "APEX" })).toBeVisible();
  const violations = await page.evaluate(() => window.__cspViolations);
  expect(violations).toEqual([]);
});

test("un script en línea sin nonce queda bloqueado", async ({ page }) => {
  test.skip(REAL_BASE !== undefined, "la página de control solo se inyecta sobre vite preview");
  await listenViolations(page);
  await serveLikeNginx(page, (html) => html.replace("</body>", "<script>window.__inlineRan = true;</script></body>"));

  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1, name: "APEX" })).toBeVisible();

  const result = await page.evaluate(() => ({ ran: window.__inlineRan === true, violations: window.__cspViolations }));
  expect(result.ran).toBe(false);
  expect(result.violations.length).toBe(1);
  expect(result.violations[0]?.directive).toBe("script-src-elem");
  expect(result.violations[0]?.blocked).toBe("inline");
});
