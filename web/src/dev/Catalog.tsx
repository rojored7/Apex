// US-068 T5: catálogo del kit (catalog.html, `npm run build:catalog`; fuera del build de
// producción y de la imagen de Nginx). Los 16 componentes de DESIGN.md en sus estados (carga,
// vacío, error, deshabilitado, abierto) y enlaces a los cuatro layouts de muestra. Lo recorren
// tests/e2e/kit.spec.ts (axe, desborde y capturas en claro y oscuro) y src/dev/Catalog.test.tsx.
// Parámetros: ?tema=light|dark fija el tema inicial; ?vista=... muestra un layout (LayoutsPreview).
// S2-F4a: StatusTag también con los cinco estados de cuenta de usuario (S2-D24).
import { useState, type ReactNode } from "react";
import { MemoryRouter } from "react-router";
import { FEATURES } from "../config/features";
import { RoleProvider } from "../core/auth";
import { setTheme, usePanelTheme, type Theme } from "../core/theme/theme";
import { ThemeToggle } from "../core/theme/ThemeToggle";
import { buildNavItems } from "../layouts/nav";
import type { AuditEntryView } from "../shared/lib/audit-labels";
import { Button } from "../shared/ui/Button";
import { Chips } from "../shared/ui/Chips";
import { ConfirmModal } from "../shared/ui/ConfirmModal";
import { DataTable, type Column } from "../shared/ui/DataTable";
import { Field } from "../shared/ui/Field";
import { FilterBar } from "../shared/ui/FilterBar";
import { HistoryAside } from "../shared/ui/HistoryAside";
import { KpiCard } from "../shared/ui/KpiCard";
import { MaskedValue } from "../shared/ui/MaskedValue";
import { PageHeader } from "../shared/ui/PageHeader";
import { Pagination } from "../shared/ui/Pagination";
import { SideNav } from "../shared/ui/SideNav";
import { SidePanel } from "../shared/ui/SidePanel";
import { ACCOUNT_LABELS, STATUS_LABELS, type AccountStatusView, type MembershipStatusView } from "../shared/ui/statusLabel";
import { StatusTag } from "../shared/ui/StatusTag";
import { Tabs } from "../shared/ui/Tabs";
import { TopBar } from "../shared/ui/TopBar";
import { LayoutsPreview, readPreviewParams } from "./LayoutsPreview";
import styles from "./preview.module.css";

export const KIT_COMPONENTS = [
  "TopBar",
  "SideNav",
  "PageHeader",
  "Button",
  "StatusTag",
  "FilterBar",
  "DataTable",
  "Pagination",
  "Chips",
  "Tabs",
  "KpiCard",
  "SidePanel",
  "ConfirmModal",
  "Field",
  "MaskedValue",
  "HistoryAside",
] as const;

interface MemberRow {
  id: string;
  name: string;
  status: MembershipStatusView;
}

const ROWS: MemberRow[] = [
  { id: "1", name: "Laura Gómez", status: "active" },
  { id: "2", name: "Camila Torres", status: "expired" },
  { id: "3", name: "Andrés Ruiz", status: "expiring" },
];

const COLUMNS: Column<MemberRow>[] = [
  { key: "name", header: "Nombre", render: (row) => row.name, sortable: true },
  { key: "status", header: "Estado", render: (row) => <StatusTag status={row.status} /> },
];

const HISTORY: AuditEntryView[] = [
  { id: "h1", at: "2026-10-20T19:32:00Z", actor_id: "u1", actor_name: "Ana P.", entity: "members", action: "update", before: { phone: "apx1.k.A256GCM.a.b" }, after: { phone: "apx1.k.A256GCM.c.d" } },
  { id: "h2", at: "2026-10-19T14:05:00Z", actor_id: "u1", actor_name: "Ana P.", entity: "members", action: "insert", before: null, after: { first_name: "Laura" } },
];

const noop = (): void => undefined;

function Section({ name, children }: { name: string; children: ReactNode }) {
  const id = `kit-${name}`;
  return (
    <section className={styles.card} aria-labelledby={id}>
      <h2 id={id} className={styles.cardTitle}>
        {name}
      </h2>
      <div className={styles.stack}>{children}</div>
    </section>
  );
}

