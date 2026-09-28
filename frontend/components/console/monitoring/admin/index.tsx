"use client";

import { useState } from "react";
import { useTranslation } from "react-i18next";

import { cn } from "@/lib/utils";

import { AdminAlertsTab } from "./alerts-tab";
import { AdminChannelsTab } from "./channels-tab";
import { AdminGroupsTab } from "./groups-tab";
import { AdminNotificationTab } from "./notification-tab";
import { AdminRulesTab } from "./rules-tab";
import { AdminServerTab } from "./server-tab";

const TABS = ["groups", "channels", "server", "alerts", "rules", "notification"] as const;
type TabKey = (typeof TABS)[number];

/** 管理侧监控告警：分组/渠道指标 + 服务器资源 + 告警记录 + 阈值规则 + 钉钉推送配置 */
export function AdminMonitoringPanel() {
  const { t } = useTranslation("console");
  const [tab, setTab] = useState<TabKey>("groups");

  return (
    <div className="flex w-full flex-col gap-6">
      <div>
        <h1 className="text-lg font-semibold">{t("monitoring.adminTitle")}</h1>
        <p className="mt-0.5 text-sm text-muted-foreground">
          {t("monitoring.adminSubtitle")}
          <span className="ml-2 text-xs">{t("monitoring.delayHint")}</span>
        </p>
      </div>

      {/* 标签页切换：仅挂载当前页签，各自拉取数据 */}
      <div className="inline-flex w-fit items-center gap-1 rounded-lg bg-muted/60 p-1">
        {TABS.map((key) => (
          <button
            key={key}
            type="button"
            onClick={() => setTab(key)}
            className={cn(
              "min-w-24 rounded-md px-4 py-1.5 text-sm font-medium transition-all",
              tab === key
                ? "bg-card text-foreground shadow-[0_1px_3px_rgb(0_0_0/8%),0_1px_2px_rgb(0_0_0/4%)]"
                : "text-muted-foreground hover:text-foreground"
            )}
          >
            {t(`monitoring.tab.${key}`)}
          </button>
        ))}
      </div>

      {tab === "groups" && <AdminGroupsTab />}
      {tab === "channels" && <AdminChannelsTab />}
      {tab === "server" && <AdminServerTab />}
      {tab === "alerts" && <AdminAlertsTab />}
      {tab === "rules" && <AdminRulesTab />}
      {tab === "notification" && <AdminNotificationTab />}
    </div>
  );
}
