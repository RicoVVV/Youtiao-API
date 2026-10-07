"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  BarChart3,
  CircleDollarSign,
  Coins,
  Gauge,
  Percent,
  RefreshCw,
  Timer,
  TrendingUp,
  Zap,
  type LucideIcon,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { DateTimePicker } from "@/components/ui/datetime-picker";
import { Loading } from "@/components/ui/loading";
import { Pagination } from "@/components/ui/pagination";
import { Select } from "@/components/ui/select";
import { toast } from "@/components/ui/toaster";
import { cn } from "@/lib/utils";
import { get } from "@/lib/request";

/* ---------------- 类型（与接入指南一致，金额/比率为十进制字符串） ---------------- */

type UsageStatisticsMetrics = {
  succeeded_count: number;
  refunded_count: number;
  settled_amount: string;
  success_rate: string;
  average_duration_ms: number;
  /** 后端尚未返回，返回前展示占位值 */
  total_tokens?: number;
  average_rpm?: string;
  average_tpm?: string;
};

type TrendItem = Omit<
  UsageStatisticsMetrics,
  "total_tokens" | "average_rpm" | "average_tpm"
> & { stat_date: string };

type ModelItem = Omit<
  UsageStatisticsMetrics,
  "total_tokens" | "average_rpm" | "average_tpm"
> & {
  model_id: string | null;
  model_name: string;
};

type Paged<T> = { items: T[]; total: number; page: number; page_size: number };

/* ---------------- 常量与纯函数 ---------------- */

const RANGE_VALUES = ["today", "last_7_days", "last_30_days", "custom"];

const PAGE_SIZE = 20;

/** 金额展示：纯字符串截取两位小数，不做数值运算（十进制字符串安全） */
const formatYuan = (amount: string) => {
  const [intPart = "0", fracPart = ""] = String(amount).trim().split(".");
  return `$${intPart}.${`${fracPart}00`.slice(0, 2)}`;
};

/** 成功率："0.9230…" → "92.31%"，仅字符串操作 */
const formatRate = (rate: string) => {
  const n = Number(rate);
  if (!Number.isFinite(n)) return "—";
  return `${(n * 100).toFixed(2)}%`;
};

/** RPM/TPM：十进制字符串保留两位小数 */
const formatDecimal = (value?: string) => {
  if (value == null) return "—";
  const n = Number(value);
  if (!Number.isFinite(n)) return "—";
  return n.toFixed(2);
};

/** Token 数：≥1 万用 K，≥100 万用 M */
const formatTokens = (value?: number) => {
  if (value == null || !Number.isFinite(value)) return "—";
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 10_000) return `${(value / 1_000).toFixed(1)}K`;
  return String(value);
};

type Translate = (key: string, options?: Record<string, unknown>) => string;

/** 平均耗时：毫秒 → 秒/分秒 */
const formatDuration = (t: Translate, ms: number) => {
  if (!ms) return "—";
  if (ms < 1000) return t("usageStatistics.durationMs", { value: ms });
  const s = ms / 1000;
  if (s < 60) return t("usageStatistics.durationSeconds", { value: s.toFixed(1) });
  const m = Math.floor(s / 60);
  const rest = Math.round(s % 60);
  return rest
    ? t("usageStatistics.durationMinutesSeconds", { minutes: m, seconds: rest })
    : t("usageStatistics.durationMinutes", { minutes: m });
};

/** datetime-local 值（上海本地）→ 带时区 ISO 字符串 */
const toIsoWithTz = (local: string) =>
  local ? new Date(local).toISOString() : undefined;

/* ---------------- 概览卡片 ---------------- */

