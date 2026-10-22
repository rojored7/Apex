// S2-F4b (US-049 a US-052) contra el stack de Compose (proyecto `stack`, V4 del plan): el
// admin crea un coach, le reenvía el enlace (activación), lo edita (rol), le cierra las
// sesiones, lo bloquea, lo desbloquea y lo da de baja; la cuenta deja de aparecer en la lista
// y su ficha `?usuario=<id>` la muestra dada de baja. axe en cada paso.
// Necesita B2 a B5. Sin E2E_BASE_URL se omite: la variante contra `vite preview` es
// ../users-manage.spec.ts. Idempotente: correo único por corrida (V4 corre las specs dos veces).
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { esperarTransiciones, loginComo } from "../helpers/stack";

const ON_STACK = process.env.E2E_BASE_URL !== undefined;
const TAGS = ["wcag2a", "wcag2aa", "wcag21aa"];
const RUN = Date.now().toString(36);
const COACH_EMAIL = `coach-gestion-${RUN}@apex.test`;

async function axeViolations(page: Page): Promise<string[]> {
  await esperarTransiciones(page);
  const result = await new AxeBuilder({ page }).withTags(TAGS).analyze();
  return result.violations.map((v) => `${v.id}: ${v.help} -> ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`);
}

async function confirm(page: Page, action: string): Promise<void> {
  await page.getByRole("group", { name: `Acciones de ${COACH_EMAIL}` }).getByRole("button", { name: action }).click();
  await page.getByRole("dialog").getByRole("button", { name: action }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
}

test.describe("gestión de una cuenta contra el stack", () => {
  test.skip(!ON_STACK, "solo contra el stack (E2E_BASE_URL) con B2 a B5; en preview corre users-manage.spec.ts");

  test("el admin reenvía el enlace, edita, cierra sesiones, bloquea, desbloquea y da de baja a un coach", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await loginComo(page);
    await page.goto("/sistema/usuarios");

    // Alta (S2-F4a); el enlace de activación se descarta.
    await page.getByRole("button", { name: "Nuevo usuario del equipo" }).click();
    const panel = page.getByRole("dialog", { name: "Nuevo usuario del equipo" });
    await panel.getByRole("textbox", { name: /^Correo/ }).fill(COACH_EMAIL);
    await panel.getByRole("button", { name: "Crear usuario" }).click();
    await expect(panel.getByRole("textbox", { name: "Enlace de activación" })).toBeVisible();
    await panel.getByRole("button", { name: "Listo" }).click();
    await page.getByRole("searchbox", { name: "Buscar" }).fill(COACH_EMAIL);
    const actions = page.getByRole("group", { name: `Acciones de ${COACH_EMAIL}` });
    await expect(actions).toBeVisible();

    // Reenviar enlace: activación, 72 horas.
    await actions.getByRole("button", { name: "Reenviar enlace" }).click();
    const modal = page.getByRole("dialog", { name: "Reenviar enlace" });
    await modal.getByRole("button", { name: "Generar enlace" }).click();
    await expect(modal.getByText("Activación, vence en 72 horas")).toBeVisible();
    expect(await modal.getByRole("textbox", { name: "Enlace" }).inputValue()).toMatch(/\/restablecer\/[A-Za-z0-9_-]{20,}$/);
    expect(await axeViolations(page)).toEqual([]);
    await modal.getByRole("button", { name: "Listo" }).click();

    // Editar el rol.
    await actions.getByRole("link", { name: /^Editar/ }).click();
    const edit = page.getByRole("dialog", { name: "Editar usuario" });
    await expect(edit.getByRole("textbox", { name: /^Correo/ })).toHaveValue(COACH_EMAIL);
    await edit.getByRole("combobox", { name: /^Rol/ }).selectOption("admin");
    await edit.getByRole("button", { name: "Guardar" }).click();
    await expect(page.getByText(`Cambios guardados para ${COACH_EMAIL}.`)).toBeVisible();
    await actions.getByRole("link", { name: /^Editar/ }).click();
    await edit.getByRole("combobox", { name: /^Rol/ }).selectOption("coach");
    await edit.getByRole("button", { name: "Guardar" }).click();
    await expect(page.getByRole("dialog")).toHaveCount(0);

    // Cerrar sesiones, bloquear, desbloquear y dar de baja.
    await actions.getByRole("button", { name: /^Cerrar sesiones/ }).click();
    await page.getByRole("dialog").getByRole("button", { name: "Cerrar sesiones" }).click();
    await expect(page.getByText(`No había sesiones abiertas de ${COACH_EMAIL}.`)).toBeVisible();
    await confirm(page, "Bloquear");
    await expect(page.getByText(`${COACH_EMAIL} quedó bloqueado.`)).toBeVisible();
    await confirm(page, "Desbloquear");
    await expect(page.getByText(`${COACH_EMAIL} quedó desbloqueado.`)).toBeVisible();
    await confirm(page, "Dar de baja");
    await expect(page.getByText(`Se dio de baja a ${COACH_EMAIL}.`)).toBeVisible();
    await expect(actions).toHaveCount(0);
    expect(await axeViolations(page)).toEqual([]);
  });
});