function Dialogs() {
  const [panel, setPanel] = useState(false);
  const [modal, setModal] = useState(false);
  return (
    <>
      <Section name="SidePanel">
        <Button
          variant="secondary"
          onClick={() => {
            setPanel(true);
          }}
        >
          Abrir panel lateral
        </Button>
        <SidePanel
          open={panel}
          title="Nuevo plan"
          onClose={() => {
            setPanel(false);
          }}
          footer={<Button>Guardar</Button>}
        >
          <Field label="Nombre del plan" name="plan" />
        </SidePanel>
      </Section>
      <Section name="ConfirmModal">
        <Button
          variant="danger"
          onClick={() => {
            setModal(true);
          }}
        >
          Abrir modal de confirmación
        </Button>
        <ConfirmModal
          open={modal}
          title="¿Anular este pago?"
          consequence="El pago queda anulado con su motivo y no se puede editar."
          confirmLabel="Anular pago"
          reasonRequired
          onConfirm={() => {
            setModal(false);
          }}
          onClose={() => {
            setModal(false);
          }}
        />
      </Section>
    </>
  );
}

function ListSamples() {
  const [query, setQuery] = useState("");
  const [chips, setChips] = useState<string[]>(["all"]);
  return (
    <>
      <Section name="FilterBar">
        <FilterBar
          query={query}
          onQueryChange={setQuery}
          onClear={() => {
            setQuery("");
          }}
          selects={[{ name: "plan", label: "Plan", value: "", options: [{ value: "mensual", label: "Mensual" }] }]}
          onSelectChange={noop}
          sort={{ value: "name", options: [{ value: "name", label: "Nombre" }], onChange: noop }}
        />
      </Section>
      <Section name="DataTable">
        <DataTable caption="Socios de muestra" columns={COLUMNS} rows={ROWS} total={3} rowKey={(r) => r.id} rowHref={(r) => `/socios/${r.id}`} />
        <DataTable caption="Socios cargando" columns={COLUMNS} rows={undefined} isLoading limit={3} rowKey={(r) => r.id} rowHref={(r) => `/socios/${r.id}`} />
        <DataTable caption="Socios sin resultados" columns={COLUMNS} rows={[]} total={0} emptyMessage="No hay socios con esos filtros." rowKey={(r) => r.id} rowHref={(r) => `/socios/${r.id}`} />
        <DataTable caption="Socios con error" columns={COLUMNS} rows={undefined} error={new Error("x")} onRetry={noop} rowKey={(r) => r.id} rowHref={(r) => `/socios/${r.id}`} />
      </Section>
      <Section name="Pagination">
        <Pagination total={312} limit={25} offset={100} onPageChange={noop} onLimitChange={noop} />
      </Section>
      <Section name="Chips">
        <Chips
          label="Estado"
          mode="single"
          value={chips}
          onChange={setChips}
          options={[
            { value: "all", label: "Todos", count: 342 },
            { value: "expiring", label: "Por vencer", count: 18, tone: "warning" },
            { value: "expired", label: "Vencidos", count: 41, tone: "danger" },
          ]}
        />
      </Section>
    </>
  );
}

