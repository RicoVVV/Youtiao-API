"use client";

import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import {
  fmtBps,
  fmtClock,
  fmtDateTime,
  fmtPercent,
  type ServerTrendSeries,
  type ServerTrendUnit,
} from "./types";

/** 各序列配色（key 稳定，由后端契约保证） */
const SERIES_COLORS: Record<string, string> = {
  "cpu.usage_percent": "#4c6fff",
  "memory.usage_percent": "#7c5cff",
  "swap.usage_percent": "#f59e0b",
  "load.load1": "#10b981",
  "load.load5": "#06b6d4",
  "load.load15": "#8b5cf6",
  "disk.usage_percent": "#ef4444",
  "network.rx_rate_bps": "#0ea5e9",
  "network.tx_rate_bps": "#f97316",
};

const FALLBACK_COLORS = ["#4c6fff", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6"];

/** 序列 key → i18n 词条名（key 含点号不能直接当 i18n 路径） */
const SERIES_LABEL_KEYS: Record<string, string> = {
  "cpu.usage_percent": "cpu",
  "memory.usage_percent": "memory",
  "swap.usage_percent": "swap",
  "load.load1": "load1",
  "load.load5": "load5",
  "load.load15": "load15",
  "disk.usage_percent": "disk",
  "network.rx_rate_bps": "rx",
  "network.tx_rate_bps": "tx",
};

type ChartRow = {
  /** X 轴显示文本（按统计时长选择 HH:mm 或 MM-dd HH:mm） */
  time: string;
  /** Tooltip 标题用的完整时间 */
  full: string;
} & {
  /** 序列 key → 值；索引签名需兼容 time/full 的 string */
  [seriesKey: string]: string | number | null;
};

/**
 * 服务器资源趋势图：一组指标一张图（如内存 + 交换分区、三条负载线）。
 * null 原样交给 recharts（connectNulls=false 断线）——未采集 / 窗口跳过 / 无法计算都不断成 0。
 */
export function ServerTrendChart({
  title,
  unit,
  xAxis,
  series,
  hours,
}: {
  title: string;
  unit: ServerTrendUnit;
  xAxis: string[];
  /** 已按 group 过滤后的序列 */
  series: ServerTrendSeries[];
  /** 统计时长，决定 X 轴时间格式 */
  hours: number;
}) {
  const { t } = useTranslation("console");

  const rows = useMemo<ChartRow[]>(
    () =>
      xAxis.map((iso, i) => {
        const row: ChartRow = {
          time: hours <= 24 ? fmtClock(iso) : fmtDateTime(iso),
          full: fmtDateTime(iso),
        };
        for (const s of series) row[s.key] = s.values[i] ?? null;
        return row;
      }),
    [xAxis, series, hours]
  );

  const colorOf = (key: string, idx: number) =>
    SERIES_COLORS[key] ?? FALLBACK_COLORS[idx % FALLBACK_COLORS.length];

  /** 序列显示名：后端 name 跟随接口语言，这里用本地 i18n 覆盖以保证一致 */
  const labelOf = (key: string) => {
    const slug = SERIES_LABEL_KEYS[key];
    if (!slug) return key;
    return t(`monitoring.server.series.${slug}`);
  };

  const fmtValue = (v: unknown) => {
    if (typeof v !== "number") return "—";
    if (unit === "percent") return fmtPercent(v);
    if (unit === "bytes_per_second") return fmtBps(v);
    return v.toFixed(2);
  };

  return (
    <div className="rounded-xl border border-border/60 bg-card/40 p-4">
      <h3 className="mb-3 text-sm font-medium">{title}</h3>
      <ResponsiveContainer width="100%" height={220}>
        <LineChart data={rows} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid
            strokeDasharray="3 3"
            vertical={false}
            className="stroke-border/60"
          />
          <XAxis
            dataKey="time"
            tick={{ fontSize: 11 }}
            minTickGap={48}
            tickLine={false}
            axisLine={false}
            className="text-muted-foreground"
          />
          <YAxis
            tick={{ fontSize: 11 }}
            tickLine={false}
            axisLine={false}
            width={56}
            domain={unit === "percent" ? [0, 100] : ["auto", "auto"]}
            tickFormatter={(v: number) =>
              unit === "percent"
                ? `${Math.round(v)}%`
                : unit === "bytes_per_second"
                  ? fmtBps(v)
                  : String(v)
            }
            className="text-muted-foreground"
          />
          <Tooltip
            labelFormatter={(_, payload) =>
              (payload?.[0]?.payload as ChartRow | undefined)?.full ?? ""
            }
            formatter={(value, name) => [
              fmtValue(value),
              labelOf(String(name)),
            ]}
            contentStyle={{
              borderRadius: 8,
              border: "1px solid var(--border)",
              background: "var(--popover)",
              color: "var(--popover-foreground)",
              fontSize: 12,
            }}
          />
          {series.length > 1 && (
            <Legend
              formatter={(value) => labelOf(String(value))}
              wrapperStyle={{ fontSize: 12 }}
            />
          )}
          {series.map((s, idx) => (
            <Line
              key={s.key}
              type="monotone"
              dataKey={s.key}
              stroke={colorOf(s.key, idx)}
              strokeWidth={2}
              dot={false}
              connectNulls={false}
              isAnimationActive={false}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
