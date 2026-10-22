// Revisión del Sprint 2 (M5): parseResponse e invalidResponseError.
import { z } from "zod";
import { ApiError } from "./errors";
import { INVALID_RESPONSE_CODE, INVALID_RESPONSE_MESSAGE, invalidResponseError, parseResponse } from "./response";
import { HTTP_BAD_REQUEST, HTTP_SERVER_ERROR, HTTP_TOO_MANY, isClientErrorStatus } from "./status";

const schema = z.object({ id: z.string(), total: z.number().int().default(0) });

describe("parseResponse", () => {
  it("devuelve el cuerpo validado con los valores por defecto del esquema", () => {
    expect(parseResponse(schema, { id: "a" })).toEqual({ id: "a", total: 0 });
  });

  it("una forma inesperada lanza invalid_response con status 0 y el mensaje común", () => {
    let caught: unknown;
    try {
      parseResponse(schema, { nope: true });
    } catch (error) {
      caught = error;
    }

    expect(caught).toBeInstanceOf(ApiError);
    expect(caught).toMatchObject({ status: 0, code: INVALID_RESPONSE_CODE, message: INVALID_RESPONSE_MESSAGE });
  });

  it("invalidResponseError da un error nuevo cada vez", () => {
    expect(invalidResponseError()).not.toBe(invalidResponseError());
  });
});

describe("status", () => {
  it.each([
    [HTTP_BAD_REQUEST, true],
    [HTTP_TOO_MANY, true],
    [HTTP_SERVER_ERROR, false],
    [0, false],
  ])("isClientErrorStatus(%i) es %s", (status, expected) => {
    expect(isClientErrorStatus(status)).toBe(expected);
  });
});
