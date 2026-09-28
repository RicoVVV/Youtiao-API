"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Loading } from "@/components/ui/loading";
import { Select } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { toast } from "@/components/ui/toaster";
import { cn } from "@/lib/utils";
import { get, post } from "@/lib/request";

import { ServerTrendChart } from "../server-trend-chart";
import {
  fmtBps,
  fmtBytes,
  fmtDateTime,
  fmtPercent,
  type ResourceRule,
  type ServerLatest,
  type ServerTrendGroup,
  type ServerTrendResponse,
} from "../types";

/** 趋势统计时长选项（接口范围 1~72 小时，默认 6） */
const HOURS_OPTIONS = [1, 3, 6, 12, 24, 48, 72];
/** 趋势分组展示顺序 */
const GROUP_ORDER: ServerTrendGroup[] = ["cpu", "memory", "load", "disk", "network"];

/** 使用率超过该值时 KPI / 明细标红 */
const DANGER_PERCENT = 90;

function KpiCard({
  label,
  value,
  sub,
  danger,
}: {
  label: string;
  value: string;
  sub?: string;
  danger?: boolean;
}) {
  return (
    <div className="rounded-xl border border-border/60 bg-card/40 p-4">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p
        className={cn(
          "mt-1.5 text-xl font-semibold whitespace-nowrap",
          danger && "text-destructive"
        )}
      >
        {value}
      </p>
      {sub && <p className="mt-1 truncate text-xs text-muted-foreground">{sub}</p>}
    </div>
  );
}

