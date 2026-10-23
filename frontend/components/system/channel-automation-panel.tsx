"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Save } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Loading } from "@/components/ui/loading";
import { Switch } from "@/components/ui/switch";
import { toast } from "@/components/ui/toaster";
import { cn } from "@/lib/utils";
import {
  getAdminSystemSettings,
  updateAdminSystemSettings,
  type AdminSystemSettings,
  type ChannelAutomationUpdatePayload,
} from "@/lib/system-settings";

import { FieldLabel, SectionHeader } from "./payment-gateway/form-helpers";

/** 渠道探测与自动禁用表单状态（数值字段以字符串编辑，提交时转数字） */
type ChannelAutomationForm = {
  channel_probe_enabled: boolean;
  channel_probe_interval_minutes: string;
  channel_probe_timeout_seconds: string;
  channel_auto_disable_enabled: boolean;
  channel_auto_enable_enabled: boolean;
  channel_auto_disable_status_codes: string;
  channel_auto_retry_status_codes: string;
  channel_auto_disable_keywords: string;
};

const EMPTY_FORM: ChannelAutomationForm = {
  channel_probe_enabled: true,
  channel_probe_interval_minutes: "1",
  channel_probe_timeout_seconds: "5",
  channel_auto_disable_enabled: true,
  channel_auto_enable_enabled: true,
  channel_auto_disable_status_codes: "",
  channel_auto_retry_status_codes: "",
  channel_auto_disable_keywords: "",
};

/** 管理员系统设置响应 → 表单快照（缺省字段回落到后端默认值） */
function snapshotFrom(data: AdminSystemSettings): ChannelAutomationForm {
  return {
    channel_probe_enabled: data.channel_probe_enabled ?? true,
    channel_probe_interval_minutes: String(data.channel_probe_interval_minutes ?? 1),
    channel_probe_timeout_seconds: String(data.channel_probe_timeout_seconds ?? 5),
    channel_auto_disable_enabled: data.channel_auto_disable_enabled ?? true,
    channel_auto_enable_enabled: data.channel_auto_enable_enabled ?? true,
    channel_auto_disable_status_codes: data.channel_auto_disable_status_codes ?? "",
    channel_auto_retry_status_codes: data.channel_auto_retry_status_codes ?? "",
    channel_auto_disable_keywords: data.channel_auto_disable_keywords ?? "",
  };
}

/** 状态码列表语法：单码 401 或范围 400-499，中/英文逗号分隔，范围 100–599，空串合法 */
function isValidStatusCodeList(value: string): boolean {
  const trimmed = value.trim();
  if (!trimmed) return true;
  const parts = trimmed.split(/[,,]/).map((p) => p.trim()).filter(Boolean);
  if (parts.length === 0) return true;
  const inRange = (n: number) => n >= 100 && n <= 599;
  for (const part of parts) {
    const m = part.match(/^(\d{3})(?:-(\d{3}))?$/);
    if (!m) return false;
    const start = Number(m[1]);
    const end = m[2] !== undefined ? Number(m[2]) : start;
    if (!inRange(start) || !inRange(end) || start > end) return false;
  }
  return true;
}

/** 整数范围校验：min–max 之间的整数 */
function isIntInRange(value: string, min: number, max: number): boolean {
  if (!/^\d+$/.test(value.trim())) return false;
  const n = Number(value);
  return Number.isInteger(n) && n >= min && n <= max;
}

