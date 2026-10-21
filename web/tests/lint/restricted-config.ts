// Reglas de frontera del front que web/eslint.config.js no puede llevar todavía: ese
// archivo está protegido por el hook config-protection y no se edita desde este flujo.
// Estas reglas se aplican con ESLint programático (sin la config del repo) a todo src/ en
// tests/lint/no-direct-fetch.test.ts, así que `npm test` falla si alguien las rompe.
// - US-059: fetch solo en src/core/api; nada de console en src/.
// - US-060: Intl y toLocale* solo en src/core/i18n.
// - US-040: el rol nunca se compara con un literal fuera de src/core/auth/permissions.ts y
//   session.ts.
// Pendiente: mover este bloque a web/eslint.config.js cuando el usuario lo autorice.
import { ESLint, type Linter } from "eslint";
import reactHooks from "eslint-plugin-react-hooks";
import { fileURLToPath } from "node:url";
import tseslint from "typescript-eslint";

export const WEB_ROOT = fileURLToPath(new URL("../../", import.meta.url));

const FETCH_GLOBAL = { name: "fetch", message: "Usa el cliente de src/core/api (api.get, api.post...)." };
const INTL_GLOBAL = { name: "Intl", message: "El formato de dinero y fechas sale de src/core/i18n/format.ts." };
const FETCH_PROPERTIES = ["window", "globalThis", "self"].map((object) => ({
  object,
  property: "fetch",
  message: FETCH_GLOBAL.message,
}));
const LOCALE_PROPERTIES = ["toLocaleString", "toLocaleDateString", "toLocaleTimeString"].map((property) => ({
  property,
  message: INTL_GLOBAL.message,
}));

const ROLE_LITERAL = "Literal[value=/^(admin|coach|member)$/]";
const ROLE_MESSAGE = "No compares el rol con un literal: usa can(), useCan() o <Can> de src/core/auth.";
const ROLE_SELECTORS = [
  // x === "admin", "coach" !== x, ...
  `BinaryExpression[operator=/^[!=]==?$/] > ${ROLE_LITERAL}`,
  // switch (role) { case "admin": ... } y cualquier case "coach":
  `SwitchStatement[discriminant.name=/^role$/i]`,
  `SwitchStatement[discriminant.property.name=/^role$/i]`,
  `SwitchCase[test.value=/^(admin|coach|member)$/]`,
].map((selector) => ({ selector, message: ROLE_MESSAGE }));

export const RESTRICTED_CONFIG: Linter.Config[] = [
  {
    files: ["**/*.{ts,tsx}"],
    // Los plugins se registran (sin activar sus reglas) para que los comentarios
    // eslint-disable de esos plugins en src/ no den "regla no encontrada".
    plugins: { "@typescript-eslint": tseslint.plugin as ESLint.Plugin, "react-hooks": reactHooks as ESLint.Plugin },
    languageOptions: { parser: tseslint.parser as Linter.Parser, parserOptions: { ecmaFeatures: { jsx: true } } },
    linterOptions: { reportUnusedDisableDirectives: "off" },
  },
  {
    files: ["src/**/*.{ts,tsx}"],
    rules: { "no-console": "error" },
  },
  {
    files: ["src/**/*.{ts,tsx}"],
    ignores: ["src/core/api/**", "src/core/i18n/**"],
    rules: {
      "no-restricted-globals": ["error", FETCH_GLOBAL, INTL_GLOBAL],
      "no-restricted-properties": ["error", ...FETCH_PROPERTIES, ...LOCALE_PROPERTIES],
    },
  },
  {
    files: ["src/core/api/**/*.{ts,tsx}"],
    rules: {
      "no-restricted-globals": ["error", INTL_GLOBAL],
      "no-restricted-properties": ["error", ...LOCALE_PROPERTIES],
    },
  },
  {
    files: ["src/core/i18n/**/*.{ts,tsx}"],
    rules: {
      "no-restricted-globals": ["error", FETCH_GLOBAL],
      "no-restricted-properties": ["error", ...FETCH_PROPERTIES],
    },
  },
  {
    // La matriz y la sesión son los únicos lugares donde el rol se compara.
    files: ["src/**/*.{ts,tsx}"],
    ignores: ["src/core/auth/permissions.ts", "src/core/auth/session.ts"],
    rules: { "no-restricted-syntax": ["error", ...ROLE_SELECTORS] },
  },
];

function linter(): ESLint {
  return new ESLint({ cwd: WEB_ROOT, overrideConfigFile: true, overrideConfig: RESTRICTED_CONFIG });
}

export interface Finding {
  file: string;
  ruleId: string;
  line: number;
  message: string;
}

/** Reglas que fallan para un fragmento de código como si viviera en `filePath` (relativo a web/). */
export async function lintSnippet(code: string, filePath: string): Promise<string[]> {
  const [result] = await linter().lintText(code, { filePath: `${WEB_ROOT}${filePath}` });
  return (result?.messages ?? []).filter((m) => m.severity === 2).map((m) => m.ruleId ?? "fatal");
}

/** Errores de las reglas restringidas en todo `src/` real. */
export async function lintSourceTree(): Promise<Finding[]> {
  const results = await linter().lintFiles(["src/**/*.{ts,tsx}"]);
  return results.flatMap((r) =>
    r.messages
      .filter((m) => m.severity === 2)
      .map((m) => ({
        file: r.filePath.slice(WEB_ROOT.length).replace(/\\/g, "/"),
        ruleId: m.ruleId ?? "fatal",
        line: m.line,
        message: m.message,
      })),
  );
}
