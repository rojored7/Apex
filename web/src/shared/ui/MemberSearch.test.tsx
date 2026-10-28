// Fase 4 del Sprint 3 (M3): el buscador de socio que comparten la venta (MemberStep) y el panel de
// pagos (PaymentMemberPicker). Presentacional: la feature le da las opciones ya resueltas (nombre,
// nota y si se puede elegir) y el estado de la búsqueda; el estado se anuncia en una región `status`
// que siempre está montada.
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "vitest-axe";
import { MemberSearch, type MemberSearchProps } from "./MemberSearch";

const OPTIONS = [
  { id: "a", name: "Laura Gómez", note: "Mensual · Al día" },
  { id: "b", name: "Andrés Ruiz", note: "Inactivo: reactívalo antes de venderle", disabled: true },
];

function setup(props: Partial<MemberSearchProps> = {}) {
  const onSelect = vi.fn();
  const onChange = vi.fn();
  const view = render(
    <MemberSearch name="member-search" value="lau" onChange={onChange} status="done" options={OPTIONS} emptyText="Sin resultados." failedText="Falló la búsqueda." onSelect={onSelect} {...props} />,
  );
  return { ...view, onSelect, onChange, user: userEvent.setup() };
}

const region = () => screen.getByRole("status", { name: "Resultado de la búsqueda" });

describe("MemberSearch", () => {
  it("pinta un searchbox 'Buscar socio' que no envía el formulario con Enter", async () => {
    const submit = vi.fn();
    const onChange = vi.fn();
    render(
      <form
        onSubmit={(event) => {
          event.preventDefault();
          submit();
        }}
      >
        <MemberSearch name="member-search" value="" onChange={onChange} status="idle" options={[]} emptyText="x" failedText="y" onSelect={vi.fn()} />
      </form>,
    );
    const user = userEvent.setup();
    const box = screen.getByRole("searchbox", { name: "Buscar socio" });

    expect(box).toHaveAttribute("autocomplete", "off");
    await user.type(box, "a{Enter}");
    expect(submit).not.toHaveBeenCalled();
    expect(onChange).toHaveBeenCalledWith("a");
  });

  it("lista las opciones con su nota; una deshabilitada no se elige", async () => {
    const { user, onSelect } = setup();
    const list = screen.getByRole("list", { name: "Socios encontrados" });

    const laura = within(list).getByRole("button", { name: /Laura Gómez/ });
    expect(laura).toHaveTextContent("Mensual · Al día");
    expect(within(list).getByRole("button", { name: /Andrés Ruiz/ })).toBeDisabled();
    await user.click(laura);
    expect(onSelect).toHaveBeenCalledWith(OPTIONS[0]);
  });

  it.each([
    ["idle", [], ""],
    ["pending", [], "Buscando…"],
    ["error", [], "Falló la búsqueda."],
    ["done", [], "Sin resultados."],
    ["done", OPTIONS, "2 socios encontrados"],
    ["done", OPTIONS.slice(0, 1), "1 socio encontrado"],
  ] as const)("estado %s con %j opciones anuncia «%s»", (status, options, text) => {
    setup({ status, options: [...options] });

    expect(region()).toHaveTextContent(text);
  });

  it("el error se pinta como error y el conteo solo para el lector de pantalla", () => {
    const { rerender } = setup({ status: "error", options: [] });
    expect(within(region()).getByText("Falló la búsqueda.")).toHaveClass(/fieldError/);

    rerender(<MemberSearch name="member-search" value="lau" onChange={vi.fn()} status="done" options={OPTIONS} emptyText="x" failedText="y" onSelect={vi.fn()} />);
    expect(within(region()).getByText("2 socios encontrados")).toHaveClass(/srOnly/);
  });

  it("muestra el error del formulario bajo el buscador", () => {
    setup({ status: "idle", options: [], error: "Elige el socio." });

    expect(screen.getByRole("searchbox", { name: "Buscar socio" })).toHaveAccessibleDescription("Elige el socio.");
  });

  it("no tiene violaciones de accesibilidad", async () => {
    const { container } = setup();

    expect(await axe(container)).toHaveNoViolations();
  });
});
