"use client";

import {
  Avatar, AvatarFallback,
  Button,
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger,
} from "@ta/ui";
import { useRouter } from "next/navigation";

import { supabase } from "@/lib/supabase/client";

interface UserMenuProps {
  email: string | null;
}

function initials(email: string | null): string {
  if (!email) return "?";
  const name = email.split("@")[0] ?? "";
  return name.slice(0, 2).toUpperCase() || "?";
}

export function UserMenu({ email }: UserMenuProps) {
  const router = useRouter();

  const onSignOut = async () => {
    await supabase.auth.signOut();
    router.push("/sign-in");
    router.refresh();
  };

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" aria-label="User menu">
          <Avatar className="h-7 w-7">
            <AvatarFallback>{initials(email)}</AvatarFallback>
          </Avatar>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuLabel className="max-w-[14rem] truncate">
          {email ?? "Signed in"}
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={() => router.push("/settings/profile")}>
          Profile
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={() => router.push("/settings/security")}>
          Security
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={() => router.push("/settings")}>
          Settings
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={() => void onSignOut()}>
          Sign out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
