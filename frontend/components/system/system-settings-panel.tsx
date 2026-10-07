"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Save } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Loading } from "@/components/ui/loading";
import { toast } from "@/components/ui/toaster";
import { cn } from "@/lib/utils";
import { ApiError } from "@/lib/request";
import { invalidatePublicSystemSettingsCache } from "@/lib/use-system-settings";
import {
  getAdminSystemSettings,
  updateAdminSystemSettings,
  type SystemSettingsUpdatePayload,
} from "@/lib/system-settings";

import { FieldLabel, SectionHeader } from "./payment-gateway/form-helpers";

/** 字段键名，与后端契约一致 */
type FieldKey = keyof SystemSettingsUpdatePayload;

const EMPTY_FORM: Record<FieldKey, string> = {
  system_name: "",
  server_url: "",
  logo_url: "",
  footer_text: "",
  about_content: "",
  homepage_content: "",
  terms_of_service: "",
  privacy_policy: "",
};

/** 简易 HTTP/HTTPS URL 校验（保存前的前端基础校验） */
function isHttpUrl(value: string): boolean {
  try {
    const url = new URL(value);
    return url.protocol === "http:" || url.protocol === "https:";
  } catch {
    return false;
  }
}

type Translate = (key: string, options?: Record<string, unknown>) => string;

