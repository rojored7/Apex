// ESLint flat config del front de APEX (US-009 T11).
import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import globals from "globals";
import tseslint from "typescript-eslint";

export default tseslint.config(
  {
    // tests/lint/ guarda archivos de control que violan las reglas a propósito;
    // los ejercita tests/lint/lint-controls.test.ts por la API de Node.
    ignores: ["dist/**", "coverage/**", "node_modules/**", "playwright-report/**", "test-results/**", "tests/lint/**", "!tests/lint/lint-controls.test.ts"],
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
    files: ["**/*.js"],
    ...tseslint.configs.disableTypeChecked,
  },
);
