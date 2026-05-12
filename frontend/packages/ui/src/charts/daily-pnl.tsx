"use client";

import {
  Bar, BarChart, CartesianGrid, Cell,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";

import { Skeleton } from "../primitives/skeleton";

export interface DailyPnLPoint {
  date: string;
  pnl:  number;
}

interface DailyPnLChartProps {
  data:     DailyPnLPoint[];
  loading?: boolean;
  height?:  number;
}

const TOOLTIP_STYLE = {
  backgroundColor: "hsl(220 16% 9%)",
  border:          "1px solid hsl(220 16% 20%)",
  borderRadius:    "10px",
  fontSize:        12,
  color:           "hsl(210 30% 94%)",
  boxShadow:       "0 8px 32px rgba(0,0,0,0.5)",
  padding:         "8px 12px",
} as const;

const GREEN = "hsl(158 72% 42%)";
const RED   = "hsl(0 72% 55%)";

export function DailyPnLChart({ data, loading, height = 220 }: DailyPnLChartProps) {
  if (loading) return <Skeleton className="w-full" style={{ height }} />;
  if (data.length === 0) return null;

  return (
    <div style={{ width: "100%", height }}>
      <ResponsiveContainer>
        <BarChart data={data} margin={{ top: 8, right: 4, left: 0, bottom: 0 }}>
          <CartesianGrid
            strokeDasharray="2 4"
            stroke="hsl(220 16% 18%)"
            vertical={false}
            strokeOpacity={0.6}
          />
          <XAxis
            dataKey="date"
            stroke="hsl(215 16% 40%)"
            fontSize={10}
            tickLine={false}
            axisLine={false}
            tick={{ fill: "hsl(215 16% 40%)" }}
          />
          <YAxis
            stroke="hsl(215 16% 40%)"
            fontSize={10}
            tickLine={false}
            axisLine={false}
            width={52}
            tick={{ fill: "hsl(215 16% 40%)" }}
            tickFormatter={(v) => `$${Number(v).toLocaleString("en", { notation: "compact" })}`}
          />
          <Tooltip
            contentStyle={TOOLTIP_STYLE}
            labelStyle={{ color: "hsl(215 16% 55%)", marginBottom: 4, fontSize: 11 }}
            formatter={(v) => [`${(Number(v) >= 0 ? "+" : "")}$${Math.abs(Number(v)).toFixed(2)}`, "P&L"]}
            cursor={{ fill: "hsl(215 20% 20%)", opacity: 0.4 }}
          />
          <Bar dataKey="pnl" radius={[4, 4, 0, 0]} maxBarSize={28}>
            {data.map((d, i) => (
              <Cell key={`c-${i}`} fill={d.pnl >= 0 ? GREEN : RED} fillOpacity={0.9} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
