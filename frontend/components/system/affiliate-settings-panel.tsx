"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Save } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Loading } from "@/components/ui/loading";
import { Switch } from "@/components/ui/switch";
import { toast } from "@/components/ui/toaster";
import { invalidatePublicSystemSettingsCache } from "@/lib/use-system-settings";
import {
  getAdminSystemSettings,
  updateAdminSystemSettings,
  type AffiliateUpdatePayload,
} from "@/lib/system-settings";

import { FieldLabel, SectionHeader } from "./payment-gateway/form-helpers";

/** 邀请返利设置表单默认值（数值以字符串编辑、提交时转数字） */
type AffiliateForm = {
  affiliate_enabled: boolean;
  affiliate_rebate_rate_percent: string;
  affiliate_rebate_freeze_hours: string;
  affiliate_rebate_duration_days: string;
  affiliate_rebate_per_invitee_cap: string;
  /** 被邀请人注册赠送额度（USD），0–1000000，0 表示不赠送 */
  affiliate_signup_bonus: string;
};

const DEFAULTS: AffiliateForm = {
  affiliate_enabled: false,
  affiliate_rebate_rate_percent: "20.00",
  affiliate_rebate_freeze_hours: "0",
  affiliate_rebate_duration_days: "0",
  affiliate_rebate_per_invitee_cap: "0",
  affiliate_signup_bonus: "0",
};

/** 金额/比例字段统一两位小数展示；非法输入原样返回交由校验提示 */
function to2dp(value: string | number): string {
  const n = Number(value);
  return Number.isFinite(n) ? n.toFixed(2) : String(value);
}

