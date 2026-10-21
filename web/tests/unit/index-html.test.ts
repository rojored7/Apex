// @vitest-environment node
// US-038 T1: el index.html construido por Vite no trae scripts ni estilos en línea,
// y cada <script>, <link rel="stylesheet"> y <link rel="modulepreload"> lleva el
// marcador de nonce que Nginx reemplaza por $request_id (sub_filter).
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { build } from "vite";
import { afterAll, beforeAll, describe, expect, it } from "vitest";

export const CSP_NONCE_MARKER = "__CSP_NONCE__";

const TAG = /<(script|style|link)\b([^>]*)>/gi;

type Tag = { name: string; attrs: string };

export function tagsOf(html: string): Tag[] {
  return [...html.matchAll(TAG)].map((m) => ({ name: (m[1] ?? "").toLowerCase(), attrs: m[2] ?? "" }));
}

function hasAttr(attrs: string, name: string): boolean {
  return new RegExp(`(^|\\s)${name}(\\s|=|$)`, "i").test(attrs);
}

function attrValue(attrs: string, name: string): string | undefined {
  const m = new RegExp(`(?:^|\\s)${name}\\s*=\\s*"([^"]*)"`, "i").exec(attrs);
  return m?.[1];
}

describe("index.html construido (US-038)", () => {
  let outDir = "";
  let html = "";

  beforeAll(async () => {
    outDir = mkdtempSync(join(tmpdir(), "apex-index-html-"));
    await build({ logLevel: "silent", configFile: "vite.config.ts", build: { outDir, emptyOutDir: true } });
    html = readFileSync(join(outDir, "index.html"), "utf8");
  }, 120_000);

  afterAll(() => {
    if (outDir) rmSync(outDir, { recursive: true, force: true });
  });

  it("no contiene <script> en línea (todos llevan src)", () => {
    const inline = tagsOf(html).filter((t) => t.name === "script" && !hasAttr(t.attrs, "src"));
    expect(inline).toEqual([]);
  });

  it("no contiene <style> en línea", () => {
    expect(tagsOf(html).filter((t) => t.name === "style")).toEqual([]);
  });

  it("cada <script> lleva nonce con el marcador", () => {
    const scripts = tagsOf(html).filter((t) => t.name === "script");
    expect(scripts.length).toBeGreaterThan(0);
    for (const s of scripts) expect(attrValue(s.attrs, "nonce")).toBe(CSP_NONCE_MARKER);
  });

  it("cada <link rel=stylesheet|modulepreload> lleva nonce con el marcador", () => {
    const links = tagsOf(html).filter((t) => {
      const rel = attrValue(t.attrs, "rel")?.toLowerCase();
      return t.name === "link" && (rel === "stylesheet" || rel === "modulepreload");
    });
    expect(links.length).toBeGreaterThan(0);
    for (const l of links) expect(attrValue(l.attrs, "nonce")).toBe(CSP_NONCE_MARKER);
  });

  it("no hay atributos style= en el HTML estático", () => {
    expect(/\sstyle\s*=/i.test(html)).toBe(false);
  });
});
