import type { Metadata } from "next";
import type { ReactNode } from "react";

import "@ta/ui/styles.css";
import "./globals.css";

export const metadata: Metadata = {
  title: "lucrandos",
  description: "lucrandos multi-agent AI trading platform",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="min-h-screen bg-background font-sans antialiased">{children}</body>
    </html>
  );
}
