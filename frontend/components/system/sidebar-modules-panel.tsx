"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { RotateCcw, Save } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Loading } from "@/components/ui/loading";
import { Switch } from "@/components/ui/switch";
import { toast } from "@/components/ui/toaster";
import {
  getAdminSidebarModules,
  updateAdminSidebarModules,
  GROUP_LABEL_KEYS,
  MODULE_LABEL_KEYS,
  type AdminSidebarModulesDetail,
  type SidebarModulesCatalog,
} from "@/lib/sidebar-modules";
import { invalidateSidebarModulesCache } from "@/lib/use-sidebar-modules";

type VisibilityState = {
  groups: Record<string, boolean>;
  modules: Record<string, boolean>;
};

/**
 * 侧边栏模块配置面板（/system/sidebar-modules 独立页面）：
 * 分组/模块两层开关，整体替换提交；父开关联动批量设置子项由前端实现。
 * 配置全站生效，对所有用户一致。
 */
export function SidebarModulesPanel() {
  const { t } = useTranslation("console");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [catalog, setCatalog] = useState<SidebarModulesCatalog>({ groups: [] });
  const [form, setForm] = useState<VisibilityState>({ groups: {}, modules: {} });
  /** 加载/保存成功时的快照，用于判断是否有改动 */
  const [initial, setInitial] = useState<VisibilityState | null>(null);

  const applyDetail = (data: AdminSidebarModulesDetail) => {
    const snapshot = {
      groups: { ...data.visibility.groups },
      modules: { ...data.visibility.modules },
    };
    setCatalog(data.catalog);
    setForm(snapshot);
    setInitial(snapshot);
  };

  /* ── 加载目录与当前配置 ── */
  const loadingRef = useRef(false);
  const load = useCallback(async () => {
    if (loadingRef.current) return;
    loadingRef.current = true;
    try {
      applyDetail(await getAdminSidebarModules());
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t("sidebarModules.loadFailed"));
    } finally {
      loadingRef.current = false;
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    // 异步触发，避免在 effect 体内同步 setState 造成级联渲染
    const timer = setTimeout(load, 0);
    return () => clearTimeout(timer);
  }, [load]);

  /* ── 开关联动：父开关批量设置子项 ── */
  const toggleGroup = (groupKey: string, checked: boolean) => {
    const group = catalog.groups.find((g) => g.key === groupKey);
    setForm((prev) => {
      const modules = { ...prev.modules };
      group?.modules.forEach((m) => {
        modules[m] = checked;
      });
      return { groups: { ...prev.groups, [groupKey]: checked }, modules };
    });
  };

  const toggleModule = (moduleKey: string, checked: boolean) => {
    setForm((prev) => ({
      ...prev,
      modules: { ...prev.modules, [moduleKey]: checked },
    }));
  };

  const dirty =
    initial !== null &&
    (JSON.stringify(form.groups) !== JSON.stringify(initial.groups) ||
      JSON.stringify(form.modules) !== JSON.stringify(initial.modules));

  /* ── 保存：整体替换（提交目录给出的全部键） ── */
  const save = async () => {
    if (!dirty) {
      toast.info(t("systemSettings.noChanges"));
      return;
    }
    setSaving(true);
    try {
      applyDetail(await updateAdminSidebarModules(form));
      // 全站配置已变更，失效可见模块缓存以便侧边栏重新拉取
      invalidateSidebarModulesCache();
      toast.success(t("sidebarModules.saveSuccess"));
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t("sidebarModules.saveFailed"));
    } finally {
      setSaving(false);
    }
  };

  /* ── 重置为默认（全部可见）= 提交空 map ── */
  const reset = async () => {
    setResetting(true);
    try {
      applyDetail(await updateAdminSidebarModules({ groups: {}, modules: {} }));
      invalidateSidebarModulesCache();
      toast.success(t("sidebarModules.resetSuccess"));
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t("sidebarModules.saveFailed"));
    } finally {
      setResetting(false);
    }
  };

  if (loading) {
    return (
      <div className="flex h-40 items-center justify-center">
        <Loading size="lg" text={t("systemSettings.loading")} />
      </div>
    );
  }

  return (
    <section className="space-y-6">
      <div className="flex items-center justify-between gap-4">
        <h1 className="text-xl font-semibold">{t("sidebarModules.title")}</h1>
        <div className="flex shrink-0 gap-2">
          <Button variant="outline" onClick={reset} disabled={saving || resetting}>
            <RotateCcw className="size-4" />
            {resetting ? t("systemSettings.saving") : t("sidebarModules.reset")}
          </Button>
          <Button onClick={save} disabled={saving || resetting || !dirty}>
            <Save className="size-4" />
            {saving ? t("systemSettings.saving") : t("sidebarModules.save")}
          </Button>
        </div>
      </div>

      <div className="space-y-6">
        {catalog.groups.map((group) => {
          const groupOn = form.groups[group.key] ?? true;
          return (
            <div
              key={group.key}
              className="rounded-2xl border border-border bg-card p-5 shadow-card sm:p-6"
            >
              {/* 分组头部：标题 + 描述 + 总开关 */}
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="text-base font-semibold">
                    {t(GROUP_LABEL_KEYS[group.key] ?? group.key)}
                  </p>
                  <p className="mt-0.5 text-sm text-muted-foreground">
                    {t(`sidebarModules.groupDesc.${group.key}`)}
                  </p>
                </div>
                <Switch
                  checked={groupOn}
                  onCheckedChange={(v) => toggleGroup(group.key, v)}
                />
              </div>
              {/* 模块列表：两列网格；分组关闭时子开关置灰 */}
              <ul className="mt-4 grid grid-cols-1 gap-x-10 sm:grid-cols-2">
                {group.modules.map((moduleKey) => (
                  <li
                    key={moduleKey}
                    className="flex items-center justify-between gap-4 py-3"
                  >
                    <div>
                      <p className="text-sm font-medium">
                        {t(MODULE_LABEL_KEYS[moduleKey] ?? moduleKey)}
                      </p>
                      <p className="mt-0.5 text-xs text-muted-foreground">
                        {t(`sidebarModules.moduleDesc.${moduleKey}`)}
                      </p>
                    </div>
                    <Switch
                      checked={groupOn && (form.modules[moduleKey] ?? true)}
                      disabled={!groupOn}
                      onCheckedChange={(v) => toggleModule(moduleKey, v)}
                    />
                  </li>
                ))}
              </ul>
            </div>
          );
        })}
      </div>
    </section>
  );
}
