"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Loading } from "@/components/ui/loading";
import { Pagination } from "@/components/ui/pagination";
import { Select } from "@/components/ui/select";
import { toast } from "@/components/ui/toaster";
import { cn } from "@/lib/utils";
import { get, post } from "@/lib/request";

import {
  fmtDateTime,
  fmtMetricValue,
  type AlertItem,
  type AlertStatus,
  type NotifyStatus,
  type Paged,
} from "../types";
import { useGroupMetricsList } from "../use-group-metrics";

const PAGE_SIZE = 20;

const STATUS_VALUES: AlertStatus[] = [
  "pending",
  "open",
  "resolved",
  "acknowledged",
  "ignored",
];

const METRIC_VALUES = [
  "success_rate",
  "average_duration_ms",
  "average_first_token_ms",
  "cpu_usage",
  "memory_usage",
  "swap_usage",
  "disk_usage",
] as const;

/** 告警状态徽标配色 */
const STATUS_BADGE: Record<AlertStatus, string> = {
  pending: "border-warning/50 text-warning",
  open: "border-transparent bg-destructive text-white",
  resolved: "border-success/50 text-success",
  acknowledged: "border-transparent bg-secondary text-secondary-foreground",
  ignored: "border-transparent bg-muted text-muted-foreground",
};

const NOTIFY_BADGE: Record<NotifyStatus, string> = {
  pending: "border-border text-muted-foreground",
  sent: "border-success/50 text-success",
  failed: "border-destructive/50 text-destructive",
  skipped: "border-border text-muted-foreground",
};

