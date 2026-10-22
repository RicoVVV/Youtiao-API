"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { RefreshCw } from "lucide-react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceArea,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Loading } from "@/components/ui/loading";
import { Select } from "@/components/ui/select";
import { get } from "@/lib/request";
import { cn } from "@/lib/utils";
import {
  fmtClock,
  fmtDateTime,
  fmtMs,
  fmtRate,
} from "@/components/console/monitoring/types";

/** 渠道运行时状态：渠道详情响应中的只读 runtime 对象；null 表示运行时状态不可用 */
export type ChannelRuntime = {
  /** 全部路由当前有效权重的算术平均 */
  effective_weight: number;
  /** 管理台配置的初始权重 */
  initial_weight: number;
  /** 熔断状态：closed 正常 / open 熔断中 / half_open 半开探测 */
  state: "closed" | "open" | "half_open";
  /** 成功率 EWMA 0~1；无样本时 null */
  success_rate: number | null;
  /** 平均耗时 EWMA（毫秒）；无样本时 null */
  average_latency_ms: number | null;
  consecutive_failures: number;
  /** 熔断冷却结束时间（ISO 8601 UTC）；非熔断时 null */
  open_until: string | null;
  /** 因健康探测自动停用的时间；人工停用或正常时 null */
  auto_disabled_at: string | null;
  last_probe: {
    tested_at: string;
    succeeded: boolean;
    latency_ms: number;
  } | null;
};

type TrendPoint = {
  bucket_start: string;
  effective_weight: number;
  success_rate: number | null;
  average_latency_ms: number | null;
  circuit_state: "closed" | "open" | "half_open";
  active: boolean;
};

type TrendResponse = {
  channel_id: string;
  bucket_seconds: number;
  start: string;
  end: string;
  /** 按 bucket_start 升序；无采样的分钟不补点 */
  points: TrendPoint[];
};

/** 趋势统计时长选项（小时） */
const HOURS_OPTIONS = [1, 6, 24, 72, 168] as const;

const SERIES_COLORS = {
  weight: "#2563eb",
  rate: "#10b981",
  latency: "#f59e0b",
} as const;

/** 熔断状态徽章配色 */
const STATE_STYLES: Record<ChannelRuntime["state"], string> = {
  closed:
    "border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400",
  open: "border-destructive/30 bg-destructive/10 text-destructive",
  half_open:
    "border-amber-500/30 bg-amber-500/10 text-amber-600 dark:text-amber-400",
};

