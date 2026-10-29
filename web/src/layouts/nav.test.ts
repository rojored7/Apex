// US-061 T1: el menú lateral sale de una función pura filtrada por can() y por las
// features habilitadas (criterios 1 a 3).
import { ENABLED_FEATURES, FEATURES, type Feature } from "../config/features";
import { canAccessRoute, findRoute } from "../core/auth/routeAccess";
import { NAV_CATALOG, buildNavItems, type NavGroup } from "./nav";

const labels = (groups: NavGroup[]): string[] => groups.flatMap((g) => g.items.map((i) => i.label));
const ALL: ReadonlySet<Feature> = new Set(FEATURES);

describe("buildNavItems", () => {
  it("admin con las features habilitadas ve Inicio, Socios, Membresías (S3-F3), Pagos (S3-F4), Planes, Usuarios, Auditoría (S4A-F1) y Configuración", () => {
    const groups = buildNavItems("admin", ENABLED_FEATURES);

    expect(labels(groups)).toEqual(["Inicio", "Socios", "Membresías", "Pagos", "Planes", "Usuarios y roles", "Auditoría", "Configuración"]);
    expect(groups.map((g) => g.id)).toEqual(["inicio", "gestion", "sistema"]);
    expect(groups.find((g) => g.id === "sistema")?.title).toBe("Sistema");
    expect(groups.find((g) => g.id === "inicio")?.title).toBeNull();
  });

  it("coach no ve Planes ni ninguna entrada de Sistema", () => {
    const groups = buildNavItems("coach", ALL);

    expect(labels(groups)).not.toContain("Planes");
    expect(groups.some((g) => g.id === "sistema")).toBe(false);
    for (const label of ["Usuarios y roles", "Auditoría", "Llaves de cifrado", "Configuración"]) {
      expect(labels(groups)).not.toContain(label);
    }
    expect(labels(groups)).toContain("Socios");
  });

  it("member y sin rol dan una lista vacía (el socio usa PortalLayout)", () => {
    expect(buildNavItems("member", ALL)).toEqual([]);
    expect(buildNavItems(null, ALL)).toEqual([]);
  });

  it("con todas las features el admin ve el catálogo completo en el orden de DESIGN.md", () => {
    const groups = buildNavItems("admin", ALL);

    expect(groups.map((g) => g.title)).toEqual([null, "Hoy", "Gestión", "Entrenamiento", "Avisos", "Sistema"]);
    expect(labels(groups)).toEqual([
      "Inicio",
      "Clases de hoy",
      "WOD de hoy",
      "Por avisar hoy",
      "Socios",
      "Membresías",
      "Pagos",
      "Planes",
      "Clases",
      "WODs",
      "Movimientos",
      "Reglas y plantillas",
      "Historial de envíos",
      "Usuarios y roles",
      "Auditoría",
      "Llaves de cifrado",
      "Configuración",
    ]);
  });

  it("una feature no habilitada no aparece: con classes aparece Clases y el grupo Hoy necesita las tres", () => {
    const base = new Set<Feature>([...ENABLED_FEATURES, "classes"]);

    expect(labels(buildNavItems("admin", base))).toContain("Clases");
    expect(labels(buildNavItems("admin", base))).not.toContain("Clases de hoy");
    expect(buildNavItems("admin", ENABLED_FEATURES).some((g) => g.id === "hoy")).toBe(false);
  });

  it("el grupo Hoy son tres enlaces a pantallas existentes y no hay ninguna ruta /hoy (Q25)", () => {
    const enabled = new Set<Feature>([...ENABLED_FEATURES, "classes", "wods", "notifications"]);
    const hoy = buildNavItems("coach", enabled).find((g) => g.id === "hoy");

    expect(hoy?.items.map((i) => i.to)).toEqual(["/clases?dia=hoy", "/wods?dia=hoy", "/avisos/hoy"]);
    expect(NAV_CATALOG.some((i) => i.to === "/hoy" || i.to.startsWith("/hoy?"))).toBe(false);
  });

  it("los grupos vacíos se omiten", () => {
    const groups = buildNavItems("coach", new Set<Feature>(["dashboard"]));

    expect(groups).toHaveLength(1);
    expect(groups[0]?.items.map((i) => i.label)).toEqual(["Inicio"]);
  });

  it("cada entrada del catálogo apunta a una ruta de la tabla con su misma feature (S2-F2)", () => {
    expect(NAV_CATALOG.length).toBeGreaterThan(0);
    for (const item of NAV_CATALOG) {
      const route = findRoute(item.to);
      expect(route, item.to).not.toBeNull();
      expect(route?.feature).toBe(item.feature);
      expect(FEATURES).toContain(item.feature);
    }
  });

  it("filtra con canAccessRoute: la visibilidad sigue al acceso de la ruta", () => {
    const enabled = new Set<Feature>(FEATURES);
    for (const role of ["admin", "coach", "member"] as const) {
      const visible = new Set(labels(buildNavItems(role, enabled)));
      for (const item of NAV_CATALOG) expect(visible.has(item.label)).toBe(canAccessRoute(role, item.to));
    }
  });
});

describe("menú y rutas hijas (S3-F3, E14)", () => {
  it("el coach también ve Membresías y Pagos con las features habilitadas (memberships.view y payments.view son de admin y coach)", () => {
    expect(labels(buildNavItems("coach", ENABLED_FEATURES))).toEqual(["Inicio", "Socios", "Membresías", "Pagos"]);
  });

  it("S3-F4: Pagos lleva a /pagos con la feature payments", () => {
    const pagos = NAV_CATALOG.find((item) => item.label === "Pagos");

    expect(pagos).toMatchObject({ to: "/pagos", feature: "payments", group: "gestion" });
    expect(labels(buildNavItems("admin", new Set<Feature>([...ENABLED_FEATURES].filter((f) => f !== "payments"))))).not.toContain("Pagos");
  });

  it("NAV_CATALOG es estático y no tiene entradas con parámetros (:)", () => {
    expect(NAV_CATALOG.filter((item) => item.to.includes(":")).map((item) => item.to)).toEqual([]);
  });
});

describe("Auditoría en el menú (S4A-F1, S4A-D30)", () => {
  it("lleva a /sistema/auditoria con la feature audit, entre Usuarios y roles y Configuración, solo para el admin", () => {
    const auditoria = NAV_CATALOG.find((item) => item.label === "Auditoría");
    const admin = labels(buildNavItems("admin", ENABLED_FEATURES));

    expect(auditoria).toMatchObject({ to: "/sistema/auditoria", feature: "audit", group: "sistema" });
    expect(admin.slice(admin.indexOf("Usuarios y roles"))).toEqual(["Usuarios y roles", "Auditoría", "Configuración"]);
    expect(labels(buildNavItems("coach", ENABLED_FEATURES))).not.toContain("Auditoría");
    expect(canAccessRoute("coach", "/sistema/auditoria")).toBe(false);
    expect(findRoute("/sistema/auditoria")?.access).toBe("audit.view");
  });
});