/** 资源告警阈值：单条全局配置；阈值留空 = 不评估该指标（提交 null） */
function ResourceRuleSection() {
  const { t } = useTranslation("console");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  const [enabled, setEnabled] = useState(false);
  const [cpuMax, setCpuMax] = useState("");
  const [memoryMax, setMemoryMax] = useState("");
  const [swapMax, setSwapMax] = useState("");
  const [diskMax, setDiskMax] = useState("");
  const [hits, setHits] = useState("3");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const r = await get<ResourceRule>("/admin/monitoring/resource-rules/detail");
      setEnabled(r.enabled);
      setCpuMax(r.cpu_usage_max == null ? "" : String(r.cpu_usage_max));
      setMemoryMax(r.memory_usage_max == null ? "" : String(r.memory_usage_max));
      setSwapMax(r.swap_usage_max == null ? "" : String(r.swap_usage_max));
      setDiskMax(r.disk_usage_max == null ? "" : String(r.disk_usage_max));
      setHits(String(r.consecutive_hits));
    } catch (err) {
      setError(err instanceof Error ? err.message : t("monitoring.loadFailed"));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    load();
  }, [load]);

  /** 0~100 数字或 null（留空）；非法返回 "err" */
  const parsePercent = (s: string): number | null | "err" => {
    if (!s.trim()) return null;
    const v = Number(s);
    return Number.isFinite(v) && v >= 0 && v <= 100 ? v : "err";
  };

  const save = async () => {
    const cpu = parsePercent(cpuMax);
    const memory = parsePercent(memoryMax);
    const swap = parsePercent(swapMax);
    const disk = parsePercent(diskMax);
    if ([cpu, memory, swap, disk].some((v) => v === "err")) {
      toast.warning(t("monitoring.server.errPercent"));
      return;
    }
    const consecutiveHits = Number(hits);
    if (!Number.isInteger(consecutiveHits) || consecutiveHits < 1 || consecutiveHits > 1440) {
      toast.warning(t("monitoring.server.errHits"));
      return;
    }
    setSaving(true);
    try {
      await post("/admin/monitoring/resource-rules/update", {
        enabled,
        cpu_usage_max: cpu,
        memory_usage_max: memory,
        swap_usage_max: swap,
        disk_usage_max: disk,
        consecutive_hits: consecutiveHits,
      });
      toast.success(t("monitoring.server.ruleSaveSuccess"));
      load();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t("monitoring.saveFailed"));
    } finally {
      setSaving(false);
    }
  };

  const thresholdField = (
    id: string,
    label: string,
    value: string,
    onChange: (v: string) => void
  ) => (
    <div className="space-y-1.5">
      <label htmlFor={id} className="text-sm font-medium">
        {label}
      </label>
      <Input
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={t("monitoring.server.thresholdPlaceholder")}
        inputMode="decimal"
        autoComplete="off"
      />
    </div>
  );

  return (
    <section className="rounded-xl border border-border/60 bg-card/40 p-4">
      <div className="mb-4">
        <h2 className="text-sm font-medium">{t("monitoring.server.ruleTitle")}</h2>
        <p className="mt-0.5 text-xs text-muted-foreground">
          {t("monitoring.server.ruleDesc")}
        </p>
      </div>

      {loading ? (
        <div className="flex justify-center py-10">
          <Loading size="md" />
        </div>
      ) : error ? (
        <div className="flex flex-col items-center gap-2 py-10 text-sm text-muted-foreground">
          <p>{t("monitoring.loadFailedWithReason", { error })}</p>
          <Button variant="outline" size="sm" onClick={load}>
            {t("monitoring.retry")}
          </Button>
        </div>
      ) : (
        <div className="grid max-w-3xl grid-cols-1 gap-5">
          <div className="flex items-center justify-between rounded-lg border border-border/60 px-3 py-2.5">
            <span className="text-sm font-medium">{t("monitoring.enabledLabel")}</span>
            <Switch checked={enabled} onCheckedChange={setEnabled} />
          </div>
          <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
            {thresholdField("res-cpu", t("monitoring.server.cpuMaxLabel"), cpuMax, setCpuMax)}
            {thresholdField("res-memory", t("monitoring.server.memoryMaxLabel"), memoryMax, setMemoryMax)}
            {thresholdField("res-swap", t("monitoring.server.swapMaxLabel"), swapMax, setSwapMax)}
            {thresholdField("res-disk", t("monitoring.server.diskMaxLabel"), diskMax, setDiskMax)}
          </div>
          <div className="max-w-60 space-y-1.5">
            <label htmlFor="res-hits" className="text-sm font-medium">
              {t("monitoring.hitsLabel")}
            </label>
            <Input
              id="res-hits"
              value={hits}
              onChange={(e) => setHits(e.target.value)}
              inputMode="numeric"
              autoComplete="off"
            />
            <p className="text-xs text-muted-foreground">
              {t("monitoring.server.hitsHint")}
            </p>
          </div>
          <div className="pt-1">
            <Button onClick={save} disabled={saving}>
              {saving && <Loading size="sm" />}
              {saving ? t("monitoring.saving") : t("monitoring.saveConfig")}
            </Button>
          </div>
        </div>
      )}
    </section>
  );
}

/**
 * 服务器资源监控：宿主机整机指标（1 分钟粒度）。
 * KPI 卡片 + 分组趋势图 + 每核 CPU / 网卡 / 磁盘明细 + 资源告警阈值。
 */
