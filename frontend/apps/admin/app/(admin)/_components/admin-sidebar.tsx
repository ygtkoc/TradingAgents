"use client";

import {
  Activity,
  AlertTriangle,
  Brain,
  ClipboardList,
  FileClock,
  Gauge,
  ListChecks,
  Lock,
  ScrollText,
  Settings,
  Shield,
  Users,
} from "lucide-react";
import { usePathname } from "next/navigation";

import { cn } from "@ta/utils";

const navSections = [
  {
    title: "Command",
    items: [
      { icon: Gauge, label: "Overview", href: "/overview" },
      { icon: Users, label: "Users", href: "/users" },
      { icon: Brain, label: "Trading brain", href: "/trading-brain" },
    ],
  },
  {
    title: "Trading",
    items: [
      { icon: Activity, label: "Trades", href: "/trades" },
      { icon: ListChecks, label: "Decisions", href: "/decisions" },
      { icon: ClipboardList, label: "Agent runs", href: "/agent-runs" },
      { icon: FileClock, label: "Reconciliation", href: "/reconciliation" },
    ],
  },
  {
    title: "Logs",
    items: [
      { icon: Shield, label: "Security logs", href: "/logs/security" },
      { icon: AlertTriangle, label: "Risk logs", href: "/logs/risk" },
      { icon: ScrollText, label: "Audit logs", href: "/logs/audit" },
    ],
  },
  {
    title: "System",
    items: [
      { icon: Settings, label: "Platform settings", href: "/system/platform-settings" },
      { icon: Lock, label: "Kill switch", href: "/operations/kill-switch" },
    ],
  },
];

export function AdminSidebar() {
  const pathname = usePathname();

  return (
    <nav className="flex min-h-full flex-col bg-[#0b1118] p-3 text-sm text-slate-200 sm:p-4">
      <div className="mb-4 border-b border-slate-800 pb-4">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md border border-blue-400/25 bg-blue-500/12 text-sm font-black text-blue-200">
            L
          </div>
          <div className="min-w-0">
            <div className="truncate text-[15px] font-semibold text-white">Lucrandos</div>
            <div className="text-[11px] font-medium text-slate-400">Admin console</div>
          </div>
        </div>
      </div>

      <div className="min-h-0 flex-1 space-y-5 overflow-y-auto pr-1">
        {navSections.map((section) => (
          <div key={section.title}>
            <div className="mb-2 px-2 text-[11px] font-semibold uppercase text-slate-500">
              {section.title}
            </div>
            <div className="space-y-1">
              {section.items.map((item) => {
                const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
                const Icon = item.icon;
                return (
                  <a
                    key={item.href}
                    className={cn(
                      "flex min-h-10 items-center gap-3 rounded-md px-3 py-2 text-[13px] font-medium transition-colors",
                      active
                        ? "border border-blue-400/30 bg-blue-500/16 text-white"
                        : "border border-transparent text-slate-300 hover:bg-slate-800/80 hover:text-white",
                    )}
                    href={item.href}
                  >
                    <Icon className={cn("h-4 w-4 shrink-0", active ? "text-blue-200" : "text-slate-500")} />
                    <span className="truncate">{item.label}</span>
                  </a>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </nav>
  );
}
