/**
 * 系统设置接口封装
 * - 公开查询：GET /api/system-settings/detail（无鉴权）
 * - 管理员查询：GET /api/admin/system-settings/detail
 * - 管理员全量更新：POST /api/admin/system-settings/update
 *
 * 详见 docs/system-settings-frontend-integration.md
 * 与 docs/register-email-verification-frontend-integration.md（邮箱验证与 SMTP 配置）
 */

import { get, post } from "@/lib/request";

/** SMTP 加密方式：465 端口通常用 ssl */
export type SmtpSecurity = "none" | "starttls" | "ssl";

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
  /** 注册邮箱验证开关：true 时注册必须提供邮箱与验证码 */
  email_verification_enabled: boolean;
};

/** 管理员系统设置：公开字段 + SMTP 配置（不返回密码明文/密文） */
export type AdminSystemSettings = SystemSettings & {
  /** SMTP 服务器地址 */
  smtp_host: string;
  /** SMTP 端口，默认 587 */
  smtp_port: number;
  /** 加密方式，默认 starttls */
  smtp_security: SmtpSecurity;
  /** SMTP 登录用户名，可为空（不认证） */
  smtp_username: string;
  /** 是否已保存 SMTP 密码 */
  smtp_password_configured: boolean;
  /** 发件人邮箱 */
  smtp_from_email: string;
  /** 发件人名称；为空时发信使用系统名称 */
  smtp_from_name: string;
  /** 余额预警总开关；开启后用户可自行设置阈值 */
  balance_alert_enabled: boolean;
  /** 是否定时测试所有渠道 */
  channel_probe_enabled: boolean;
  /** 定时测试间隔分钟数，1–1440 */
  channel_probe_interval_minutes: number;
  /** 单次测试最长响应秒数，1–600 */
  channel_probe_timeout_seconds: number;
  /** 失败时是否自动禁用渠道 */
  channel_auto_disable_enabled: boolean;
  /** 成功后是否自动启用渠道 */
  channel_auto_enable_enabled: boolean;
  /** 触发自动禁用的上游状态码（单码/范围，逗号分隔） */
  channel_auto_disable_status_codes: string;
  /** 允许自动重试的上游状态码（504/524 始终不重试） */
  channel_auto_retry_status_codes: string;
  /** 触发自动禁用的错误关键词，换行分隔，不区分大小写 */
  channel_auto_disable_keywords: string;
};

/** 站点品牌字段全量更新请求体：除 logo_url 外均不可为 null */
export type SystemSettingsUpdatePayload = Omit<
  SystemSettings,
  "logo_url" | "email_verification_enabled"
> & {
  /** 传 null 清空徽标；填写时必须是 HTTP/HTTPS URL */
  logo_url: string | null;
};

/** 邮箱验证与 SMTP 更新请求体（差异提交，仅传变更字段） */
export type EmailVerificationUpdatePayload = {
  /** 开启时要求 smtp_host、smtp_port、smtp_from_email 均有效 */
  email_verification_enabled: boolean;
  /** 最长 255 */
  smtp_host: string;
  /** 1–65535 */
  smtp_port: number;
  smtp_security: SmtpSecurity;
  /** 最长 320 */
  smtp_username: string;
  /** 只写字段：不传保留原密码；传 "" 清空；传非空则加密替换 */
  smtp_password: string;
  /** 最长 320 */
  smtp_from_email: string;
  /** 最长 255 */
  smtp_from_name: string;
};

/** 余额预警更新请求体（差异提交，仅传变更字段）；阈值由用户自行设置，管理员只维护总开关 */
export type BalanceAlertUpdatePayload = {
  /** 开启时要求 email_verification_enabled 保持开启且 SMTP 配置完整 */
  balance_alert_enabled: boolean;
};

/** 渠道探测与自动禁用更新请求体（差异提交，仅传变更字段） */
export type ChannelAutomationUpdatePayload = {
  channel_probe_enabled: boolean;
  /** 1–1440 */
  channel_probe_interval_minutes: number;
  /** 1–600 */
  channel_probe_timeout_seconds: number;
  channel_auto_disable_enabled: boolean;
  channel_auto_enable_enabled: boolean;
  /** 单码 401 或范围 400-499，逗号分隔，100–599；空串不匹配任何状态码 */
  channel_auto_disable_status_codes: string;
  /** 语法同上；504/524 始终不参与自动重试 */
  channel_auto_retry_status_codes: string;
  /** 换行分隔，匹配上游错误消息文本，不区分大小写 */
  channel_auto_disable_keywords: string;
};

/** 公开读取系统设置（无需登录） */
export function getPublicSystemSettings() {
  return get<SystemSettings>("/system-settings/detail");
}

/** 管理员读取系统设置 */
export function getAdminSystemSettings() {
  return get<AdminSystemSettings>("/admin/system-settings/detail");
}

/** 管理员更新系统设置（差异提交，仅传变更字段），返回后端规范化后的完整对象 */
export function updateAdminSystemSettings(
  payload: Partial<
    SystemSettingsUpdatePayload &
      EmailVerificationUpdatePayload &
      BalanceAlertUpdatePayload &
      ChannelAutomationUpdatePayload
  >
) {
  return post<AdminSystemSettings>("/admin/system-settings/update", payload);
}
