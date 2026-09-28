"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  AlertTriangle,
  CheckCircle2,
  MinusCircle,
  RefreshCw,
  XCircle,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Loading } from "@/components/ui/loading";
import { cn } from "@/lib/utils";
import { get } from "@/lib/request";

import {
  fmtDateTime,
  fmtMs,
  fmtRate,
  REQUEST_TYPES,
  TYPE_COLORS,
  type GroupMetricItem,
  type RequestType,
  type TrendResponse,
} from "./types";
import { useGroupMetricsList, type TrendGroup } from "./use-group-metrics";

/* ---------------- 健康度 ---------------- */

type Health = "good" | "warn" | "bad" | "none";

/** 成功率分档：>=98% 绿 / >=90% 琥珀 / 其余红 / 无数据灰 */
const healthOf = (rate: number | null | undefined): Health =>
  rate == null ? "none" : rate >= 0.98 ? "good" : rate >= 0.9 ? "warn" : "bad";

const HEALTH_RANK: Record<Health, number> = { none: 0, good: 1, warn: 2, bad: 3 };

const BAR_COLOR: Record<Health, string> = {
  good: "bg-emerald-500",
  warn: "bg-amber-400",
  bad: "bg-red-500",
  none: "bg-muted-foreground/10",
};

/** 卡片头部健康点颜色 */
const DOT_COLOR: Record<Health, string> = {
  good: "bg-emerald-500",
  warn: "bg-amber-400",
  bad: "bg-red-500",
  none: "bg-muted-foreground/40",
};

const TEXT_COLOR: Record<Health, string> = {
  good: "text-emerald-600 dark:text-emerald-400",
  warn: "text-amber-600 dark:text-amber-400",
  bad: "text-red-600 dark:text-red-400",
  none: "text-muted-foreground",
};

const PILL_CLASS: Record<Health, string> = {
  good: "border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400",
  warn: "border-amber-500/30 bg-amber-500/10 text-amber-600 dark:text-amber-400",
  bad: "border-red-500/30 bg-red-500/10 text-red-600 dark:text-red-400",
  none: "border-border/60 bg-muted/50 text-muted-foreground",
};

/** 顶部状态胶囊：分组整体最差成功率 */
function StatusPill({ health, rate }: { health: Health; rate: number | null }) {
  const { t } = useTranslation("console");
  const Icon =
    health === "good"
      ? CheckCircle2
      : health === "warn"
        ? AlertTriangle
        : health === "bad"
          ? XCircle
          : MinusCircle;
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-semibold tabular-nums",
        PILL_CLASS[health]
      )}
    >
      <Icon className="size-3.5" />
      {rate == null ? t("monitoring.noData") : fmtRate(rate)}
    </span>
  );
}