/** 从 422 响应体中提取字段错误：data[].loc 形如 ["body", "字段名"] */
function map422FieldErrors(
  err: ApiError,
  t: Translate
): Partial<Record<FieldKey, string>> {
  const errors: Partial<Record<FieldKey, string>> = {};
  if (!err.data || typeof err.data !== "object") return errors;
  const list = (err.data as Record<string, unknown>).data;
  if (!Array.isArray(list)) return errors;
  for (const item of list) {
    if (!item || typeof item !== "object") continue;
    const loc = (item as Record<string, unknown>).loc;
    if (!Array.isArray(loc)) continue;
    const field = loc[loc.length - 1];
    if (typeof field === "string" && field in EMPTY_FORM) {
      // 不依赖后端英文 msg，给统一提示
      errors[field as FieldKey] = t("systemSettings.fieldInvalid");
    }
  }
  return errors;
}
export function SystemSettingsPanel() {
  const { t } = useTranslation("console");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState<Record<FieldKey, string>>(EMPTY_FORM);
  /** 加载完成时的初始快照，用于差异提交 */
  const [initial, setInitial] = useState<Record<FieldKey, string> | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Partial<Record<FieldKey, string>>>({});

  const set = (key: FieldKey) => (value: string) => {
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
      const snapshot = {
        system_name: data.system_name ?? "",
        server_url: data.server_url ?? "",
        logo_url: data.logo_url ?? "",
        footer_text: data.footer_text ?? "",
        about_content: data.about_content ?? "",
        homepage_content: data.homepage_content ?? "",
        terms_of_service: data.terms_of_service ?? "",
        privacy_policy: data.privacy_policy ?? "",
      };
      setForm(snapshot);
      setInitial(snapshot);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t("systemSettings.loadFailed"));
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

  /* ── 保存：前端基础校验 + 全量提交 ── */
  const save = async () => {
    const errors: Partial<Record<FieldKey, string>> = {};
    if (form.system_name.length > 255) {
      errors.system_name = t("systemSettings.systemNameTooLong");
    }
    if (form.server_url.trim() && !isHttpUrl(form.server_url.trim())) {
      errors.server_url = t("systemSettings.serverUrlInvalid");
    }
    if (form.logo_url.trim() && !isHttpUrl(form.logo_url.trim())) {
      errors.logo_url = t("systemSettings.logoUrlInvalid");
    }
    if (form.footer_text.length > 2000) {
      errors.footer_text = t("systemSettings.footerTooLong");
    }
    if (Object.keys(errors).length > 0) {
      setFieldErrors(errors);
      toast.error(t("systemSettings.fixFormErrors"));
      return;
    }

    // 差异提交：只提交与初始快照不同的字段
    const payload = {} as Partial<SystemSettingsUpdatePayload>;
    if (initial) {
      (Object.keys(EMPTY_FORM) as FieldKey[]).forEach((key) => {
        if (form[key] === initial[key]) return;
        if (key === "logo_url") {
          payload.logo_url = form.logo_url.trim() ? form.logo_url.trim() : null;
        } else if (key === "server_url") {
          // 选填：清空时不提交该字段，避免后端 URL 校验报错（保持原值）
          if (form.server_url.trim()) payload.server_url = form.server_url.trim();
        } else if (key === "system_name") {
          // 选填：清空时不提交该字段（保持原值）
          if (form.system_name.trim()) payload.system_name = form.system_name;
        } else {
          (payload as Record<string, string>)[key] = form[key];
        }
      });
    }
    if (Object.keys(payload).length === 0) {
      toast.info(t("systemSettings.noChanges"));
      return;
    }

    setSaving(true);
    try {
      const data = await updateAdminSystemSettings(payload);
      // 公开设置已变更，失效缓存以便站点头部/页脚重新拉取
      invalidatePublicSystemSettingsCache();
      // 用响应回写本地表单与快照，采用后端规范化后的 URL
      const snapshot = {
        system_name: data.system_name ?? "",
        server_url: data.server_url ?? "",
        logo_url: data.logo_url ?? "",
        footer_text: data.footer_text ?? "",
        about_content: data.about_content ?? "",
        homepage_content: data.homepage_content ?? "",
        terms_of_service: data.terms_of_service ?? "",
        privacy_policy: data.privacy_policy ?? "",
      };
      setForm(snapshot);
      setInitial(snapshot);
      toast.success(t("systemSettings.saveSuccess"));
    } catch (e) {
      // 422：按 data[].loc 映射到表单字段；401/403 已由请求封装统一处理
      if (e instanceof ApiError && e.status === 422) {
        const mapped = map422FieldErrors(e, t);
        if (Object.keys(mapped).length > 0) {
          setFieldErrors(mapped);
        }
      }
      toast.error(e instanceof Error ? e.message : t("systemSettings.saveFailed"));
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Loading size="lg" text={t("systemSettings.loading")} />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">{t("systemSettings.title")}</h1>
        <Button onClick={save} disabled={saving}>
          <Save className="size-4" />
          {saving ? t("systemSettings.saving") : t("systemSettings.save")}
        </Button>
      </div>

      {/* 站点信息 */}
      <section className="space-y-4">
        <SectionHeader
          title={t("systemSettings.siteSectionTitle")}
          description={t("systemSettings.siteSectionDesc")}
        />
        <div className="grid gap-4 md:grid-cols-2">
          <Field
            label={t("systemSettings.systemName")}
            hint={t("systemSettings.systemNameHint")}
            error={fieldErrors.system_name}
          >
            <Input
              value={form.system_name}
              onChange={(e) => set("system_name")(e.target.value)}
              placeholder="Velo"
              maxLength={255}
              aria-invalid={!!fieldErrors.system_name}
            />
          </Field>
          <Field
            label={t("systemSettings.serverUrl")}
            hint={t("systemSettings.serverUrlHint")}
            error={fieldErrors.server_url}
          >
            <Input
              value={form.server_url}
              onChange={(e) => set("server_url")(e.target.value)}
              placeholder="https://api.example.com"
              aria-invalid={!!fieldErrors.server_url}
            />
          </Field>
          <Field
            label={t("systemSettings.logoUrl")}
            hint={t("systemSettings.logoUrlHint")}
            error={fieldErrors.logo_url}
            className="md:col-span-2"
          >
            <Input
              value={form.logo_url}
              onChange={(e) => set("logo_url")(e.target.value)}
              placeholder="https://cdn.example.com/logo.svg"
              aria-invalid={!!fieldErrors.logo_url}
            />
          </Field>
        </div>
      </section>

      {/* 页脚 */}
      <section className="space-y-4">
        <SectionHeader title={t("systemSettings.footerSectionTitle")} description={t("systemSettings.footerSectionDesc")} />
        <Field
          label={t("systemSettings.footerText")}
          hint={t("systemSettings.footerTextHint")}
          error={fieldErrors.footer_text}
        >
          <Textarea
            value={form.footer_text}
            onChange={(e) => set("footer_text")(e.target.value)}
            placeholder={
              '<p>© 2026 Example。保留所有权利。<a href="https://beian.miit.gov.cn/" target="_blank" rel="noopener noreferrer">ICP备案号</a></p>'
            }
            rows={4}
            maxLength={2000}
            aria-invalid={!!fieldErrors.footer_text}
          />
        </Field>
      </section>

      {/* 页面内容 */}
      <section className="space-y-4">
        <SectionHeader
          title={t("systemSettings.contentSectionTitle")}
          description={t("systemSettings.contentSectionDesc")}
        />
        <div className="grid gap-4">
          <Field
            label={t("systemSettings.aboutContent")}
            hint={t("systemSettings.aboutContentHint")}
          >
            <Textarea
              value={form.about_content}
              onChange={(e) => set("about_content")(e.target.value)}
              placeholder={t("systemSettings.aboutContentPlaceholder")}
              rows={4}
            />
          </Field>
          <Field label={t("systemSettings.homepageContent")} hint={t("systemSettings.homepageContentHint")}>
            <Textarea
              value={form.homepage_content}
              onChange={(e) => set("homepage_content")(e.target.value)}
              placeholder={t("systemSettings.homepageContentPlaceholder")}
              rows={4}
            />
          </Field>
          <Field
            label={t("systemSettings.termsOfService")}
            hint={t("systemSettings.termsOfServiceHint")}
          >
            <Textarea
              value={form.terms_of_service}
              onChange={(e) => set("terms_of_service")(e.target.value)}
              placeholder={t("systemSettings.termsOfServicePlaceholder")}
              rows={6}
            />
          </Field>
          <Field
            label={t("systemSettings.privacyPolicy")}
            hint={t("systemSettings.privacyPolicyHint")}
          >
            <Textarea
              value={form.privacy_policy}
              onChange={(e) => set("privacy_policy")(e.target.value)}
              placeholder={t("systemSettings.privacyPolicyPlaceholder")}
              rows={6}
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

function Textarea({
  className,
  ...props
}: React.ComponentProps<"textarea">) {
  return (
    <textarea
      className={cn(
        "placeholder:text-muted-foreground selection:bg-primary selection:text-primary-foreground dark:bg-input/30 border-input w-full min-w-0 rounded-md border bg-transparent px-3 py-2 text-base shadow-xs transition-[color,box-shadow] outline-none disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50 md:text-sm",
        "focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px]",
        "aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40 aria-invalid:border-destructive",
        className
      )}
      {...props}
    />
  );
}
