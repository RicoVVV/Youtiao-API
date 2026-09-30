"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Save } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Loading } from "@/components/ui/loading";
import { Select } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { toast } from "@/components/ui/toaster";
import { ApiError } from "@/lib/request";
import { invalidatePublicSystemSettingsCache } from "@/lib/use-system-settings";
import {
  getAdminSystemSettings,
  updateAdminSystemSettings,
  type EmailVerificationUpdatePayload,
  type SmtpSecurity,
} from "@/lib/system-settings";

import { FieldLabel, SectionHeader } from "./payment-gateway/form-helpers";

/**
 * 注册邮箱验证（SMTP）管理面板
 * 接口契约见 docs/register-email-verification-frontend-integration.md 第 5 节：
 * - GET  /admin/system-settings/detail  查询（smtp_password_configured 只表示已配置，不返回密码）
 * - POST /admin/system-settings/update  差异提交；smtp_password 不传保留、传 "" 清空、传非空加密替换
 */

/** SMTP 文本字段键名（smtp_security 走 Select、email_verification_enabled 走 Switch，单独管理） */
type SmtpFieldKey =
  | "smtp_host"
  | "smtp_port"
  | "smtp_username"
  | "smtp_password"
  | "smtp_from_email"
  | "smtp_from_name";

const EMPTY_FORM: Record<SmtpFieldKey, string> = {
  smtp_host: "",
  smtp_port: "587",
  smtp_username: "",
  smtp_password: "",
  smtp_from_email: "",
  smtp_from_name: "",
};

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

type Translate = (key: string, options?: Record<string, unknown>) => string;

/** 从 422 响应体中提取字段错误：data[].loc 形如 ["body", "字段名"] */
function map422FieldErrors(
  err: ApiError,
  t: Translate
): Partial<Record<SmtpFieldKey, string>> {
  const errors: Partial<Record<SmtpFieldKey, string>> = {};
  if (!err.data || typeof err.data !== "object") return errors;
  const list = (err.data as Record<string, unknown>).data;
  if (!Array.isArray(list)) return errors;
  for (const item of list) {
    if (!item || typeof item !== "object") continue;
    const loc = (item as Record<string, unknown>).loc;
    if (!Array.isArray(loc)) continue;
    const field = loc[loc.length - 1];
    if (typeof field === "string" && field in EMPTY_FORM) {
      errors[field as SmtpFieldKey] = t("authSettings.fieldInvalid");
    }
  }
  return errors;
}

