"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Loading } from "@/components/ui/loading";
import { Select } from "@/components/ui/select";
import { cn } from "@/lib/utils";
import { get } from "@/lib/request";

import {
  fmtDateTime,
  fmtMs,
  fmtRate,
  type ChannelListResponse,
} from "../types";
import { useGroupMetricsList } from "../use-group-metrics";

/**
 * 渠道维度指标：最新一个已固化窗口的「分组 × 渠道 × 类型」，
 * 用于定位是哪个渠道在报错或变慢；该数据不落历史。
 */
export function AdminChannelsTab() {
  const { t } = useTranslation("console");
  const { groups } = useGroupMetricsList("/admin");
  const [groupId, setGroupId] = useState("all");

  const [data, setData] = useState<ChannelListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const res = await get<ChannelListResponse>(
        "/admin/monitoring/channels/list",
        { params: { group_id: groupId === "all" ? undefined : Number(groupId) } }
      );
      setData(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("monitoring.loadFailed"));
    } finally {
      setLoading(false);
    }
  }, [groupId, t]);

  useEffect(() => {
    load();
  }, [load]);

  const groupOptions = useMemo(
    () => [
      { value: "all", label: t("monitoring.allGroups") },
      ...groups.map((g) => ({ value: String(g.id), label: g.name })),
    ],
    [groups, t]
  );

  return (
    <section className="rounded-xl border border-border/60 bg-card/40 p-4">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-medium">{t("monitoring.channelsTitle")}</h2>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {data?.window_start
              ? t("monitoring.channelsWindowLabel", {
                  time: fmtDateTime(data.window_start),
                })
              : t("monitoring.channelsWindowEmpty")}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Select
            value={groupId}
            onValueChange={setGroupId}
            options={groupOptions}
            className="w-44"
            aria-label={t("monitoring.colGroup")}
          />
          <Button
            variant="outline"
            size="sm"
            onClick={load}
            disabled={loading}
          >
            <RefreshCw className={cn("size-4", loading && "animate-spin")} />
            {t("monitoring.refresh")}
          </Button>
        </div>
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
      ) : !data || data.items.length === 0 ? (
        <div className="py-10 text-center text-sm text-muted-foreground">
          {t("monitoring.channelsEmpty")}
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border/60 text-xs text-muted-foreground">
                <th className="py-2.5 pr-4 text-left font-medium">
                  {t("monitoring.colGroup")}
                </th>
                <th className="px-4 py-2.5 text-left font-medium">
                  {t("monitoring.colChannel")}
                </th>
                <th className="px-4 py-2.5 text-left font-medium">
                  {t("monitoring.colType")}
                </th>
                <th className="px-4 py-2.5 text-center font-medium">
                  {t("monitoring.colSamples")}
                </th>
                <th className="px-4 py-2.5 text-center font-medium">
                  {t("monitoring.colSuccessRate")}
                </th>
                <th className="px-4 py-2.5 text-center font-medium">
                  {t("monitoring.colAvgDuration")}
                </th>
                <th className="py-2.5 pl-4 text-center font-medium">
                  {t("monitoring.colFirstToken")}
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/60">
              {data.items.map((it) => {
                const lowRate =
                  it.success_rate != null && it.success_rate < 0.9;
                return (
                  <tr
                    key={`${it.group_id}-${it.channel_id}-${it.request_type}`}
                    className="transition-colors hover:bg-accent/40"
                  >
                    <td className="max-w-40 truncate py-2.5 pr-4">
                      {it.group_name}
                    </td>
                    <td className="max-w-48 truncate px-4 py-2.5">
                      {it.channel_name}
                    </td>
                    <td className="px-4 py-2.5 text-muted-foreground">
                      {t(`monitoring.type.${it.request_type}`)}
                    </td>
                    <td className="px-4 py-2.5 text-center">{it.sample_count}</td>
                    <td
                      className={cn(
                        "px-4 py-2.5 text-center",
                        lowRate && "font-medium text-destructive"
                      )}
                    >
                      {fmtRate(it.success_rate)}
                    </td>
                    <td className="px-4 py-2.5 text-center text-muted-foreground">
                      {fmtMs(it.average_duration_ms)}
                    </td>
                    <td className="py-2.5 pl-4 text-center text-muted-foreground">
                      {it.request_type === "text"
                        ? fmtMs(it.average_first_token_ms)
                        : "—"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