/** 顶部胶囊式分段选择器 */
function PillGroup<T extends string>({
  value,
  onChange,
  options,
  ariaLabel,
}: {
  value: T;
  onChange: (v: T) => void;
  options: Array<{ value: T; label: string }>;
  ariaLabel: string;
}) {
  return (
    <div
      role="group"
      aria-label={ariaLabel}
      className="inline-flex items-center gap-0.5 rounded-full border border-border/60 bg-muted/40 p-0.5"
    >
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          onClick={() => onChange(o.value)}
          className={cn(
            "rounded-full px-3 py-1 text-xs font-medium transition-all",
            value === o.value
              ? "bg-primary text-primary-foreground shadow-sm"
              : "text-muted-foreground hover:text-foreground"
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

/* ---------------- 状态条 ---------------- */

/**
 * 逐窗口状态条：每个窗口一根色块，悬浮显示该窗口明细。
 * 整行共享一个 tooltip（按索引定位），避免每根条渲染额外节点。
 */
function BarRow({
  xAxis,
  rates,
  durations,
  firstTokens,
}: {
  xAxis: string[];
  rates: (number | null)[];
  durations?: (number | null)[];
  firstTokens?: (number | null)[];
}) {
  const { t } = useTranslation("console");
  const [hover, setHover] = useState<number | null>(null);
  const count = rates.length;
  if (count === 0) return null;

  const gap = count <= 24 ? "gap-[3px]" : count <= 96 ? "gap-[2px]" : "gap-px";
  const round =
    count <= 24 ? "rounded-md" : count <= 96 ? "rounded-[3px]" : "rounded-[1px]";

  return (
    <div className="relative" onMouseLeave={() => setHover(null)}>
      {hover != null && hover < count && (
        <div
          className="pointer-events-none absolute bottom-full z-20 mb-2 -translate-x-1/2 rounded-lg border border-border bg-popover px-2.5 py-1.5 text-xs whitespace-nowrap text-popover-foreground shadow-lg"
          style={{
            // 两端钳制，避免 tooltip 溢出卡片
            left: `${Math.min(92, Math.max(8, ((hover + 0.5) / count) * 100))}%`,
          }}
        >
          <div className="mb-0.5 text-muted-foreground">
            {fmtDateTime(xAxis[hover])}
          </div>
          {rates[hover] == null ? (
            <div>{t("monitoring.noTraffic")}</div>
          ) : (
            <>
              <div>
                {t("monitoring.metric.success_rate")}：
                <b className={TEXT_COLOR[healthOf(rates[hover])]}>
                  {fmtRate(rates[hover])}
                </b>
              </div>
              {durations?.[hover] != null && (
                <div>
                  {t("monitoring.metric.average_duration_ms")}：
                  {fmtMs(durations[hover])}
                </div>
              )}
              {firstTokens?.[hover] != null && (
                <div>
                  {t("monitoring.metric.average_first_token_ms")}：
                  {fmtMs(firstTokens[hover])}
                </div>
              )}
            </>
          )}
        </div>
      )}
      <div className={cn("flex items-stretch", gap)}>
        {rates.map((v, i) => (
          <div
            key={i}
            onMouseEnter={() => setHover(i)}
            className={cn(
              "h-8 min-w-0 flex-1 transition-all duration-75 hover:scale-y-110 hover:brightness-110",
              round,
              BAR_COLOR[healthOf(v)]
            )}
          />
        ))}
      </div>
    </div>
  );
}

/* ---------------- 分组卡片 ---------------- */

/** 内联次要指标：标签轻量灰、数值强调，与主指标同一基线 */
function InlineMetric({ label, value }: { label: string; value: string }) {
  return (
    <span className="text-xs text-muted-foreground">
      {label}
      <span className="ml-1 text-sm font-medium tabular-nums text-foreground">
        {value}
      </span>
    </span>
  );
}

type TypeSection = {
  type: RequestType;
  /** 汇总指标：优先取近 24h，无流量时退回最新窗口 */
  summary: GroupMetricItem | null;
  rates: (number | null)[];
  durations?: (number | null)[];
  firstTokens?: (number | null)[];
};

function GroupStatusCard({
  apiBase,
  group,
  items,
  mode,
  reqType,
  hours,
}: {
  apiBase: "" | "/admin";
  group: TrendGroup;
  /** 该分组在列表接口里的全部行（latest + last_24h × 各类型） */
  items: GroupMetricItem[];
  mode: "user" | "admin";
  reqType: string;
  hours: number;
}) {
  const { t } = useTranslation("console");
  const [trend, setTrend] = useState<TrendResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const res = await get<TrendResponse>(`${apiBase}/monitoring/groups/trend`, {
        params: {
          group_id: group.id,
          request_type: reqType === "all" ? undefined : reqType,
          hours,
        },
      });
      setTrend(res);
    } catch (err) {
      setTrend(null);
      setError(err instanceof Error ? err.message : t("monitoring.loadFailed"));
    } finally {
      setLoading(false);
    }
  }, [apiBase, group.id, reqType, hours, t]);

  useEffect(() => {
    load();
  }, [load]);

  /** 按请求类型分段；只保留有流量（汇总或趋势任一）的类型 */
  const sections = useMemo<TypeSection[]>(() => {
    const xLen = trend?.x_axis.length ?? 0;
    return REQUEST_TYPES.filter((tp) => reqType === "all" || tp === reqType)
      .map((tp) => {
        const latest =
          items.find((i) => i.request_type === tp && i.period === "latest") ??
          null;
        const day =
          items.find(
            (i) => i.request_type === tp && i.period === "last_24h"
          ) ?? null;
        const summary =
          day && day.sample_count > 0 ? day : latest && latest.sample_count > 0 ? latest : (day ?? latest);

        const series = (trend?.series ?? []).filter(
          (s) => s.request_type === tp
        );
        const raw = series.find((s) => s.metric === "success_rate")?.values;
        // 与 x_axis 严格等长，缺位补 null（断开而非 0）
        const rates = Array.from({ length: xLen }, (_, i) => raw?.[i] ?? null);
        const hasTraffic =
          (summary?.sample_count ?? 0) > 0 || rates.some((v) => v != null);
        return {
          type: tp,
          summary,
          rates,
          durations: series.find((s) => s.metric === "average_duration_ms")
            ?.values,
          firstTokens: series.find(
            (s) => s.metric === "average_first_token_ms"
          )?.values,
          hasTraffic,
        };
      })
      .filter((s) => s.hasTraffic);
  }, [items, trend, reqType]);

  /** 卡片右上角胶囊：取各类型中最差的健康度 */
  const worst = useMemo(() => {
    let health: Health = "none";
    let rate: number | null = null;
    for (const s of sections) {
      const r = s.summary && s.summary.sample_count > 0 ? s.summary.success_rate : null;
      const h = healthOf(r);
      if (HEALTH_RANK[h] > HEALTH_RANK[health]) {
        health = h;
        rate = r;
      }
    }
    return { health, rate };
  }, [sections]);

  return (
    <div className="rounded-xl border border-border/60 bg-card p-4 transition-all duration-300 hover:border-border hover:shadow-sm">
      {/* 头部：健康点 + 名称 + 告警徽标 + 状态胶囊 */}
      <div className="mb-1 flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          <span
            className={cn(
              "size-2 shrink-0 rounded-full",
              DOT_COLOR[worst.health]
            )}
          />
          <h3 className="truncate text-sm font-semibold">{group.name}</h3>
          {mode === "admin"
            ? group.alertCount > 0 && (
                <Badge
                  variant="outline"
                  className="border-destructive/40 bg-destructive/10 text-destructive"
                >
                  {group.alertCount}
                </Badge>
              )
            : group.hasAlert && (
                <Badge
                  variant="outline"
                  className="border-destructive/40 bg-destructive/10 text-destructive"
                >
                  {t("monitoring.alertYes")}
                </Badge>
              )}
        </div>
        <StatusPill health={worst.health} rate={worst.rate} />
      </div>

      {loading ? (
        <div className="flex justify-center py-8">
          <Loading size="md" />
        </div>
      ) : error ? (
        <div className="flex flex-col items-center gap-2 py-8 text-sm text-muted-foreground">
          <p>{t("monitoring.trendLoadFailed", { error })}</p>
          <Button variant="outline" size="sm" onClick={load}>
            {t("monitoring.retry")}
          </Button>
        </div>
      ) : sections.length === 0 ? (
        <div className="py-8 text-center text-sm text-muted-foreground">
          {t("monitoring.noTraffic")}
        </div>
      ) : (
        <div className="flex flex-col divide-y divide-border/40">
          {sections.map((s) => (
            <div key={s.type} className="py-3 first:pt-1 last:pb-0">
              {/* 多类型时显示类型标签（带类型色点） */}
              {sections.length > 1 && (
                <div className="mb-1.5 flex items-center gap-1.5">
                  <span
                    className="size-1.5 rounded-full"
                    style={{ backgroundColor: TYPE_COLORS[s.type] }}
                  />
                  <span className="text-xs font-medium text-muted-foreground">
                    {t(`monitoring.type.${s.type}`)}
                  </span>
                </div>
              )}

              {/* 指标行：成功率为主指标大号突出，其余内联轻量展示 */}
              <div className="mb-2 flex flex-wrap items-baseline gap-x-4 gap-y-1">
                <span
                  className={cn(
                    "text-base font-semibold tabular-nums",
                    TEXT_COLOR[healthOf(s.summary?.success_rate)]
                  )}
                >
                  {fmtRate(s.summary?.success_rate)}
                </span>
                <InlineMetric
                  label={t("monitoring.metric.average_duration_ms")}
                  value={fmtMs(s.summary?.average_duration_ms)}
                />
                {s.type === "text" && (
                  <InlineMetric
                    label={t("monitoring.metric.average_first_token_ms")}
                    value={fmtMs(s.summary?.average_first_token_ms)}
                  />
                )}
                <InlineMetric
                  label={t("monitoring.sampleLabel")}
                  value={s.summary ? String(s.summary.sample_count) : "—"}
                />
              </div>

              <BarRow
                xAxis={trend?.x_axis ?? []}
                rates={s.rates}
                durations={s.durations}
                firstTokens={s.firstTokens}
              />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ---------------- 卡片墙 ---------------- */

/**
 * 分组状态墙：全部分组卡片平铺，每张卡片展示
 * 汇总指标（近 24h / 最新窗口）+ 逐窗口状态条（趋势接口）。
 */
export function GroupStatusWall({
  apiBase,
  mode,
  hoursOptions,
}: {
  apiBase: "" | "/admin";
  mode: "user" | "admin";
  hoursOptions: number[];
}) {
  const { t } = useTranslation("console");
  const list = useGroupMetricsList(apiBase);
  const [reqType, setReqType] = useState("all");
  const [hours, setHours] = useState(
    String(hoursOptions[0] ?? 1)
  );
  /** 手动刷新：重挂载所有卡片强制重新拉取趋势 */
  const [nonce, setNonce] = useState(0);

  const itemsByGroup = useMemo(() => {
    const m = new Map<number, GroupMetricItem[]>();
    for (const it of list.data?.items ?? []) {
      const arr = m.get(it.group_id);
      if (arr) arr.push(it);
      else m.set(it.group_id, [it]);
    }
    return m;
  }, [list.data]);

  const hoursLabel = (h: number) =>
    h > 24 && h % 24 === 0
      ? t("monitoring.daysPill", { n: h / 24 })
      : t("monitoring.hoursPill", { n: h });

  return (
    <section className="flex flex-col gap-4">
      {/* 控制区：类型筛选 + 时长 + 刷新 + 更新时间 */}
      <div className="flex flex-wrap items-center justify-end gap-2">
        <PillGroup
          value={reqType}
          onChange={setReqType}
          ariaLabel={t("monitoring.colType")}
          options={[
            { value: "all", label: t("monitoring.type.all") },
            { value: "text", label: t("monitoring.type.text") },
            { value: "image", label: t("monitoring.type.image") },
            { value: "video", label: t("monitoring.type.video") },
          ]}
        />
        <PillGroup
          value={hours}
          onChange={setHours}
          ariaLabel={t("monitoring.filterHours")}
          options={hoursOptions.map((h) => ({
            value: String(h),
            label: hoursLabel(h),
          }))}
        />
        <Button
          variant="outline"
          size="sm"
          onClick={() => {
            list.reload();
            setNonce((n) => n + 1);
          }}
          disabled={list.loading}
        >
          <RefreshCw className={cn("size-4", list.loading && "animate-spin")} />
          {t("monitoring.refresh")}
        </Button>
        {list.updatedAt && (
          <span className="text-xs text-muted-foreground tabular-nums">
            {t("monitoring.updatedAt", {
              time: list.updatedAt.toLocaleTimeString(),
            })}
          </span>
        )}
      </div>

      {list.loading && !list.data ? (
        <div className="flex justify-center rounded-xl border border-border/60 bg-card py-16">
          <Loading size="md" />
        </div>
      ) : list.error ? (
        <div className="flex flex-col items-center gap-2 rounded-xl border border-border/60 bg-card py-16 text-sm text-muted-foreground">
          <p>{t("monitoring.loadFailedWithReason", { error: list.error })}</p>
          <Button variant="outline" size="sm" onClick={list.reload}>
            {t("monitoring.retry")}
          </Button>
        </div>
      ) : list.groups.length === 0 ? (
        <div className="rounded-xl border border-border/60 bg-card py-16 text-center text-sm text-muted-foreground">
          {t("monitoring.wallEmpty")}
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-2 2xl:grid-cols-3">
          {list.groups.map((g) => (
            <GroupStatusCard
              key={`${g.id}-${nonce}`}
              apiBase={apiBase}
              group={g}
              items={itemsByGroup.get(g.id) ?? []}
              mode={mode}
              reqType={reqType}
              hours={Number(hours)}
            />
          ))}
        </div>
      )}
    </section>
  );
}
