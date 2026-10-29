// @vitest-environment node
// Revisión del Sprint 2 (M7 general, parte front): cada código de error que el front reconoce
// existe como literal en api/src (lectura del repo, como types.contract.test.ts con
// docs/openapi.json), y ningún archivo del front compara `code` con un literal suelto.
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";
import { fileURLToPath } from "node:url";
import { API_ERROR_CODES, BUSY_MESSAGE, CLIENT_ERROR_CODES } from "./errorCodes";

const API_SRC = fileURLToPath(new URL("../../../../api/src/", import.meta.url));
const WEB_SRC = fileURLToPath(new URL("../../", import.meta.url));

function walk(dir: string, pattern: RegExp): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return name === "__pycache__" ? [] : walk(path, pattern);
    return pattern.test(name) ? [path] : [];
  });
}

const API_TEXT = walk(API_SRC, /\.py$/)
  .map((file) => readFileSync(file, "utf8"))
  .join("\n");

describe("códigos de error del api (core/api/errorCodes.ts)", () => {
  // Revisión: no basta con que el texto aparezca en cualquier parte. Debe estar donde el api
  // define un código: `code = "x"`, `code="x"`, `SomeError("x", ...)`, la tabla de códigos por
  // estado (`401: ("x", ...)`) o un Literal de razones (WeakReason).
  it.each(Object.values(API_ERROR_CODES))("%s es un código que define api/src", (code) => {
    const literal = `["']${code}["']`;
    const contexts = [String.raw`code\s*=\s*${literal}`, String.raw`Error\(\s*${literal}`, String.raw`\d{3}:\s*\(\s*${literal}`, String.raw`Literal\[[^\]]*${literal}`];
    expect(API_TEXT).toMatch(new RegExp(contexts.join("|")));
  });

  it("los códigos del cliente no chocan con los del api", () => {
    const api = new Set<string>(Object.values(API_ERROR_CODES));

    expect(Object.values(CLIENT_ERROR_CODES).filter((code) => api.has(code))).toEqual([]);
  });

  it("fuera de core/api nadie compara ni arma un code con un literal: usa errorCodes.ts", () => {
    const literal = /\bcode\s*(?:===|!==|:)\s*["'][a-z_]+["']/;
    const offenders = walk(WEB_SRC, /\.(ts|tsx)$/)
      .filter((file) => !/\.test\.(ts|tsx)$/.test(file))
      .map((file) => relative(WEB_SRC, file).split(sep).join("/"))
      .filter((file) => !file.startsWith("core/api/") && !file.startsWith("test/"))
      .filter((file) => literal.test(readFileSync(join(WEB_SRC, file), "utf8")));

    expect(offenders).toEqual([]);
  });
});

describe("códigos del Sprint 3 (S3-F3)", () => {
  it("incluye los de vender, primer pago y renovar, y el 503 busy", () => {
    expect(Object.values(API_ERROR_CODES)).toEqual(
      expect.arrayContaining([
        "busy",
        "member_inactive",
        "plan_invalid",
        "plan_inactive",
        "start_date_too_retroactive",
        "start_date_too_far",
        "membership_conflict",
        "membership_overlap",
        "future_membership_exists",
        "membership_not_found",
        "payment_exceeds_balance",
        "payment_possible_duplicate",
        "payment_limit_reached",
        "paid_at_too_retroactive",
      ]),
    );
  });

  it("el mensaje genérico del busy dice qué pasó y qué hacer", () => {
    expect(BUSY_MESSAGE).toBe("El sistema está ocupado; intenta de nuevo.");
  });
});

describe("códigos del Sprint 3 (S3-F4)", () => {
  it("incluye los de registrar y anular pagos", () => {
    expect(API_ERROR_CODES).toMatchObject({
      membershipCancelled: "membership_cancelled",
      paymentNotFound: "payment_not_found",
      paymentAlreadyVoided: "payment_already_voided",
    });
  });
});

describe("códigos del Sprint 3 (S3-F1)", () => {
  it("incluye los de revelar, editar, dar de baja y reactivar socios (members/exceptions.py)", () => {
    expect(Object.values(API_ERROR_CODES)).toEqual(
      expect.arrayContaining(["forbidden_field", "member_deactivated", "member_already_deactivated", "member_not_deactivated", "consent_cannot_be_withdrawn", "member_document_duplicated"]),
    );
  });
});

describe("códigos del Sprint 4A (S4A-F1)", () => {
  it("incluye los de la auditoría (audit/exceptions.py, S4A-D35)", () => {
    expect(API_ERROR_CODES).toMatchObject({
      verificationRunning: "verification_running",
      auditEntryNotFound: "audit_entry_not_found",
    });
  });
});