function OverviewCards({
  data,
  loading,
  error,
  onRetry,
}: {
  data: UsageStatisticsMetrics | null;
  loading: boolean;
  error: string;
  onRetry: () => void;
}) {
  const { t } = useTranslation("console");
  const cards: Array<{
    label: string;
    value: string;
    icon: LucideIcon;
    iconClass: string;
  }> = data
    ? [
        {
          label: t("usageStatistics.cardConsumption"),
          value: formatYuan(data.settled_amount),
          icon: CircleDollarSign,
          iconClass:
            "from-[#4c6fff]/15 to-[#7c5cff]/15 text-[#4c6fff] dark:text-[#8fa2ff]",
        },
        {
          label: t("usageStatistics.cardTotalCount"),
          value: String(data.succeeded_count + data.refunded_count),
          icon: BarChart3,
          iconClass: "from-success/15 to-success/5 text-success",
        },
        {
          label: t("usageStatistics.cardSuccessRate"),
          value: formatRate(data.success_rate),
          icon: Percent,
          iconClass: "from-[#7c5cff]/15 to-[#7c5cff]/5 text-[#7c5cff]",
        },
        {
          label: t("usageStatistics.cardTotalTokens"),
          value: formatTokens(data.total_tokens),
          icon: Coins,
          iconClass: "from-warning/15 to-warning/5 text-warning",
        },
        {
          label: t("usageStatistics.cardAverageRpm"),
          value: formatDecimal(data.average_rpm),
          icon: Gauge,
          iconClass:
            "from-[#4c6fff]/15 to-[#4c6fff]/5 text-[#4c6fff] dark:text-[#8fa2ff]",
        },
        {
          label: t("usageStatistics.cardAverageTpm"),
          value: formatDecimal(data.average_tpm),
          icon: Zap,
          iconClass:
            "from-muted-foreground/15 to-muted-foreground/5 text-muted-foreground",
        },
      ]
    : [];

  return (
    <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
      {loading ? (
        <div className="col-span-full flex justify-center rounded-xl border border-border/60 bg-card/40 py-10">
          <Loading size="md" />
        </div>
      ) : error ? (
        <div className="col-span-full flex flex-col items-center gap-2 rounded-xl border border-border/60 bg-card/40 py-10 text-sm text-muted-foreground">
          <p>{t("usageStatistics.overviewLoadFailed", { error })}</p>
          <Button variant="outline" size="sm" onClick={onRetry}>
            {t("usageStatistics.retry")}
          </Button>
        </div>
      ) : (
        cards.map((c) => (
          <div
            key={c.label}
            className="group relative overflow-hidden rounded-xl border border-border/60 bg-card/40 px-4 py-4 shadow-card transition-all duration-200 hover:-translate-y-0.5 hover:border-border hover:shadow-lg"
          >
            {/* 右上角渐变光晕装饰 */}
            <div
              className={cn(
                "pointer-events-none absolute -top-8 -right-8 size-24 rounded-full bg-gradient-to-br opacity-60 blur-2xl transition-opacity duration-200 group-hover:opacity-100",
                c.iconClass
              )}
            />
            <div className="relative flex items-start justify-between gap-2">
              <div className="min-w-0">
                <p className="text-xs text-muted-foreground">{c.label}</p>
                <p className="mt-2 truncate text-lg font-semibold tracking-tight">
                  {c.value}
                </p>
              </div>
              <span
                className={cn(
                  "flex size-8 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br",
                  c.iconClass
                )}
              >
                <c.icon className="size-4" />
              </span>
            </div>
          </div>
        ))
      )}
    </div>
  );
}

/* ---------------- 按日趋势（轻量柱状图，无第三方依赖） ---------------- */

