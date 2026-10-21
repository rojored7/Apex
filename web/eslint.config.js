// ESLint flat config del front de APEX (US-009 T11).
import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import globals from "globals";
import tseslint from "typescript-eslint";

export default tseslint.config(
  {
    // tests/lint/ guarda archivos de control que violan las reglas a propósito;
    // los ejercita tests/lint/lint-controls.test.ts por la API de Node.
    ignores: ["dist/**", "coverage/**", "node_modules/**", "playwright-report/**", "test-results/**", "tests/lint/*", "!tests/lint/lint-controls.test.ts"],
  },
  js.configs.recommended,
  ...tseslint.configs.strictTypeChecked,
  {
    languageOptions: {
      globals: { ...globals.browser, ...globals.node },
      parserOptions: {
        projectService: true,
        tsconfigRootDir: import.meta.dirname,
      },
    },
  },
  reactHooks.configs.flat.recommended,
  {
    // Nada de colores ni fuentes literales en estilos en línea: todo sale de tokens.css.
    files: ["**/*.{ts,tsx}"],
    rules: {
      "no-restricted-syntax": [
        "error",
        {
          selector: "JSXAttribute[name.name='style'] Literal[value=/#[0-9a-fA-F]{3,8}/]",
          message: "Color hex literal en style: usa una variable de tokens.css (var(--...)).",
        },
        {
          selector: "JSXAttribute[name.name='style'] Literal[value=/(rgba?|hsla?)[(]/]",
          message: "rgb()/hsl() literal en style: usa una variable de tokens.css (var(--...)).",
        },
        {
          selector: "JSXAttribute[name.name='style'] TemplateElement[value.raw=/#[0-9a-fA-F]{3,8}|(rgba?|hsla?)[(]/]",
          message: "Color literal en style: usa una variable de tokens.css (var(--...)).",
        },
        {
          selector: "JSXAttribute[name.name='style'] Property[key.name='fontFamily']",
          message: "fontFamily en style: la tipografía sale de tokens.css (var(--font-...) o var(--text-...)) en un CSS Module.",
        },
      ],
    },
  },
  {
    files: ["**/*.js"],
    ...tseslint.configs.disableTypeChecked,
  },
);
