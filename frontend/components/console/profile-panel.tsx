"use client";

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Gauge, Wallet } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Loading } from "@/components/ui/loading";
import { get } from "@/lib/request";
import { cn } from "@/lib/utils";

type Profile = {
  id: string;
  username: string;
  is_active: boolean;
  is_admin: boolean;
  balance: string;
  usage: string;
  created_at: string;
};

export function ProfilePanel() {
  const { t, i18n } = useTranslation("console");
  const locale = i18n.language === "zh" ? "zh-CN" : "en-US";
  const [profile, setProfile] = useState<Profile | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    get<Profile>("/user/info")
      .then(setProfile)
      .catch((err) => setError(err instanceof Error ? err.message : t("profile.loadFailed")));
  }, [t]);

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

  const stats = [
    {
      icon: Wallet,
      label: t("profile.balance"),
      value: `$ ${profile.balance}`,
      hint: t("profile.balanceHint"),
      iconClass: "from-[#4c6fff] to-[#7c9aff]",
      cardClass: "from-[#4c6fff]/10",
      glowClass: "bg-[#4c6fff]/20",
    },
    {
      icon: Gauge,
      label: t("profile.totalUsage"),
      value: `$ ${profile.usage}`,
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
    </div>
  );
}
