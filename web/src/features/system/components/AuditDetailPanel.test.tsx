// S4A-F1 · US-103 (front): el detalle de una entrada de auditoría en un panel lateral. Metadatos,
// cambios antes → después, valores cifrados como "Cifrado" con su llave (marcador o prefijo), sin
// ninguna acción de descifrar, hashes en monoespaciada, 404, carga y error. Todo valor es texto
// (S4A-D58: `<script>` no se interpreta), un objeto anidado se aplana y se corta a 2.000 caracteres,
// y un `seq` que no es entero seguro >= 1 no pide nada.
import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { KEY_ID, LAURA_ID, auditDetail, encryptedMarker } from "../../../test/audit";
import { mockApi, testQueryClient, type MockHandler } from "../../../test/server";
import { auditDetailSchema } from "../schemas";
import { AuditDetailPanel } from "./AuditDetailPanel";

const BLOB = `apx1.${KEY_ID}.A256GCM.bm9uY2U.Y2lmcmFkbw`;

function renderPanel(rawSeq: string | null = "88412", handler: MockHandler = { status: 200, body: auditDetail() }) {
  const mock = mockApi({ "GET /audit/88412": handler });
  const onClose = vi.fn();
  const view = render(
    <QueryClientProvider client={testQueryClient()}>
      <MemoryRouter>
        <AuditDetailPanel rawSeq={rawSeq} onClose={onClose} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return { mock, onClose, user: userEvent.setup(), ...view };
}

const detailWith = (changes: unknown[], extra: Record<string, unknown> = {}) => ({ status: 200, body: auditDetail({ changes, ...extra }) });

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("AuditDetailPanel · metadatos y cambios", () => {
  it("muestra la entrada, quién, cuándo, la acción, la entidad y el registro", async () => {
    renderPanel();

    const panel = await screen.findByRole("dialog", { name: "Entrada #88412" });
    expect(await within(panel).findByText("20 oct 2026, 11:52 a. m.")).toBeInTheDocument();
    expect(within(panel).getByText("admin@apex.test")).toBeInTheDocument();
    expect(within(panel).getByText("Cambiar")).toBeInTheDocument();
    expect(within(panel).getByText("Socio")).toBeInTheDocument();
    expect(within(panel).getByText(LAURA_ID)).toBeInTheDocument();
    expect(within(panel).getByRole("link", { name: "Ver la ficha del socio" })).toHaveAttribute("href", `/socios/${LAURA_ID}`);
  });

  it("lista cada cambio como antes → después", async () => {
    renderPanel();

    const list = await screen.findByRole("list", { name: "Cambios" });
    const notes = within(list).getByText("notes").closest("li");
    expect(notes).not.toBeNull();
    expect(notes).toHaveTextContent("Llamar en la tarde → Llamar en la mañana");
  });

  it("un valor cifrado se ve como Cifrado con el key_id del marcador; ninguna acción lo descifra", async () => {
    renderPanel();

    const list = await screen.findByRole("list", { name: "Cambios" });
    const phone = within(list).getByText("Teléfono").closest("li");
    expect(phone).toHaveTextContent(`Cifrado · llave ${KEY_ID}`);
    expect(screen.queryByRole("button", { name: /mostrar|descifrar|ver/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /mostrar|descifrar|^ver$/i })).not.toBeInTheDocument();
  });

  it("un blob apx1. que llegara sin marcador también se ve como Cifrado con su llave (defensa en profundidad)", async () => {
    renderPanel("88412", detailWith([{ field: "document", kind: "changed", before: BLOB, after: BLOB, encrypted: false }]));

    const list = await screen.findByRole("list", { name: "Cambios" });
    expect(within(list).getByText("Documento").closest("li")).toHaveTextContent(`Cifrado · llave ${KEY_ID}`);
    expect(document.body.textContent).not.toContain("bm9uY2U");
  });

  it("el marcador con key_id nulo (S4A-D105) es Cifrado sin llave y {truncated: true} es (recortado)", async () => {
    renderPanel(
      "88412",
      detailWith([
        { field: "phone", kind: "changed", before: encryptedMarker(null), after: encryptedMarker(), encrypted: true },
        { field: "metadata", kind: "added", before: null, after: { truncated: true }, encrypted: false },
      ]),
    );

    const list = await screen.findByRole("list", { name: "Cambios" });
    expect(within(list).getByText("Teléfono").closest("li")).toHaveTextContent("Cifrado · sin llave identificable");
    expect(within(list).getByText("metadata").closest("li")).toHaveTextContent("(recortado)");
  });

  it("un valor con <script> se pinta como texto", async () => {
    const evil = "<script>window.hacked = true</script><img src=x onerror=alert(1)>";
    renderPanel("88412", detailWith([{ field: "notes", kind: "changed", before: "hola", after: evil, encrypted: false }]));

    const list = await screen.findByRole("list", { name: "Cambios" });
    expect(within(list).getByText(evil, { exact: false })).toBeInTheDocument();
    expect(document.querySelector("script")).toBeNull();
    expect(document.querySelector("img")).toBeNull();
  });

  it("un objeto anidado se aplana y se corta a 2.000 caracteres", async () => {
    const nested = { contacto: { nombre: "Ana", nota: "x".repeat(5_000) }, lista: [1, 2] };
    renderPanel("88412", detailWith([{ field: "emergency", kind: "added", before: null, after: nested, encrypted: false }]));

    const list = await screen.findByRole("list", { name: "Cambios" });
    const value = within(list).getByTestId("audit-value-after-0");
    expect(value.textContent).toMatch(/^contacto\.nombre: Ana · contacto\.nota: x+/);
    expect(value.textContent.length).toBeLessThanOrEqual(2_001);
    expect(value.textContent.endsWith("…")).toBe(true);
  });

  it("un cambio añadido o quitado dice el lado vacío", async () => {
    renderPanel(
      "88412",
      detailWith([
        { field: "reference", kind: "added", before: null, after: "M123", encrypted: false },
        { field: "voided", kind: "removed", before: false, after: null, encrypted: false },
      ]),
    );

    const list = await screen.findByRole("list", { name: "Cambios" });
    expect(within(list).getByText("Referencia").closest("li")).toHaveTextContent("(sin valor) → M123");
    expect(within(list).getByText("Anulado").closest("li")).toHaveTextContent("no → (sin valor)");
  });

  it("sin cambios de campos lo dice", async () => {
    renderPanel("88412", detailWith([], { action: "verify", table_name: "audit.verifications" }));

    expect(await screen.findByText("Esta acción no cambió campos del registro.")).toBeInTheDocument();
  });

  it("prev_hash y hash van en fuente monoespaciada", async () => {
    renderPanel();

    const hash = await screen.findByText("b".repeat(64));
    expect(hash.tagName).toBe("CODE");
    expect(screen.getByText("a".repeat(64)).tagName).toBe("CODE");
  });
});

describe("AuditDetailPanel · estados", () => {
  it("muestra la carga mientras llega el detalle", async () => {
    renderPanel("88412", () => new Promise(() => undefined));

    expect(await screen.findByText("Cargando la entrada…")).toBeInTheDocument();
  });

  it("un 404 dice que ese registro ya no existe", async () => {
    renderPanel("88412", { status: 404, body: { error: { code: "audit_entry_not_found", message: "x" } } });

    expect(await screen.findByText("Ese registro ya no existe. Cierra el panel y elige otra entrada de la lista.")).toBeInTheDocument();
  });

  it("un error se explica y Reintentar vuelve a pedir", async () => {
    let fail = true;
    const { mock, user } = renderPanel("88412", () => (fail ? { status: 500, body: { error: { code: "internal_error", message: "x" } } } : { status: 200, body: auditDetail() }));

    expect(await screen.findByText("No pudimos cargar la entrada. Intenta de nuevo en un momento.")).toBeInTheDocument();
    fail = false;
    await user.click(screen.getByRole("button", { name: "Reintentar" }));

    expect(await screen.findByRole("list", { name: "Cambios" })).toBeInTheDocument();
    expect(mock.callsTo("GET /audit/88412")).toHaveLength(2);
  });

  it("Cerrar avisa a la página", async () => {
    const { onClose, user } = renderPanel();
    const panel = await screen.findByRole("dialog", { name: "Entrada #88412" });

    await user.click(within(panel).getByRole("button", { name: "Cerrar" }));

    expect(onClose).toHaveBeenCalled();
  });

  it.each(["abc", "0", "-1", "1.5", "99999999999999999999"])("?seq=%s no dispara ninguna petición ni abre el panel", async (raw) => {
    const { mock } = renderPanel(raw);

    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
    expect(mock.calls).toEqual([]);
  });

  it("sin seq no hay panel", () => {
    const { mock } = renderPanel(null);

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(mock.calls).toEqual([]);
  });
});

describe("AuditDetailPanel · revisión de seguridad de F1", () => {
  it("LOW 2: una clave anidada o un campo que parece un blob se pinta como (clave cifrada)", async () => {
    renderPanel(
      "88412",
      detailWith([
        { field: "extra", kind: "added", before: null, after: { [BLOB]: "valor", visible: "ok" }, encrypted: false },
        { field: BLOB, kind: "changed", before: "a", after: "b", encrypted: false },
      ]),
    );

    const list = await screen.findByRole("list", { name: "Cambios" });
    expect(within(list).getByTestId("audit-value-after-0")).toHaveTextContent("(clave cifrada): valor · visible: ok");
    expect(within(list).getByText("(clave cifrada)")).toBeInTheDocument();
    expect(document.body.textContent).not.toContain("Y2lmcmFkbw");
  });

  it("LOW 3: el detalle validado no conserva las fotos before y after del api", () => {
    const parsed = auditDetailSchema.parse(auditDetail());

    expect(parsed).not.toHaveProperty("before");
    expect(parsed).not.toHaveProperty("after");
    expect(parsed.changes).toHaveLength(2);
    expect(auditDetailSchema.safeParse({ ...auditDetail(), extra: 1 }).success).toBe(false);
  });
});
