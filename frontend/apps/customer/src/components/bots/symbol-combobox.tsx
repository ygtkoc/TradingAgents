"use client";

import { Input, Skeleton } from "@ta/ui";
import { cn } from "@ta/utils";
import { Check, ChevronsUpDown, Search } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { useBinanceSymbols, type BinanceSymbol } from "@/lib/hooks/queries/use-binance-symbols";

interface Props {
  value: string;                         // internal symbol, e.g. "BTC/USDT"
  onChange: (internal: string) => void;
  placeholder?: string;
  /** Cap how many results render at once. */
  maxResults?: number;
}

/**
 * Searchable USDT-pair picker.
 *
 *   • Loads the full Binance USDT-spot universe once (24h cache).
 *   • Filters as you type by base asset OR by Binance symbol.
 *   • Shows a fallback message if the API call failed and only the static
 *     {BTC,ETH,SOL}/USDT trio is available.
 *   • Always returns the slashed form (`BTC/USDT`) so the rest of the app
 *     receives a single canonical format.
 */
export function SymbolCombobox({
  value,
  onChange,
  placeholder = "Search symbol — e.g. BTC, ETH, DOGE",
  maxResults = 100,
}: Props) {
  const { data: all, isLoading, isError } = useBinanceSymbols();
  const [open,   setOpen]   = useState(false);
  const [query,  setQuery]  = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const rootRef  = useRef<HTMLDivElement>(null);

  // Click-outside to close
  useEffect(() => {
    if (!open) return;
    const onDocClick = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    };
    window.addEventListener("mousedown", onDocClick);
    return () => window.removeEventListener("mousedown", onDocClick);
  }, [open]);

  const filtered = useMemo<BinanceSymbol[]>(() => {
    const list = all ?? [];
    if (!query.trim()) return list.slice(0, maxResults);
    const q = query.trim().toUpperCase();
    return list
      .filter((s) => s.base.includes(q) || s.binance.includes(q) || s.internal.includes(q))
      .slice(0, maxResults);
  }, [all, query, maxResults]);

  const hasFullList = (all?.length ?? 0) > 5;

  return (
    <div ref={rootRef} className="relative">
      {/* Trigger */}
      <button
        type="button"
        onClick={() => {
          setOpen((o) => !o);
          setTimeout(() => inputRef.current?.focus(), 0);
        }}
        className={cn(
          "flex h-10 w-full items-center justify-between rounded-md border border-input bg-background px-3 py-2 text-sm",
          "ring-offset-background focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2",
        )}
        aria-haspopup="listbox"
        aria-expanded={open}
      >
        <span className={cn("truncate font-mono", !value && "text-muted-foreground")}>
          {value || placeholder}
        </span>
        <ChevronsUpDown className="h-4 w-4 shrink-0 opacity-50" />
      </button>

      {/* Popover */}
      {open ? (
        <div className="absolute z-50 mt-1 w-full overflow-hidden rounded-md border bg-popover shadow-lg">
          <div className="flex items-center gap-2 border-b px-2 py-1.5">
            <Search className="h-3.5 w-3.5 text-muted-foreground" />
            <Input
              ref={inputRef}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={placeholder}
              className="h-8 border-0 px-1 text-sm shadow-none focus-visible:ring-0"
            />
            {!hasFullList && !isLoading ? (
              <span className="rounded bg-warning/10 px-1.5 py-0.5 text-[10px] text-warning">
                fallback list
              </span>
            ) : null}
          </div>

          <div className="max-h-72 overflow-y-auto">
            {isLoading ? (
              <div className="space-y-2 p-2">
                {Array.from({ length: 6 }).map((_, i) => (
                  <Skeleton key={i} className="h-6 w-full" />
                ))}
              </div>
            ) : isError && filtered.length === 0 ? (
              <div className="px-3 py-6 text-center text-xs text-muted-foreground">
                Binance API unreachable and no fallback symbols available.
              </div>
            ) : filtered.length === 0 ? (
              <div className="px-3 py-6 text-center text-xs text-muted-foreground">
                No symbols match &quot;{query}&quot;.
              </div>
            ) : (
              <ul role="listbox" className="py-1">
                {filtered.map((s) => {
                  const selected = value === s.internal;
                  return (
                    <li key={s.binance}>
                      <button
                        type="button"
                        role="option"
                        aria-selected={selected}
                        onClick={() => {
                          onChange(s.internal);
                          setOpen(false);
                          setQuery("");
                        }}
                        className={cn(
                          "flex w-full items-center justify-between gap-2 px-3 py-1.5 text-sm",
                          "text-left transition-colors hover:bg-accent hover:text-accent-foreground",
                          selected && "bg-accent/50",
                        )}
                      >
                        <span className="flex items-baseline gap-2">
                          <span className="font-mono">{s.internal}</span>
                          <span className="text-[10px] text-muted-foreground">{s.base}</span>
                        </span>
                        {selected ? <Check className="h-3.5 w-3.5" /> : null}
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>

          {!isLoading && filtered.length === maxResults ? (
            <div className="border-t px-3 py-1.5 text-[10px] text-muted-foreground">
              Showing first {maxResults}. Refine your search to see more.
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