export function AffiliateSettingsPanel() {
  const { t } = useTranslation("console");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState<AffiliateForm>(DEFAULTS);
  /** 加载完成时的初始快照，用于差异提交 */
  const [initial, setInitial] = useState<AffiliateForm | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Partial<Record<string, string>>>({});

  const set = (key: keyof AffiliateForm) => (value: string | boolean) => {
    setForm((prev) => ({ ...prev, [key]: value }));
    setFieldErrors((prev) => {
      if (!prev[key]) return prev;
      const next = { ...prev };
      delete next[key];
      return next;
    });
  };

  /* ── 加载管理员系统设置中的返利配置 ── */
  const loadingRef = useRef(false);
  const load = useCallback(async () => {
    if (loadingRef.current) return;
    loadingRef.current = true;
    try {
      const data = await getAdminSystemSettings();
      // 金额/比例字段统一按两位小数展示，加载时规范化
      const snapshot: AffiliateForm = {
        affiliate_enabled: data.affiliate_enabled ?? false,
        affiliate_rebate_rate_percent: String(data.affiliate_rebate_rate_percent ?? "20.00"),
        affiliate_rebate_freeze_hours: String(data.affiliate_rebate_freeze_hours ?? 0),
        affiliate_rebate_duration_days: String(data.affiliate_rebate_duration_days ?? 0),
        affiliate_rebate_per_invitee_cap: to2dp(data.affiliate_rebate_per_invitee_cap ?? "0"),
        affiliate_signup_bonus: to2dp(data.affiliate_signup_bonus ?? "0"),
      };
      setForm(snapshot);
      setInitial(snapshot);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t("affiliateSettings.loadFailed"));
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
    const errors: Partial<Record<string, string>> = {};
    const rate = Number(form.affiliate_rebate_rate_percent);
    if (!Number.isFinite(rate) || rate < 0 || rate > 100) {
      errors.affiliate_rebate_rate_percent = t("affiliateSettings.rebateRateInvalid");
    }
    const freezeHours = Number(form.affiliate_rebate_freeze_hours);
    if (!Number.isInteger(freezeHours) || freezeHours < 0 || freezeHours > 720) {
      errors.affiliate_rebate_freeze_hours = t("affiliateSettings.freezeHoursInvalid");
    }
    const durationDays = Number(form.affiliate_rebate_duration_days);
    if (!Number.isInteger(durationDays) || durationDays < 0 || durationDays > 3650) {
      errors.affiliate_rebate_duration_days = t("affiliateSettings.durationDaysInvalid");
    }
    const cap = Number(form.affiliate_rebate_per_invitee_cap);
    if (!Number.isFinite(cap) || cap < 0) {
      errors.affiliate_rebate_per_invitee_cap = t("affiliateSettings.perInviteeCapInvalid");
    }
    const signupBonus = Number(form.affiliate_signup_bonus);
    if (!Number.isFinite(signupBonus) || signupBonus < 0 || signupBonus > 1000000) {
      errors.affiliate_signup_bonus = t("affiliateSettings.signupBonusInvalid");
    }
    if (Object.keys(errors).length > 0) {
      setFieldErrors(errors);
      toast.error(t("affiliateSettings.fixFormErrors"));
      return;
    }

    // 差异提交：数值类提交数字，比例/上限保留字符串以便后端统一金额格式
    const payload = {} as Partial<AffiliateUpdatePayload>;
    if (initial) {
      if (form.affiliate_enabled !== initial.affiliate_enabled) {
        payload.affiliate_enabled = form.affiliate_enabled;
      }
      if (form.affiliate_rebate_rate_percent !== initial.affiliate_rebate_rate_percent) {
        payload.affiliate_rebate_rate_percent = form.affiliate_rebate_rate_percent;
      }
      if (form.affiliate_rebate_freeze_hours !== initial.affiliate_rebate_freeze_hours) {
        payload.affiliate_rebate_freeze_hours = Number(form.affiliate_rebate_freeze_hours);
      }
      if (form.affiliate_rebate_duration_days !== initial.affiliate_rebate_duration_days) {
        payload.affiliate_rebate_duration_days = Number(form.affiliate_rebate_duration_days);
      }
      if (form.affiliate_rebate_per_invitee_cap !== initial.affiliate_rebate_per_invitee_cap) {
        payload.affiliate_rebate_per_invitee_cap = form.affiliate_rebate_per_invitee_cap;
      }
      if (form.affiliate_signup_bonus !== initial.affiliate_signup_bonus) {
        payload.affiliate_signup_bonus = form.affiliate_signup_bonus;
      }
    }
    if (Object.keys(payload).length === 0) {
      toast.info(t("affiliateSettings.noChanges"));
      return;
    }

    setSaving(true);
    try {
      const data = await updateAdminSystemSettings(payload);
      // 总开关属于公开设置：失效缓存以便注册页/邀请入口重新拉取
      invalidatePublicSystemSettingsCache();
      // 用响应回写快照，采用后端规范化后的值（金额两位小数）
      const snapshot: AffiliateForm = {
        affiliate_enabled: data.affiliate_enabled ?? false,
        affiliate_rebate_rate_percent: String(data.affiliate_rebate_rate_percent ?? "20.00"),
        affiliate_rebate_freeze_hours: String(data.affiliate_rebate_freeze_hours ?? 0),
        affiliate_rebate_duration_days: String(data.affiliate_rebate_duration_days ?? 0),
        affiliate_rebate_per_invitee_cap: to2dp(data.affiliate_rebate_per_invitee_cap ?? "0"),
        affiliate_signup_bonus: to2dp(data.affiliate_signup_bonus ?? "0"),
      };
      setForm(snapshot);
      setInitial(snapshot);
      toast.success(t("affiliateSettings.saveSuccess"));
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t("affiliateSettings.saveFailed"));
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Loading size="lg" text={t("affiliateSettings.loading")} />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">{t("affiliateSettings.title")}</h1>
        <Button onClick={save} disabled={saving}>
          <Save className="size-4" />
          {saving ? t("affiliateSettings.saving") : t("affiliateSettings.save")}
        </Button>
      </div>

      {/* 邀请返利规则 */}
      <section className="space-y-4">
        <SectionHeader
          title={t("affiliateSettings.sectionTitle")}
          description={t("affiliateSettings.sectionDesc")}
        />
        <div className="flex items-center justify-between rounded-lg border border-border px-4 py-3">
          <FieldLabel
            label={t("affiliateSettings.enabled")}
            hint={t("affiliateSettings.enabledHint")}
          />
          <Switch
            checked={form.affiliate_enabled}
            onCheckedChange={(checked) => set("affiliate_enabled")(checked)}
          />
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          <Field
            label={t("affiliateSettings.rebateRate")}
            hint={t("affiliateSettings.rebateRateHint")}
            error={fieldErrors.affiliate_rebate_rate_percent}
          >
            <Input
              type="number"
              min={0}
              max={100}
              step="0.01"
              value={form.affiliate_rebate_rate_percent}
              onChange={(e) => set("affiliate_rebate_rate_percent")(e.target.value)}
              aria-invalid={!!fieldErrors.affiliate_rebate_rate_percent}
            />
          </Field>
          <Field
            label={t("affiliateSettings.freezeHours")}
            hint={t("affiliateSettings.freezeHoursHint")}
            error={fieldErrors.affiliate_rebate_freeze_hours}
          >
            <Input
              type="number"
              min={0}
              max={720}
              step={1}
              value={form.affiliate_rebate_freeze_hours}
              onChange={(e) => set("affiliate_rebate_freeze_hours")(e.target.value)}
              aria-invalid={!!fieldErrors.affiliate_rebate_freeze_hours}
            />
          </Field>
          <Field
            label={t("affiliateSettings.durationDays")}
            hint={t("affiliateSettings.durationDaysHint")}
            error={fieldErrors.affiliate_rebate_duration_days}
          >
            <Input
              type="number"
              min={0}
              max={3650}
              step={1}
              value={form.affiliate_rebate_duration_days}
              onChange={(e) => set("affiliate_rebate_duration_days")(e.target.value)}
              aria-invalid={!!fieldErrors.affiliate_rebate_duration_days}
            />
          </Field>
          <Field
            label={t("affiliateSettings.perInviteeCap")}
            hint={t("affiliateSettings.perInviteeCapHint")}
            error={fieldErrors.affiliate_rebate_per_invitee_cap}
          >
            <Input
              type="number"
              min={0}
              step="0.01"
              value={form.affiliate_rebate_per_invitee_cap}
              onChange={(e) => set("affiliate_rebate_per_invitee_cap")(e.target.value)}
              aria-invalid={!!fieldErrors.affiliate_rebate_per_invitee_cap}
            />
          </Field>
          <Field
            label={t("affiliateSettings.signupBonus")}
            hint={t("affiliateSettings.signupBonusHint")}
            error={fieldErrors.affiliate_signup_bonus}
          >
            <Input
              type="number"
              min={0}
              max={1000000}
              step="0.01"
              value={form.affiliate_signup_bonus}
              onChange={(e) => set("affiliate_signup_bonus")(e.target.value)}
              aria-invalid={!!fieldErrors.affiliate_signup_bonus}
            />
          </Field>
        </div>
      </section>
    </div>
  );
}

/* ── 内部小组件（与 system-settings-panel 同款） ── */

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
