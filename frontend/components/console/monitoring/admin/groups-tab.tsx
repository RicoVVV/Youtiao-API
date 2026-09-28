"use client";

import { GroupStatusWall } from "../status-wall";

/** 管理侧分组指标：全部分组（含停用/受限）状态卡片墙，可跨 168 小时 */
export function AdminGroupsTab() {
  return (
    <GroupStatusWall
      apiBase="/admin"
      mode="admin"
      hoursOptions={[1, 6, 24, 72, 168]}
    />
  );
}
