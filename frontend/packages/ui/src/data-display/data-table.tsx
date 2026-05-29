"use client";

import {
  flexRender,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type SortingState,
} from "@tanstack/react-table";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { useState, type ReactNode } from "react";

import { cn } from "@ta/utils";

import { Skeleton } from "../primitives/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "../primitives/table";

interface DataTableProps<TData> {
  columns:     ColumnDef<TData, unknown>[];
  data:        TData[];
  loading?:    boolean;
  empty?:      ReactNode;
  onRowClick?: (row: TData) => void;
  rowClassName?: (row: TData) => string;
  pageSize?:   number;
}

export function DataTable<TData>({
  columns,
  data,
  loading,
  empty,
  onRowClick,
  rowClassName,
  pageSize = 25,
}: DataTableProps<TData>) {
  const [sorting, setSorting] = useState<SortingState>([]);

  const table = useReactTable({
    data,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel:       getCoreRowModel(),
    getSortedRowModel:     getSortedRowModel(),
    getFilteredRowModel:   getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    initialState: { pagination: { pageSize } },
  });

  return (
    <div className="surface-panel overflow-hidden rounded-lg">
      <Table>
        <TableHeader>
          {table.getHeaderGroups().map((hg) => (
            <TableRow
              key={hg.id}
              className="border-b border-border/50 bg-white/[0.025] hover:bg-transparent"
            >
              {hg.headers.map((header) => (
                <TableHead
                  key={header.id}
                  className="py-3 text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground/70"
                >
                  {header.isPlaceholder
                    ? null
                    : flexRender(header.column.columnDef.header, header.getContext())}
                </TableHead>
              ))}
            </TableRow>
          ))}
        </TableHeader>
        <TableBody>
          {loading ? (
            Array.from({ length: 5 }).map((_, i) => (
              <TableRow key={`s-${i}`} className="border-b border-border/20 hover:bg-transparent">
                {columns.map((_c, j) => (
                  <TableCell key={`s-${i}-${j}`} className="py-3">
                    <Skeleton className="h-4 w-full rounded-md" />
                  </TableCell>
                ))}
              </TableRow>
            ))
          ) : table.getRowModel().rows.length === 0 ? (
            <TableRow className="hover:bg-transparent">
              <TableCell colSpan={columns.length} className="py-2">
                {empty ?? (
                  <div className="py-8 text-center text-[13px] text-muted-foreground/50">
                    No results.
                  </div>
                )}
              </TableCell>
            </TableRow>
          ) : (
            table.getRowModel().rows.map((row) => (
              <TableRow
                key={row.id}
                onClick={onRowClick ? () => onRowClick(row.original) : undefined}
                className={cn(
                  "border-b border-border/25 transition-colors",
                  "last:border-0",
                  onRowClick && "cursor-pointer hover:bg-primary/[0.035]",
                  rowClassName?.(row.original),
                )}
              >
                {row.getVisibleCells().map((cell) => (
                  <TableCell key={cell.id} className="py-3">
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </TableCell>
                ))}
              </TableRow>
            ))
          )}
        </TableBody>
      </Table>

      {/* Pagination */}
      {!loading && table.getPageCount() > 1 && (
        <div className="flex items-center justify-between border-t border-border/40 bg-white/[0.02] px-5 py-3">
          <span className="text-[11px] text-muted-foreground/60">
            Page {table.getState().pagination.pageIndex + 1} of {table.getPageCount()}
            <span className="ml-2 text-muted-foreground/40">
              ({data.length} total)
            </span>
          </span>
          <div className="flex items-center gap-1">
            <button
              type="button"
              className={cn(
                "flex h-7 w-7 items-center justify-center rounded-lg border border-border/60 bg-card/60 text-muted-foreground",
                "hover:border-border hover:text-foreground transition-colors",
                "disabled:cursor-not-allowed disabled:opacity-30",
              )}
              onClick={() => table.previousPage()}
              disabled={!table.getCanPreviousPage()}
            >
              <ChevronLeft className="h-3.5 w-3.5" />
            </button>
            <button
              type="button"
              className={cn(
                "flex h-7 w-7 items-center justify-center rounded-lg border border-border/60 bg-card/60 text-muted-foreground",
                "hover:border-border hover:text-foreground transition-colors",
                "disabled:cursor-not-allowed disabled:opacity-30",
              )}
              onClick={() => table.nextPage()}
              disabled={!table.getCanNextPage()}
            >
              <ChevronRight className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export type { ColumnDef };