/** 告警记录：筛选 + 分页 + 确认/忽略处置 */
export function AdminAlertsTab() {
  const { t } = useTranslation("console");
  const { groups } = useGroupMetricsList("/admin");

  /* 筛选条件（查询按钮生效） */
  const [scope, setScope] = useState("all");
  const [status, setStatus] = useState("all");
  const [metric, setMetric] = useState("all");
  const [groupId, setGroupId] = useState("all");
  const [hours, setHours] = useState("24");
  const [applied, setApplied] = useState({ scope: "all", status: "all", metric: "all", groupId: "all", hours: "24" });

  const [page, setPage] = useState(1);
  const [data, setData] = useState<Paged<AlertItem> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  /** 正在处置的告警 id，防止重复点击 */
  const [actingId, setActingId] = useState<string | null>(null);

  const load = useCallback(
    async (p: number) => {
      setLoading(true);
      setError("");
      try {
        const h = Number(applied.hours);
        const res = await get<Paged<AlertItem>>("/admin/monitoring/alerts/list", {
          params: {
            scope: applied.scope === "all" ? undefined : applied.scope,
            status: applied.status === "all" ? undefined : applied.status,
            metric: applied.metric === "all" ? undefined : applied.metric,
            // 资源告警没有分组维度：scope=server 时不传 group_id，避免把结果过滤空
            group_id:
              applied.scope === "server" || applied.groupId === "all"
                ? undefined
                : Number(applied.groupId),
            hours: applied.hours && Number.isFinite(h) && h > 0 ? h : undefined,
            page: p,
            page_size: PAGE_SIZE,
          },
        });
        setData(res);
      } catch (err) {
        setError(err instanceof Error ? err.message : t("monitoring.loadFailed"));
      } finally {
        setLoading(false);
      }
    },
    [applied, t]
  );

  useEffect(() => {
    load(page);
  }, [load, page]);

  const search = () => {
    const h = hours.trim();
    if (h && (!/^\d+$/.test(h) || Number(h) < 1 || Number(h) > 720)) {
      toast.warning(t("monitoring.alertsHoursInvalid"));
      return;
    }
    setApplied({ scope, status, metric, groupId, hours });
    // applied / page 变化会触发上面的 effect 重新加载
    setPage(1);
  };

  /** 处置告警：acknowledged / ignored；只有 pending/open 可处置，已结束的由后端返回 422 */
  const act = async (alert: AlertItem, target: "acknowledged" | "ignored") => {
    setActingId(alert.id);
    try {
      await post("/admin/monitoring/alerts/update-status", {
        alert_id: alert.id,
        status: target,
      });
      toast.success(
        t(target === "acknowledged" ? "monitoring.ackSuccess" : "monitoring.ignoreSuccess")
      );
      load(page);
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : t("monitoring.actionFailed")
      );
    } finally {
      setActingId(null);
    }
  };

  const groupOptions = useMemo(
    () => [
      { value: "all", label: t("monitoring.allGroups") },
      ...groups.map((g) => ({ value: String(g.id), label: g.name })),
    ],
    [groups, t]
  );

  const totalPages = Math.max(1, Math.ceil((data?.total ?? 0) / PAGE_SIZE));

  return (
    <section className="rounded-xl border border-border/60 bg-card/40 p-4">
      {/* 筛选区 */}
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <h2 className="mr-auto text-sm font-medium">
          {t("monitoring.alertsTitle")}
          {data && (
            <span className="ml-2 text-xs font-normal text-muted-foreground">
              {t("monitoring.alertsTotal", { total: data.total })}
            </span>
          )}
        </h2>
        <Select
          value={scope}
          onValueChange={setScope}
          options={[
            { value: "all", label: t("monitoring.scope.all") },
            { value: "group", label: t("monitoring.scope.group") },
            { value: "server", label: t("monitoring.scope.server") },
          ]}
          className="w-32"
          aria-label={t("monitoring.filterScope")}
        />
        <Select
          value={status}
          onValueChange={setStatus}
          options={[
            { value: "all", label: t("monitoring.status.all") },
            ...STATUS_VALUES.map((s) => ({
              value: s,
              label: t(`monitoring.status.${s}`),
            })),
          ]}
          className="w-32"
          aria-label={t("monitoring.filterStatus")}
        />
        <Select
          value={metric}
          onValueChange={setMetric}
          options={[
            { value: "all", label: t("monitoring.metricAll") },
            ...METRIC_VALUES.map((m) => ({
              value: m,
              label: t(`monitoring.metric.${m}`),
            })),
          ]}
          className="w-36"
          aria-label={t("monitoring.filterMetric")}
        />
        {/* 资源告警无分组维度，scope=server 时隐藏分组筛选 */}
        {scope !== "server" && (
          <Select
            value={groupId}
            onValueChange={setGroupId}
            options={groupOptions}
            className="w-40"
            aria-label={t("monitoring.colGroup")}
          />
        )}
        <Input
          value={hours}
          onChange={(e) => setHours(e.target.value)}
          placeholder={t("monitoring.hoursPlaceholder")}
          className="w-36"
          inputMode="numeric"
          aria-label={t("monitoring.filterHours")}
        />
        <Button variant="outline" size="sm" onClick={search} disabled={loading}>
          {t("monitoring.search")}
        </Button>
      </div>

      {loading && !data ? (
        <div className="flex justify-center py-10">
          <Loading size="md" />
        </div>
      ) : error ? (
        <div className="flex flex-col items-center gap-2 py-10 text-sm text-muted-foreground">
          <p>{t("monitoring.loadFailedWithReason", { error })}</p>
          <Button variant="outline" size="sm" onClick={() => load(page)}>
            {t("monitoring.retry")}
          </Button>
        </div>
      ) : !data || data.items.length === 0 ? (
        <div className="py-10 text-center text-sm text-muted-foreground">
          {t("monitoring.alertsEmpty")}
        </div>
      ) : (
        <>
          <div
            className={cn(
              "overflow-x-auto transition-opacity duration-300",
              loading && "pointer-events-none opacity-40"
            )}
          >
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border/60 text-xs text-muted-foreground">
                  <th className="py-2.5 pr-4 text-left font-medium">
                    {t("monitoring.colTriggerTime")}
                  </th>
                  <th className="px-4 py-2.5 text-left font-medium">
                    {t("monitoring.colGroup")}
                  </th>
                  <th className="px-4 py-2.5 text-left font-medium">
                    {t("monitoring.colChannel")}
                  </th>
                  <th className="px-4 py-2.5 text-left font-medium">
                    {t("monitoring.colMetric")}
                  </th>
                  <th className="px-4 py-2.5 text-center font-medium">
                    {t("monitoring.colStatus")}
                  </th>
                  <th className="px-4 py-2.5 text-center font-medium">
                    {t("monitoring.colValue")}
                  </th>
                  <th className="px-4 py-2.5 text-center font-medium">
                    {t("monitoring.colSamples")}
                  </th>
                  <th className="px-4 py-2.5 text-center font-medium">
                    {t("monitoring.colConsecutive")}
                  </th>
                  <th className="px-4 py-2.5 text-center font-medium">
                    {t("monitoring.colNotify")}
                  </th>
                  <th className="py-2.5 pl-4 text-center font-medium">
                    {t("monitoring.colActions")}
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/60">
                {data.items.map((a) => {
                  const actionable = a.status === "pending" || a.status === "open";
                  // 服务器资源告警：group / channel 均为 null，样本数恒为 1（不展示）
                  const isServer = a.group_id === null;
                  return (
                    <tr key={a.id} className="transition-colors hover:bg-accent/40">
                      <td className="py-2.5 pr-4 whitespace-nowrap text-muted-foreground">
                        {fmtDateTime(a.triggered_at ?? a.last_window_start)}
                      </td>
                      <td className="max-w-36 truncate px-4 py-2.5">
                        {isServer ? (
                          <Badge variant="secondary">
                            {t("monitoring.scope.server")}
                          </Badge>
                        ) : (
                          a.group_name
                        )}
                      </td>
                      <td className="max-w-36 truncate px-4 py-2.5">
                        {isServer ? (
                          <span className="text-xs text-muted-foreground">—</span>
                        ) : (
                          (a.channel_name ?? (
                            <Badge variant="outline" className="text-muted-foreground">
                              {t("monitoring.groupLevel")}
                            </Badge>
                          ))
                        )}
                      </td>
                      <td className="px-4 py-2.5 whitespace-nowrap">
                        {t(`monitoring.metric.${a.metric}`)}
                      </td>
                      <td className="px-4 py-2.5 text-center">
                        <Badge variant="outline" className={STATUS_BADGE[a.status]}>
                          {t(`monitoring.status.${a.status}`)}
                        </Badge>
                      </td>
                      <td className="px-4 py-2.5 text-center whitespace-nowrap">
                        {fmtMetricValue(a.metric, a.actual_value)}
                        <span className="mx-1 text-muted-foreground">/</span>
                        <span className="text-muted-foreground">
                          {fmtMetricValue(a.metric, a.threshold_value)}
                        </span>
                      </td>
                      <td className="px-4 py-2.5 text-center">
                        {isServer ? (
                          <span className="text-xs text-muted-foreground">—</span>
                        ) : (
                          a.sample_count
                        )}
                      </td>
                      <td className="px-4 py-2.5 text-center">{a.consecutive_hits}</td>
                      <td className="px-4 py-2.5 text-center">
                        <Badge
                          variant="outline"
                          className={NOTIFY_BADGE[a.notification_status]}
                          title={a.notification_error ?? undefined}
                        >
                          {t(`monitoring.notify.${a.notification_status}`)}
                        </Badge>
                      </td>
                      <td className="py-2.5 pl-4 text-center whitespace-nowrap">
                        {actionable ? (
                          <div className="flex items-center justify-center gap-1.5">
                            <Button
                              variant="outline"
                              size="sm"
                              disabled={actingId === a.id}
                              onClick={() => act(a, "acknowledged")}
                            >
                              {t("monitoring.ack")}
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              disabled={actingId === a.id}
                              onClick={() => act(a, "ignored")}
                            >
                              {t("monitoring.ignore")}
                            </Button>
                          </div>
                        ) : (
                          <span className="text-xs text-muted-foreground">—</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          {totalPages > 1 && (
            <Pagination
              page={page}
              totalPages={totalPages}
              loading={loading}
              onChange={setPage}
              className="mt-4"
            />
          )}
        </>
      )}
    </section>
  );
}