function TrendChart({
  items,
  loading,
  error,
  onRetry,
}: {
  items: TrendItem[];
  loading: boolean;
  error: string;
  onRetry: () => void;
}) {
  const { t } = useTranslation("console");
  /** 金额字符串转数值仅用于柱高比例，不参与任何结算展示计算 */
  const max = useMemo(
    () => Math.max(0, ...items.map((i) => Number(i.settled_amount) || 0)),
    [items]
  );

  return (
    <section className="rounded-xl border border-border/60 bg-card/40 p-4">
      <div className="mb-4 flex items-center gap-2">
        <TrendingUp className="size-4 text-muted-foreground" />
        <h2 className="text-sm font-medium">{t("usageStatistics.trendTitle")}</h2>
      </div>
      {loading ? (
        <div className="flex justify-center py-10">
          <Loading size="md" />
        </div>
      ) : error ? (
        <div className="flex flex-col items-center gap-2 py-10 text-sm text-muted-foreground">
          <p>{t("usageStatistics.trendLoadFailed", { error })}</p>
          <Button variant="outline" size="sm" onClick={onRetry}>
            {t("usageStatistics.retry")}
          </Button>
        </div>
      ) : (
        <div className="flex h-44 items-end gap-1.5 overflow-x-auto pb-1">
          {items.map((i) => {
            const v = Number(i.settled_amount) || 0;
            const h = max > 0 ? Math.max(2, (v / max) * 100) : 2;
            return (
              <div
                key={i.stat_date}
                className={cn(
                  "group flex w-10 shrink-0 flex-col items-center gap-1.5",
                  items.length > 10 && "min-w-0 flex-1"
                )}
                title={`${i.stat_date}\n${t("usageStatistics.trendTooltip", {
                  amount: formatYuan(i.settled_amount),
                  count: i.succeeded_count,
                  rate: formatRate(i.success_rate),
                })}`}
              >
                <div className="flex h-32 w-full items-end">
                  <div
                    className="w-full rounded-t-md bg-gradient-to-t from-[#4c6fff]/70 to-[#7c5cff]/70 transition-opacity group-hover:opacity-100"
                    style={{ height: `${h}%`, opacity: v > 0 ? 0.85 : 0.15 }}
                  />
                </div>
                <span className="text-[10px] whitespace-nowrap text-muted-foreground">
                  {i.stat_date.slice(5)}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}

/* ---------------- 模型用量分布 ---------------- */

function ModelTable({
  data,
  total,
  page,
  loading,
  error,
  onPage,
  onRetry,
}: {
  data: ModelItem[];
  total: number;
  page: number;
  loading: boolean;
  error: string;
  onPage: (p: number) => void;
  onRetry: () => void;
}) {
  const { t } = useTranslation("console");
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <section className="rounded-xl border border-border/60 bg-card/40 p-4">
      <div className="mb-4 flex items-center gap-2">
        <BarChart3 className="size-4 text-muted-foreground" />
        <h2 className="text-sm font-medium">{t("usageStatistics.modelTitle")}</h2>
      </div>
      {error && data.length === 0 ? (
        <div className="flex flex-col items-center gap-2 py-10 text-sm text-muted-foreground">
          <p>{t("usageStatistics.modelLoadFailed", { error })}</p>
          <Button variant="outline" size="sm" onClick={onRetry}>
            {t("usageStatistics.retry")}
          </Button>
        </div>
      ) : data.length === 0 ? (
        <div className="flex justify-center py-10 text-sm text-muted-foreground">
          {loading ? <Loading size="md" /> : t("usageStatistics.modelEmpty")}
        </div>
      ) : (
        <>
          <table
            className={cn(
              "w-full text-sm transition-opacity duration-300",
              loading && "pointer-events-none opacity-40"
            )}
          >
            <thead>
              <tr className="border-b border-border/60 text-xs text-muted-foreground">
                <th className="py-2.5 text-left font-medium">{t("usageStatistics.colModel")}</th>
                <th className="px-4 py-2.5 text-center font-medium">
                  {t("usageStatistics.colConsumption")}
                </th>
                <th className="px-4 py-2.5 text-center font-medium">
                  {t("usageStatistics.colSucceeded")}
                </th>
                <th className="px-4 py-2.5 text-center font-medium">{t("usageStatistics.colSuccessRate")}</th>
                <th className="px-4 py-2.5 text-center font-medium">
                  {t("usageStatistics.colAvgDuration")}
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/60">
              {data.map((m, idx) => (
                <tr
                  key={m.model_id ?? `unknown-${idx}`}
                  className="transition-colors hover:bg-accent/40"
                >
                  <td className="max-w-56 truncate py-2.5 pr-4">
                    {m.model_name}
                  </td>
                  <td className="px-4 py-2.5 text-center font-mono text-xs">
                    {formatYuan(m.settled_amount)}
                  </td>
                  <td className="px-4 py-2.5 text-center">
                    {m.succeeded_count}
                  </td>
                  <td className="px-4 py-2.5 text-center">
                    {formatRate(m.success_rate)}
                  </td>
                  <td className="px-4 py-2.5 text-center text-muted-foreground">
                    {formatDuration(t, m.average_duration_ms)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {totalPages > 1 && (
            <Pagination
              page={page}
              totalPages={totalPages}
              loading={loading}
              onChange={onPage}
              className="mt-4"
            />
          )}
        </>
      )}
    </section>
  );
}

/* ---------------- 页面面板 ---------------- */

export function UsageStatisticsPanel() {
  const { t } = useTranslation("console");
  /** 角色未知时不发请求，避免管理员误用用户视角接口 */
  const [isAdmin, setIsAdmin] = useState<boolean | null>(null);
  const [range, setRange] = useState("today");
  const [startLocal, setStartLocal] = useState("");
  const [endLocal, setEndLocal] = useState("");

  const [overview, setOverview] = useState<UsageStatisticsMetrics | null>(null);
  const [trend, setTrend] = useState<TrendItem[]>([]);
  const [models, setModels] = useState<ModelItem[]>([]);
  const [modelsTotal, setModelsTotal] = useState(0);
  const [modelPage, setModelPage] = useState(1);

  const [overviewState, setOverviewState] = useState({ loading: true, error: "" });
  const [trendState, setTrendState] = useState({ loading: true, error: "" });
  const [modelsState, setModelsState] = useState({ loading: true, error: "" });

  const rangeOptions = useMemo(
    () =>
      RANGE_VALUES.map((value) => ({
        value,
        label: t(`usageStatistics.range.${value}`),
      })),
    [t]
  );

  /** 自定义范围未选满时不发请求；range 与自定义同时存在时以自定义为准 */
  const queryParams = useMemo(() => {
    if (range === "custom") {
      if (!startLocal || !endLocal) return null;
      if (new Date(endLocal) <= new Date(startLocal)) return null;
      return {
        start_at: toIsoWithTz(startLocal),
        end_at: toIsoWithTz(endLocal),
      };
    }
    return { range };
  }, [range, startLocal, endLocal]);

  /** 管理员使用全量统计口径，普通用户只看自己的数据 */
  useEffect(() => {
    get<{ is_admin: boolean }>("/user/info")
      .then((p) => setIsAdmin(p.is_admin))
      .catch(() => setIsAdmin(false));
  }, []);

  const loadOverview = useCallback(async () => {
    if (!queryParams || isAdmin === null) return;
    setOverviewState({ loading: true, error: "" });
    try {
      const data = await get<UsageStatisticsMetrics>(
        `${isAdmin ? "/admin" : ""}/usage/statistics/overview`,
        { params: queryParams }
      );
      setOverview(data);
      setOverviewState({ loading: false, error: "" });
    } catch (err) {
      setOverviewState({
        loading: false,
        error: err instanceof Error ? err.message : t("usageStatistics.loadFailed"),
      });
    }
  }, [queryParams, isAdmin, t]);

  const loadTrend = useCallback(async () => {
    if (!queryParams || isAdmin === null) return;
    setTrendState({ loading: true, error: "" });
    try {
      const data = await get<{ items: TrendItem[] }>(
        `${isAdmin ? "/admin" : ""}/usage/statistics/trend`,
        { params: queryParams }
      );
      setTrend(data.items);
      setTrendState({ loading: false, error: "" });
    } catch (err) {
      setTrendState({
        loading: false,
        error: err instanceof Error ? err.message : t("usageStatistics.loadFailed"),
      });
    }
  }, [queryParams, isAdmin, t]);

  const loadModels = useCallback(
    async (p: number) => {
      if (!queryParams || isAdmin === null) return;
      setModelsState({ loading: true, error: "" });
      try {
        const data = await get<Paged<ModelItem>>(
          isAdmin
            ? "/admin/usage/statistics/dimensions/list"
            : "/usage/statistics/models/list",
          {
            params: {
              ...queryParams,
              ...(isAdmin ? { dimension: "model" } : {}),
              page: p,
              page_size: PAGE_SIZE,
            },
          }
        );
        setModels(data.items);
        setModelsTotal(data.total);
        setModelsState({ loading: false, error: "" });
      } catch (err) {
        setModelsState({
          loading: false,
          error: err instanceof Error ? err.message : t("usageStatistics.loadFailed"),
        });
      }
    },
    [queryParams, isAdmin, t]
  );

  /* 筛选变化时并行刷新三个模块，互不影响 */
  useEffect(() => {
    if (!queryParams || isAdmin === null) return;
    loadOverview();
    loadTrend();
    setModelPage(1);
    loadModels(1);
  }, [queryParams, isAdmin, loadOverview, loadTrend, loadModels]);

  const refreshAll = () => {
    if (!queryParams) {
      toast.warning(t("usageStatistics.selectCompleteRange"));
      return;
    }
    loadOverview();
    loadTrend();
    loadModels(modelPage);
  };

  const refreshing =
    overviewState.loading || trendState.loading || modelsState.loading;

  return (
    <div className="flex w-full flex-col gap-6">
      {/* 页头与时间选择 */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold">{t("usageStatistics.title")}</h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            {isAdmin
              ? t("usageStatistics.subtitleAdmin")
              : t("usageStatistics.subtitleUser")}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Select
            value={range}
            onValueChange={(v) => setRange(v)}
            options={rangeOptions}
            className="w-auto"
            aria-label={t("usageStatistics.rangeLabel")}
          />
          {range === "custom" && (
            <>
              <DateTimePicker
                value={startLocal}
                onChange={setStartLocal}
                placeholder={t("usageStatistics.startTime")}
                className="w-48"
              />
              <span className="text-xs text-muted-foreground">{t("usageStatistics.rangeTo")}</span>
              <DateTimePicker
                value={endLocal}
                onChange={setEndLocal}
                placeholder={t("usageStatistics.endTime")}
                className="w-48"
              />
            </>
          )}
          <Button
            variant="outline"
            size="sm"
            onClick={refreshAll}
            disabled={refreshing}
          >
            <RefreshCw className={cn("size-4", refreshing && "animate-spin")} />
            {t("usageStatistics.refresh")}
          </Button>
        </div>
      </div>

      {range === "custom" && !queryParams ? (
        <div className="rounded-xl border border-border/60 bg-card/40 py-14 text-center text-sm text-muted-foreground">
          {startLocal && endLocal && new Date(endLocal) <= new Date(startLocal)
            ? t("usageStatistics.endBeforeStart")
            : t("usageStatistics.selectCompleteRangeHint")}
        </div>
      ) : (
        <>
          <OverviewCards
            data={overview}
            loading={overviewState.loading}
            error={overviewState.error}
            onRetry={loadOverview}
          />
          <TrendChart
            items={trend}
            loading={trendState.loading}
            error={trendState.error}
            onRetry={loadTrend}
          />
          <ModelTable
            data={models}
            total={modelsTotal}
            page={modelPage}
            loading={modelsState.loading}
            error={modelsState.error}
            onPage={(p) => {
              setModelPage(p);
              loadModels(p);
            }}
            onRetry={() => loadModels(modelPage)}
          />
        </>
      )}
    </div>
  );
}
