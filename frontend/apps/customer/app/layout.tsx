import type { Metadata } from "next";
import type { ReactNode } from "react";

import "@ta/ui/styles.css";
import "./globals.css";

import { Providers } from "./providers";

export const metadata: Metadata = {
  title: "lucrandos - Dashboard",
  description: "lucrandos customer dashboard",
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
