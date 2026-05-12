import type { Config } from "tailwindcss";

const preset = require("@ta/ui/tailwind");

export default {
  presets: [preset],
  content: [
    "./app/**/*.{ts,tsx,mdx}",
    "../../packages/ui/src/**/*.{ts,tsx}",
  ],
} satisfies Config;
