"use client";

import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Copy, Gift, HandCoins, Loader2, Percent, PowerOff } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Pagination } from "@/components/ui/pagination";
import { toast } from "@/components/ui/toaster";
import {
  getAffiliateDetail,
  getAffiliateInvitees,
  getAffiliateRecords,
  transferAffiliateQuota,
  type AffiliateDetail,
  type AffiliateInvitee,
  type AffiliateRecord,
} from "@/lib/affiliate";
import { useLocale } from "@/i18n/client";
import { cn } from "@/lib/utils";

const PAGE_SIZE = 20;

/** 金额展示：后端为 6 位小数字符串，前端保留两位 */
const fmt = (v: string) => Number(v).toFixed(2);

/** 复制文本：优先 Clipboard API，非安全上下文降级 execCommand */
async function copyText(value: string): Promise<boolean> {
  if (navigator.clipboard && window.isSecureContext) {
    try {
      await navigator.clipboard.writeText(value);
      return true;
    } catch {
      // 继续尝试降级方案
    }
  }
  try {
    const textarea = document.createElement("textarea");
    textarea.value = value;
    textarea.style.position = "fixed";
    textarea.style.opacity = "0";
    document.body.appendChild(textarea);
    textarea.focus();
    textarea.select();
    const ok = document.execCommand("copy");
    document.body.removeChild(textarea);
    return ok;
  } catch {
    return false;
  }
}

type Tab = "records" | "invitees";

