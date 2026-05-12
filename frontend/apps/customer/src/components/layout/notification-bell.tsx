"use client";

import { Button } from "@ta/ui";
import { Bell } from "lucide-react";
import Link from "next/link";

import { useUnreadNotificationCount } from "@/lib/hooks/queries/use-notifications";

export function NotificationBell() {
  const { data: count } = useUnreadNotificationCount();
  const unread = count ?? 0;

  return (
    <Link href="/notifications" aria-label={`Notifications, ${unread} unread`}>
      <Button variant="ghost" size="icon" className="relative">
        <Bell className="h-4 w-4" />
        {unread > 0 ? (
          <span className="absolute -right-1 -top-1 flex h-4 min-w-[1rem] items-center justify-center rounded-full bg-destructive px-1 text-[10px] font-bold leading-none text-destructive-foreground">
            {unread > 99 ? "99+" : unread}
          </span>
        ) : null}
      </Button>
    </Link>
  );
}
