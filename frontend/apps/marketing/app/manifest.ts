import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Lucrandos AI Trading System",
    short_name: "Lucrandos",
    description:
      "Multi-agent AI trading system for crypto decisions, paper trading, risk controls, and trade lifecycle monitoring.",
    start_url: "/",
    scope: "/",
    display: "standalone",
    background_color: "#07090b",
    theme_color: "#2dd4bf",
    categories: ["finance", "business", "productivity"],
    icons: [
      {
        src: "/icon.svg",
        sizes: "any",
        type: "image/svg+xml",
      },
      {
        src: "/apple-icon.svg",
        sizes: "180x180",
        type: "image/svg+xml",
        purpose: "any",
      },
    ],
  };
}
