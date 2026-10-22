// US-061 T1: el menú lateral sale de una función pura filtrada por can() y por las
// features habilitadas (criterios 1 a 3).
import { ENABLED_FEATURES, FEATURES, type Feature } from "../config/features";
import { ACTIONS } from "../core/auth";
import { NAV_CATALOG, buildNavItems, type NavGroup } from "./nav";

const labels = (groups: NavGroup[]): string[] => groups.flatMap((g) => g.items.map((i) => i.label));
const ALL: ReadonlySet<Feature> = new Set(FEATURES);

describe("buildNavItems", () => {
  it("admin con las features del Sprint 2 ve Inicio, Socios, Planes, Usuarios y Configuración", () => {
    const groups = buildNavItems("admin", ENABLED_FEATURES);

    expect(labels(groups)).toEqual(["Inicio", "Socios", "Planes", "Usuarios y roles", "Configuración"]);
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

  it("cada entrada del catálogo declara una acción de la matriz y una feature conocida", () => {
    expect(NAV_CATALOG.length).toBeGreaterThan(0);
    for (const item of NAV_CATALOG) {
      expect(ACTIONS).toContain(item.action);
      expect(FEATURES).toContain(item.feature);
      expect(item.to.startsWith("/")).toBe(true);
    }
  });
});
