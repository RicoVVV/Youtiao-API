/**
 * 侧边栏模块可见性接口封装
 * - 公开查询：GET /api/system-settings/sidebar-modules/detail（无鉴权）
 * - 管理员查询：GET /api/admin/system-settings/sidebar-modules/detail
 * - 管理员整体替换：POST /api/admin/system-settings/sidebar-modules/update
 *
 * 详见 docs/侧边栏模块前端接入文档.md
 */

import { get, post } from "@/lib/request";

/** 模块 key → console.json 中的菜单文案键（nav.*） */
export const MODULE_LABEL_KEYS: Record<string, string> = {
  playground: "nav.playground",
  canvas: "nav.canvas",
  usage: "nav.usage",
  monitoring: "nav.monitoring",
  "api-keys": "nav.apiKeys",
  "usage-records": "nav.usageRecords",
  billing: "nav.billing",
  affiliate: "nav.affiliate",
  profile: "nav.profile",
};

/** 分组 key → console.json 中的分组标题键（nav.*） */
export const GROUP_LABEL_KEYS: Record<string, string> = {
  chat: "nav.chat",
  general: "nav.general",
  account: "nav.account",
};

/** 从 /console/<key> 路径解析模块 key；不在目录内（如 overview、管理页）返回 null */
export function moduleKeyFromPath(barePath: string): string | null {
  const seg = barePath.replace(/^\/console\/?/, "").split("/")[0];
  return seg && seg in MODULE_LABEL_KEYS ? seg : null;
}

/** 公开查询响应：生效可见的模块 key 列表 */
export type VisibleSidebarModules = {
  modules: string[];
};

/** 管理端目录与配置 */
export type SidebarModulesCatalog = {
  groups: { key: string; modules: string[] }[];
};

export type SidebarModulesVisibility = {
  groups: Record<string, boolean>;
  modules: Record<string, boolean>;
};

export type AdminSidebarModulesDetail = {
  catalog: SidebarModulesCatalog;
  visibility: SidebarModulesVisibility;
};

/** 整体替换请求体：提交内容即落库内容，空对象表示重置为默认（全部可见） */
export type SidebarModulesUpdatePayload = SidebarModulesVisibility;

/** 公开读取可见模块（无需登录） */
export function getVisibleSidebarModules() {
  return get<VisibleSidebarModules>("/system-settings/sidebar-modules/detail");
}

/** 管理员读取目录与当前配置（visibility 已补全全部键） */
export function getAdminSidebarModules() {
  return get<AdminSidebarModulesDetail>(
    "/admin/system-settings/sidebar-modules/detail"
  );
}

/** 管理员整体替换配置；传 {groups:{},modules:{}} 重置为默认。响应为更新后的完整状态 */
export function updateAdminSidebarModules(payload: SidebarModulesUpdatePayload) {
  return post<AdminSidebarModulesDetail>(
    "/admin/system-settings/sidebar-modules/update",
    payload
  );
}
