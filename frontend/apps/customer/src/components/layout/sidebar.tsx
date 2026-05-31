"use client";

import { cn } from "@ta/utils";
import {
  Activity,
  Bell,
  Bot,
  CandlestickChart,
  CircuitBoard,
  GaugeCircle,
  KeyRound,
  ListChecks,
  RadioTower,
  Send,
  Settings,
  ShieldCheck,
  Wallet,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { useBots } from "@/lib/hooks/queries/use-bots";
import { usePaperAccount } from "@/lib/hooks/queries/use-paper-account";

interface NavItem {
  href: string;
  label: string;
  icon: typeof Activity;
}

const NAV_SECTIONS: { title: string; items: NavItem[] }[] = [
  {
    title: "Command",
    items: [{ href: "/dashboard", label: "System overview", icon: GaugeCircle }],
  },
  {
    title: "Trading",
    items: [
      { href: "/paper", label: "Paper engine", icon: CircuitBoard },
      { href: "/live", label: "Live gates", icon: Wallet },
      { href: "/markets", label: "Markets", icon: CandlestickChart },
      { href: "/trades", label: "Positions", icon: CandlestickChart },
    ],
  },
  {
    title: "Intelligence",
    items: [
      { href: "/bots", label: "Agent fleet", icon: Bot },
      { href: "/decisions", label: "Decision ledger", icon: ListChecks },
      { href: "/telegram", label: "Signal intake", icon: Send },
      { href: "/notifications", label: "Event stream", icon: Bell },
    ],
  },
  {
    title: "Controls",
    items: [
      { href: "/settings/exchanges", label: "Exchange vault", icon: KeyRound },
      { href: "/settings", label: "Risk policy", icon: Settings },
    ],
  },
];

function isActive(pathname: string | null, href: string): boolean {
  if (!pathname) return false;
  if (href === "/dashboard") return pathname === href;
  return pathname === href || pathname.startsWith(`${href}/`);
}

function NavLink({ href, label, icon: Icon }: NavItem) {
  const pathname = usePathname();
  const active = isActive(pathname, href);

  return (
    <Link
      href={href}
      className={cn(
        "group relative flex items-center gap-3 rounded-md px-3 py-2 text-[13px] font-medium transition-all duration-150",
        active
          ? "bg-primary/12 text-foreground shadow-[inset_0_0_0_1px_hsl(var(--primary)/0.18)]"
          : "text-muted-foreground hover:bg-white/[0.045] hover:text-foreground",
      )}
    >
      <span
        className={cn(
          "flex h-7 w-7 shrink-0 items-center justify-center rounded-md border transition-all",
          active
            ? "border-primary/35 bg-primary/15 text-primary"
            : "border-border/50 bg-card/45 text-muted-foreground/75 group-hover:border-border group-hover:text-foreground",
        )}
      >
        <Icon className="h-3.5 w-3.5" />
      </span>
      <span className="min-w-0 flex-1 truncate">{label}</span>
      {active ? <span className="h-1.5 w-1.5 rounded-full bg-primary shadow-[0_0_14px_hsl(var(--primary)/0.8)]" /> : null}
    </Link>
  );
}

function StatusFooter() {
  const account = usePaperAccount();
  const bots = useBots();
  const status = account.data?.status ?? "inactive";
  const activeBots = (bots.data ?? []).filter((bot) => bot.mode === "paper" && !bot.is_archived).length;
  const isLive = status === "active";

  return (
    <div className="mx-3 mb-3 rounded-lg border border-border/60 bg-card/45 p-3 shadow-[inset_0_1px_0_rgba(255,255,255,0.035)]">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className={cn("h-2 w-2 rounded-full", isLive ? "bg-success shadow-[0_0_16px_hsl(var(--success)/0.65)]" : "bg-muted-foreground/35")} />
          <span className={cn("text-[12px] font-semibold", isLive ? "text-success" : "text-muted-foreground")}>
            Paper {isLive ? "autonomous" : status}
          </span>
        </div>
        <RadioTower className="h-3.5 w-3.5 text-muted-foreground/45" />
      </div>
      <div className="mt-2 grid grid-cols-2 gap-2 text-[11px]">
        <div className="rounded-md border border-border/45 bg-background/45 px-2 py-1.5">
          <div className="text-muted-foreground/55">Agents</div>
          <div className="font-semibold text-foreground">{activeBots}</div>
        </div>
        <div className="rounded-md border border-border/45 bg-background/45 px-2 py-1.5">
          <div className="text-muted-foreground/55">Safety</div>
          <div className="font-semibold text-success">armed</div>
        </div>
      </div>
    </div>
  );
}

export function Sidebar() {
  return (
    <nav className="flex h-full flex-col overflow-hidden">
      <div className="border-b border-border/55 px-4 py-4">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg border border-primary/30 bg-primary/12 shadow-[0_0_24px_hsl(var(--primary)/0.12)]">
            <Activity className="h-5 w-5 text-primary" />
          </div>
          <div className="min-w-0">
            <div className="truncate text-[15px] font-semibold tracking-[0] text-foreground">
              lucrandos
            </div>
            <div className="flex items-center gap-1.5 text-[10px] font-medium uppercase tracking-[0.16em] text-muted-foreground">
              <ShieldCheck className="h-3 w-3 text-success" />
              AI trading OS
            </div>
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-3 py-3">
        {NAV_SECTIONS.map((section) => (
          <div key={section.title} className="mb-4 space-y-1">
            <div className="px-3 pb-1 text-[10px] font-semibold uppercase tracking-[0.16em] text-muted-foreground/55">
              {section.title}
            </div>
            {section.items.map((item) => (
              <NavLink key={item.href} {...item} />
            ))}
          </div>
        ))}
      </div>

      <StatusFooter />
    </nav>
  );
}
