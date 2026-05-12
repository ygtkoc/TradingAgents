"use client";

import {
  Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";

import { Skeleton } from "../primitives/skeleton";

export interface EquityPoint {
  date:   string;
  equity: number;
}

interface EquityCurveProps {
  data:     EquityPoint[];
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

export function EquityCurve({ data, loading, height = 260 }: EquityCurveProps) {
  if (loading) return <Skeleton className="w-full" style={{ height }} />;
  if (data.length === 0) return null;

  const last  = data[data.length - 1]?.equity ?? 0;
  const first = data[0]?.equity ?? 0;
  const isPositive = last >= first;
  const color = isPositive ? "hsl(158 72% 42%)" : "hsl(0 72% 55%)";
  const gradId = isPositive ? "equityFillPos" : "equityFillNeg";

  return (
    <div style={{ width: "100%", height }}>
      <ResponsiveContainer>
        <AreaChart data={data} margin={{ top: 8, right: 4, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%"   stopColor={color} stopOpacity={0.25} />
              <stop offset="100%" stopColor={color} stopOpacity={0} />
            </linearGradient>
          </defs>
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
            formatter={(v) => [`$${Number(v).toFixed(2)}`, "Equity"]}
            cursor={{ stroke: color, strokeWidth: 1, strokeDasharray: "4 2" }}
          />
          <Area
            type="monotone"
            dataKey="equity"
            stroke={color}
            strokeWidth={2}
            fillOpacity={1}
            fill={`url(#${gradId})`}
            dot={false}
            activeDot={{ r: 4, fill: color, stroke: "hsl(220 16% 9%)", strokeWidth: 2 }}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