export function Catalog() {
  usePanelTheme();
  const groups = buildNavItems("admin", new Set(FEATURES));
  return (
    <RoleProvider value="admin">
      <MemoryRouter initialEntries={["/socios"]}>
        <main className={styles.index}>
          <div className={styles.stack}>
            <div className={styles.row}>
              <h1 className={styles.screenTitle}>Kit de componentes</h1>
              <ThemeToggle />
            </div>
            <nav aria-label="Layouts de muestra">
              <ul className={styles.linkList}>
                <li><a href="?vista=panel&rol=admin">Panel (admin)</a></li>
                <li><a href="?vista=panel&rol=coach">Panel (coach)</a></li>
                <li><a href="?vista=portal">Portal</a></li>
                <li><a href="?vista=gym">Tablet del box</a></li>
                <li><a href="?vista=tv">TV</a></li>
              </ul>
            </nav>
            <Section name="TopBar">
              <TopBar user={{ email: "ana@apex.test", roleLabel: "Admin" }} gymName="Box de muestra" onChangePassword={noop} onLogout={noop} />
              <TopBar user={{ email: "carlos@apex.test", roleLabel: "Coach" }} logoutPending onLogout={noop} />
            </Section>
            <Section name="SideNav">
              <div className={styles.navSample}>
                <SideNav groups={groups} />
              </div>
            </Section>
            <Section name="PageHeader">
              <PageHeader
                title="Socios"
                total="342 en total · 269 con membresía"
                breadcrumbs={[{ label: "Inicio", href: "/" }, { label: "Socios" }]}
                actions={[
                  { id: "nuevo", label: "Nuevo socio", href: "/socios/nuevo", variant: "primary" },
                  { id: "vender", label: "Vender membresía", onClick: noop },
                  { id: "pago", label: "Registrar pago", onClick: noop },
                  { id: "exportar", label: "Exportar", onClick: noop },
                ]}
              />
            </Section>
            <Section name="Button">
              <div className={styles.row}>
                <Button>Principal</Button>
                <Button variant="secondary">Secundario</Button>
                <Button variant="danger">Dar de baja</Button>
                <Button variant="ghost">Fantasma</Button>
                <Button size="lg">Llegó</Button>
                <Button loading>Guardando</Button>
                <Button disabled>Deshabilitado</Button>
              </div>
            </Section>
            <Section name="StatusTag">
              <div className={styles.row}>
                {(Object.keys(STATUS_LABELS) as MembershipStatusView[]).map((status) => (
                  <StatusTag key={status} status={status} />
                ))}
              </div>
              <div className={styles.row}>
                {(Object.keys(ACCOUNT_LABELS) as AccountStatusView[]).map((account) => (
                  <StatusTag key={account} account={account} />
                ))}
              </div>
            </Section>
            <ListSamples />
            <Section name="Tabs">
              <Tabs label="Ficha del socio" tabs={[{ id: "datos", label: "Datos" }, { id: "pagos", label: "Pagos" }, { id: "clases", label: "Asistencia", disabledUntil: "v0.4" }, { id: "historial", label: "Historial" }]}>
                {(active) => <p>Contenido de la pestaña {active}.</p>}
              </Tabs>
            </Section>
            <Section name="KpiCard">
              <div className={styles.row}>
                <KpiCard label="Socios al día" value={210} kind="count" note="de 269 con membresía" />
                <KpiCard label="Vencen en 7 días" value={18} kind="count" attention note="3 vencen hoy" />
                <KpiCard label="Ingresos de octubre" value={18_240_000} kind="money" />
                <KpiCard label="Asistencia" value={null} kind="count" availableIn="v0.4" />
                <KpiCard label="Cargando" value={undefined} kind="count" isLoading />
                <KpiCard label="Con error" value={undefined} kind="count" error onRetry={noop} />
              </div>
            </Section>
            <Dialogs />
            <Section name="Field">
              <Field label="Correo" name="email" type="email" hint="Lo usa para entrar al portal." />
              <Field label="Documento" name="document" required error="Ya existe un socio con ese documento." errorAction={{ href: "/socios/1", text: "Ver socio" }} />
              <Field label="Teléfono" name="phone" disabled />
            </Section>
            <Section name="MaskedValue">
              <MaskedValue label="Documento" masked="CC •••• 4417" kind="document" onReveal={async () => Promise.resolve("CC 1020304417")} />
              <MaskedValue label="Teléfono" masked={null} kind="phone" onReveal={async () => Promise.resolve("")} />
            </Section>
            <Section name="HistoryAside">
              <HistoryAside entries={HISTORY} total={5} onLoadMore={noop} />
            </Section>
          </div>
        </main>
      </MemoryRouter>
    </RoleProvider>
  );
}

function initialTheme(search: string): Theme | null {
  const value = new URLSearchParams(search).get("tema");
  return value === "dark" || value === "light" ? value : null;
}

/** catalog.html: el kit, o un layout de muestra si llega ?vista=. */
export function CatalogApp({ search = window.location.search }: { search?: string }) {
  useState(() => {
    const theme = initialTheme(search);
    if (theme && readPreviewParams(search).view === null) setTheme(theme);
    return theme;
  });
  return readPreviewParams(search).view === null ? <Catalog /> : <LayoutsPreview search={search} />;
}
