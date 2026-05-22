import type { Metadata } from "next";
import type { ReactNode } from "react";

import "@ta/ui/styles.css";
import "./globals.css";

import { Providers } from "./providers";

export const metadata: Metadata = {
  title: "lucrandos - Admin",
  description: "lucrandos platform operations dashboard",
  // Don't index admin
  robots: { index: false, follow: false },
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
