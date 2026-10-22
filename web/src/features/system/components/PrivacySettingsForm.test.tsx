// S2-F5 · US-057: pestaña Privacidad. Versión vigente con su fecha, texto de la política
// como texto plano (nunca HTML) con contador, años de retención, "Autorización obligatoria
// desde", confirmación al publicar una versión nueva y conflicto 409.
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "vitest-axe";
import { mockApi, renderWithProviders, type MockReply } from "../../../test/server";
import { CONFLICT_REPLY, fieldErrorReply, privacySection } from "../../../test/settings";
import { PrivacySettingsForm } from "./PrivacySettingsForm";

const PUBLISHED = privacySection({ policy_version: "2026-10", policy_text: "Autorizo a APEX el tratamiento de mis datos.", retention_years: 5 }, 3);

afterEach(() => {
  vi.unstubAllGlobals();
});

async function renderLoaded(section = PUBLISHED, handlers: Record<string, MockReply | (() => MockReply)> = {}) {
  const mock = mockApi({ "GET /settings/privacy": { status: 200, body: section }, ...handlers });
  const user = userEvent.setup();
  const view = renderWithProviders(<PrivacySettingsForm />, { role: "admin" });
  await screen.findByRole("textbox", { name: /Versión de la política/ });
  return { mock, user, ...view };
}

const textArea = () => screen.getByRole("textbox", { name: /Texto de la política/ });

