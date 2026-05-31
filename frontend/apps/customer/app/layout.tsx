import type { Metadata } from "next";
import type { ReactNode } from "react";

import "@ta/ui/styles.css";
import "./globals.css";

import { Providers } from "./providers";
import { PwaRegister } from "./pwa-register";

export const viewport = {
  themeColor: "#07090b",
  colorScheme: "dark",
};

export const metadata: Metadata = {
  metadataBase: new URL("https://customer.lucrandos.com"),
  applicationName: "Lucrandos",
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
  appleWebApp: {
    capable: true,
    title: "Lucrandos",
    statusBarStyle: "black-translucent",
  },
  formatDetection: {
    telephone: false,
  },
  icons: {
    icon: "/icon.svg",
    apple: "/apple-icon.svg",
  },
  manifest: "/manifest.webmanifest",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className="dark" suppressHydrationWarning>
      <body className="min-h-screen bg-background font-sans antialiased">
        <Providers>
          <PwaRegister />
          {children}
        </Providers>
      </body>
    </html>
  );
}
