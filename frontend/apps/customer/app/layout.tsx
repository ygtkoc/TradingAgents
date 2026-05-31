import type { Metadata } from "next";
import type { ReactNode } from "react";

import "@ta/ui/styles.css";
import "./globals.css";

import { Providers } from "./providers";

export const metadata: Metadata = {
  metadataBase: new URL("https://customer.lucrandos.com"),
  title: {
    default: "Lucrandos Command Center",
    template: "%s | Lucrandos Command Center",
  },
  description:
    "Secure Lucrandos customer dashboard for AI trading decisions, paper positions, wallet status, manual approvals, and trade lifecycle controls.",
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
    <html lang="en" className="dark" suppressHydrationWarning>
      <body className="min-h-screen bg-background font-sans antialiased">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
