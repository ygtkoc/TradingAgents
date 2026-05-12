/**
 * Shared Tailwind preset. Each app extends this in its own tailwind.config.ts
 * and adds its own `content` globs.
 */
const animate = require("tailwindcss-animate");

/** @type {import("tailwindcss").Config} */
module.exports = {
  darkMode: ["class"],
  theme: {
    extend: {
      colors: {
        border:     "hsl(var(--border))",
        input:      "hsl(var(--input))",
        ring:       "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",

        primary: {
          DEFAULT:   "hsl(var(--primary))",
          foreground:"hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT:   "hsl(var(--secondary))",
          foreground:"hsl(var(--secondary-foreground))",
        },
        muted: {
          DEFAULT:   "hsl(var(--muted))",
          foreground:"hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT:   "hsl(var(--accent))",
          foreground:"hsl(var(--accent-foreground))",
        },
        destructive: {
          DEFAULT:   "hsl(var(--destructive))",
          foreground:"hsl(var(--destructive-foreground))",
        },
        success: {
          DEFAULT:   "hsl(var(--success))",
          foreground:"hsl(var(--success-foreground))",
        },
        warning: {
          DEFAULT:   "hsl(var(--warning))",
          foreground:"hsl(var(--warning-foreground))",
        },
        card: {
          DEFAULT:   "hsl(var(--card))",
          foreground:"hsl(var(--card-foreground))",
        },
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
      fontFamily: {
        sans: ["var(--font-sans)", "ui-sans-serif", "system-ui"],
        mono: ["var(--font-mono)", "ui-monospace"],
      },
      keyframes: {
        shimmer: {
          "0%":   { backgroundPosition: "-200% 0" },
          "100%": { backgroundPosition:  "200% 0" },
        },
        "pulse-ring": {
          "0%":   { boxShadow: "0 0 0 0 hsl(158 72% 42% / 0.6)" },
          "70%":  { boxShadow: "0 0 0 6px hsl(158 72% 42% / 0)" },
          "100%": { boxShadow: "0 0 0 0 hsl(158 72% 42% / 0)" },
        },
      },
      animation: {
        shimmer: "shimmer 1.8s ease-in-out infinite",
        "pulse-ring": "pulse-ring 2s cubic-bezier(0.455,0.03,0.515,0.955) infinite",
      },
    },
  },
  plugins: [animate],
};
