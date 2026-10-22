// US-062 T5: página de muestra de los cuatro layouts con contenido de ejemplo. Solo se sirve
// en catalog.html (`npm run build:catalog`), nunca en el build de producción.
// Parámetros: ?vista=panel|portal|gym|tv, &rol=admin|coach (panel), &tema=light|dark (panel).
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router";
import { FEATURES } from "../config/features";
import { ROLE_LABELS, ROLES, type Role } from "../core/auth";
import { GymLayout } from "../layouts/GymLayout";
import { buildNavItems } from "../layouts/nav";
import { PanelLayout } from "../layouts/PanelLayout";
import { PortalLayout } from "../layouts/PortalLayout";
import { TvLayout } from "../layouts/TvLayout";
import { useForcedTheme, type ForcedTheme } from "../shared/hooks/useForcedTheme";
import { Button } from "../shared/ui/Button";
import { StatusTag } from "../shared/ui/StatusTag";
import styles from "./preview.module.css";

export const VIEWS = ["panel", "portal", "gym", "tv"] as const;
export type PreviewView = (typeof VIEWS)[number];

const ALL_FEATURES = new Set(FEATURES);

export interface PreviewParams {
  view: PreviewView | null;
  role: Role;
  theme: "light" | "dark";
}

export function readPreviewParams(search: string): PreviewParams {
  const params = new URLSearchParams(search);
  const view = VIEWS.find((v) => v === params.get("vista")) ?? null;
  const role = ROLES.find((r) => r === params.get("rol")) ?? ROLES[0];
  const theme = params.get("tema") === "dark" ? "dark" : "light";
  return { view, role, theme };
}

function PanelSample({ role, theme }: { role: Role; theme: ForcedTheme }) {
  useForcedTheme(theme);
  return (
    <MemoryRouter initialEntries={["/socios"]}>
      <PanelLayout
        user={{ email: `${role}@apex.test`, roleLabel: ROLE_LABELS[role] }}
        gymName="Box de muestra"
        navGroups={buildNavItems(role, ALL_FEATURES)}
        onChangePassword={() => undefined}
        onLogout={() => undefined}
      >
        <div className={styles.stack}>
          <h1 className={styles.screenTitle}>Socios</h1>
          <p>Contenido de ejemplo dentro del panel. La lista real llega con su pantalla.</p>
          <div className={styles.row}>
            <Button>Nuevo socio</Button>
            <Button variant="secondary">Exportar</Button>
            <StatusTag status="active" />
            <StatusTag status="expiring" />
          </div>
        </div>
      </PanelLayout>
    </MemoryRouter>
  );
}

function PortalSample() {
  return (
    <MemoryRouter initialEntries={["/mi"]}>
      <PortalLayout gymName="Box de muestra">
        <div className={styles.stack}>
          <h1 className={styles.greeting}>Hola, Laura</h1>
          {["Mi plan", "WOD de hoy", "Este mes", "Próxima clase"].map((title) => (
            <section key={title} className={styles.card} aria-label={title}>
              <h2 className={styles.cardTitle}>{title}</h2>
              <p>Bloque de ejemplo del portal.</p>
            </section>
          ))}
          <p className={styles.card}>Último bloque del contenido</p>
        </div>
      </PortalLayout>
    </MemoryRouter>
  );
}

function GymSample() {
  return (
    <MemoryRouter>
      <GymLayout title="Check-in · 17:00 · Coach María" subtitle="Martes 20 de octubre · cupo 12" exitTo="/clases" exitLabel="Clases">
        <div className={styles.row}>
          <Button>Llegó</Button>
          <Button variant="secondary">Llegó igual</Button>
          <StatusTag status="expired" />
        </div>
      </GymLayout>
    </MemoryRouter>
  );
}

function TvSample() {
  return (
    <TvLayout>
      <p className={styles.tvLabel}>WOD del día</p>
      <p className={styles.tvTitle}>Helen</p>
      <p>3 rondas por tiempo: run 400 m · 21 KB swing · 12 pull-up</p>
    </TvLayout>
  );
}

function Index() {
  const links: readonly [string, string][] = [
    ["Panel (admin)", "?vista=panel&rol=admin"],
    ["Panel (coach)", "?vista=panel&rol=coach"],
    ["Panel en oscuro", "?vista=panel&rol=admin&tema=dark"],
    ["Portal", "?vista=portal"],
    ["Tablet del box", "?vista=gym"],
    ["TV", "?vista=tv"],
  ];
  return (
    <main className={styles.index}>
      <h1 className={styles.screenTitle}>Layouts de muestra</h1>
      <ul>
        {links.map(([label, href]) => (
          <li key={href}>
            <a href={href}>{label}</a>
          </li>
        ))}
      </ul>
    </main>
  );
}

export function LayoutsPreview({ search = window.location.search }: { search?: string }): ReactNode {
  const { view, role, theme } = readPreviewParams(search);
  if (view === "panel") return <PanelSample role={role} theme={theme} />;
  if (view === "portal") return <PortalSample />;
  if (view === "gym") return <GymSample />;
  if (view === "tv") return <TvSample />;
  return <Index />;
}
