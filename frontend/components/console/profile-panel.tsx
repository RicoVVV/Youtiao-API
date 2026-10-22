"use client";

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { BellRing, Crown, Gauge, Save, Wallet } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Loading } from "@/components/ui/loading";
import { Switch } from "@/components/ui/switch";
import { toast } from "@/components/ui/toaster";
import { ApiError, get, post } from "@/lib/request";
import type { UserMembership } from "@/lib/membership";
import { cn } from "@/lib/utils";

type Profile = {
  id: string;
  username: string;
  is_active: boolean;
  is_admin: boolean;
  balance: string;
  usage: string;
  created_at: string;
  membership: UserMembership;
  /** 注册邮箱；邮箱注册或 Google 登录才有，否则为 null */
  email: string | null;
  /** 用户自设预警收件邮箱；null 表示使用注册邮箱 */
  balance_alert_email: string | null;
  /** 预警阈值（6 位小数字符串）；null 表示未开启余额预警 */
  balance_alert_threshold: string | null;
};

/** 余额预警更新响应：后端已规范化邮箱为小写 */
type BalanceAlertUpdateResponse = {
  balance_alert_threshold: string | null;
  balance_alert_email: string | null;
};

/** 阈值格式：大于 0、最多 6 位小数 */
const THRESHOLD_RE = /^\d+(\.\d{1,6})?$/;
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function ProfilePanel() {
  const { t, i18n } = useTranslation("console");
  const locale = i18n.language === "zh" ? "zh-CN" : "en-US";
  const [profile, setProfile] = useState<Profile | null>(null);
  const [error, setError] = useState("");
  /** 余额预警表单：开关只改本地状态，保存时才提交 */
  const [alertEnabled, setAlertEnabled] = useState(false);
  const [alertThreshold, setAlertThreshold] = useState("");
  const [alertEmail, setAlertEmail] = useState("");
  const [alertSaving, setAlertSaving] = useState(false);
  const [alertFieldErrors, setAlertFieldErrors] = useState<{
    threshold?: string;
    email?: string;
  }>({});

  useEffect(() => {
    get<Profile>("/user/info")
      .then((data) => {
        setProfile(data);
        // 阈值非空即视为已开启，并回填表单
        setAlertEnabled(data.balance_alert_threshold != null);
        setAlertThreshold(data.balance_alert_threshold ?? "");
        setAlertEmail(data.balance_alert_email ?? "");
      })
      .catch((err) => setError(err instanceof Error ? err.message : t("profile.loadFailed")));
  }, [t]);

  /** 保存余额预警：关闭时提交 null 阈值；422 时按字段定位错误 */
  const saveBalanceAlert = async () => {
    const trimmedThreshold = alertThreshold.trim();
    const trimmedEmail = alertEmail.trim();
    const fieldErrors: { threshold?: string; email?: string } = {};
    if (alertEnabled) {
      if (!THRESHOLD_RE.test(trimmedThreshold) || Number(trimmedThreshold) <= 0) {
        fieldErrors.threshold = t("profile.balanceAlert.thresholdInvalid");
      }
      if (trimmedEmail && !EMAIL_RE.test(trimmedEmail)) {
        fieldErrors.email = t("profile.balanceAlert.emailInvalid");
      }
      if (!profile?.email && !trimmedEmail) {
        fieldErrors.email = t("profile.balanceAlert.emailRequired");
      }
    }
    setAlertFieldErrors(fieldErrors);
    if (Object.keys(fieldErrors).length > 0) return;

    setAlertSaving(true);
    try {
      const res = await post<BalanceAlertUpdateResponse>(
        "/user/balance-alert/update",
        {
          threshold: alertEnabled ? trimmedThreshold : null,
          email: alertEnabled ? trimmedEmail || null : null,
        }
      );
      // 后端已规范化邮箱，用响应回写表单与资料
      setAlertThreshold(res.balance_alert_threshold ?? "");
      setAlertEmail(res.balance_alert_email ?? "");
      setProfile((prev) =>
        prev
          ? {
              ...prev,
              balance_alert_threshold: res.balance_alert_threshold,
              balance_alert_email: res.balance_alert_email,
            }
          : prev
      );
      toast.success(t("profile.balanceAlert.saveSuccess"));
    } catch (err) {
      if (err instanceof ApiError && err.status === 422) {
        const detail = (err.data as { data?: unknown } | null)?.data;
        const nextErrors: { threshold?: string; email?: string } = {};
        if (Array.isArray(detail)) {
          for (const entry of detail) {
            const loc = (entry as { loc?: unknown[] })?.loc;
            const field = Array.isArray(loc) ? loc[loc.length - 1] : undefined;
            const message = (entry as { msg?: string })?.msg;
            if (field === "threshold") {
              nextErrors.threshold =
                message ?? t("profile.balanceAlert.thresholdInvalid");
            }
            if (field === "email") {
              nextErrors.email = message ?? t("profile.balanceAlert.emailInvalid");
            }
          }
        }
        setAlertFieldErrors(nextErrors);
      }
      toast.error(
        err instanceof Error ? err.message : t("profile.balanceAlert.saveFailed")
      );
    } finally {
      setAlertSaving(false);
    }
  };

  if (error) {
    return (
      <Card className="w-full">
        <CardContent className="py-6">
          <p className="text-base font-semibold">{t("profile.loadFailed")}</p>
          <p className="mt-1 text-sm text-muted-foreground">{error}</p>
        </CardContent>
      </Card>
    );
  }

  if (!profile) {
    return (
      <div className="flex items-center justify-center py-20 text-muted-foreground">
        <Loading size="lg" />
      </div>
    );
  }

  const metaItems = [
    { label: t("profile.userId"), value: profile.id, mono: true },
    {
      label: t("profile.accountStatus"),
      value: profile.is_active ? t("profile.statusNormal") : t("profile.statusDisabled"),
    },
    {
      label: t("profile.registeredAt"),
      value: new Date(profile.created_at).toLocaleString(locale, {
        hour12: false,
      }),
    },
  ];

  const membership = profile.membership;
  const membershipActive = membership?.is_active && membership.level;

  const stats = [
    {
      icon: Wallet,
      label: t("profile.balance"),
      value: `¥ ${profile.balance}`,
      hint: t("profile.balanceHint"),
      iconClass: "from-[#4c6fff] to-[#7c9aff]",
      cardClass: "from-[#4c6fff]/10",
      glowClass: "bg-[#4c6fff]/20",
    },
    {
      icon: Gauge,
      label: t("profile.totalUsage"),
      value: `¥ ${profile.usage}`,
      hint: t("profile.totalUsageHint"),
      iconClass: "from-[#129dc2] to-[#5cc8e0]",
      cardClass: "from-[#129dc2]/10",
      glowClass: "bg-[#129dc2]/20",
    },
  ];

  return (
    <div className="w-full space-y-6">
      {/* 用户信息：头像 + 基础资料整行展示 */}
      <Card className="w-full">
        <CardContent className="flex flex-col gap-6 sm:flex-row sm:items-center">
          <div className="flex min-w-0 items-center gap-4">
            <span className="flex size-16 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-[#4c6fff] to-[#7c9aff] text-2xl font-semibold text-white shadow-md">
              {profile.username.charAt(0).toUpperCase()}
            </span>
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <p className="truncate text-xl font-semibold">
                  {profile.username}
                </p>
                <Badge variant={profile.is_active ? "default" : "destructive"}>
                  {profile.is_active ? t("profile.statusNormal") : t("profile.statusDisabled")}
                </Badge>
                {profile.is_admin && <Badge variant="secondary">{t("profile.adminBadge")}</Badge>}
                {membershipActive && (
                  <Badge
                    variant="secondary"
                    className="border-amber-500/40 bg-amber-500/10 text-amber-600 dark:text-amber-400"
                  >
                    <Crown className="mr-1 size-3" />
                    {membership.level!.name}
                  </Badge>
                )}
              </div>
              <p className="mt-1 text-sm text-muted-foreground">
                {t("profile.currentAccount")}
              </p>
            </div>
          </div>

          {/* 分隔线：移动端横向，桌面端竖向 */}
          <div aria-hidden className="h-px w-full bg-border sm:hidden" />
          <div aria-hidden className="hidden h-14 w-px bg-border sm:block" />

          <div className="grid min-w-0 flex-1 grid-cols-1 gap-x-8 gap-y-4 sm:grid-cols-3">
            {metaItems.map((item) => (
              <div key={item.label} className="min-w-0">
                <p className="text-xs text-muted-foreground">{item.label}</p>
                <p
                  className={cn(
                    "mt-1 truncate text-sm font-medium",
                    item.mono && "font-mono text-xs"
                  )}
                >
                  {item.value}
                </p>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* 会员状态 */}
      {membership && (membership.level || membership.is_active) && (
        <Card className="relative w-full overflow-hidden bg-gradient-to-br from-amber-500/10 to-transparent">
          <div
            aria-hidden
            className="absolute -right-8 -top-8 size-28 rounded-full bg-amber-500/15 blur-2xl"
          />
          <CardContent className="relative flex flex-col gap-4 sm:flex-row sm:items-center">
            <span className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-[#f59e0b] to-[#ec4899] text-white shadow-md">
              <Crown className="size-5" />
            </span>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <p className="text-base font-semibold">
                  {membership.level?.name ?? t("profile.membershipNone")}
                </p>
                <Badge variant={membership.is_active ? "default" : "outline"}>
                  {membership.is_active
                    ? t("profile.membershipActive")
                    : t("profile.membershipExpired")}
                </Badge>
              </div>
              <div className="mt-1.5 flex flex-wrap gap-x-6 gap-y-1 text-sm text-muted-foreground">
                {membership.expires_at && (
                  <span>
                    {t("profile.membershipExpires", {
                      date: new Date(membership.expires_at).toLocaleString(locale, {
                        year: "numeric",
                        month: "2-digit",
                        day: "2-digit",
                        hour12: false,
                      }),
                    })}
                  </span>
                )}
                {membership.is_active && membership.groups.length > 0 && (
                  <span>
                    {t("profile.membershipGroups", {
                      names: membership.groups.map((g) => g.name).join("、"),
                    })}
                  </span>
                )}
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* 用量统计：与钱包样式保持一致 */}
      <div className="grid gap-4 sm:grid-cols-2">
        {stats.map((stat) => (
          <Card
            key={stat.label}
            className={cn(
              "relative overflow-hidden bg-gradient-to-br to-transparent transition-all duration-200 hover:-translate-y-0.5 hover:shadow-lg",
              stat.cardClass
            )}
          >
            {/* 角落装饰光斑 */}
            <div
              aria-hidden
              className={cn(
                "absolute -right-8 -top-8 size-28 rounded-full blur-2xl",
                stat.glowClass
              )}
            />
            <CardContent className="relative flex items-center gap-4">
              <span
                className={cn(
                  "flex size-11 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br text-white shadow-md",
                  stat.iconClass
                )}
              >
                <stat.icon className="size-5" />
              </span>
              <div className="min-w-0">
                <p className="text-sm text-muted-foreground">{stat.label}</p>
                <p className="mt-0.5 truncate text-2xl font-semibold tracking-tight">
                  {stat.value}
                </p>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  {stat.hint}
                </p>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* 余额预警：开关只改本地状态，点保存才提交 */}
      <Card className="w-full">
        <CardContent className="space-y-4">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="flex min-w-0 items-start gap-3">
              <span className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-[#f59e0b] to-[#ef4444] text-white shadow-md">
                <BellRing className="size-5" />
              </span>
              <div className="min-w-0">
                <p className="text-base font-semibold">
                  {t("profile.balanceAlert.title")}
                </p>
                <p className="mt-0.5 text-sm text-muted-foreground">
                  {t("profile.balanceAlert.description")}
                </p>
              </div>
            </div>
            <Switch
              checked={alertEnabled}
              onCheckedChange={(v) => {
                setAlertEnabled(v);
                setAlertFieldErrors({});
              }}
              checkedLabel={t("profile.balanceAlert.switchOn")}
              uncheckedLabel={t("profile.balanceAlert.switchOff")}
            />
          </div>

          {alertEnabled && (
            <>
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-1.5">
                  <label
                    htmlFor="balance-alert-threshold"
                    className="text-sm font-medium"
                  >
                    {t("profile.balanceAlert.threshold")}
                  </label>
                  <Input
                    id="balance-alert-threshold"
                    value={alertThreshold}
                    onChange={(e) => {
                      setAlertThreshold(e.target.value);
                      setAlertFieldErrors((prev) => ({
                        ...prev,
                        threshold: undefined,
                      }));
                    }}
                    placeholder="5.000000"
                    inputMode="decimal"
                    maxLength={20}
                    aria-invalid={!!alertFieldErrors.threshold}
                  />
                  <p
                    className={cn(
                      "text-xs",
                      alertFieldErrors.threshold
                        ? "text-destructive"
                        : "text-muted-foreground"
                    )}
                  >
                    {alertFieldErrors.threshold ??
                      t("profile.balanceAlert.thresholdHint")}
                  </p>
                </div>
                <div className="space-y-1.5">
                  <label
                    htmlFor="balance-alert-email"
                    className="text-sm font-medium"
                  >
                    {t("profile.balanceAlert.email")}
                  </label>
                  <Input
                    id="balance-alert-email"
                    value={alertEmail}
                    onChange={(e) => {
                      setAlertEmail(e.target.value);
                      setAlertFieldErrors((prev) => ({
                        ...prev,
                        email: undefined,
                      }));
                    }}
                    placeholder={
                      profile.email
                        ? t("profile.balanceAlert.emailPlaceholder", {
                            email: profile.email,
                          })
                        : t("profile.balanceAlert.emailPlaceholderRequired")
                    }
                    inputMode="email"
                    maxLength={320}
                    aria-invalid={!!alertFieldErrors.email}
                  />
                  <p
                    className={cn(
                      "text-xs",
                      alertFieldErrors.email
                        ? "text-destructive"
                        : "text-muted-foreground"
                    )}
                  >
                    {alertFieldErrors.email ??
                      (profile.email
                        ? t("profile.balanceAlert.emailHint")
                        : t("profile.balanceAlert.emailHintRequired"))}
                  </p>
                </div>
              </div>
              <div className="flex justify-end">
                <Button
                  type="button"
                  onClick={() => void saveBalanceAlert()}
                  disabled={alertSaving}
                >
                  {alertSaving ? (
                    <Loading size="sm" />
                  ) : (
                    <Save className="size-4" />
                  )}
                  {alertSaving
                    ? t("profile.balanceAlert.saving")
                    : t("profile.balanceAlert.save")}
                </Button>
              </div>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
