"use client";

import { useTranslation } from "react-i18next";

import { GroupStatusWall } from "./status-wall";

/** 用户侧分组监控：可用分组的状态卡片墙（指标汇总 + 逐窗口状态条） */
export function MonitoringPanel() {
  const { t } = useTranslation("console");

  return (
    <div className="flex w-full flex-col gap-6">
      <div>
        <h1 className="text-lg font-semibold">{t("monitoring.title")}</h1>
        <p className="mt-0.5 text-sm text-muted-foreground">
          {t("monitoring.subtitle")}
          <span className="ml-2 text-xs">{t("monitoring.delayHint")}</span>
        </p>
      </div>

      <GroupStatusWall apiBase="" mode="user" hoursOptions={[1, 3, 6, 12, 24]} />
    </div>
  );
}