/** 运维-渠道测试：渠道探测与自动禁用配置，复用管理员系统设置接口差异提交 */
export function ChannelAutomationPanel() {
  const { t } = useTranslation("console");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState<ChannelAutomationForm>(EMPTY_FORM);
  /** 加载完成时的初始快照，用于差异提交 */
  const [initial, setInitial] = useState<ChannelAutomationForm | null>(null);
  const [errors, setErrors] = useState<Partial<Record<keyof ChannelAutomationForm, string>>>({});

  const set = <K extends keyof ChannelAutomationForm>(key: K, value: ChannelAutomationForm[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }));
    setErrors((prev) => {
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
      const snapshot = snapshotFrom(data);
      setForm(snapshot);
      setInitial(snapshot);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t("channelAutomation.loadFailed"));
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

  /* ── 保存：前端校验 + 差异提交 ── */
  const save = async () => {
    const nextErrors: Partial<Record<keyof ChannelAutomationForm, string>> = {};
    if (!isIntInRange(form.channel_probe_interval_minutes, 1, 1440)) {
      nextErrors.channel_probe_interval_minutes = t("channelAutomation.probeIntervalInvalid");
    }
    if (!isIntInRange(form.channel_probe_timeout_seconds, 1, 600)) {
      nextErrors.channel_probe_timeout_seconds = t("channelAutomation.probeTimeoutInvalid");
    }
    if (!isValidStatusCodeList(form.channel_auto_disable_status_codes)) {
      nextErrors.channel_auto_disable_status_codes = t("channelAutomation.statusCodesInvalid");
    }
    if (!isValidStatusCodeList(form.channel_auto_retry_status_codes)) {
      nextErrors.channel_auto_retry_status_codes = t("channelAutomation.statusCodesInvalid");
    }
    if (Object.keys(nextErrors).length > 0) {
      setErrors(nextErrors);
      toast.error(t("channelAutomation.fixFormErrors"));
      return;
    }

    // 差异提交：只提交与初始快照不同的字段；数值字段转 number
    const payload: Partial<ChannelAutomationUpdatePayload> = {};
    if (initial) {
      const f = form;
      const i = initial;
      if (f.channel_probe_enabled !== i.channel_probe_enabled)
        payload.channel_probe_enabled = f.channel_probe_enabled;
      if (f.channel_probe_interval_minutes !== i.channel_probe_interval_minutes)
        payload.channel_probe_interval_minutes = Number(f.channel_probe_interval_minutes);
      if (f.channel_probe_timeout_seconds !== i.channel_probe_timeout_seconds)
        payload.channel_probe_timeout_seconds = Number(f.channel_probe_timeout_seconds);
      if (f.channel_auto_disable_enabled !== i.channel_auto_disable_enabled)
        payload.channel_auto_disable_enabled = f.channel_auto_disable_enabled;
      if (f.channel_auto_enable_enabled !== i.channel_auto_enable_enabled)
        payload.channel_auto_enable_enabled = f.channel_auto_enable_enabled;
      if (f.channel_auto_disable_status_codes !== i.channel_auto_disable_status_codes)
        payload.channel_auto_disable_status_codes = f.channel_auto_disable_status_codes;
      if (f.channel_auto_retry_status_codes !== i.channel_auto_retry_status_codes)
        payload.channel_auto_retry_status_codes = f.channel_auto_retry_status_codes;
      if (f.channel_auto_disable_keywords !== i.channel_auto_disable_keywords)
        payload.channel_auto_disable_keywords = f.channel_auto_disable_keywords;
    }
    if (Object.keys(payload).length === 0) {
      toast.info(t("channelAutomation.noChanges"));
      return;
    }

    setSaving(true);
    try {
      const data = await updateAdminSystemSettings(payload);
      // 用响应回写本地表单与快照，采用后端规范化后的值
      const snapshot = snapshotFrom(data);
      setForm(snapshot);
      setInitial(snapshot);
      toast.success(t("channelAutomation.saveSuccess"));
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t("channelAutomation.saveFailed"));
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Loading size="lg" text={t("channelAutomation.loading")} />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">{t("channelAutomation.title")}</h1>
        <Button onClick={save} disabled={saving}>
          <Save className="size-4" />
          {saving ? t("channelAutomation.saving") : t("channelAutomation.save")}
        </Button>
      </div>

      <section className="space-y-4">
        <SectionHeader
          title={t("channelAutomation.sectionTitle")}
          description={t("channelAutomation.sectionDesc")}
        />
        <div className="space-y-4">
          <SwitchRow
            label={t("channelAutomation.probeEnabled")}
            hint={t("channelAutomation.probeEnabledHint")}
            checked={form.channel_probe_enabled}
            onCheckedChange={(v) => set("channel_probe_enabled", v)}
          />
          <div className="grid gap-4 md:grid-cols-2">
            <Field
              label={t("channelAutomation.probeInterval")}
              hint={t("channelAutomation.probeIntervalHint")}
              error={errors.channel_probe_interval_minutes}
            >
              <Input
                inputMode="numeric"
                value={form.channel_probe_interval_minutes}
                onChange={(e) => set("channel_probe_interval_minutes", e.target.value)}
                aria-invalid={!!errors.channel_probe_interval_minutes}
              />
            </Field>
            <Field
              label={t("channelAutomation.probeTimeout")}
              hint={t("channelAutomation.probeTimeoutHint")}
              error={errors.channel_probe_timeout_seconds}
            >
              <Input
                inputMode="numeric"
                value={form.channel_probe_timeout_seconds}
                onChange={(e) => set("channel_probe_timeout_seconds", e.target.value)}
                aria-invalid={!!errors.channel_probe_timeout_seconds}
              />
            </Field>
          </div>
          <SwitchRow
            label={t("channelAutomation.autoDisableEnabled")}
            hint={t("channelAutomation.autoDisableEnabledHint")}
            checked={form.channel_auto_disable_enabled}
            onCheckedChange={(v) => set("channel_auto_disable_enabled", v)}
          />
          <SwitchRow
            label={t("channelAutomation.autoEnableEnabled")}
            hint={t("channelAutomation.autoEnableEnabledHint")}
            checked={form.channel_auto_enable_enabled}
            onCheckedChange={(v) => set("channel_auto_enable_enabled", v)}
          />
          <div className="grid gap-4 md:grid-cols-2">
            <Field
              label={t("channelAutomation.autoDisableStatusCodes")}
              hint={t("channelAutomation.autoDisableStatusCodesHint")}
              error={errors.channel_auto_disable_status_codes}
            >
              <Input
                value={form.channel_auto_disable_status_codes}
                onChange={(e) => set("channel_auto_disable_status_codes", e.target.value)}
                placeholder="401,429"
                autoComplete="off"
                aria-invalid={!!errors.channel_auto_disable_status_codes}
              />
            </Field>
            <Field
              label={t("channelAutomation.autoRetryStatusCodes")}
              hint={t("channelAutomation.autoRetryStatusCodesHint")}
              error={errors.channel_auto_retry_status_codes}
            >
              <Input
                value={form.channel_auto_retry_status_codes}
                onChange={(e) => set("channel_auto_retry_status_codes", e.target.value)}
                placeholder="401-407,409-499,500-503"
                autoComplete="off"
                aria-invalid={!!errors.channel_auto_retry_status_codes}
              />
            </Field>
          </div>
          <Field
            label={t("channelAutomation.autoDisableKeywords")}
            hint={t("channelAutomation.autoDisableKeywordsHint")}
          >
            <Textarea
              value={form.channel_auto_disable_keywords}
              onChange={(e) => set("channel_auto_disable_keywords", e.target.value)}
              rows={6}
            />
          </Field>
        </div>
      </section>
    </div>
  );
}

/* ── 内部小组件 ── */

/** 开关行：左侧标签与说明，右侧开关 */
function SwitchRow({
  label,
  hint,
  checked,
  onCheckedChange,
}: {
  label: string;
  hint?: string;
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
}) {
  return (
    <div className="flex items-center justify-between gap-4">
      <FieldLabel label={label} hint={hint} />
      <Switch checked={checked} onCheckedChange={onCheckedChange} />
    </div>
  );
}

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
