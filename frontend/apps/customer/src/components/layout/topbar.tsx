"use client";

import { Button, Sheet, SheetContent, SheetTrigger } from "@ta/ui";
import { Menu } from "lucide-react";

import { EnvironmentBadge } from "./environment-badge";
import { NotificationBell } from "./notification-bell";
import { PriceTicker } from "./price-ticker";
import { Sidebar } from "./sidebar";
import { UserMenu } from "./user-menu";

interface TopbarProps {
  email: string | null;
}

export function Topbar({ email }: TopbarProps) {
  return (
    <div className="flex w-full flex-col">
      <div className="flex h-14 w-full items-center gap-3">
        <Sheet>
          <SheetTrigger asChild>
            <Button variant="ghost" size="icon" className="md:hidden" aria-label="Open menu">
              <Menu className="h-4 w-4" />
            </Button>
          </SheetTrigger>
          <SheetContent side="left" className="w-[220px] border-border/50 bg-card/95 p-0 backdrop-blur-xl">
            <Sidebar />
          </SheetContent>
        </Sheet>

        <div className="flex flex-1 items-center gap-2.5">
          <EnvironmentBadge />
        </div>

        <div className="flex items-center gap-0.5">
          <NotificationBell />
          <UserMenu email={email} />
        </div>
      </div>

      <PriceTicker />
    </div>
  );
}