export function AuthSettingsPanel() {
  const { t } = useTranslation("console");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [enabled, setEnabled] = useState(false);
  const [security, setSecurity] = useState<SmtpSecurity>("starttls");
  const [form, setForm] = useState<Record<SmtpFieldKey, string>>(EMPTY_FORM);
  const [passwordConfigured, setPasswordConfigured] = useState(false);
  /** 加载完成时的初始快照（不含密码，密码框恒为空、按需提交），用于差异提交 */
  const [initial, setInitial] = useState<{
    enabled: boolean;
    security: SmtpSecurity;
    form: Record<SmtpFieldKey, string>;
  } | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Partial<Record<SmtpFieldKey, string>>>({});

  const set = (key: SmtpFieldKey) => (value: string) => {
    setForm((prev) => ({ ...prev, [key]: value }));
    setFieldErrors((prev) => {
      if (!prev[key]) return prev;
      const next = { ...prev };
      delete next[key];
      return next;
    });
  };

  /* ── 加载管理员系统设置 ── */
  const loadingRef = useRef(false);
  const load = useCallback(async () => {
    if (loadingRef.current) return;
    loadingRef.current = true;
    try {
      const data = await getAdminSystemSettings();
      const snapshotForm: Record<SmtpFieldKey, string> = {
        smtp_host: data.smtp_host ?? "",
        smtp_port: String(data.smtp_port ?? 587),
        smtp_username: data.smtp_username ?? "",
        // 密码只写不回显
        smtp_password: "",
        smtp_from_email: data.smtp_from_email ?? "",
        smtp_from_name: data.smtp_from_name ?? "",
      };
      setEnabled(data.email_verification_enabled);
      setSecurity(data.smtp_security ?? "starttls");
      setForm(snapshotForm);
      setPasswordConfigured(data.smtp_password_configured);
      setInitial({
        enabled: data.email_verification_enabled,
        security: data.smtp_security ?? "starttls",
        form: snapshotForm,
      });
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t("authSettings.loadFailed"));
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

  /* ── 保存：前端基础校验 + 差异提交 ── */
  const save = async () => {
    if (!initial) return;
    const errors: Partial<Record<SmtpFieldKey, string>> = {};
    const port = Number(form.smtp_port);
    // 除发件人名称外均不允许为空
    if (!form.smtp_host.trim()) {
      errors.smtp_host = t("authSettings.required");
    }
    if (!form.smtp_port.trim()) {
      errors.smtp_port = t("authSettings.required");
    } else if (!Number.isInteger(port) || port < 1 || port > 65535) {
      errors.smtp_port = t("authSettings.smtpPortInvalid");
    }
    if (!form.smtp_username.trim()) {
      errors.smtp_username = t("authSettings.required");
    }
    // 密码只写：已配置时留空表示保持不变；未配置时必填
    if (!passwordConfigured && !form.smtp_password) {
      errors.smtp_password = t("authSettings.required");
    }
    if (!form.smtp_from_email.trim()) {
      errors.smtp_from_email = t("authSettings.required");
    } else if (!EMAIL_RE.test(form.smtp_from_email.trim())) {
      errors.smtp_from_email = t("authSettings.smtpFromEmailInvalid");
    }
    if (Object.keys(errors).length > 0) {
      setFieldErrors(errors);
      toast.error(t("authSettings.fixFormErrors"));
      return;
    }

    // 差异提交：只提交与初始快照不同的字段
    const payload: Partial<EmailVerificationUpdatePayload> = {};
    if (enabled !== initial.enabled) {
      payload.email_verification_enabled = enabled;
    }
    if (security !== initial.security) {
      payload.smtp_security = security;
    }
    (Object.keys(EMPTY_FORM) as SmtpFieldKey[]).forEach((key) => {
      if (key === "smtp_password") return;
      if (form[key] === initial.form[key]) return;
      if (key === "smtp_port") {
        payload.smtp_port = port;
      } else {
        (payload as Record<string, string>)[key] = form[key].trim();
      }
    });
    // 密码只写字段：留空表示保持不变，不提交
    if (form.smtp_password) {
      payload.smtp_password = form.smtp_password;
    }
    if (Object.keys(payload).length === 0) {
      toast.info(t("authSettings.noChanges"));
      return;
    }

    setSaving(true);
    try {
      const data = await updateAdminSystemSettings(payload);
      // 开关属公开设置：失效缓存以便注册页重新拉取
      invalidatePublicSystemSettingsCache();
      // 用响应回写本地表单与快照
      const snapshotForm: Record<SmtpFieldKey, string> = {
        smtp_host: data.smtp_host ?? "",
        smtp_port: String(data.smtp_port ?? 587),
        smtp_username: data.smtp_username ?? "",
        smtp_password: "",
        smtp_from_email: data.smtp_from_email ?? "",
        smtp_from_name: data.smtp_from_name ?? "",
      };
      setEnabled(data.email_verification_enabled);
      setSecurity(data.smtp_security ?? "starttls");
      setForm(snapshotForm);
      setPasswordConfigured(data.smtp_password_configured);
      setInitial({
        enabled: data.email_verification_enabled,
        security: data.smtp_security ?? "starttls",
        form: snapshotForm,
      });
      toast.success(t("authSettings.saveSuccess"));
    } catch (e) {
      // 422：按 data[].loc 映射到表单字段；401/403 已由请求封装统一处理
      if (e instanceof ApiError && e.status === 422) {
        const mapped = map422FieldErrors(e, t);
        if (Object.keys(mapped).length > 0) {
          setFieldErrors(mapped);
        }
      }
      toast.error(e instanceof Error ? e.message : t("authSettings.saveFailed"));
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Loading size="lg" text={t("authSettings.loading")} />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">{t("authSettings.title")}</h1>
        <Button onClick={save} disabled={saving}>
          <Save className="size-4" />
          {saving ? t("authSettings.saving") : t("authSettings.save")}
        </Button>
      </div>

      {/* 注册邮箱验证开关 */}
      <section className="space-y-4">
        <SectionHeader
          title={t("authSettings.enableSectionTitle")}
          description={t("authSettings.enableSectionDesc")}
        />
        <div className="flex items-center gap-3">
          <Switch
            checked={enabled}
            onCheckedChange={setEnabled}
            checkedLabel={t("authSettings.switchOn")}
            uncheckedLabel={t("authSettings.switchOff")}
          />
          <p className="text-sm text-muted-foreground">
            {t("authSettings.enableHint")}
          </p>
        </div>
      </section>

      {/* SMTP 配置 */}
      <section className="space-y-4">
        <SectionHeader
          title={t("authSettings.smtpSectionTitle")}
          description={t("authSettings.smtpSectionDesc")}
        />
        <div className="grid gap-4 md:grid-cols-2">
          <Field
            label={t("authSettings.smtpHost")}
            hint={t("authSettings.smtpHostHint")}
            error={fieldErrors.smtp_host}
          >
            <Input
              value={form.smtp_host}
              onChange={(e) => set("smtp_host")(e.target.value)}
              placeholder="smtp.example.com"
              maxLength={255}
              aria-invalid={!!fieldErrors.smtp_host}
            />
          </Field>
          <Field
            label={t("authSettings.smtpPort")}
            hint={t("authSettings.smtpPortHint")}
            error={fieldErrors.smtp_port}
          >
            <Input
              value={form.smtp_port}
              onChange={(e) => set("smtp_port")(e.target.value.replace(/\D/g, ""))}
              placeholder="587"
              inputMode="numeric"
              maxLength={5}
              aria-invalid={!!fieldErrors.smtp_port}
            />
          </Field>
          <Field label={t("authSettings.smtpSecurity")}>
            <Select
              value={security}
              onValueChange={(v) => setSecurity(v as SmtpSecurity)}
              options={[
                { value: "none", label: t("authSettings.securityNone") },
                { value: "starttls", label: t("authSettings.securityStarttls") },
                { value: "ssl", label: t("authSettings.securitySsl") },
              ]}
              aria-label={t("authSettings.smtpSecurity")}
            />
          </Field>
          <Field
            label={t("authSettings.smtpUsername")}
            hint={t("authSettings.smtpUsernameHint")}
            error={fieldErrors.smtp_username}
          >
            <Input
              value={form.smtp_username}
              onChange={(e) => set("smtp_username")(e.target.value)}
              placeholder="noreply@example.com"
              maxLength={320}
              autoComplete="off"
              aria-invalid={!!fieldErrors.smtp_username}
            />
          </Field>
          <Field
            label={t("authSettings.smtpPassword")}
            hint={
              passwordConfigured
                ? t("authSettings.smtpPasswordConfiguredHint")
                : t("authSettings.smtpPasswordEmptyHint")
            }
            error={fieldErrors.smtp_password}
          >
            <Input
              type="password"
              value={form.smtp_password}
              onChange={(e) => set("smtp_password")(e.target.value)}
              autoComplete="new-password"
              aria-invalid={!!fieldErrors.smtp_password}
            />
          </Field>
          <Field
            label={t("authSettings.smtpFromEmail")}
            hint={t("authSettings.smtpFromEmailHint")}
            error={fieldErrors.smtp_from_email}
          >
            <Input
              value={form.smtp_from_email}
              onChange={(e) => set("smtp_from_email")(e.target.value)}
              placeholder="noreply@example.com"
              maxLength={320}
              aria-invalid={!!fieldErrors.smtp_from_email}
            />
          </Field>
          <Field
            label={t("authSettings.smtpFromName")}
            hint={t("authSettings.smtpFromNameHint")}
            error={fieldErrors.smtp_from_name}
          >
            <Input
              value={form.smtp_from_name}
              onChange={(e) => set("smtp_from_name")(e.target.value)}
              maxLength={255}
              aria-invalid={!!fieldErrors.smtp_from_name}
            />
          </Field>
        </div>
      </section>
    </div>
  );
}

/* ── 内部小组件 ── */

function Field({
  label,
  hint,
  error,
  className,
  children,
}: {
  label: string;
  hint?: string;
  error?: string;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div className={className}>
      <FieldLabel label={label} hint={hint} />
      <div className="mt-1.5">{children}</div>
      {error && <p className="mt-1 text-xs text-destructive">{error}</p>}
    </div>
  );
}
