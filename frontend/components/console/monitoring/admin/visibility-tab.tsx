"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Loading } from "@/components/ui/loading";
import { Switch } from "@/components/ui/switch";
import { toast } from "@/components/ui/toaster";
import { cn } from "@/lib/utils";
import { get, post } from "@/lib/request";

import {
  REQUEST_TYPES,
  TYPE_COLORS,
  type MonitorMode,
  type MonitorModes,
  type RequestType,
  type UserVisibilityConfig,
} from "../types";

/** 按请求类型的数据模式配置响应 */
type ModeConfig = {
  modes: MonitorModes;
  /** 嗅探周期（秒），默认 60，范围 30–3600 */
  probe_interval_seconds: number;
  updated_at: string | null;
};

/** 监控设置：请求类型 Tab（可见性 + 按类型的数据模式），仅文本可切换真实/嗅探 */
export function AdminVisibilityTab() {
  const { t } = useTranslation("console");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [modes, setModes] = useState<MonitorModes>({
    text: "probe",
    image: "real",
    video: "real",
  });
  const [modeSwitching, setModeSwitching] = useState(false);
  const [intervalInput, setIntervalInput] = useState("60");
  const [intervalSaving, setIntervalSaving] = useState(false);
  const [enabled, setEnabled] = useState(false);
  const [groupIds, setGroupIds] = useState<Set<number>>(new Set());
  const [requestTypes, setRequestTypes] = useState<Set<RequestType>>(
    new Set()
  );
  const [activeType, setActiveType] = useState<RequestType>("text");
  const [options, setOptions] = useState<UserVisibilityConfig["groups"]>([]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [cfg, modeCfg] = await Promise.all([
        get<UserVisibilityConfig>("/admin/monitoring/user-visibility/detail"),
        get<ModeConfig>("/admin/monitoring/mode/detail"),
      ]);
      setEnabled(cfg.enabled);
      setGroupIds(new Set(cfg.group_ids ?? []));
      setRequestTypes(new Set(cfg.request_types ?? []));
      setOptions(cfg.groups ?? []);
      setModes(modeCfg.modes ?? { text: "probe", image: "real", video: "real" });
      setIntervalInput(String(modeCfg.probe_interval_seconds ?? 60));
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : t("monitoring.loadFailed")
      );
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    load();
  }, [load]);

  const toggleGroup = (id: number, checked: boolean) => {
    setGroupIds((prev) => {
      const next = new Set(prev);
      if (checked) next.add(id);
      else next.delete(id);
      return next;
    });
  };

  /** 取消类型可见时，联动剔除不再支持任何已选类型的分组 */
  const pruneGroups = (nextTypes: Set<RequestType>) => {
    setGroupIds((prev) => {
      const next = new Set<number>();
      for (const id of prev) {
        const g = options.find((o) => o.id === id);
        if (g && g.request_types.some((rt) => nextTypes.has(rt))) next.add(id);
      }
      return next;
    });
  };

  /** 切换某个类型对用户可见；启用时默认全选该类型下的分组，禁用时联动剔除失效分组 */
  const toggleTypeVisible = (tp: RequestType, checked: boolean) => {
    const nextTypes = new Set(requestTypes);
    if (checked) nextTypes.add(tp);
    else nextTypes.delete(tp);
    setRequestTypes(nextTypes);
    if (checked) {
      setGroupIds((prev) => {
        const next = new Set(prev);
        for (const g of options) {
          if (g.request_types.includes(tp)) next.add(g.id);
        }
        return next;
      });
    } else {
      pruneGroups(nextTypes);
    }
  };

  /** 各类型已勾选分组数（Tab 角标） */
  const selectedCountByType = useMemo(() => {
    const counts = {} as Record<RequestType, number>;
    for (const tp of REQUEST_TYPES) counts[tp] = 0;
    for (const id of groupIds) {
      const g = options.find((o) => o.id === id);
      if (!g) continue;
      for (const tp of g.request_types) counts[tp] += 1;
    }
    return counts;
  }, [groupIds, options]);

  /** 当前 Tab 下可选的分组：支持当前类型 */
  const activeGroups = useMemo(
    () => options.filter((g) => g.request_types.includes(activeType)),
    [options, activeType]
  );

  /** 当前 Tab 已勾选数量 */
  const activeSelectedCount = useMemo(
    () => activeGroups.filter((g) => groupIds.has(g.id)).length,
    [activeGroups, groupIds]
  );

  /** 全选/清空当前 Tab 下的分组 */
  const setAllActiveGroups = (checked: boolean) => {
    setGroupIds((prev) => {
      const next = new Set(prev);
      for (const g of activeGroups) {
        if (checked) next.add(g.id);
        else next.delete(g.id);
      }
      return next;
    });
  };

  /** 切换文本类型的数据模式：立即生效，影响管理与用户两侧的监控页 */
  const switchTextMode = async (next: MonitorMode) => {
    if (modeSwitching || next === modes.text) return;
    setModeSwitching(true);
    try {
      const res = await post<ModeConfig>("/admin/monitoring/mode/update", {
        modes: { text: next },
      });
      setModes(res.modes);
      toast.success(t("monitoring.modeUpdateSuccess"));
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : t("monitoring.modeUpdateFailed")
      );
    } finally {
      setModeSwitching(false);
    }
  };

  /** 保存嗅探周期：30–3600 秒，复用 mode/update 接口 */
  const saveInterval = async () => {
    const n = Number(intervalInput);
    if (!Number.isInteger(n) || n < 30 || n > 3600) {
      toast.warning(t("monitoring.errProbeInterval"));
      return;
    }
    setIntervalSaving(true);
    try {
      await post("/admin/monitoring/mode/update", {
        probe_interval_seconds: n,
      });
      toast.success(t("monitoring.probeIntervalSaved"));
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : t("monitoring.modeUpdateFailed")
      );
    } finally {
      setIntervalSaving(false);
    }
  };

  const save = async () => {
    // 可见类型集合：全局关闭时视为全部可见
    const visible = enabled
      ? REQUEST_TYPES.filter((tp) => requestTypes.has(tp))
      : [...REQUEST_TYPES];
    if (enabled) {
      if (visible.length === 0) {
        toast.warning(t("monitoring.errVisibilityTypes"));
        return;
      }
      // 按可见类型逐一校验：禁用类型不参与；某类型下有候选分组但一个都没选时拦截
      for (const tp of visible) {
        const candidates = options.filter((g) =>
          g.request_types.includes(tp)
        );
        if (
          candidates.length > 0 &&
          !candidates.some((g) => groupIds.has(g.id))
        ) {
          toast.warning(
            t("monitoring.errVisibilityGroupsPerType", {
              type: t(`monitoring.type.${tp}`),
            })
          );
          return;
        }
      }
    }
    setSaving(true);
    try {
      const res = await post<UserVisibilityConfig>(
        "/admin/monitoring/user-visibility/update",
        {
          enabled,
          // 只提交仍可见类型覆盖的分组，过滤已禁用类型下的残留勾选
          group_ids: [...groupIds].filter((id) => {
            const g = options.find((o) => o.id === id);
            return g && g.request_types.some((tp) => visible.includes(tp));
          }),
          // 按固定顺序提交，避免 Set 迭代顺序导致接口 diff 抖动
          request_types: visible,
        }
      );
      // 直接用响应就地更新，避免重新拉取触发整页 loading 造成布局跳动
      setEnabled(res.enabled);
      setGroupIds(new Set(res.group_ids ?? []));
      setRequestTypes(new Set(res.request_types ?? []));
      setOptions(res.groups ?? []);
      toast.success(t("monitoring.visibilitySaveSuccess"));
    } catch (err) {
      toast.error(
        err instanceof Error
          ? err.message
          : t("monitoring.visibilitySaveFailed")
      );
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex justify-center rounded-xl border border-border/60 bg-card/40 py-16">
        <Loading size="md" />
      </div>
    );
  }

  // 全局可见性关闭时：类型恒为可见且开关禁用
  const typeVisible = enabled ? requestTypes.has(activeType) : true;
  // 分组勾选禁用：全局关闭，或当前类型未对用户可见
  const groupsDisabled = !enabled || !typeVisible;
  const allChecked =
    activeGroups.length > 0 && activeSelectedCount === activeGroups.length;

  return (
    <section className="rounded-xl border border-border/60 bg-card/40 p-4">
      <div className="mb-5">
        <div className="flex items-center gap-3">
          <h2 className="text-sm font-medium">
            {t("monitoring.visibilityTitle")}
          </h2>
          <div className="flex items-center gap-2 rounded-full border border-border/60 bg-muted/30 py-1 pl-3 pr-1.5">
            <span className="text-xs text-muted-foreground">
              {t("monitoring.visibilityEnabledLabel")}
            </span>
            <Switch
              checked={enabled}
              onCheckedChange={(v) => {
                setEnabled(v);
                // 关闭可见性限制时，分组勾选一并清空，恢复为不限
                if (!v) setGroupIds(new Set());
              }}
            />
          </div>
        </div>
        <p className="mt-0.5 text-xs text-muted-foreground">
          {t("monitoring.visibilityDesc")}
        </p>
      </div>

      <div className="grid max-w-3xl grid-cols-1 gap-5">
        {/* 请求类型 Tab 栏：类型色点 + 名称 + 已选分组数；未对用户可见的类型置灰 */}
        <div className="overflow-hidden rounded-xl border border-border/60 bg-background/60">
          <div
            role="tablist"
            aria-label={t("monitoring.visibilityTypesLabel")}
            className="flex gap-1 border-b border-border/60 bg-muted/30 p-1.5"
          >
            {REQUEST_TYPES.map((tp) => {
              const selected = requestTypes.has(tp);
              const active = activeType === tp;
              return (
                <button
                  key={tp}
                  type="button"
                  role="tab"
                  aria-selected={active}
                  onClick={() => setActiveType(tp)}
                  className={cn(
                    "flex flex-1 items-center justify-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium transition-all",
                    active
                      ? "bg-background text-foreground shadow-sm"
                      : "text-muted-foreground hover:text-foreground",
                    !selected && "opacity-50"
                  )}
                >
                  <span
                    className="size-1.5 rounded-full"
                    style={{ backgroundColor: TYPE_COLORS[tp] }}
                  />
                  {t(`monitoring.type.${tp}`)}
                  {selectedCountByType[tp] > 0 && (
                    <Badge
                      variant="outline"
                      className="border-primary/30 bg-primary/10 px-1.5 py-0 text-xs tabular-nums text-primary"
                    >
                      {selectedCountByType[tp]}
                    </Badge>
                  )}
                </button>
              );
            })}
          </div>

          {/* 当前类型面板 */}
          <div className="space-y-4 p-4">
            {/* 第一行：类型可见性开关 + 数据模式 */}
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-center gap-2 rounded-full border border-border/60 bg-muted/30 py-1 pl-3 pr-1.5">
                <span className="text-xs text-muted-foreground">
                  {t("monitoring.typeVisibleLabel", {
                    type: t(`monitoring.type.${activeType}`),
                  })}
                </span>
                <Switch
                  checked={typeVisible}
                  disabled={!enabled}
                  onCheckedChange={(v) => toggleTypeVisible(activeType, v)}
                />
              </div>
              {activeType === "text" ? (
                <div
                  role="group"
                  aria-label={t("monitoring.modeLabel")}
                  className="inline-flex items-center gap-0.5 rounded-full border border-border/60 bg-muted/40 p-0.5"
                >
                  {(["real", "probe"] as const).map((m) => (
                    <button
                      key={m}
                      type="button"
                      disabled={modeSwitching}
                      onClick={() => switchTextMode(m)}
                      className={
                        modes.text === m
                          ? "rounded-full bg-primary px-3 py-1 text-xs font-medium text-primary-foreground shadow-sm transition-all"
                          : "rounded-full px-3 py-1 text-xs font-medium text-muted-foreground transition-all hover:text-foreground"
                      }
                    >
                      {t(`monitoring.mode.${m}`)}
                    </button>
                  ))}
                </div>
              ) : (
                <span className="text-xs text-muted-foreground">
                  {t("monitoring.mode.real")}
                </span>
              )}
            </div>

            {/* 嗅探周期：仅文本嗅探模式下展示，30–3600 秒 */}
            {activeType === "text" && modes.text === "probe" && (
              <div className="flex flex-wrap items-center gap-2 rounded-lg bg-muted/30 px-3 py-2">
                <label
                  htmlFor="probe-interval"
                  className="text-xs text-muted-foreground"
                >
                  {t("monitoring.probeIntervalLabel")}
                </label>
                <Input
                  id="probe-interval"
                  value={intervalInput}
                  onChange={(e) => setIntervalInput(e.target.value)}
                  inputMode="numeric"
                  autoComplete="off"
                  className="h-8 w-24"
                />
                <Button
                  variant="outline"
                  size="sm"
                  onClick={saveInterval}
                  disabled={intervalSaving || modeSwitching}
                >
                  {intervalSaving && <Loading size="sm" />}
                  {t("monitoring.save")}
                </Button>
                <span className="text-xs text-muted-foreground">
                  {t("monitoring.probeIntervalHint")}
                </span>
              </div>
            )}

            {/* 分组选择：明确标题 + 全选 + 卡片式勾选项；全局关闭或类型未对用户可见时禁用勾选 */}
            <div
              className={cn(
                "space-y-2 transition-opacity",
                groupsDisabled && "pointer-events-none opacity-40"
              )}
            >
              <div className="flex items-center justify-between">
                <p className="text-sm font-medium">
                  {t("monitoring.visibilityGroupsLabel")}
                  <span className="ml-1.5 text-xs font-normal text-muted-foreground">
                    {t("monitoring.groupsSelectedCount", {
                      count: activeSelectedCount,
                      total: activeGroups.length,
                    })}
                  </span>
                </p>
                {activeGroups.length > 1 && (
                  <label
                    className={cn(
                      "flex items-center gap-1.5 text-xs text-muted-foreground",
                      groupsDisabled
                        ? "cursor-not-allowed"
                        : "cursor-pointer hover:text-foreground"
                    )}
                  >
                    <input
                      type="checkbox"
                      checked={allChecked}
                      disabled={groupsDisabled}
                      onChange={(e) => setAllActiveGroups(e.target.checked)}
                      className="size-3.5 accent-current disabled:cursor-not-allowed"
                    />
                    {t("monitoring.selectAll")}
                  </label>
                )}
              </div>

              {activeGroups.length === 0 ? (
                <div className="rounded-lg border border-dashed border-border/60 py-6 text-center text-xs text-muted-foreground">
                  {t("monitoring.visibilityGroupsEmpty")}
                </div>
              ) : (
                <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
                  {activeGroups.map((g) => {
                    const checked = groupIds.has(g.id);
                    return (
                      <label
                        key={g.id}
                        className={cn(
                          "flex items-center gap-2 rounded-lg border px-3 py-2 text-sm transition-all",
                          groupsDisabled
                            ? "cursor-not-allowed border-border/60 text-muted-foreground"
                            : checked
                              ? "cursor-pointer border-primary/50 bg-primary/5 text-foreground"
                              : "cursor-pointer border-border/60 text-muted-foreground hover:border-border hover:text-foreground"
                        )}
                      >
                        <input
                          type="checkbox"
                          checked={checked}
                          disabled={groupsDisabled}
                          onChange={(e) => toggleGroup(g.id, e.target.checked)}
                          className="size-3.5 accent-current disabled:cursor-not-allowed"
                        />
                        <span className="truncate">{g.name}</span>
                      </label>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        </div>

        <div className="pt-1">
          <Button onClick={save} disabled={saving}>
            {saving && <Loading size="sm" />}
            {saving ? t("monitoring.saving") : t("monitoring.saveConfig")}
          </Button>
        </div>
      </div>
    </section>
  );
}