describe("PrivacySettingsForm", () => {
  it("muestra la versión vigente con la fecha en español corto", async () => {
    await renderLoaded();

    expect(screen.getByText("Versión vigente: 2026-10 · vigente desde 21 oct 2026")).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: /Versión de la política/ })).toHaveValue("2026-10");
    expect(textArea()).toHaveValue("Autorizo a APEX el tratamiento de mis datos.");
    expect(screen.getByRole("spinbutton", { name: /Años de retención/ })).toHaveValue(5);
    expect(screen.getByLabelText(/Autorización obligatoria desde/)).toHaveValue("");
  });

  it("sin política publicada guía a publicar la primera", async () => {
    await renderLoaded(privacySection());

    expect(screen.getByText("Todavía no hay una política publicada. Escribe la versión y el texto para publicar la primera.")).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: /Versión de la política/ })).toHaveValue("");
    expect(screen.getByRole("spinbutton", { name: /Años de retención/ })).toHaveValue(5);
  });

  it("el texto de la política se muestra como texto plano, nunca como HTML", async () => {
    const html = '<b>negrita</b><script>window.hacked = true</script><img src=x onerror="alert(1)">';
    const { container } = await renderLoaded(privacySection({ policy_version: "v1", policy_text: html }, 1));

    expect(textArea()).toHaveValue(html);
    expect(container.querySelector("b, script, img")).toBeNull();
    expect((window as unknown as { hacked?: boolean }).hacked).toBeUndefined();
  });

  it("cuenta los caracteres del texto contra el máximo de 20.000", async () => {
    const { user } = await renderLoaded(privacySection());

    expect(screen.getByText("0 de 20.000 caracteres")).toBeInTheDocument();
    await user.type(textArea(), "Hola");

    expect(screen.getByText("4 de 20.000 caracteres")).toBeInTheDocument();
    expect(textArea()).toHaveAccessibleDescription(expect.stringContaining("4 de 20.000 caracteres"));
  });

  it("la primera publicación guarda sin pedir confirmación", async () => {
    const { mock, user } = await renderLoaded(privacySection(), {
      "PATCH /settings/privacy": { status: 200, body: privacySection({ policy_version: "2026-10", policy_text: "Autorizo." }, 1) },
    });

    await user.type(screen.getByRole("textbox", { name: /Versión de la política/ }), "2026-10");
    await user.type(textArea(), "Autorizo.");
    await user.click(screen.getByRole("button", { name: "Guardar" }));

    expect(await screen.findByText("Cambios guardados")).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(mock.callsTo("PATCH /settings/privacy")[0]?.body).toEqual({
      value: { policy_version: "2026-10", policy_text: "Autorizo.", retention_years: 5, consent_required_from: null },
      version: 0,
    });
  });

  it("cambiar la versión pide confirmación; Volver no guarda", async () => {
    const { mock, user } = await renderLoaded();
    const version = screen.getByRole("textbox", { name: /Versión de la política/ });

    await user.clear(version);
    await user.type(version, "2026-11");
    await user.click(screen.getByRole("button", { name: "Guardar" }));

    const dialog = await screen.findByRole("dialog", { name: "¿Publicar la versión 2026-11?" });
    expect(dialog).toHaveTextContent("Los socios que ya aceptaron conservan la versión anterior.");
    await user.click(within(dialog).getByRole("button", { name: "Volver" }));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(mock.callsTo("PATCH /settings/privacy")).toHaveLength(0);
    expect(version).toHaveValue("2026-11");
  });

  it("al confirmar la versión nueva la publica con la fecha de autorización", async () => {
    const { mock, user } = await renderLoaded(PUBLISHED, {
      "PATCH /settings/privacy": { status: 200, body: privacySection({ policy_version: "2026-11", policy_text: "Nuevo texto.", consent_required_from: "2026-11-01" }, 4) },
    });
    const version = screen.getByRole("textbox", { name: /Versión de la política/ });
    await user.clear(version);
    await user.type(version, "2026-11");
    await user.clear(textArea());
    await user.type(textArea(), "Nuevo texto.");
    await user.type(screen.getByLabelText(/Autorización obligatoria desde/), "2026-11-01");
    await user.click(screen.getByRole("button", { name: "Guardar" }));

    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Publicar versión" }));

    expect(await screen.findByText("Cambios guardados")).toBeInTheDocument();
    expect(mock.callsTo("PATCH /settings/privacy")[0]?.body).toEqual({
      value: { policy_version: "2026-11", policy_text: "Nuevo texto.", retention_years: 5, consent_required_from: "2026-11-01" },
      version: 3,
    });
    expect(screen.getByText("Versión vigente: 2026-11 · vigente desde 21 oct 2026")).toBeInTheDocument();
  });

  it("con la misma versión guarda sin confirmar (por ejemplo, años de retención)", async () => {
    const { mock, user } = await renderLoaded(PUBLISHED, {
      "PATCH /settings/privacy": { status: 200, body: privacySection({ ...PUBLISHED.value, retention_years: 10 }, 4) },
    });
    const years = screen.getByRole("spinbutton", { name: /Años de retención/ });

    await user.clear(years);
    await user.type(years, "10");
    await user.click(screen.getByRole("button", { name: "Guardar" }));

    expect(await screen.findByText("Cambios guardados")).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(mock.callsTo("PATCH /settings/privacy")[0]?.body).toMatchObject({ value: { retention_years: 10 }, version: 3 });
  });

  it("valida versión, texto y años antes de llamar al api", async () => {
    const { mock, user } = await renderLoaded(privacySection());
    const years = screen.getByRole("spinbutton", { name: /Años de retención/ });

    await user.clear(years);
    await user.type(years, "25");
    await user.click(screen.getByRole("button", { name: "Guardar" }));

    expect(await screen.findByText("Escribe la versión de la política, por ejemplo 2026-10.")).toBeInTheDocument();
    expect(screen.getByText("Escribe o pega el texto de la política.")).toBeInTheDocument();
    expect(screen.getByText("Escribe un número entre 1 y 20.")).toBeInTheDocument();
    expect(mock.callsTo("PATCH /settings/privacy")).toHaveLength(0);
  });

  it("un 422 de value.policy_text marca el texto", async () => {
    const { user } = await renderLoaded(PUBLISHED, { "PATCH /settings/privacy": fieldErrorReply("value.policy_text") });

    await user.type(textArea(), " Más.");
    await user.click(screen.getByRole("button", { name: "Guardar" }));

    await waitFor(() => {
      expect(textArea()).toHaveAttribute("aria-invalid", "true");
    });
    expect(textArea()).toHaveAccessibleDescription(expect.stringContaining("El servidor no aceptó el texto. Revísalo y vuelve a guardar."));
  });

  it("un 409 muestra el aviso de conflicto con Recargar", async () => {
    const { user } = await renderLoaded(PUBLISHED, { "PATCH /settings/privacy": CONFLICT_REPLY });

    await user.type(textArea(), " Más.");
    await user.click(screen.getByRole("button", { name: "Guardar" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Otra persona cambió esta sección. Recarga para ver los cambios.");
    expect(within(alert).getByRole("button", { name: "Recargar" })).toBeInTheDocument();
  });

  it("es accesible", async () => {
    const { container } = await renderLoaded();

    expect(await axe(container)).toHaveNoViolations();
  });
});
