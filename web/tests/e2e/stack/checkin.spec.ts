// S7-F4 / S7-F4b (US-159, US-161, S7-D24, S7-D27, S7-D41) contra el stack de Compose: el check-in en modo tablet con la CUENTA DE UN COACH.
// Cubre: las siete banderas con su dato (vencido, sin plan, congelado, pendiente de pago, cupo lleno, fuera de horario, otro día),
// el 409 `already_checked_in` por el api, «atrás» y la barra de direcciones que vuelven al check-in, la recarga que sigue en él,
// la salida con contraseña, la tiquetera de 10 clases (10 → 9 → 10) y que nunca sale una petición a /reveal. axe en cada paso.
// La inactividad de 10 minutos la cubre la prueba unitaria de GymShell (no se espera en el stack).
// Necesita C1 a C4, la cuenta del admin del seed (E2E_ADMIN_EMAIL y E2E_ADMIN_PASSWORD) y crea su propio coach. Sin E2E_BASE_URL se omite. Corre en V5.
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import {
  borrarUsuario,
  congelarPorApi,
  crearCoach,
  crearPlan,
  crearSocio,
  darDeBajaSocio,
  esperarTransiciones,
  fechaBogota,
  loginComo,
  sameOriginHeaders,
  venderMembresia,
  venderMembresiaDesde,
  type CoachCreado,
  type SocioCreado,
} from "../helpers/stack";

const ON_STACK = process.env.E2E_BASE_URL !== undefined;
const TAGS = ["wcag2a", "wcag2aa", "wcag21aa"];
const API = "/api/v1";
const CHECKIN = /\/clases\/[^/]+\/checkin$/;

async function axeViolations(page: Page): Promise<string[]> {
  await esperarTransiciones(page);
  const result = await new AxeBuilder({ page }).withTags(TAGS).analyze();
  return result.violations.map(
    (v) =>
      `${v.id}: ${v.help} -> ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`,
  );
}

interface SesionCreada {
  id: string;
  name: string;
  /** HH:MM de Bogotá. */
  hora: string;
}

const MS_MINUTO = 60_000;
const BOGOTA_OFFSET_MS = 5 * 60 * 60 * 1_000;

/** Ahora más `minutos`, redondeado al minuto (V7 M-2: las sesiones de hoy quedan a futuro y siguen «programadas»). */
const ahoraMas = (minutos: number): Date =>
  new Date(Math.floor((Date.now() + minutos * MS_MINUTO) / MS_MINUTO) * MS_MINUTO);

/** El día civil de Bogotá de un instante ("AAAA-MM-DD"). */
const diaBogota = (instante: Date): string =>
  new Date(instante.getTime() - BOGOTA_OFFSET_MS).toISOString().slice(0, 10);

/** La hora de Bogotá de un instante ("HH:MM"), como la rotula el selector «Clases de hoy». */
const horaBogota = (instante: Date): string =>
  new Date(instante.getTime() - BOGOTA_OFFSET_MS).toISOString().slice(11, 16);

/** Un día de Bogotá a las 17:MM, con MM del reloj: dos corridas no chocan por la misma hora (409 session_duplicate). */
const diaALas17 = (dias: number): Date => {
  const minuto = String(new Date().getMinutes()).padStart(2, "0");
  return new Date(`${fechaBogota(dias)}T17:${minuto}:00-05:00`);
};

/** Sesión extra por el api (POST /class-sessions, S7-D11) en el instante dado (V7 HIGH-1: un instante distinto por sesión y por corrida). */
async function crearSesion(
  page: Page,
  token: string,
  inicio: Date,
  capacity: number,
  marca: string,
): Promise<SesionCreada> {
  const headers = { Authorization: `Bearer ${token}`, ...sameOriginHeaders() };
  const name = `E2E ${String(Date.now())}-${marca}`;
  const response = await page.request.post(`${API}/class-sessions`, {
    headers,
    data: {
      starts_at: inicio.toISOString(),
      duration_min: 60,
      capacity,
      name,
    },
  });
  if (!response.ok())
    throw new Error(
      `POST /class-sessions respondió ${String(response.status())}.`,
    );
  return { ...((await response.json()) as { id: string }), name, hora: horaBogota(inicio) };
}

async function clasesQuedan(
  page: Page,
  token: string,
  socioId: string,
): Promise<number | null> {
  const response = await page.request.get(
    `${API}/members/${socioId}/memberships`,
    { headers: { Authorization: `Bearer ${token}` } },
  );
  const body = (await response.json()) as {
    items: { classes_remaining: number | null }[];
  };
  return body.items[0]?.classes_remaining ?? null;
}

