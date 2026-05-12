import type { Config } from "tailwindcss";

const preset = require("@ta/ui/tailwind");

export default {
  presets: [preset],
  content: [
    "./app/**/*.{ts,tsx,mdx}",
    "./src/**/*.{ts,tsx}",
    "../../packages/ui/src/**/*.{ts,tsx}",
  ],
} satisfies Config;
