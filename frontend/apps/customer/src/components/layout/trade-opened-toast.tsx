"use client";

import { queryKeys } from "@ta/query/keys";
import { cn, formatCurrency } from "@ta/utils";
import { useQueryClient } from "@tanstack/react-query";
import { BellRing, X } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { formatPrice } from "@/lib/format-price";
import { isDemoMode } from "@/lib/demo";
import { useCurrentUser } from "@/lib/hooks/queries/use-current-user";
import { supabase } from "@/lib/supabase/client";

interface ToastState {
  id: string;
  title: string;
  body: string;
  tradeId: string | null;
  symbol: string;
  direction: string;
  entryPrice: number | null;
  quantity: number | null;
  riskAmount: number | null;
}

export function TradeOpenedToast() {
  const router = useRouter();
  const qc = useQueryClient();
  const { data: user } = useCurrentUser();
  const [toast, setToast] = useState<ToastState | null>(null);
  const lastSeenId = useRef<string | null>(null);

  useEffect(() => {
    if (!user || isDemoMode) return;

    const ch = supabase
      .channel(`trade-opened-toast:${user.id}`)
      .on(
        "postgres_changes",
        {
          event: "INSERT",
          schema: "public",
          table: "notifications",
          filter: `user_id=eq.${user.id}`,
        },
        (payload) => {
          const row = payload.new as Record<string, unknown>;
          if (row.type !== "trade_opened") return;
          const id = String(row.id ?? "");
          if (!id || lastSeenId.current === id) return;
          lastSeenId.current = id;

          const metadata = (row.metadata as Record<string, unknown> | null) ?? {};
          const nextToast: ToastState = {
            id,
            title: String(row.title ?? "İşlem açıldı"),
            body: String(row.message ?? row.body ?? ""),
            tradeId: String(row.related_id ?? metadata.trade_id ?? "") || null,
            symbol: String(metadata.symbol ?? ""),
            direction: String(metadata.direction ?? ""),
            entryPrice: toNumber(metadata.entry_price),
            quantity: toNumber(metadata.quantity),
            riskAmount: toNumber(metadata.risk_amount),
          };

          setToast(nextToast);
          playDing();
          void qc.invalidateQueries({ queryKey: queryKeys.notifications.list(user.id) });
          void qc.invalidateQueries({ queryKey: queryKeys.notifications.unread(user.id) });
          void qc.invalidateQueries({ queryKey: queryKeys.trades.all() });
          window.setTimeout(() => {
            setToast((current) => current?.id === id ? null : current);
          }, 9000);
        },
      )
      .subscribe();

    return () => {
      void supabase.removeChannel(ch);
    };
  }, [qc, user]);

  if (!toast) return null;

  return (
    <div className="fixed bottom-5 right-5 z-50 w-[min(380px,calc(100vw-2rem))]">
      <button
        type="button"
        onClick={() => {
          if (toast.tradeId) router.push(`/trades/${toast.tradeId}`);
          setToast(null);
        }}
        className={cn(
          "w-full rounded-xl border border-primary/25 bg-background/95 p-4 text-left shadow-2xl backdrop-blur",
          "transition hover:border-primary/45 hover:bg-card",
        )}
      >
        <div className="flex items-start gap-3">
          <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary/12 text-primary">
            <BellRing className="h-4 w-4" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex items-start justify-between gap-2">
              <div className="text-[13px] font-bold text-foreground">{toast.title}</div>
              <X
                className="h-3.5 w-3.5 shrink-0 text-muted-foreground/60"
                onClick={(event) => {
                  event.stopPropagation();
                  setToast(null);
                }}
              />
            </div>
            <div className="mt-1 text-[12px] leading-relaxed text-muted-foreground">
              {toast.body}
            </div>
            <div className="mt-3 grid grid-cols-2 gap-2 text-[11px]">
              <ToastMetric label="Symbol" value={toast.symbol || "-"} />
              <ToastMetric label="Side" value={toast.direction ? toast.direction.toUpperCase() : "-"} />
              <ToastMetric label="Entry" value={toast.entryPrice != null ? formatPrice(toast.entryPrice) : "-"} />
              <ToastMetric label="1R" value={toast.riskAmount != null ? formatCurrency(toast.riskAmount) : "-"} />
            </div>
          </div>
        </div>
      </button>
    </div>
  );
}

function ToastMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-border/30 bg-card/45 px-2 py-1.5">
      <div className="text-[9px] font-semibold uppercase tracking-[0.1em] text-muted-foreground/55">{label}</div>
      <div className="mt-0.5 font-mono text-[11px] font-semibold text-foreground">{value}</div>
    </div>
  );
}

function playDing() {
  try {
    const AudioContextClass = window.AudioContext || (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!AudioContextClass) return;
    const ctx = new AudioContextClass();
    const now = ctx.currentTime;
    const gain = ctx.createGain();
    gain.gain.setValueAtTime(0.0001, now);
    gain.gain.exponentialRampToValueAtTime(0.18, now + 0.01);
    gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.55);
    gain.connect(ctx.destination);

    for (const [offset, frequency] of [[0, 880], [0.08, 1320]] as const) {
      const osc = ctx.createOscillator();
      osc.type = "sine";
      osc.frequency.setValueAtTime(frequency, now + offset);
      osc.connect(gain);
      osc.start(now + offset);
      osc.stop(now + offset + 0.32);
    }
    window.setTimeout(() => void ctx.close(), 900);
  } catch {
    // Browsers may block audio until the user interacts with the page.
  }
}

function toNumber(value: unknown): number | null {
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}