export function AdminServerTab() {
  const { t } = useTranslation("console");

  const [latest, setLatest] = useState<ServerLatest | null>(null);
  const [latestLoading, setLatestLoading] = useState(true);
  const [latestError, setLatestError] = useState("");

  const [hours, setHours] = useState("6");
  const [trend, setTrend] = useState<ServerTrendResponse | null>(null);
  const [trendLoading, setTrendLoading] = useState(true);
  const [trendError, setTrendError] = useState("");

  const loadLatest = useCallback(async () => {
    setLatestLoading(true);
    setLatestError("");
    try {
      setLatest(await get<ServerLatest>("/admin/monitoring/server/latest"));
    } catch (err) {
      setLatestError(err instanceof Error ? err.message : t("monitoring.loadFailed"));
    } finally {
      setLatestLoading(false);
    }
  }, [t]);

  const loadTrend = useCallback(async () => {
    setTrendLoading(true);
    setTrendError("");
    try {
      setTrend(
        await get<ServerTrendResponse>("/admin/monitoring/server/trend", {
          params: { hours: Number(hours) },
        })
      );
    } catch (err) {
      setTrend(null);
      setTrendError(err instanceof Error ? err.message : t("monitoring.loadFailed"));
    } finally {
      setTrendLoading(false);
    }
  }, [hours, t]);

  useEffect(() => {
    loadLatest();
  }, [loadLatest]);
  useEffect(() => {
    loadTrend();
  }, [loadTrend]);

  /** 对外流量合计：过滤回环 lo；速率不可比的网卡跳过 */
  const netTotal = useMemo(() => {
    if (!latest) return { rx: null as number | null, tx: null as number | null };
    let rx = 0;
    let tx = 0;
    let hasRx = false;
    let hasTx = false;
    for (const nic of latest.network_interfaces) {
      if (nic.name === "lo") continue;
      if (nic.rx_rate_bps != null) {
        rx += nic.rx_rate_bps;
        hasRx = true;
      }
      if (nic.tx_rate_bps != null) {
        tx += nic.tx_rate_bps;
        hasTx = true;
      }
    }
    return { rx: hasRx ? rx : null, tx: hasTx ? tx : null };
  }, [latest]);

  /** 按 group 分图；组内序列单位一致（契约保证） */
  const charts = useMemo(
    () =>
      GROUP_ORDER.map((group) => ({
        group,
        series: (trend?.series ?? []).filter((s) => s.group === group),
      })).filter((c) => c.series.length > 0),
    [trend]
  );

  const errState = (error: string, retry: () => void) => (
    <div className="flex flex-col items-center gap-2 rounded-xl border border-border/60 bg-card/40 py-10 text-sm text-muted-foreground">
      <p>{t("monitoring.loadFailedWithReason", { error })}</p>
      <Button variant="outline" size="sm" onClick={retry}>
        {t("monitoring.retry")}
      </Button>
    </div>
  );

  return (
    <div className="flex flex-col gap-4">
      {/* KPI 卡片 */}
      <section className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-3">
          <h2 className="mr-auto text-sm font-medium">
            {t("monitoring.server.kpiTitle")}
            {latest?.has_data && latest.window_start && (
              <span className="ml-2 text-xs font-normal text-muted-foreground">
                {t("monitoring.server.windowLabel", {
                  time: fmtDateTime(latest.window_start),
                })}
              </span>
            )}
          </h2>
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              loadLatest();
              loadTrend();
            }}
            disabled={latestLoading || trendLoading}
          >
            <RefreshCw className={cn("size-4", (latestLoading || trendLoading) && "animate-spin")} />
            {t("monitoring.refresh")}
          </Button>
        </div>

        {latestLoading && !latest ? (
          <div className="flex justify-center rounded-xl border border-border/60 bg-card/40 py-10">
            <Loading size="md" />
          </div>
        ) : latestError && !latest ? (
          errState(latestError, loadLatest)
        ) : !latest?.has_data ? (
          <div className="rounded-xl border border-border/60 bg-card/40 py-10 text-center text-sm text-muted-foreground">
            {t("monitoring.server.empty")}
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 2xl:grid-cols-6">
            <KpiCard
              label={t("monitoring.server.kpiCpu")}
              value={fmtPercent(latest.cpu.usage_percent)}
              sub={t("monitoring.server.kpiCores", { count: latest.cpu.core_count })}
              danger={(latest.cpu.usage_percent ?? 0) >= DANGER_PERCENT}
            />
            <KpiCard
              label={t("monitoring.server.kpiLoad")}
              value={
                latest.load.load1 == null ? "—" : latest.load.load1.toFixed(2)
              }
              sub={t("monitoring.server.kpiLoadSub", {
                l5: latest.load.load5?.toFixed(2) ?? "—",
                l15: latest.load.load15?.toFixed(2) ?? "—",
              })}
            />
            <KpiCard
              label={t("monitoring.server.kpiMemory")}
              value={fmtPercent(latest.memory.usage_percent)}
              sub={t("monitoring.server.usageOf", {
                used: fmtBytes(latest.memory.used_bytes),
                total: fmtBytes(latest.memory.total_bytes),
              })}
              danger={(latest.memory.usage_percent ?? 0) >= DANGER_PERCENT}
            />
            <KpiCard
              label={t("monitoring.server.kpiSwap")}
              value={
                latest.swap.usage_percent == null
                  ? t("monitoring.server.swapOff")
                  : fmtPercent(latest.swap.usage_percent)
              }
              sub={
                latest.swap.total_bytes == null
                  ? undefined
                  : t("monitoring.server.usageOf", {
                      used: fmtBytes(latest.swap.used_bytes),
                      total: fmtBytes(latest.swap.total_bytes),
                    })
              }
              danger={(latest.swap.usage_percent ?? 0) >= DANGER_PERCENT}
            />
            <KpiCard
              label={t("monitoring.server.kpiDisk")}
              value={fmtPercent(latest.max_disk_usage_percent)}
              sub={latest.max_disk_mount ?? undefined}
              danger={(latest.max_disk_usage_percent ?? 0) >= DANGER_PERCENT}
            />
            <KpiCard
              label={t("monitoring.server.kpiNetwork")}
              value={`↓ ${fmtBps(netTotal.rx)}`}
              sub={`↑ ${fmtBps(netTotal.tx)}`}
            />
          </div>
        )}
      </section>

      {/* 趋势图 */}
      <section className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="mr-auto text-sm font-medium">
            {t("monitoring.server.trendTitle")}
            <span className="ml-2 text-xs font-normal text-muted-foreground">
              {t("monitoring.server.trendHint")}
            </span>
          </h2>
          <Select
            value={hours}
            onValueChange={setHours}
            options={HOURS_OPTIONS.map((h) => ({
              value: String(h),
              label: t("monitoring.hoursOption", { n: h }),
            }))}
            className="w-32"
            aria-label={t("monitoring.trendHoursLabel")}
          />
        </div>

        {trendLoading && !trend ? (
          <div className="flex justify-center rounded-xl border border-border/60 bg-card/40 py-10">
            <Loading size="md" />
          </div>
        ) : trendError ? (
          errState(trendError, loadTrend)
        ) : charts.length === 0 ? (
          <div className="rounded-xl border border-border/60 bg-card/40 py-10 text-center text-sm text-muted-foreground">
            {t("monitoring.trendEmpty")}
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
            {charts.map((c) => (
              <ServerTrendChart
                key={c.group}
                title={t(`monitoring.server.chart.${c.group}`)}
                unit={c.series[0].unit}
                xAxis={trend?.x_axis ?? []}
                series={c.series}
                hours={Number(hours)}
              />
            ))}
          </div>
        )}
      </section>

      {/* 明细：每核 CPU + 磁盘 + 网卡 */}
      {latest?.has_data && (
        <>
          <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
            <section className="rounded-xl border border-border/60 bg-card/40 p-4">
              <h3 className="mb-3 text-sm font-medium">
                {t("monitoring.server.perCoreTitle")}
              </h3>
              {!latest.cpu.per_core_percent ? (
                <p className="py-6 text-center text-sm text-muted-foreground">
                  {t("monitoring.server.perCoreEmpty")}
                </p>
              ) : (
                <div className="grid grid-cols-4 gap-x-3 gap-y-2.5 sm:grid-cols-6">
                  {latest.cpu.per_core_percent.map((v, i) => (
                    <div key={i}>
                      <div className="flex items-baseline justify-between text-[11px]">
                        <span className="text-muted-foreground">#{i}</span>
                        <span
                          className={cn(
                            "font-medium",
                            (v ?? 0) >= DANGER_PERCENT && "text-destructive"
                          )}
                        >
                          {v == null ? "—" : `${v.toFixed(0)}%`}
                        </span>
                      </div>
                      <div className="mt-0.5 h-1.5 overflow-hidden rounded-full bg-muted">
                        <div
                          className={cn(
                            "h-full rounded-full bg-primary transition-all",
                            (v ?? 0) >= DANGER_PERCENT && "bg-destructive"
                          )}
                          style={{ width: `${Math.min(100, Math.max(0, v ?? 0))}%` }}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </section>

            <section className="rounded-xl border border-border/60 bg-card/40 p-4">
              <h3 className="mb-3 text-sm font-medium">
                {t("monitoring.server.diskTitle")}
              </h3>
              {latest.disks.length === 0 ? (
                <p className="py-6 text-center text-sm text-muted-foreground">
                  {t("monitoring.server.diskEmpty")}
                </p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-border/60 text-xs text-muted-foreground">
                        <th className="py-2 pr-4 text-left font-medium">
                          {t("monitoring.server.colMount")}
                        </th>
                        <th className="px-4 py-2 text-right font-medium">
                          {t("monitoring.server.colUsed")}
                        </th>
                        <th className="px-4 py-2 text-right font-medium">
                          {t("monitoring.server.colTotal")}
                        </th>
                        <th className="py-2 pl-4 text-right font-medium">
                          {t("monitoring.server.colUsage")}
                        </th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border/60">
                      {latest.disks.map((d) => (
                        <tr key={d.mount} className="transition-colors hover:bg-accent/40">
                          <td className="max-w-48 truncate py-2 pr-4 font-mono text-xs">
                            {d.mount}
                          </td>
                          <td className="px-4 py-2 text-right whitespace-nowrap text-muted-foreground">
                            {fmtBytes(d.used_bytes)}
                          </td>
                          <td className="px-4 py-2 text-right whitespace-nowrap text-muted-foreground">
                            {fmtBytes(d.total_bytes)}
                          </td>
                          <td
                            className={cn(
                              "py-2 pl-4 text-right whitespace-nowrap",
                              (d.usage_percent ?? 0) >= DANGER_PERCENT &&
                                "font-medium text-destructive"
                            )}
                          >
                            {fmtPercent(d.usage_percent)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>
          </div>

          <section className="rounded-xl border border-border/60 bg-card/40 p-4">
            <h3 className="mb-3 text-sm font-medium">
              {t("monitoring.server.nicTitle")}
              <span className="ml-2 text-xs font-normal text-muted-foreground">
                {t("monitoring.server.nicHint")}
              </span>
            </h3>
            {latest.network_interfaces.length === 0 ? (
              <p className="py-6 text-center text-sm text-muted-foreground">
                {t("monitoring.server.nicEmpty")}
              </p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border/60 text-xs text-muted-foreground">
                      <th className="py-2 pr-4 text-left font-medium">
                        {t("monitoring.server.colNic")}
                      </th>
                      <th className="px-4 py-2 text-right font-medium">
                        {t("monitoring.server.colRxRate")}
                      </th>
                      <th className="px-4 py-2 text-right font-medium">
                        {t("monitoring.server.colTxRate")}
                      </th>
                      <th className="px-4 py-2 text-right font-medium">
                        {t("monitoring.server.colRxBytes")}
                      </th>
                      <th className="px-4 py-2 text-right font-medium">
                        {t("monitoring.server.colTxBytes")}
                      </th>
                      <th className="px-4 py-2 text-right font-medium">
                        {t("monitoring.server.colErrors")}
                      </th>
                      <th className="py-2 pl-4 text-right font-medium">
                        {t("monitoring.server.colDropped")}
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/60">
                    {latest.network_interfaces.map((n) => (
                      <tr key={n.name} className="transition-colors hover:bg-accent/40">
                        <td className="py-2 pr-4 font-mono text-xs">{n.name}</td>
                        <td className="px-4 py-2 text-right whitespace-nowrap">
                          {fmtBps(n.rx_rate_bps)}
                        </td>
                        <td className="px-4 py-2 text-right whitespace-nowrap">
                          {fmtBps(n.tx_rate_bps)}
                        </td>
                        <td className="px-4 py-2 text-right whitespace-nowrap text-muted-foreground">
                          {fmtBytes(n.rx_bytes)}
                        </td>
                        <td className="px-4 py-2 text-right whitespace-nowrap text-muted-foreground">
                          {fmtBytes(n.tx_bytes)}
                        </td>
                        <td className="px-4 py-2 text-right whitespace-nowrap text-muted-foreground">
                          {n.rx_errors} / {n.tx_errors}
                        </td>
                        <td className="py-2 pl-4 text-right whitespace-nowrap text-muted-foreground">
                          {n.rx_dropped} / {n.tx_dropped}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      )}

      {/* 资源告警阈值 */}
      <ResourceRuleSection />
    </div>
  );
}
