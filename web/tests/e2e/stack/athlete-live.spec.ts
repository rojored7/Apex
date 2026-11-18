// V7 (revisión de Fase 4, hueco E2E) contra el stack de Compose: anular un resultado desde el panel relee las vistas del atleta
// (invalidateResultViews -> invalidateAthleteViews) SIN recargar la página.
// - Un resultado de 100 kg (por el api) deriva el RM; «RMs por movimiento» lo muestra y queda en la caché de TanStack (staleTime 30 s).
// - Por enlaces de la SPA (sin recarga): «Récords» -> «Ver el WOD» -> «Todos los resultados» -> «Anular» con motivo. Atrás dos veces
//   (entradas del propio React Router) y «RMs por movimiento»: el RM ya no está. Sin la invalidación se vería el de la caché.
//   Un marcador en `window` prueba que la página nunca se recargó.
// No se usa la pantalla de resultados de la clase: es ruta de tablet y salir de ella pide la contraseña (por diseño, S7-F5).
// Datos: una clase de hoy con un WOD por carga (movimiento principal en kg) y el socio presente. Después de las 23:49 de Bogotá
// la spec se omite. Sin E2E_BASE_URL se omite.
import { expect, test } from "@playwright/test";
import { axeViolations } from "../helpers/axe";
import {
  ahoraMas,
  asegurarMovimientoKg,
  cancelarClase,
  crearClaseDeHoy,
  crearSocio,
  darDeBajaSocio,
  diaBogota,
  diaLibreDeWod,
  loginComo,
  PRIMER_DIA_WOD,
  sameOriginHeaders,
  type SocioCreado,
} from "../helpers/stack";

const ON_STACK = process.env.E2E_BASE_URL !== undefined;
const API = "/api/v1";

test.describe("La pestaña Atleta se actualiza al guardar un resultado, contra el stack", () => {
  test.skip(
    !ON_STACK,
    "solo contra el stack (E2E_BASE_URL) con A3 y C2; en preview no hay api",
  );

  const socios: SocioCreado[] = [];
  const sesiones: string[] = [];
  test.afterEach(async ({ page }) => {
    const fallos: Error[] = [];
    try {
      for (const socio of socios.splice(0))
        await darDeBajaSocio(page, socio.id);
    } catch (error) {
      fallos.push(error instanceof Error ? error : new Error(String(error)));
    }
    // Con resultados la clase no se cancela (409 locked_by_results): cancelarClase tolera solo eso.
    for (const id of sesiones.splice(0)) {
      try {
        await cancelarClase(page, id);
      } catch (error) {
        fallos.push(error instanceof Error ? error : new Error(String(error)));
      }
    }
    if (fallos[0]) throw fallos[0];
  });

  test("anular el resultado de 100 kg desde el WOD quita el RM de Atleta sin recargar", async ({
    page,
  }) => {
    const inicio = ahoraMas(10);
    test.skip(
      diaBogota(inicio) !== diaBogota(new Date()),
      "después de las 23:49 de Bogotá la clase de hoy no cabe en el día",
    );
    await page.setViewportSize({ width: 1440, height: 900 });
    const headers = {
      Authorization: `Bearer ${await loginComo(page)}`,
      ...sameOriginHeaders(),
    };

    const movimiento = await asegurarMovimientoKg(page, headers);
    const nombre = `Vivo E2E ${Date.now().toString(36)}`;
    const sesionId = await crearClaseDeHoy(page, headers, inicio, nombre);
    sesiones.push(sesionId);
    const wod = await page.request.post(`${API}/wods`, {
      headers,
      data: {
        date: await diaLibreDeWod(page, PRIMER_DIA_WOD),
        title: nombre,
        description: "",
        score_type: "load",
        movements: [
          {
            movement_id: movimiento.id,
            position: 1,
            reps: "1",
            is_primary: true,
            notes: "",
          },
        ],
      },
    });
    expect(wod.ok()).toBe(true);
    const wodId = ((await wod.json()) as { id: string }).id;
    expect(
      (
        await page.request.patch(`${API}/class-sessions/${sesionId}`, {
          headers,
          data: { wod_id: wodId },
        })
      ).ok(),
    ).toBe(true);
    const socio = await crearSocio(page);
    socios.push(socio);
    expect(
      (
        await page.request.post(`${API}/attendance`, {
          headers,
          data: { session_id: sesionId, member_id: socio.id },
        })
      ).ok(),
    ).toBe(true);

    const registro = await page.request.put(`${API}/results`, {
      headers,
      data: {
        member_id: socio.id,
        wod_id: wodId,
        session_id: sesionId,
        level: "rx",
        load_g: 100_000,
      },
    });
    expect(registro.ok()).toBe(true);

    // RMs con el de 100 kg: queda en la caché.
    await page.goto(`/socios/${socio.id}/atleta?tab=rms`);
    const rms = page.getByRole("table", {
      name: "RMs por movimiento del socio",
    });
    await expect(
      rms.getByRole("row").filter({ hasText: movimiento.name }),
    ).toContainText("100 kg");
    await page.evaluate(() => {
      (window as unknown as { __sinRecarga: boolean }).__sinRecarga = true;
    });

    // Por enlaces de la SPA al WOD y anular el resultado con motivo.
    await page.getByRole("tab", { name: "Récords" }).click();
    await page
      .getByRole("link", { name: `Ver el WOD de ${movimiento.name} 1RM` })
      .click();
    await expect(page).toHaveURL(new RegExp(`/wods/${wodId}`));
    await page.getByRole("tab", { name: /^Todos los resultados/ }).click();
    await page.getByRole("button", { name: "Anular" }).click();
    const modal = page.getByRole("dialog", { name: "¿Anular este resultado?" });
    await modal.getByLabel(/^Motivo/).fill("Socio equivocado");
    await modal.getByRole("button", { name: "Anular resultado" }).click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Anular" })).toHaveCount(0);

    // Atrás a Atleta y a «RMs por movimiento»: el RM ya no está, sin recargar.
    // Dos entradas: «Todos los resultados» (?tab=todos) y el WOD.
    await page.goBack();
    await page.goBack();
    await expect(page).toHaveURL(
      new RegExp(`/socios/${socio.id}/atleta\\?tab=records`),
    );
    await page.getByRole("tab", { name: "RMs por movimiento" }).click();
    await expect(
      page.getByText(
        "Todavía no hay RMs registrados. Usa «Registrar récord» para guardar el primero.",
      ),
    ).toBeVisible();
    expect(
      await page.evaluate(
        () => (window as unknown as { __sinRecarga?: boolean }).__sinRecarga,
      ),
    ).toBe(true);
    expect(await axeViolations(page)).toEqual([]);
  });
});
