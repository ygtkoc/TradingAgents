"use client";

import { cn } from "@ta/utils";
import {
  Activity, Bell, Bot, CandlestickChart,
  GaugeCircle, KeyRound, ListChecks, Send, Sparkles, Wallet, Settings,
  TrendingUp,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { usePaperAccount } from "@/lib/hooks/queries/use-paper-account";
import { useBots } from "@/lib/hooks/queries/use-bots";

interface NavItem {
  href:    string;
  label:   string;
  icon:    typeof Activity;
  badge?:  () => React.ReactNode;
}

const PRIMARY: NavItem[] = [
  { href: "/dashboard", label: "Dashboard", icon: GaugeCircle },
];

const TRADING: NavItem[] = [
  { href: "/paper",  label: "Paper trading", icon: Sparkles },
  { href: "/live",   label: "Live trading",  icon: Wallet },
  { href: "/trades", label: "Trades",        icon: CandlestickChart },
];

const SYSTEM: NavItem[] = [
  { href: "/bots",          label: "Bots",          icon: Bot },
  { href: "/telegram",      label: "Telegram",      icon: Send },
  { href: "/decisions",     label: "Decisions",     icon: ListChecks },
  { href: "/notifications", label: "Notifications", icon: Bell },
];

const SETTINGS_NAV: NavItem[] = [
  { href: "/settings/exchanges", label: "Exchanges", icon: KeyRound },
  { href: "/settings",           label: "Settings",  icon: Settings },
];

function isActive(pathname: string | null, href: string): boolean {
  if (!pathname) return false;
  if (href === "/dashboard") return pathname === href;
  return pathname === href || pathname.startsWith(`${href}/`);
}

function NavLink({ href, label, icon: Icon, badge }: NavItem) {
  const pathname = usePathname();
  const active   = isActive(pathname, href);

  return (
    <Link
      href={href}
      className={cn(
        "group relative flex items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-[13px] font-medium transition-all duration-150",
        active
          ? [
              "bg-primary/10 text-primary",
              "before:absolute before:left-0 before:top-1/2 before:-translate-y-1/2",
              "before:h-4 before:w-[3px] before:rounded-r-full before:bg-primary",
            ]
          : "text-muted-foreground hover:bg-white/[0.04] hover:text-foreground",
      )}
    >
      <Icon
        className={cn(
          "h-4 w-4 shrink-0 transition-colors",
          active ? "text-primary" : "text-muted-foreground/70 group-hover:text-foreground",
        )}
      />
      <span className="flex-1 truncate">{label}</span>
      {badge ? badge() : null}
    </Link>
  );
}

function Section({ title, items }: { title: string; items: NavItem[] }) {
  return (
    <div className="space-y-0.5">
      <div className="mb-1.5 mt-4 px-2.5 text-[10px] font-semibold uppercase tracking-[0.15em] text-muted-foreground/40">
        {title}
      </div>
      {items.map((item) => (
        <NavLink key={item.href} {...item} />
      ))}
    </div>
  );
}

/**
 * Live status footer — shows paper account status + active bot count.
 * Updates in realtime via the polling hooks.
 */
function StatusFooter() {
  const acct = usePaperAccount();
  const bots = useBots();

  const status     = acct.data?.status ?? "inactive";
  const activeBots = (bots.data ?? []).filter((b) => b.mode === "paper" && !b.is_archived).length;
  const isLive     = status === "active";

  return (
    <div className="mx-2 mb-2 rounded-xl border border-border/40 bg-white/[0.02] p-3 text-[11px]">
      <div className="flex items-center gap-2">
        {isLive ? (
          <span className="relative flex h-2 w-2 shrink-0">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-success opacity-60" />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-success" />
          </span>
        ) : (
          <span className="h-2 w-2 shrink-0 rounded-full bg-muted-foreground/30" />
        )}
        <span className={cn("font-medium", isLive ? "text-success" : "text-muted-foreground")}>
          Paper {isLive ? "live" : status}
        </span>
      </div>
      {activeBots > 0 ? (
        <div className="mt-1 flex items-center gap-1 text-muted-foreground/60">
          <TrendingUp className="h-3 w-3" />
          <span>{activeBots} bot{activeBots !== 1 ? "s" : ""} running</span>
        </div>
      ) : (
        <div className="mt-1 text-muted-foreground/40">No active bots</div>
      )}
    </div>
  );
}

export function Sidebar() {
  return (
    <nav className="flex h-full flex-col overflow-hidden">
      {/* ── Logo / Brand ─────────────────────────────────────────────────── */}
      <div className="flex items-center gap-2.5 border-b border-border/30 px-3.5 py-4">
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-primary/15 ring-1 ring-primary/20">
          <Activity className="h-4 w-4 text-primary" />
        </div>
        <div className="min-w-0 leading-tight">
          <div className="truncate text-[13px] font-bold tracking-tight text-foreground">
            lucrandos
          </div>
          <div className="text-[10px] text-muted-foreground/60">Multi-agent AI</div>
        </div>
      </div>

      {/* ── Nav sections ─────────────────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto px-2 py-1">
        <Section title="Overview"  items={PRIMARY} />
        <Section title="Trading"   items={TRADING} />
        <Section title="System"    items={SYSTEM} />
        <Section title="Settings"  items={SETTINGS_NAV} />
      </div>

      {/* ── Status footer ────────────────────────────────────────────────── */}
      <StatusFooter />
    </nav>
  );
}
