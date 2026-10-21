// US-063 T10: axe sobre DataTable (con datos, vacía y con error), Pagination, FilterBar y Chips.
import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router";
import { axe } from "vitest-axe";
import { ApiError } from "../../core/api/errors";
import { Chips } from "./Chips";
import { DataTable, type Column } from "./DataTable";
import { FilterBar } from "./FilterBar";
import { Pagination } from "./Pagination";

interface Row {
  id: string;
  name: string;
  plan: string;
}

const COLUMNS: Column<Row>[] = [
  { key: "name", header: "Socio", render: (r) => r.name, sortable: true },
  { key: "plan", header: "Plan", render: (r) => r.plan },
];

function table(extra: Partial<Parameters<typeof DataTable<Row>>[0]>): ReactElement {
  return (
    <DataTable<Row>
      caption="Socios"
      columns={COLUMNS}
      rows={[{ id: "1", name: "Laura", plan: "Mensual" }]}
      total={1}
      rowKey={(r) => r.id}
      rowHref={(r) => `/socios/${r.id}`}
      sort={{ field: "name", direction: "asc" }}
      onSortChange={() => undefined}
      {...extra}
    />
  );
}

async function check(ui: ReactElement): Promise<void> {
  const { container } = render(
    <MemoryRouter>
      <main>{ui}</main>
    </MemoryRouter>,
  );
  expect(await axe(container)).toHaveNoViolations();
}

describe("accesibilidad del kit de listas", () => {
  it("DataTable con datos", async () => {
    await check(table({}));
  });

  it("DataTable cargando", async () => {
    await check(table({ isLoading: true, rows: undefined, limit: 3 }));
  });

  it("DataTable vacía", async () => {
    await check(table({ rows: [], total: 0 }));
  });

  it("DataTable con error", async () => {
    await check(table({ rows: undefined, error: new ApiError({ status: 500, code: "x", message: "Error interno" }), onRetry: () => undefined }));
  });

  it("DataTable en tarjetas", async () => {
    vi.stubGlobal(
      "matchMedia",
      vi.fn(() => ({ matches: true, addEventListener: () => undefined, removeEventListener: () => undefined })),
    );
    await check(table({}));
    vi.unstubAllGlobals();
  });

  it("Pagination", async () => {
    await check(<Pagination total={312} limit={50} offset={100} onPageChange={() => undefined} onLimitChange={() => undefined} />);
  });

  it("FilterBar completa", async () => {
    await check(
      <FilterBar
        query="ana"
        onQueryChange={() => undefined}
        onClear={() => undefined}
        selects={[{ name: "plan", label: "Plan", value: "", options: [{ value: "p1", label: "Mensual" }] }]}
        onSelectChange={() => undefined}
        dateRange={{ label: "Fecha de pago", from: "", to: "", onChange: () => undefined }}
        sort={{ value: "", options: [{ value: "last_name", label: "Nombre A–Z" }], onChange: () => undefined }}
      />,
    );
  });

  it("Chips", async () => {
    await check(
      <Chips
        label="Estado"
        mode="multiple"
        value={["active"]}
        onChange={() => undefined}
        options={[
          { value: "active", label: "Al día", count: 210 },
          { value: "pending_payment", label: "Pendiente de pago", count: 7, tone: "warning" },
        ]}
      />,
    );
  });
});
