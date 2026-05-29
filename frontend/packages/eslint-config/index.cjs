/**
 * Base ESLint config — shared by all apps and libraries.
 *
 * SECURITY:
 *   - `no-restricted-imports` blocks the Supabase service-role module from
 *     ever being imported by app/library code. Service-role usage is
 *     reserved for backend Edge Functions only.
 */
/** @type {import("eslint").Linter.Config} */
module.exports = {
  root: false,
  parser: "@typescript-eslint/parser",
  parserOptions: {
    ecmaVersion: 2022,
    sourceType: "module",
    ecmaFeatures: { jsx: true },
  },
  plugins: ["@typescript-eslint", "import"],
  extends: [
    "eslint:recommended",
    "plugin:@typescript-eslint/recommended",
    "plugin:import/recommended",
    "plugin:import/typescript",
    "prettier",
  ],
  settings: {
    "import/resolver": {
      node: true,
    },
  },
  rules: {
    "@typescript-eslint/no-unused-vars": "off",
    "@typescript-eslint/consistent-type-imports": "off",
    "@typescript-eslint/no-explicit-any": "off",
    "prefer-const": "off",
    "import/order": "off",
    "import/no-unresolved": "off",
    "import/namespace": "off",
    "import/export": "off",
    "import/no-duplicates": "off",

    // ── SECURITY: forbid any frontend import of the service-role module ──
    "no-restricted-imports": [
      "error",
      {
        paths: [
          {
            name: "@ta/supabase/service-role",
            message:
              "Service-role keys must NEVER be used in frontend code. Use Edge Functions instead.",
          },
          {
            name: "@supabase/supabase-js",
            importNames: ["createClient"],
            message:
              "Do not call createClient directly. Use @ta/supabase/browser, @ta/supabase/server, or @ta/supabase/middleware.",
          },
        ],
        patterns: [
          {
            group: ["**/service-role*"],
            message:
              "Service-role keys must NEVER be used in frontend code. Use Edge Functions instead.",
          },
        ],
      },
    ],
  },
  ignorePatterns: [
    "node_modules/",
    ".next/",
    "dist/",
    "build/",
    ".turbo/",
    "next-env.d.ts",
    "*.config.js",
    "*.config.cjs",
    "*.config.mjs",
  ],
};
