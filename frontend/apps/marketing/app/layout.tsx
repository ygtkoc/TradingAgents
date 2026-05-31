import type { Metadata } from "next";
import type { ReactNode } from "react";

import "@ta/ui/styles.css";
import "./globals.css";

const siteUrl = "https://lucrandos.com";
const title = "Lucrandos AI Trading System";
const description =
  "Lucrandos is a multi-agent AI trading system for crypto market decisions, paper trading, risk controls, live decision review, and automated trade lifecycle monitoring.";

export const metadata: Metadata = {
  metadataBase: new URL(siteUrl),
  applicationName: "Lucrandos",
  title: {
    default: title,
    template: "%s | Lucrandos",
  },
  description,
  keywords: [
    "AI trading system",
    "AI trading platform",
    "multi-agent trading",
    "crypto trading AI",
    "automated trading system",
    "paper trading platform",
    "trading agents",
    "risk managed trading",
    "algorithmic trading",
    "crypto decision engine",
    "Lucrandos",
  ],
  authors: [{ name: "Lucrandos" }],
  creator: "Lucrandos",
  publisher: "Lucrandos",
  category: "finance",
  classification: "AI trading software",
  alternates: {
    canonical: "/",
  },
  openGraph: {
    type: "website",
    locale: "en_US",
    url: siteUrl,
    siteName: "Lucrandos",
    title,
    description,
    images: [
      {
        url: "/opengraph-image",
        width: 1200,
        height: 630,
        alt: "Lucrandos AI Trading System live decision dashboard",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title,
    description,
    images: ["/opengraph-image"],
  },
  robots: {
    index: true,
    follow: true,
    googleBot: {
      index: true,
      follow: true,
      "max-image-preview": "large",
      "max-snippet": -1,
      "max-video-preview": -1,
    },
  },
  icons: {
    icon: "/icon.svg",
    apple: "/apple-icon.svg",
  },
  manifest: "/manifest.webmanifest",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="min-h-screen bg-background font-sans antialiased">{children}</body>
    </html>
  );
}
