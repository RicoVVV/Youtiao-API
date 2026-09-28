"use client";

import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Gauge, Gift, Loader2, Wallet } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { toast } from "@/components/ui/toaster";
import { get, post } from "@/lib/request";
import { cn } from "@/lib/utils";

type BillingAccount = {
  id: string;
  /** 可用余额，元，字符串保留两位小数 */
  balance: string;
  /** 累计实际用量，元 */
  usage: string;
};

/** 金额保留两位小数 */
const fmt = (v: string) => Number(v).toFixed(2);

/** 核销兑换码响应 */
type RedeemResult = {
  redemption_code_id: string;
  /** 入账金额，元 */
  amount: string;
  /** 入账后的当前余额，元 */
  balance: string;
};

export function BillingOverview() {
  const { t } = useTranslation("console");
  const [account, setAccount] = useState<BillingAccount | null>(null);
  const [error, setError] = useState(false);
  const [code, setCode] = useState("");
  const [redeeming, setRedeeming] = useState(false);

  const load = useCallback(() => {
    get<BillingAccount>("/wallet/detail")
      .then(setAccount)
      .catch(() => setError(true));
  }, []);

  /** 核销兑换码：成功后刷新余额并提示入账金额 */
  const handleRedeem = async () => {
    const value = code.trim();
    if (!value || redeeming) return;
    setRedeeming(true);
    try {
      const res = await post<RedeemResult>("/billing/redemptions/redeem", {
        code: value,
      });
      setAccount((prev) => (prev ? { ...prev, balance: res.balance } : prev));
      setCode("");
      toast.success(t("billing.redeemSuccess", { amount: res.amount }));
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t("billing.redeemFailed"));
    } finally {
      setRedeeming(false);
    }
  };
  useEffect(() => {
    load();
    window.addEventListener("wallet:refresh", load);
    return () => window.removeEventListener("wallet:refresh", load);
  }, [load]);

  const stats = [
    {
      icon: Wallet,
      label: t("billing.balance"),
      value: account ? `$ ${fmt(account.balance)}` : "—",
      hint: t("billing.balanceHint"),
      iconClass: "from-[#4c6fff] to-[#7c9aff]",
      cardClass: "from-[#4c6fff]/10",
      glowClass: "bg-[#4c6fff]/20",
    },
    {
      icon: Gauge,
      label: t("billing.totalUsage"),
      value: account ? `$ ${fmt(account.usage)}` : "—",
      hint: t("billing.totalUsageHint"),
      iconClass: "from-[#129dc2] to-[#5cc8e0]",
      cardClass: "from-[#129dc2]/10",
      glowClass: "bg-[#129dc2]/20",
    },
  ];

  return (
    <div className="space-y-4">
      <div className="grid gap-4 lg:grid-cols-3">
        {stats.map((stat) => (
          <Card
            key={stat.label}
            className={cn(
              "relative overflow-hidden bg-gradient-to-br to-transparent transition-all duration-200 hover:-translate-y-0.5 hover:shadow-lg",
              stat.cardClass,
              error && "opacity-60"
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
                {account ? (
                  <p className="mt-0.5 text-2xl font-semibold tracking-tight">
                    {stat.value}
                  </p>
                ) : (
                  <div className="mt-1.5 h-7 w-20 animate-pulse rounded-md bg-muted" />
                )}
                <p className="mt-0.5 text-xs text-muted-foreground">{stat.hint}</p>
              </div>
            </CardContent>
          </Card>
        ))}

        <Card className="relative overflow-hidden bg-gradient-to-br from-amber-500/10 to-transparent transition-all duration-200 hover:-translate-y-0.5 hover:shadow-lg">
          <div
            aria-hidden
            className="absolute -right-8 -top-8 size-28 rounded-full bg-amber-500/15 blur-2xl"
          />
          <CardContent className="relative flex h-full flex-col justify-center gap-3">
            <p className="flex items-center gap-1.5 text-sm text-muted-foreground">
              <Gift className="size-4 text-amber-500" />
              {t("billing.haveCode")}
            </p>
            <div className="flex gap-2">
              <Input
                value={code}
                onChange={(e) => setCode(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleRedeem()}
                placeholder={t("billing.codePlaceholder")}
                disabled={redeeming}
                className="h-10 min-w-0 flex-1"
                maxLength={256}
              />
              <Button
                onClick={handleRedeem}
                disabled={!code.trim() || redeeming}
                className="h-10 shrink-0 px-4"
              >
                {redeeming && <Loader2 className="size-4 animate-spin" />}
                {t("billing.redeem")}
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
