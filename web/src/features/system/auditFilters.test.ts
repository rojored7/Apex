// S4A-F1 (S4A-D58, S4A-D106): de la URL al api. Solo viaja lo que tiene la forma que el api
// acepta; las fechas son días de Bogotá y viajan en UTC con `to` exclusivo; `q` nunca sale de la URL.
import { MAX_AUDIT_OFFSET, parseSeq, readAuditFilters, toApiParams } from "./auditFilters";

const UUID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const OTHER = "22222222-2222-4222-8222-222222222222";

const params = (search: string, q = ""): Record<string, string> => Object.fromEntries(toApiParams(search, q));

describe("toApiParams", () => {
  it("devuelve URLSearchParams con limit y offset por defecto", () => {
    const result = toApiParams("");

    expect(result).toBeInstanceOf(URLSearchParams);
    expect(Object.fromEntries(result)).toEqual({ limit: "25", offset: "0" });
  });

  it("lleva los filtros válidos con los nombres del api", () => {
    expect(params(`table=members.members&user_id=${OTHER}&action=update&record_id=${UUID}&subject_member_id=${UUID}`)).toEqual({
      limit: "25",
      offset: "0",
      table: "members.members",
      user_id: OTHER,
      action: "update",
      record_id: UUID,
      subject_member_id: UUID,
    });
  });

  it("descarta user_id, record_id y subject_member_id que no son UUID", () => {
    expect(params("table=members.members&user_id=yo&record_id=1%20OR%201&subject_member_id=abc")).toEqual({ limit: "25", offset: "0", table: "members.members" });
  });

  it.each(["members", "Members.members", "members.members;drop", "members.members.extra", `${"a".repeat(64)}.members`, "otra.tabla"])("descarta la tabla %s", (table) => {
    expect(params(`table=${encodeURIComponent(table)}`)).toEqual({ limit: "25", offset: "0" });
  });

  it("record_id sin tabla no viaja (S4A-D106: el api exige la tabla)", () => {
    expect(params(`record_id=${UUID}`)).toEqual({ limit: "25", offset: "0" });
  });

  it("descarta una acción fuera de la lista", () => {
    expect(params("action=descifrar")).toEqual({ limit: "25", offset: "0" });
    expect(params("action=reveal")).toEqual({ limit: "25", offset: "0", action: "reveal" });
  });

  it("from y to son días de Bogotá y viajan en UTC; to es el inicio del día siguiente (rango [from, to))", () => {
    expect(params("from=2026-10-13&to=2026-10-20")).toEqual({ limit: "25", offset: "0", from: "2026-10-13T05:00:00.000Z", to: "2026-10-21T05:00:00.000Z" });
  });

  it("una fecha que no es real o un rango invertido no viajan", () => {
    expect(params("from=2026-02-30")).toEqual({ limit: "25", offset: "0" });
    expect(params("from=2026-10-20&to=2026-10-13")).toEqual({ limit: "25", offset: "0" });
  });

  it("q nunca se lee de la URL; viaja solo el que se pasa en memoria", () => {
    expect(params("q=ana%40apex.test")).toEqual({ limit: "25", offset: "0" });
    expect(params("", "  carlos ")).toEqual({ limit: "25", offset: "0", q: "carlos" });
  });

  it("offset es múltiplo de limit y no pasa del tope del api (S4A-D45)", () => {
    expect(params("limit=50&offset=120")).toEqual({ limit: "50", offset: "100" });
    expect(params("limit=100&offset=-5")).toEqual({ limit: "100", offset: "0" });
    expect(params("limit=25&offset=abc")).toEqual({ limit: "25", offset: "0" });
    expect(Number(params(`limit=25&offset=${String(MAX_AUDIT_OFFSET * 3)}`).offset)).toBe(MAX_AUDIT_OFFSET);
    expect(Number(params(`limit=100&offset=${String(MAX_AUDIT_OFFSET + 99)}`).offset)).toBe(MAX_AUDIT_OFFSET);
  });

  it("limit fuera de 1..200 vuelve a 25", () => {
    expect(params("limit=500")).toEqual({ limit: "25", offset: "0" });
  });

  it("ignora claves que el api no conoce y el seq del detalle", () => {
    expect(params("seq=4&evil=1&sort=-at")).toEqual({ limit: "25", offset: "0" });
  });
});

describe("readAuditFilters", () => {
  it("lee los valores válidos de la URL y deja vacío lo demás", () => {
    expect(readAuditFilters(`from=2026-10-13&to=x&table=plans.plans&user_id=${OTHER}&action=nada&record_id=${UUID}`)).toEqual({
      from: "2026-10-13",
      to: "",
      table: "plans.plans",
      user_id: OTHER,
      action: "",
      record_id: UUID,
      subject_member_id: "",
    });
  });
});

describe("parseSeq (S4A-D58)", () => {
  it.each([
    ["1", 1],
    ["88412", 88412],
  ])("%s es un seq válido", (raw, expected) => {
    expect(parseSeq(raw)).toBe(expected);
  });

  it.each([null, "", "abc", "0", "-3", "1.5", "1e3", " 7", "9007199254740993", "0x10"])("%s no es un seq válido", (raw) => {
    expect(parseSeq(raw)).toBeNull();
  });
});
