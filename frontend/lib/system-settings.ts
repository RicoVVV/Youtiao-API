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
  payload: Partial<SystemSettingsUpdatePayload & EmailVerificationUpdatePayload>
) {
  return post<AdminSystemSettings>("/admin/system-settings/update", payload);
}