/** 渠道详情 - 运行时状态区块：runtime 为 null 时按“暂无运行时数据”展示 */
export function ChannelRuntimeSection({
  runtime,
}: {
  runtime: ChannelRuntime | null | undefined;
}) {
  const { t } = useTranslation("console");

  if (!runtime) {
    return (
      <section className="space-y-2">
        <h3 className="text-xs font-medium uppercase tracking-wider text-muted-foreground/70">
          {t("channels.runtimeTitle")}
        </h3>
        <p className="rounded-lg border border-dashed border-border/70 py-4 text-center text-xs text-muted-foreground">
          {t("channels.runtimeEmpty")}
        </p>
      </section>
    );
  }

  const stateLabel = {
    closed: t("channels.runtimeStateClosed"),
    open: t("channels.runtimeStateOpen"),
    half_open: t("channels.runtimeStateHalfOpen"),
  }[runtime.state];

  const items: { label: string; value: React.ReactNode }[] = [
    {
      label: t("channels.runtimeStateLabel"),
      value: (
        <Badge variant="outline" className={STATE_STYLES[runtime.state]}>
          {stateLabel}
        </Badge>
      ),
    },
    {
      label: t("channels.runtimeEffectiveWeight"),
      value: (
        <span className="font-mono">
          {runtime.effective_weight}
          <span className="text-muted-foreground">
            {" / "}
            {runtime.initial_weight}
          </span>
        </span>
      ),
    },
    {
      label: t("channels.runtimeSuccessRate"),
      value: <span className="font-mono">{fmtRate(runtime.success_rate)}</span>,
    },
    {
      label: t("channels.runtimeAvgLatency"),
      value: (
        <span className="font-mono">{fmtMs(runtime.average_latency_ms)}</span>
      ),
    },
    {
      label: t("channels.runtimeConsecutiveFailures"),
      value: (
        <span
          className={cn(
            "font-mono",
            runtime.consecutive_failures > 0 && "text-destructive"
          )}
        >
          {runtime.consecutive_failures}
        </span>
      ),
    },
    {
      label: t("channels.runtimeOpenUntil"),
      value: (
        <span className="font-mono text-xs">
          {runtime.open_until ? fmtDateTime(runtime.open_until) : "—"}
        </span>
      ),
    },
    {
      label: t("channels.runtimeAutoDisabledAt"),
      value: (
        <span className="font-mono text-xs">
          {runtime.auto_disabled_at ? fmtDateTime(runtime.auto_disabled_at) : "—"}
        </span>
      ),
    },
    {
      label: t("channels.runtimeLastProbe"),
      value: runtime.last_probe ? (
        <span className="inline-flex flex-wrap items-center justify-end gap-1.5 font-mono text-xs">
          <span>{fmtDateTime(runtime.last_probe.tested_at)}</span>
          <Badge
            variant="outline"
            className={
              runtime.last_probe.succeeded
                ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
                : "border-destructive/30 bg-destructive/10 text-destructive"
            }
          >
            {runtime.last_probe.succeeded
              ? t("channels.runtimeProbeSucceeded")
              : t("channels.runtimeProbeFailed")}
          </Badge>
          <span>{fmtMs(runtime.last_probe.latency_ms)}</span>
        </span>
      ) : (
        "—"
      ),
    },
  ];

  return (
    <section className="space-y-2">
      <h3 className="text-xs font-medium uppercase tracking-wider text-muted-foreground/70">
        {t("channels.runtimeTitle")}
      </h3>
      <dl className="grid grid-cols-1 gap-x-6 gap-y-2 rounded-lg border border-border/60 bg-muted/10 p-3.5 text-sm sm:grid-cols-2">
        {items.map((item) => (
          <div
            key={item.label}
            className="flex items-center justify-between gap-3"
          >
            <dt className="shrink-0 text-xs text-muted-foreground">
              {item.label}
            </dt>
            <dd className="text-right">{item.value}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

type ChartRow = {
  /** X 轴分类值：分钟桶起点 ISO（保证唯一，ReferenceArea 依赖） */
  bucket: string;
  weight: number;
  /** 成功率 ×100；null 原样保留以断线 */
  rate: number | null;
  latency: number | null;
};

/** 连续满足条件的点合并为色带区间 [x1, x2] */
function computeBands(
  points: TrendPoint[],
  predicate: (p: TrendPoint) => boolean
): { x1: string; x2: string }[] {
  const bands: { x1: string; x2: string }[] = [];
  let start = -1;
  for (let i = 0; i <= points.length; i++) {
    const inRegion = i < points.length && predicate(points[i]);
    if (inRegion && start === -1) start = i;
    if (!inRegion && start !== -1) {
      bands.push({
        x1: points[start].bucket_start,
        x2: points[i - 1].bucket_start,
      });
      start = -1;
    }
  }
  return bands;
}

/**
 * 渠道运行趋势折线图：
 * 左轴有效权重，右轴成功率（%）与平均耗时；熔断/停用区间绘制背景色带；
 * null 指标断线（connectNulls=false），points 为空展示占位文案。
 */
export function ChannelTrendCard({ channelId }: { channelId: string }) {
  const { t } = useTranslation("console");
  const [hours, setHours] = useState<number>(24);
  const [data, setData] = useState<TrendResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(
    async (h: number) => {
      setLoading(true);
      setError("");
      try {
        const res = await get<TrendResponse>("/admin/channels/trend", {
          params: { channel_id: channelId, hours: h },
        });
        setData(res);
      } catch (err) {
        setData(null);
        setError(
          err instanceof Error ? err.message : t("channels.trendLoadFailed")
        );
      } finally {
        setLoading(false);
      }
    },
    [channelId, t]
  );

  useEffect(() => {
    load(hours);
  }, [load, hours]);

  const points = useMemo(() => data?.points ?? [], [data]);

  const rows = useMemo<ChartRow[]>(
    () =>
      points.map((p) => ({
        bucket: p.bucket_start,
        weight: p.effective_weight,
        // null 必须断线，不能按 0 绘制（无样本 ≠ 0% / 0ms）
        rate: p.success_rate == null ? null : p.success_rate * 100,
        latency: p.average_latency_ms,
      })),
    [points]
  );

  /** 熔断色带：open 红色 / half_open 浅橙色区分 */
  const openBands = useMemo(
    () => computeBands(points, (p) => p.circuit_state === "open"),
    [points]
  );
  const halfOpenBands = useMemo(
    () => computeBands(points, (p) => p.circuit_state === "half_open"),
    [points]
  );
  /** 停用色带：灰色 */
  const inactiveBands = useMemo(
    () => computeBands(points, (p) => !p.active),
    [points]
  );

  const tickFormatter = (iso: string) =>
    hours <= 24 ? fmtClock(iso) : fmtDateTime(iso);

  return (
    <section className="space-y-2">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-xs font-medium uppercase tracking-wider text-muted-foreground/70">
          {t("channels.trendTitle")}
        </h3>
        <div className="flex items-center gap-1.5">
          <Select
            value={String(hours)}
            onValueChange={(v) => setHours(Number(v))}
            options={HOURS_OPTIONS.map((h) => ({
              value: String(h),
              label: t("channels.trendHoursOption", { count: h }),
            }))}
            aria-label={t("channels.trendHoursAria")}
            className="h-7 w-28 text-xs"
          />
          <Button
            variant="ghost"
            size="icon"
            className="size-7"
            onClick={() => load(hours)}
            disabled={loading}
            aria-label={t("channels.refresh")}
          >
            <RefreshCw className={cn("size-3.5", loading && "animate-spin")} />
          </Button>
        </div>
      </div>

      <div className="rounded-lg border border-border/60 bg-muted/10 p-3.5">
        {loading && !data ? (
          <div className="flex h-56 items-center justify-center">
            <Loading size="lg" />
          </div>
        ) : error ? (
          <div className="flex h-56 flex-col items-center justify-center gap-2 text-xs text-muted-foreground">
            <p>{error}</p>
            <Button
              variant="outline"
              size="sm"
              onClick={() => load(hours)}
            >
              {t("channels.retry")}
            </Button>
          </div>
        ) : rows.length === 0 ? (
          <div className="flex h-56 items-center justify-center text-xs text-muted-foreground">
            {t("channels.trendEmpty")}
          </div>
        ) : (
          <>
            <ResponsiveContainer width="100%" height={240}>
              <LineChart
                data={rows}
                margin={{ top: 4, right: 4, bottom: 0, left: 0 }}
              >
                <CartesianGrid
                  strokeDasharray="3 3"
                  vertical={false}
                  className="stroke-border/60"
                />
                <XAxis
                  dataKey="bucket"
                  tickFormatter={tickFormatter}
                  tick={{ fontSize: 11 }}
                  minTickGap={48}
                  tickLine={false}
                  axisLine={false}
                  className="text-muted-foreground"
                />
                <YAxis
                  yAxisId="weight"
                  tick={{ fontSize: 11 }}
                  tickLine={false}
                  axisLine={false}
                  width={44}
                  domain={[0, "auto"]}
                  className="text-muted-foreground"
                />
                <YAxis
                  yAxisId="metric"
                  orientation="right"
                  tick={{ fontSize: 11 }}
                  tickLine={false}
                  axisLine={false}
                  width={48}
                  domain={[0, "auto"]}
                  className="text-muted-foreground"
                />
                <Tooltip
                  labelFormatter={(label) => fmtDateTime(String(label))}
                  formatter={(value, name) => {
                    if (name === "rate")
                      return [
                        typeof value === "number"
                          ? `${value.toFixed(2)}%`
                          : "—",
                        t("channels.trendSuccessRate"),
                      ];
                    if (name === "latency")
                      return [
                        typeof value === "number" ? fmtMs(value) : "—",
                        t("channels.trendLatency"),
                      ];
                    return [value, t("channels.trendWeight")];
                  }}
                  contentStyle={{
                    borderRadius: 8,
                    border: "1px solid var(--border)",
                    background: "var(--popover)",
                    color: "var(--popover-foreground)",
                    fontSize: 12,
                  }}
                />
                <Legend
                  formatter={(value) =>
                    value === "rate"
                      ? t("channels.trendSuccessRate")
                      : value === "latency"
                        ? t("channels.trendLatency")
                        : t("channels.trendWeight")
                  }
                  wrapperStyle={{ fontSize: 12 }}
                />
                {/* 背景色带先于折线渲染，置于底层 */}
                {inactiveBands.map((b) => (
                  <ReferenceArea
                    key={`inactive-${b.x1}`}
                    yAxisId="weight"
                    x1={b.x1}
                    x2={b.x2}
                    fill="#6b7280"
                    fillOpacity={0.12}
                  />
                ))}
                {halfOpenBands.map((b) => (
                  <ReferenceArea
                    key={`half-${b.x1}`}
                    yAxisId="weight"
                    x1={b.x1}
                    x2={b.x2}
                    fill="#f59e0b"
                    fillOpacity={0.10}
                  />
                ))}
                {openBands.map((b) => (
                  <ReferenceArea
                    key={`open-${b.x1}`}
                    yAxisId="weight"
                    x1={b.x1}
                    x2={b.x2}
                    fill="#ef4444"
                    fillOpacity={0.12}
                  />
                ))}
                <Line
                  yAxisId="weight"
                  type="monotone"
                  dataKey="weight"
                  stroke={SERIES_COLORS.weight}
                  strokeWidth={2}
                  dot={false}
                  connectNulls={false}
                  isAnimationActive={false}
                />
                <Line
                  yAxisId="metric"
                  type="monotone"
                  dataKey="rate"
                  stroke={SERIES_COLORS.rate}
                  strokeWidth={2}
                  dot={false}
                  connectNulls={false}
                  isAnimationActive={false}
                />
                <Line
                  yAxisId="metric"
                  type="monotone"
                  dataKey="latency"
                  stroke={SERIES_COLORS.latency}
                  strokeWidth={2}
                  dot={false}
                  connectNulls={false}
                  isAnimationActive={false}
                />
              </LineChart>
            </ResponsiveContainer>
            {/* 色带图例：仅在对应区间存在时展示 */}
            {(openBands.length > 0 ||
              halfOpenBands.length > 0 ||
              inactiveBands.length > 0) && (
              <div className="mt-2 flex flex-wrap items-center gap-3 text-[11px] text-muted-foreground">
                {openBands.length > 0 && (
                  <span className="inline-flex items-center gap-1.5">
                    <span className="size-2.5 rounded-sm bg-[#ef4444]/30" />
                    {t("channels.trendBandOpen")}
                  </span>
                )}
                {halfOpenBands.length > 0 && (
                  <span className="inline-flex items-center gap-1.5">
                    <span className="size-2.5 rounded-sm bg-[#f59e0b]/30" />
                    {t("channels.trendBandHalfOpen")}
                  </span>
                )}
                {inactiveBands.length > 0 && (
                  <span className="inline-flex items-center gap-1.5">
                    <span className="size-2.5 rounded-sm bg-[#6b7280]/30" />
                    {t("channels.trendBandInactive")}
                  </span>
                )}
              </div>
            )}
          </>
        )}
      </div>
    </section>
  );
}