export function AffiliateCenter() {
  const { t } = useTranslation("console");
  const locale = useLocale();

  const [detail, setDetail] = useState<AffiliateDetail | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [transferring, setTransferring] = useState(false);

  const [tab, setTab] = useState<Tab>("records");
  const [records, setRecords] = useState<AffiliateRecord[]>([]);
  const [recordsTotal, setRecordsTotal] = useState(0);
  const [recordsPage, setRecordsPage] = useState(1);
  const [recordsLoading, setRecordsLoading] = useState(false);
  const [invitees, setInvitees] = useState<AffiliateInvitee[]>([]);
  const [inviteesTotal, setInviteesTotal] = useState(0);
  const [inviteesPage, setInviteesPage] = useState(1);
  const [inviteesLoading, setInviteesLoading] = useState(false);

  const loadDetail = useCallback(() => {
    getAffiliateDetail()
      .then(setDetail)
      .catch(() => setLoadError(true));
  }, []);

  /** 拉取返利流水（loading 状态由调用方控制，避免在 effect 中同步 setState） */
  const fetchRecords = useCallback(
    (page: number) =>
      getAffiliateRecords(page, PAGE_SIZE)
        .then((res) => {
          setRecords(res.items);
          setRecordsTotal(res.total);
          setRecordsPage(res.page);
        })
        .catch(() => toast.error(t("affiliate.loadListFailed"))),
    [t]
  );

  /** 拉取被邀请人列表 */
  const fetchInvitees = useCallback(
    (page: number) =>
      getAffiliateInvitees(page, PAGE_SIZE)
        .then((res) => {
          setInvitees(res.items);
          setInviteesTotal(res.total);
          setInviteesPage(res.page);
        })
        .catch(() => toast.error(t("affiliate.loadListFailed"))),
    [t]
  );

  useEffect(() => {
    loadDetail();
    fetchRecords(1);
    fetchInvitees(1);
  }, [loadDetail, fetchRecords, fetchInvitees]);

  /** 分页切换：事件处理中先置 loading 再拉取 */
  const loadRecords = (page: number) => {
    setRecordsLoading(true);
    fetchRecords(page).finally(() => setRecordsLoading(false));
  };

  const loadInvitees = (page: number) => {
    setInviteesLoading(true);
    fetchInvitees(page).finally(() => setInviteesLoading(false));
  };

  const handleCopy = async (value: string) => {
    const ok = await copyText(value);
    if (ok) {
      toast.success(t("affiliate.copySuccess"));
    } else {
      toast.error(t("affiliate.copyFailed"));
    }
  };

  /** 邀请链接：后端未配置站点公开地址时返回相对路径，用当前源补齐 */
  const inviteUrl = detail?.invite_url
    ? detail.invite_url.startsWith("/")
      ? `${window.location.origin}${detail.invite_url}`
      : detail.invite_url
    : "";

  const handleTransfer = async () => {
    if (transferring) return;
    setTransferring(true);
    try {
      const res = await transferAffiliateQuota();
      toast.success(
        t("affiliate.transferSuccess", { amount: fmt(res.transferred_quota) })
      );
      loadDetail();
      // 钱包余额变化：通知钱包概览等监听组件刷新
      window.dispatchEvent(new Event("wallet:refresh"));
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t("affiliate.transferFailed"));
    } finally {
      setTransferring(false);
    }
  };

  const formatTime = (value: string) =>
    new Date(value).toLocaleString(locale, { hour12: false });

  // 功能关闭：总开关未开启
  if (detail && !detail.enabled) {
    return (
      <div className="flex min-h-[60vh] flex-col items-center justify-center gap-4 text-center">
        <PowerOff className="size-10 text-muted-foreground/60" />
        <div className="space-y-1.5">
          <p className="text-lg font-medium">{t("affiliate.disabled")}</p>
          <p className="text-sm text-muted-foreground">
            {t("affiliate.disabledDesc")}
          </p>
        </div>
      </div>
    );
  }

  const stats = [
    { label: t("affiliate.statInvitees"), value: detail?.aff_count },
    { label: t("affiliate.statTotal"), value: detail ? `$ ${fmt(detail.history_quota)}` : undefined },
    { label: t("affiliate.statFrozen"), value: detail ? `$ ${fmt(detail.frozen_quota)}` : undefined },
  ];

  const recordTotalPages = Math.max(1, Math.ceil(recordsTotal / PAGE_SIZE));
  const inviteeTotalPages = Math.max(1, Math.ceil(inviteesTotal / PAGE_SIZE));

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">
          {t("affiliate.title")}
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          {t("affiliate.subtitle")}
        </p>
      </div>

      {/* 专属邀请码 */}
      <Card>
        <CardContent className="flex flex-col items-center gap-4 py-10">
          <span className="flex size-12 items-center justify-center rounded-full bg-primary/10">
            <Gift className="size-6 text-primary" />
          </span>
          <div className="text-center">
            <p className="text-sm text-muted-foreground">
              {t("affiliate.inviteCodeLabel")}
            </p>
            {detail ? (
              <p className="mt-1 text-3xl font-semibold tracking-[0.2em]">
                {detail.aff_code}
              </p>
            ) : (
              <div className="mx-auto mt-2 h-8 w-40 animate-pulse rounded-md bg-muted" />
            )}
          </div>
          <div className="flex flex-wrap items-center justify-center gap-3">
            <Button
              variant="outline"
              disabled={!inviteUrl}
              onClick={() => handleCopy(inviteUrl)}
            >
              {t("affiliate.copyLink")}
            </Button>
            <Button
              disabled={!detail}
              onClick={() => detail && handleCopy(detail.aff_code)}
            >
              <Copy className="size-4" />
              {t("affiliate.copyCode")}
            </Button>
          </div>
          {/* 被邀请人注册赠送额度提示 */}
          {detail && Number(detail.signup_bonus) > 0 && (
            <p className="text-sm text-muted-foreground">
              {t("affiliate.signupBonus", { amount: fmt(detail.signup_bonus) })}
            </p>
          )}
        </CardContent>
      </Card>

      {/* 可用返利 / 返利比例 */}
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardContent className="flex items-center justify-between gap-4">
            <div className="min-w-0">
              <p className="flex items-center gap-1.5 text-sm text-muted-foreground">
                <HandCoins className="size-4 text-primary" />
                {t("affiliate.available")}
              </p>
              {detail ? (
                <p className="mt-1 text-2xl font-semibold tracking-tight">
                  $ {fmt(detail.available_quota)}
                </p>
              ) : (
                <div className="mt-2 h-7 w-24 animate-pulse rounded-md bg-muted" />
              )}
              <p className="mt-0.5 text-xs text-muted-foreground">
                {t("affiliate.availableHint")}
              </p>
            </div>
            <Button
              variant="secondary"
              disabled={!detail || Number(detail.available_quota) <= 0 || transferring}
              onClick={handleTransfer}
            >
              {transferring && <Loader2 className="size-4 animate-spin" />}
              {t("affiliate.transfer")}
            </Button>
          </CardContent>
        </Card>
        <Card>
          <CardContent>
            <p className="flex items-center gap-1.5 text-sm text-muted-foreground">
              <Percent className="size-4 text-primary" />
              {t("affiliate.rate")}
            </p>
            {detail ? (
              <p className="mt-1 text-2xl font-semibold tracking-tight">
                {fmt(detail.effective_rebate_rate_percent)}%
              </p>
            ) : (
              <div className="mt-2 h-7 w-16 animate-pulse rounded-md bg-muted" />
            )}
            <p className="mt-0.5 text-xs text-muted-foreground">
              {t("affiliate.rateHint")}
            </p>
          </CardContent>
        </Card>
      </div>

      {/* 邀请总览 */}
      <div>
        <p className="mb-3 text-base font-medium">{t("affiliate.overviewTitle")}</p>
        <div className="grid gap-4 sm:grid-cols-3">
          {stats.map((stat) => (
            <Card key={stat.label}>
              <CardContent>
                <p className="text-sm text-muted-foreground">{stat.label}</p>
                {stat.value !== undefined ? (
                  <p className="mt-1 text-2xl font-semibold tracking-tight">
                    {stat.value}
                  </p>
                ) : (
                  <div className="mt-2 h-7 w-16 animate-pulse rounded-md bg-muted" />
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      </div>

      {/* 返利账单 / 邀请列表 */}
      <Card>
        <div className="flex items-center gap-6 border-b border-border px-6">
          {(
            [
              { key: "records", label: t("affiliate.tabRecords") },
              { key: "invitees", label: t("affiliate.tabInvitees") },
            ] as { key: Tab; label: string }[]
          ).map((item) => (
            <button
              key={item.key}
              type="button"
              onClick={() => setTab(item.key)}
              className={cn(
                "relative -mb-px border-b-2 py-3 text-sm transition-colors",
                tab === item.key
                  ? "border-primary font-medium text-foreground"
                  : "border-transparent text-muted-foreground hover:text-foreground"
              )}
            >
              {item.label}
            </button>
          ))}
        </div>
        <CardContent className="pt-4">
          {tab === "records" ? (
            <div className="space-y-3">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-xs text-muted-foreground">
                      <th className="py-2 pr-4 font-medium">{t("affiliate.colTime")}</th>
                      <th className="py-2 pr-4 font-medium">{t("affiliate.colType")}</th>
                      <th className="py-2 pr-4 font-medium">{t("affiliate.colAmount")}</th>
                      <th className="py-2 pr-4 font-medium">{t("affiliate.colSource")}</th>
                      <th className="py-2 font-medium">{t("affiliate.colOrder")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {records.map((r) => (
                      <tr key={r.id} className="border-t border-border/60">
                        <td className="py-2.5 pr-4 text-muted-foreground">
                          {formatTime(r.created_at)}
                        </td>
                        <td className="py-2.5 pr-4">
                          {r.action === "accrue"
                            ? t("affiliate.recordAccrue")
                            : t("affiliate.recordTransfer")}
                        </td>
                        <td className="py-2.5 pr-4 font-medium">
                          {r.action === "accrue" ? "+" : "-"}
                          {fmt(r.amount)}
                        </td>
                        <td className="py-2.5 pr-4 text-muted-foreground">
                          {r.source_username ?? "—"}
                        </td>
                        <td className="py-2.5 text-muted-foreground">{r.order_no ?? "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {!recordsLoading && records.length === 0 && (
                <p className="py-8 text-center text-sm text-muted-foreground">
                  {t("affiliate.emptyRecords")}
                </p>
              )}
              {recordsTotal > 0 && (
                <Pagination
                  page={recordsPage}
                  totalPages={recordTotalPages}
                  loading={recordsLoading}
                  onChange={loadRecords}
                />
              )}
            </div>
          ) : (
            <div className="space-y-3">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-xs text-muted-foreground">
                      <th className="py-2 pr-4 font-medium">{t("affiliate.colUsername")}</th>
                      <th className="py-2 pr-4 font-medium">{t("affiliate.colBoundAt")}</th>
                      <th className="py-2 font-medium">{t("affiliate.colTotalRebate")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {invitees.map((inv) => (
                      <tr key={inv.user_id} className="border-t border-border/60">
                        <td className="py-2.5 pr-4 font-medium">{inv.username}</td>
                        <td className="py-2.5 pr-4 text-muted-foreground">
                          {formatTime(inv.created_at)}
                        </td>
                        <td className="py-2.5">$ {fmt(inv.total_rebate)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {!inviteesLoading && invitees.length === 0 && (
                <p className="py-8 text-center text-sm text-muted-foreground">
                  {t("affiliate.emptyInvitees")}
                </p>
              )}
              {inviteesTotal > 0 && (
                <Pagination
                  page={inviteesPage}
                  totalPages={inviteeTotalPages}
                  loading={inviteesLoading}
                  onChange={loadInvitees}
                />
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {loadError && !detail && (
        <p className="text-center text-sm text-destructive">
          {t("affiliate.loadFailed")}
        </p>
      )}
    </div>
  );
}
