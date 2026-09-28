"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { get } from "@/lib/request";

import type { GroupListResponse } from "./types";

/** 带告警状态的分组项（由列表接口去重得出） */
export type TrendGroup = {
  id: number;
  name: string;
  hasAlert: boolean;
  alertCount: number;
};

/** 拉取分组指标列表；apiBase 为 ""（用户侧）或 "/admin"（管理侧） */
export function useGroupMetricsList(apiBase: "" | "/admin") {
  const { t } = useTranslation("console");
  const [data, setData] = useState<GroupListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const res = await get<GroupListResponse>(
        `${apiBase}/monitoring/groups/list`
      );
      setData(res);
      setUpdatedAt(new Date());
    } catch (err) {
      setError(err instanceof Error ? err.message : t("monitoring.loadFailed"));
    } finally {
      setLoading(false);
    }
  }, [apiBase, t]);

  useEffect(() => {
    reload();
  }, [reload]);

  /** 去重后的分组选项（含告警状态），供状态卡片/筛选下拉使用 */
  const groups = useMemo(() => {
    const seen = new Map<number, TrendGroup>();
    for (const it of data?.items ?? []) {
      const g = seen.get(it.group_id);
      if (!g) {
        seen.set(it.group_id, {
          id: it.group_id,
          name: it.group_name,
          hasAlert: it.has_open_alert ?? false,
          alertCount: it.open_alert_count ?? 0,
        });
      } else {
        g.hasAlert = g.hasAlert || (it.has_open_alert ?? false);
        g.alertCount = Math.max(g.alertCount, it.open_alert_count ?? 0);
      }
    }
    return [...seen.values()];
  }, [data]);

  return { data, groups, loading, error, updatedAt, reload };
}
