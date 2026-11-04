// Reglas de frontera del front que web/eslint.config.js no puede llevar todavía: ese
// archivo está protegido por el hook config-protection y no se edita desde este flujo.
// Estas reglas se aplican con ESLint programático (sin la config del repo) a todo src/ en
// tests/lint/no-direct-fetch.test.ts, así que `npm test` falla si alguien las rompe.
// - US-059: fetch solo en src/core/api; nada de console en src/.
// - US-060: Intl y toLocale* solo en src/core/i18n.
// - Acceso calculado a window/globalThis/self prohibido (no-restricted-syntax).
//   Límite aceptado: un alias (const w = window; w.sessionStorage) no se detecta sin análisis de flujo.
// - Estas reglas corren con `npm test` (lintSourceTree; gates y CI), no con `npm run lint`.
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
const SESSION_GLOBAL = {
  name: "sessionStorage",
  message: "sessionStorage solo se usa en src/pages/RouteError.tsx (S4B-D51).",
};
const SESSION_PROPERTIES = ["window", "globalThis", "self"].map((object) => ({
  object,
  property: "sessionStorage",
  message: SESSION_GLOBAL.message,
}));
const COMPUTED_GLOBAL_SELECTOR = {
  selector: "MemberExpression[computed=true][object.name=/^(window|globalThis|self)$/]",
  message: "Acceso calculado a globales prohibido: usa el nombre directo (window.fetch, no window[k]).",
};
const ROLE_EXEMPT = ["src/core/auth/permissions.ts", "src/core/auth/session.ts"];
const SESSION_ALLOWED = ["src/pages/RouteError.tsx", "src/**/*.test.{ts,tsx}"];
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

/**
 * Reglas de globales y propiedades por ámbito. Con `withSession` suman sessionStorage a todo src salvo
 * la lista blanca; sin él, los mismos ámbitos acotados a la lista blanca conservan las demás reglas.
 */
function scopedRules({ withSession }: { withSession: boolean }): Linter.Config[] {
  const scopes = [
    {
      files: ["src/**/*.{ts,tsx}"],
      ignores: ["src/core/api/**", "src/core/i18n/**"],
      allowed: ["src/pages/RouteError.tsx", "src/**/*.test.{ts,tsx}"],
      globals: [FETCH_GLOBAL, INTL_GLOBAL],
      properties: [...FETCH_PROPERTIES, ...LOCALE_PROPERTIES],
    },
    {
      files: ["src/core/api/**/*.{ts,tsx}"],
      ignores: [],
      allowed: ["src/core/api/**/*.test.{ts,tsx}"],
      globals: [INTL_GLOBAL],
      properties: LOCALE_PROPERTIES,
    },
    {
      files: ["src/core/i18n/**/*.{ts,tsx}"],
      ignores: [],
      allowed: ["src/core/i18n/**/*.test.{ts,tsx}"],
      globals: [FETCH_GLOBAL],
      properties: FETCH_PROPERTIES,
    },
  ];
  return scopes.map((scope) => ({
    files: withSession ? scope.files : scope.allowed,
    ignores: withSession ? [...scope.ignores, ...scope.allowed] : scope.ignores,
    rules: {
      "no-restricted-globals": ["error", ...scope.globals, ...(withSession ? [SESSION_GLOBAL] : [])],
      "no-restricted-properties": ["error", ...scope.properties, ...(withSession ? SESSION_PROPERTIES : [])],
    },
  }));
}

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
  ...scopedRules({ withSession: true }),
  // En flat config gana el último bloque que coincide: la lista blanca repite las listas sin sessionStorage.
  ...scopedRules({ withSession: false }),
  // no-restricted-syntax: el rol solo se compara en la matriz y la sesión; el acceso calculado a window,
  // globalThis o self (window[k]) no puede esquivar las reglas de globales salvo en la lista blanca de
  // sessionStorage. Tres bloques disjuntos porque en flat config gana el último que coincide.
  {
    files: ["src/**/*.{ts,tsx}"],
    ignores: [...ROLE_EXEMPT, ...SESSION_ALLOWED],
    rules: { "no-restricted-syntax": ["error", ...ROLE_SELECTORS, COMPUTED_GLOBAL_SELECTOR] },
  },
  {
    files: ROLE_EXEMPT,
    rules: { "no-restricted-syntax": ["error", COMPUTED_GLOBAL_SELECTOR] },
  },
  {
    files: SESSION_ALLOWED,
    ignores: ROLE_EXEMPT,
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
