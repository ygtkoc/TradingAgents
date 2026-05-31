import type { Metadata } from "next";
import type { ReactNode } from "react";

import "@ta/ui/styles.css";
import "./globals.css";

import { Providers } from "./providers";

export const metadata: Metadata = {
  metadataBase: new URL("https://admin.lucrandos.com"),
  title: {
    default: "Lucrandos Admin",
    template: "%s | Lucrandos Admin",
  },
  description:
    "Private Lucrandos operations dashboard for platform administration, queue monitoring, agent oversight, and trading system controls.",
  robots: {
    index: false,
    follow: false,
    nocache: true,
    googleBot: {
      index: false,
      follow: false,
      noimageindex: true,
    },
  },
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="min-h-screen bg-background font-sans antialiased">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
