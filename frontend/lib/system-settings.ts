/**
 * 系统设置接口封装
 * - 公开查询：GET /api/system-settings/detail（无鉴权）
 * - 管理员查询：GET /api/admin/system-settings/detail
 * - 管理员全量更新：POST /api/admin/system-settings/update
 *
 * 详见 docs/system-settings-frontend-integration.md
 */

import { get, post } from "@/lib/request";

/** 系统设置对象（三个接口返回结构一致） */
export type SystemSettings = {
  /** 系统/站点名称 */
  system_name: string;
  /** 平台公开服务器地址（响应中为规范化 HTTP/HTTPS URL） */
  server_url: string;
  /** 徽标公开 URL；未设置时为空字符串 */
  logo_url: string;
  /** 页脚文本 */
  footer_text: string;
  /** 关于页面内容 */
  about_content: string;
  /** 首页内容 */
  homepage_content: string;
  /** 用户服务条款内容 */
  terms_of_service: string;
  /** 隐私政策内容 */
  privacy_policy: string;
};

/** 全量更新请求体：除 logo_url 外均不可为 null */
export type SystemSettingsUpdatePayload = Omit<SystemSettings, "logo_url"> & {
  /** 传 null 清空徽标；填写时必须是 HTTP/HTTPS URL */
  logo_url: string | null;
};

/** 公开读取系统设置（无需登录） */
export function getPublicSystemSettings() {
  return get<SystemSettings>("/system-settings/detail");
}

/** 管理员读取系统设置 */
export function getAdminSystemSettings() {
  return get<SystemSettings>("/admin/system-settings/detail");
}

/** 管理员更新系统设置（差异提交，仅传变更字段），返回后端规范化后的完整对象 */
export function updateAdminSystemSettings(
  payload: Partial<SystemSettingsUpdatePayload>
) {
  return post<SystemSettings>("/admin/system-settings/update", payload);
}