async function buscar(page: Page, nombre: string): Promise<void> {
  await page.getByRole("searchbox", { name: "Buscar socio" }).fill(nombre);
  await expect(
    page.getByRole("list", { name: "Socios encontrados" }),
  ).toBeVisible();
}

/** Busca al socio y toca «Llegó» o «Llegó igual»; espera a que figure en «Asistentes». */
async function llegar(page: Page, socio: SocioCreado): Promise<void> {
  await buscar(page, socio.nombre);
  await page
    .getByRole("list", { name: "Socios encontrados" })
    .getByRole("button", { name: /^Llegó/ })
    .click();
  await expect(
    page.getByRole("list", { name: "Asistentes" }).getByText(socio.nombre),
  ).toBeVisible();
}

function filaAsistente(page: Page, socio: SocioCreado) {
  return page
    .getByRole("list", { name: "Asistentes" })
    .getByRole("listitem")
    .filter({ hasText: socio.nombre });
}

test.describe("check-in en modo tablet contra el stack", () => {
  test.skip(!ON_STACK, "solo contra el stack (E2E_BASE_URL) con C1 a C4");

  const socios: SocioCreado[] = [];
  test.afterEach(async ({ page }) => {
    for (const socio of socios.splice(0)) await darDeBajaSocio(page, socio.id);
  });

  test("siete banderas, 409, atrás y recarga vuelven al check-in, tiquetera y salida con contraseña", async ({
    page,
  }) => {
    // V7 M-2: las clases de hoy empiezan dentro de 2 y 2,5 horas; pasadas las 21:00 de Bogotá cruzarían la medianoche.
    test.skip(
      diaBogota(ahoraMas(150)) !== fechaBogota(0),
      "después de las 21:00 de Bogotá las clases de hoy no caben en el día",
    );
    await page.setViewportSize({ width: 1024, height: 768 });
    const adminToken = await loginComo(page);
    const llamadas: string[] = [];
    page.on("request", (request) =>
      llamadas.push(new URL(request.url()).pathname),
    );

    // Datos de las siete banderas (todo con la cuenta del admin; el coach entra al final).
    const alDia = await crearSocio(page);
    const vencido = await crearSocio(page);
    const sinPlan = await crearSocio(page);
    const congelado = await crearSocio(page);
    const pendiente = await crearSocio(page);
    const tiquetera = await crearSocio(page);
    socios.push(alDia, vencido, sinPlan, congelado, pendiente, tiquetera);
    const plan = await crearPlan(page);
    await venderMembresia(page, alDia.id, plan.id, {
      amount_cop: plan.precio,
      method: "cash",
    });
    await venderMembresiaDesde(page, vencido.id, plan.id, fechaBogota(-60), {
      amount_cop: plan.precio,
      method: "cash",
    });
    const aCongelar = await venderMembresiaDesde(
      page,
      congelado.id,
      plan.id,
      fechaBogota(-7),
      { amount_cop: plan.precio, method: "cash" },
    );
    expect(
      await congelarPorApi(page, aCongelar.id, fechaBogota(0), fechaBogota(5)),
    ).toBe(200);
    expect((await venderMembresia(page, pendiente.id, plan.id)).status).toBe(
      "pending_payment",
    );
    const diez = await page.request.post(`${API}/plans`, {
      headers: {
        Authorization: `Bearer ${adminToken}`,
        ...sameOriginHeaders(),
      },
      data: {
        name: `0 E2E diez ${String(Date.now())}`,
        price_cop: 150_000,
        kind: "classes",
        duration_days: 60,
        class_count: 10,
      },
    });
    const planDiez = (await diez.json()) as { id: string };
    await venderMembresia(page, tiquetera.id, planDiez.id, {
      amount_cop: 150_000,
      method: "cash",
    });
    // Hoy con cupo 3 (el cuarto llega con «Cupo lleno»), ayer (fuera de horario) y dentro de 7 días (otro día).
    const hoy = await crearSesion(page, adminToken, ahoraMas(120), 3, "hoy");
    const ayer = await crearSesion(page, adminToken, diaALas17(-1), 12, "ayer");
    const otroDia = await crearSesion(page, adminToken, diaALas17(7), 12, "mas7");
    // Otra clase de hoy para el selector «Clases de hoy» (S7-D42), media hora después.
    const hoyOtra = await crearSesion(page, adminToken, ahoraMas(150), 12, "hoy-b");
    const sesiones = [hoy, ayer, otroDia, hoyOtra];

    // La tablet usa una cuenta de coach propia.
    const coach: CoachCreado = await crearCoach(page);
    const asistenciasExtra: string[] = [];
    try {
      const coachToken = await loginComo(page, coach);

      // Se entra por la pantalla (con clic) para que «atrás» pase por el router: Clases de hoy → sesión → Abrir check-in.
      await page.goto("/clases?dia=hoy");
      await page.getByText(hoy.name).first().click();
      const kioskRespuesta = page.waitForResponse(
        (r) =>
          r.request().method() === "POST" &&
          new URL(r.url()).pathname === `${API}/auth/kiosk`,
      );
      await page.getByRole("link", { name: "Abrir check-in" }).click();
      await expect(page).toHaveURL(CHECKIN);
      const kioskAccess = (
        (await (await kioskRespuesta).json()) as { access_token: string }
      ).access_token;
      await expect(page.getByRole("heading", { level: 1 })).toContainText(
        "Check-in",
      );
      // Modo tablet: ningún enlace al panel.
      await expect(page.getByRole("link")).toHaveCount(0);
      expect(await axeViolations(page)).toEqual([]);

      // Banderas de membresía: vencido, sin plan, congelado y pendiente de pago entran igual y quedan marcados.
      await llegar(page, alDia);
      await llegar(page, vencido);
      await expect(
        filaAsistente(page, vencido).getByText("Vencido"),
      ).toBeVisible();
      await llegar(page, sinPlan);
      await expect(
        filaAsistente(page, sinPlan).getByText("Sin plan"),
      ).toBeVisible();
      // Cupo lleno: con tres dentro, el cuarto llega con la bandera «Cupo lleno» (y la de su estado).
      await llegar(page, congelado);
      await expect(
        filaAsistente(page, congelado).getByText("Congelado"),
      ).toBeVisible();
      await expect(
        filaAsistente(page, congelado).getByText("Cupo lleno"),
      ).toBeVisible();
      await llegar(page, pendiente);
      await expect(
        filaAsistente(page, pendiente).getByText("Pendiente de pago"),
      ).toBeVisible();
      expect(await axeViolations(page)).toEqual([]);

      // 409 already_checked_in: el mismo registro repetido por el api.
      const headers = {
        Authorization: `Bearer ${coachToken}`,
        ...sameOriginHeaders(),
      };
      const repetido = await page.request.post(`${API}/attendance`, {
        headers,
        data: { session_id: hoy.id, member_id: alDia.id },
      });
      expect(repetido.status()).toBe(409);
      expect(
        ((await repetido.json()) as { error: { code: string } }).error.code,
      ).toBe("already_checked_in");
      // En pantalla el socio que ya llegó no se puede registrar otra vez.
      await buscar(page, alDia.nombre);
      await expect(
        page.getByRole("button", { name: "Ya llegó" }),
      ).toBeDisabled();

      // Tiquetera: 10 → 9 al registrar → 10 al quitar.
      expect(await clasesQuedan(page, adminToken, tiquetera.id)).toBe(10);
      await llegar(page, tiquetera);
      expect(await clasesQuedan(page, adminToken, tiquetera.id)).toBe(9);
      await page
        .getByRole("button", { name: `Quitar a ${tiquetera.nombre}` })
        .click();
      await page
        .getByRole("dialog")
        .getByRole("button", { name: "Quitar asistencia" })
        .click();
      await expect(page.getByRole("dialog")).toHaveCount(0);
      expect(await clasesQuedan(page, adminToken, tiquetera.id)).toBe(10);

      // S7-D42: el selector «Clases de hoy» pasa a otra clase de hoy sin contraseña y deja volver; el servidor mantiene la marca.
      const selector = page.getByRole("combobox", { name: "Clases de hoy" });
      await selector.selectOption({ label: `${hoyOtra.hora} · ${hoyOtra.name}` });
      await page.getByRole("button", { name: "Cambiar de clase" }).click();
      await expect(page).toHaveURL(`/clases/${hoyOtra.id}/checkin`);
      await expect(page.getByRole("link")).toHaveCount(0);
      await selector.selectOption({ label: `${hoy.hora} · ${hoy.name}` });
      await page.getByRole("button", { name: "Cambiar de clase" }).click();
      await expect(page).toHaveURL(CHECKIN);
      // La clase de dentro de 7 días no es de hoy: POST /auth/kiosk responde 403 kiosk_mode y la marca sigue.
      const rechazo = await page.request.post(`${API}/auth/kiosk`, {
        headers: { Authorization: `Bearer ${coachToken}`, ...sameOriginHeaders() },
        data: { path: `/clases/${otroDia.id}/checkin` },
      });
      expect(rechazo.status()).toBe(403);
      expect(((await rechazo.json()) as { error: { code: string } }).error.code).toBe("kiosk_mode");

      // La marca es de esta sesión de clase: las de ayer y de dentro de 7 días se prueban por el api (otra sesión exige salir del modo).
      for (const [sesion, bandera] of [
        [ayer, "out_of_window"],
        [otroDia, "other_day"],
      ] as const) {
        // V7 M-3: con el admin; el access del coach ya es el del quiosco y no depende del residuo de 15 minutos del access previo.
        const respuesta = await page.request.post(`${API}/attendance`, {
          headers: { Authorization: `Bearer ${adminToken}`, ...sameOriginHeaders() },
          data: { session_id: sesion.id, member_id: alDia.id },
        });
        expect(respuesta.status()).toBe(201);
        const creada = (await respuesta.json()) as {
          id: string;
          flags: string[];
        };
        asistenciasExtra.push(creada.id);
        expect(creada.flags).toContain(bandera);
      }

      // Defensa real: con el access del quiosco el servidor niega revelar datos (403 kiosk_mode), aunque se pida a mano.
      const reveal = await page.request.post(
        `${API}/members/${alDia.id}/reveal`,
        {
          headers: {
            Authorization: `Bearer ${kioskAccess}`,
            ...sameOriginHeaders(),
          },
          data: {},
        },
      );
      expect(reveal.status()).toBe(403);
      expect(
        ((await reveal.json()) as { error: { code: string } }).error.code,
      ).toBe("kiosk_mode");

      // «Atrás» pasa por el router: abre el diálogo de salida y el check-in sigue en pantalla; la barra de direcciones y la recarga también vuelven.
      await page.goBack();
      const salida = page.getByRole("dialog", {
        name: "¿Salir del modo tablet?",
      });
      await expect(salida).toBeVisible();
      await expect(page).toHaveURL(CHECKIN);
      await salida.getByRole("button", { name: "Volver" }).click();
      await expect(salida).toHaveCount(0);
      await expect(page.getByRole("link")).toHaveCount(0);
      await page.goto("/socios");
      await expect(page).toHaveURL(CHECKIN);
      await page.reload();
      await expect(page).toHaveURL(CHECKIN);
      await expect(page.getByRole("link")).toHaveCount(0);
      // La tablet nunca revela datos cifrados ni lee la ficha desde la pantalla.
      expect(llamadas.filter((ruta) => ruta.includes("/reveal"))).toEqual([]);

      // Salir del modo tablet exige la contraseña del coach.
      await page.getByRole("button", { name: "Clases" }).click();
      const dialogo = page.getByRole("dialog", {
        name: "¿Salir del modo tablet?",
      });
      await dialogo.getByLabel(/Contraseña/).fill("contraseña-equivocada");
      await dialogo
        .getByRole("button", { name: "Salir del modo tablet" })
        .click();
      await expect(dialogo.getByRole("alert")).toContainText(
        "Contraseña incorrecta",
      );
      await dialogo.getByLabel(/Contraseña/).fill(coach.password);
      await dialogo
        .getByRole("button", { name: "Salir del modo tablet" })
        .click();
      await expect(page).toHaveURL(/\/clases$/);
      // Ya sin la marca, la barra de direcciones deja ir al panel.
      await page.goto("/socios");
      await expect(page).toHaveURL(/\/socios$/);
    } finally {
      await borrarUsuario(page, coach.id);
      // V7 M-3: el access del admin tiene 15 minutos; se renueva antes de limpiar.
      const limpieza = {
        Authorization: `Bearer ${await loginComo(page)}`,
        ...sameOriginHeaders(),
      };
      // LOW-3: las asistencias de ayer y de +7 días se quitan con el admin; el coach solo puede quitar las de hoy o ayer.
      for (const id of asistenciasExtra)
        await page.request.delete(`${API}/attendance/${id}`, {
          headers: limpieza,
          data: { reason: "limpieza E2E" },
        });
      // V7 HIGH-1: las cuatro sesiones se cancelan para que la siguiente corrida no choque (la de ayer ya terminó: el api puede negarlo).
      for (const sesion of sesiones)
        await page.request.post(`${API}/class-sessions/${sesion.id}/cancel`, {
          headers: limpieza,
          data: { reason: "limpieza E2E" },
        });
    }
  });
});
