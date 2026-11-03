"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export interface ChartPoint {
  period: string;
  revenue: number | null;
  profit: number | null;
}

/** Revenue and profit for full fiscal years. Values are plotted as reported. */
export function FinancialsChart({ data, unit }: { data: ChartPoint[]; unit: string }) {
  if (data.length === 0) return null;
  return (
    <figure className="w-full">
      <div className="h-64 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 8 }}>
            <CartesianGrid
              strokeDasharray="3 3"
              vertical={false}
              stroke="currentColor"
              opacity={0.15}
            />
            <XAxis dataKey="period" tick={{ fontSize: 12, fill: "currentColor" }} />
            <YAxis
              tick={{ fontSize: 12, fill: "currentColor" }}
              tickFormatter={(v: number) => v.toLocaleString("en-US")}
              width={72}
            />
            <Tooltip
              formatter={(v: number) => v.toLocaleString("en-US")}
              contentStyle={{ fontSize: 12 }}
            />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Bar
              dataKey="revenue"
              name="Revenue from operations"
              fill="#0369a1"
              radius={[3, 3, 0, 0]}
            />
            <Bar dataKey="profit" name="Profit after tax" fill="#059669" radius={[3, 3, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <figcaption className="mt-1 text-xs text-neutral-500 dark:text-neutral-400">
        {unit}. Full fiscal years only; part-year periods are in the table below.
      </figcaption>
    </figure>
  );
}
