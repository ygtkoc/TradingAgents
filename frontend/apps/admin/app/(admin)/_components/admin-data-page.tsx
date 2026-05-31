"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { Badge, Card, CardContent, Input, PageHeader, ProductPage } from "@ta/ui";

import { supabase } from "@/lib/supabase/client";

type Column = {
  key: string;
  label: string;
  format?: (value: unknown, row: Record<string, unknown>) => string;
};

type AdminDataPageProps = {
  columns: Column[];
  description: string;
  eyebrow: string;
  orderBy?: string;
  searchKeys?: string[];
  table: string;
  title: string;
};

export function AdminDataPage({
  columns,
  description,
  eyebrow,
  orderBy = "created_at",
  searchKeys = [],
  table,
  title,
}: AdminDataPageProps) {
  const [search, setSearch] = useState("");
  const query = useQuery({
    queryKey: ["admin-table", table, orderBy],
    queryFn: async () => {
      const { data, error } = await supabase
        .from(table)
        .select("*")
        .order(orderBy, { ascending: false })
        .limit(100);
      if (error) throw error;
      return (data ?? []) as Record<string, unknown>[];
    },
  });

  const rows = useMemo(() => query.data ?? [], [query.data]);
  const filtered = useMemo(() => {
    const needle = search.trim().toLowerCase();
    if (!needle) return rows;
    const keys = searchKeys.length ? searchKeys : columns.map((column) => column.key);
    return rows.filter((row) => keys.some((key) => String(row[key] ?? "").toLowerCase().includes(needle)));
  }, [columns, rows, search, searchKeys]);

  return (
    <ProductPage size="xl">
      <PageHeader eyebrow={eyebrow} title={title} description={description} />

      <div className="grid gap-3 md:grid-cols-4">
        <AdminStat label="Rows" value={String(rows.length)} />
        <AdminStat label="Filtered" value={String(filtered.length)} />
        <AdminStat label="Table" value={table} />
        <AdminStat label="Status" value={query.isError ? "error" : query.isLoading ? "loading" : "ready"} />
      </div>

      <Card className="overflow-hidden border-border/70 bg-card/70">
        <CardContent className="p-0">
          <div className="flex flex-col gap-3 border-b border-border/50 p-4 sm:flex-row sm:items-center sm:justify-between">
            <Input
              className="max-w-md"
              onChange={(event) => setSearch(event.target.value)}
              placeholder={`Search ${title.toLowerCase()}...`}
              value={search}
            />
            <Badge variant={query.isError ? "destructive" : "secondary"}>
              {query.isError ? "Read failed" : `${filtered.length} shown`}
            </Badge>
          </div>

          {query.isLoading ? (
            <div className="p-8 text-sm text-muted-foreground">Loading records...</div>
          ) : query.isError ? (
            <div className="p-8 text-sm text-destructive">{(query.error as Error).message}</div>
          ) : filtered.length === 0 ? (
            <div className="p-8 text-sm text-muted-foreground">No records found.</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[760px] text-left text-sm">
                <thead className="border-b border-border/50 bg-muted/20 text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
                  <tr>
                    {columns.map((column) => (
                      <th key={column.key} className="px-4 py-3 font-black">{column.label}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((row, index) => (
                    <tr key={String(row.id ?? index)} className="border-b border-border/35 transition-colors hover:bg-white/[0.035]">
                      {columns.map((column) => (
                        <td key={column.key} className="max-w-[280px] truncate px-4 py-3 text-muted-foreground">
                          {column.format ? column.format(row[column.key], row) : formatCell(row[column.key])}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </ProductPage>
  );
}

export function AdminStat({ label, value }: { label: string; value: string }) {
  return (
    <Card className="border-border/70 bg-card/70">
      <CardContent className="p-4">
        <div className="text-[10px] font-black uppercase tracking-[0.14em] text-muted-foreground">{label}</div>
        <div className="mt-1 truncate text-xl font-black text-foreground">{value}</div>
      </CardContent>
    </Card>
  );
}

export function formatDate(value: unknown) {
  if (!value) return "-";
  const date = new Date(String(value));
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString();
}

export function money(value: unknown) {
  const next = Number(value ?? 0);
  if (!Number.isFinite(next)) return "-";
  return `$${next.toLocaleString("en-US", { maximumFractionDigits: 2 })}`;
}

function formatCell(value: unknown) {
  if (value == null) return "-";
  if (typeof value === "boolean") return value ? "yes" : "no";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}
