"use client";

import { Button, PageHeader } from "@ta/ui";
import { Plus, Bot } from "lucide-react";
import Link from "next/link";

import { BotsTable } from "@/components/bots/bots-table";

export default function BotsPage() {
  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-5">
      <PageHeader
        title="Bots"
        description="Manage your autonomous trading bots — configure, start, pause or archive."
        actions={
          <Link href="/bots/new">
            <Button size="sm" className="gap-1.5">
              <Plus className="h-4 w-4" />
              New bot
            </Button>
          </Link>
        }
      />
      <BotsTable />
    </div>
  );
}
