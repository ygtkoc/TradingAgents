"use client";

import { Button, Sheet, SheetContent, SheetTrigger } from "@ta/ui";
import { Activity, Menu, ShieldCheck } from "lucide-react";

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
      <div className="flex h-16 w-full items-center gap-3">
        <Sheet>
          <SheetTrigger asChild>
            <Button variant="ghost" size="icon" className="md:hidden" aria-label="Open menu">
              <Menu className="h-4 w-4" />
            </Button>
          </SheetTrigger>
          <SheetContent side="left" className="w-[256px] border-border/60 bg-background/96 p-0 backdrop-blur-2xl">
            <Sidebar />
          </SheetContent>
        </Sheet>

        <div className="flex flex-1 items-center gap-2.5">
          <div className="hidden items-center gap-2 rounded-md border border-border/50 bg-card/45 px-3 py-2 text-[12px] text-muted-foreground sm:flex">
            <Activity className="h-3.5 w-3.5 text-primary" />
            <span className="font-medium text-foreground">Autonomous market intelligence</span>
            <span className="text-muted-foreground/45">/</span>
            <ShieldCheck className="h-3.5 w-3.5 text-success" />
            <span>risk gated</span>
          </div>
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
