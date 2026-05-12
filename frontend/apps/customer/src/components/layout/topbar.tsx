"use client";

import { Button, Sheet, SheetContent, SheetTrigger } from "@ta/ui";
import { Menu } from "lucide-react";

import { EnvironmentBadge } from "./environment-badge";
import { NotificationBell } from "./notification-bell";
import { Sidebar } from "./sidebar";
import { UserMenu } from "./user-menu";

interface TopbarProps {
  email: string | null;
}

export function Topbar({ email }: TopbarProps) {
  return (
    <div className="flex w-full items-center gap-3">
      {/* Mobile sidebar trigger */}
      <Sheet>
        <SheetTrigger asChild>
          <Button variant="ghost" size="icon" className="md:hidden" aria-label="Open menu">
            <Menu className="h-4 w-4" />
          </Button>
        </SheetTrigger>
        <SheetContent side="left" className="w-[220px] p-0 border-border/50 bg-card/95 backdrop-blur-xl">
          <Sidebar />
        </SheetContent>
      </Sheet>

      {/* Left side — breadcrumb / env badge area */}
      <div className="flex flex-1 items-center gap-2.5">
        <EnvironmentBadge />
      </div>

      {/* Right side — actions */}
      <div className="flex items-center gap-0.5">
        <NotificationBell />
        <UserMenu email={email} />
      </div>
    </div>
  );
}
