"use client";

import { useCallback, useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import {
  Activity,
  ArrowRight,
  BarChart3,
  Boxes,
  ChevronRight,
  Clock,
  Copy,
  ExternalLink,
  Flame,
  Globe,
  KeyRound,
  Megaphone,
  TrendingUp,
  Wallet,
  type LucideIcon,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Loading } from "@/components/ui/loading";
import { Pagination } from "@/components/ui/pagination";
import { toast } from "@/components/ui/toaster";
import { LocaleLink } from "@/components/locale-link";
import { markMessageRead, type InboxMessage, type MessageType } from "@/lib/messages";
import { badgeDotClass, getOverviewDetail, type OverviewDetail } from "@/lib/overview";
import { cn } from "@/lib/utils";

const MESSAGE_PAGE_SIZE = 10;

/** 金额展示：纯字符串截取两位小数，不做数值运算（十进制字符串安全） */
const formatYuan = (amount: string) => {
  const [intPart = "0", fracPart = ""] = String(amount).trim().split(".");
  return `¥${intPart}.${`${fracPart}00`.slice(0, 2)}`;
};

/** 公告列表的类型圆点颜色 */
const MESSAGE_DOT: Record<MessageType, string> = {
  notice: "bg-blue-500",
  maintenance: "bg-red-500",
  update: "bg-emerald-500",
  activity: "bg-amber-500",
};

const MESSAGE_BADGE_VARIANT: Record<
  MessageType,
  "default" | "secondary" | "destructive" | "outline"
> = {
  notice: "default",
  maintenance: "destructive",
  update: "secondary",
  activity: "outline",
};

/** 公告详情弹窗：markdown 渲染正文（Portal 到 body，避免被裁切） */
function MessageDetailDialog({
  item,
  onClose,
}: {
  item: InboxMessage;
  onClose: () => void;
}) {
  const { t, i18n } = useTranslation("console");
  const locale = i18n.language === "zh" ? "zh-CN" : "en-US";

  return createPortal(
    <div
      className="fixed inset-0 z-[80] flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="flex max-h-[85vh] w-full max-w-lg flex-col rounded-xl border bg-background p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-3">
          <h2 className="text-base font-semibold">{item.title}</h2>
          <Badge variant={MESSAGE_BADGE_VARIANT[item.type]} className="shrink-0">
            {t(`messages.type.${item.type}`)}
          </Badge>
        </div>
        <p className="mt-1 text-xs text-muted-foreground">
          {new Date(item.created_at ?? item.start_at).toLocaleString(locale, {
            hour12: false,
          })}
        </p>
        <div className="markdown-body mt-4 flex-1 overflow-y-auto border-t border-border/60 pt-4">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{item.content}</ReactMarkdown>
        </div>
        <div className="mt-6 flex justify-end">
          <Button variant="outline" onClick={onClose}>
            {t("overview.close")}
          </Button>
        </div>
      </div>
    </div>,
    document.body
  );
}

export function OverviewPanel() {
  const { t, i18n } = useTranslation("console");
  const locale = i18n.language === "zh" ? "zh-CN" : "en-US";
  const [detail, setDetail] = useState<OverviewDetail | null>(null);
  const [error, setError] = useState("");
  const [messagePage, setMessagePage] = useState(1);
  const [messageLoading, setMessageLoading] = useState(false);
  const [activeMessage, setActiveMessage] = useState<InboxMessage | null>(null);

  const load = useCallback(
    (page: number) => {
      setMessageLoading(true);
      getOverviewDetail({ message_page: page, message_page_size: MESSAGE_PAGE_SIZE })
        .then(setDetail)
        .catch((err) =>
          setError(err instanceof Error ? err.message : t("overview.loadFailed"))
        )
        .finally(() => setMessageLoading(false));
    },
    [t]
  );

  useEffect(() => {
    load(messagePage);
  }, [load, messagePage]);

  const copyUrl = async (url: string) => {
    try {
      await navigator.clipboard.writeText(url);
      toast.success(t("overview.copySuccess"));
    } catch {
      toast.error(t("overview.copyFailed"));
    }
  };

  /** 打开公告详情并乐观标记已读 */
  const onOpenMessage = (item: InboxMessage) => {
    setActiveMessage(item);
    if (item.is_read) return;
    setDetail((prev) =>
      prev
        ? {
            ...prev,
            messages: {
              ...prev.messages,
              items: prev.messages.items.map((m) =>
                m.id === item.id ? { ...m, is_read: true } : m
              ),
            },
          }
        : prev
    );
    markMessageRead(item.id).catch(() => {
      // 已读标记失败静默，下次刷新自动校准
    });
  };

  if (error) {
    return (
      <Card className="w-full">
        <CardContent className="py-6">
          <p className="text-base font-semibold">{t("overview.loadFailed")}</p>
          <p className="mt-1 text-sm text-muted-foreground">{error}</p>
        </CardContent>
      </Card>
    );
  }

  if (!detail) {
    return (
      <div className="flex items-center justify-center py-20 text-muted-foreground">
        <Loading size="lg" />
      </div>
    );
  }

  const quickActions: Array<{
    href: string;
    icon: LucideIcon;
    label: string;
    desc: string;
    iconClass: string;
  }> = [
    {
      href: "/console/api-keys",
      icon: KeyRound,
      label: t("overview.quickActionApiKeys"),
      desc: t("overview.quickActionApiKeysDesc"),
      iconClass: "bg-teal-500/10 text-teal-500",
    },
    {
      href: "/console/usage-records",
      icon: BarChart3,
      label: t("overview.quickActionUsageRecords"),
      desc: t("overview.quickActionUsageRecordsDesc"),
      iconClass: "bg-emerald-500/10 text-emerald-500",
    },
    {
      href: "/console/models",
      icon: Boxes,
      label: t("overview.quickActionModels"),
      desc: t("overview.quickActionModelsDesc"),
      iconClass: "bg-purple-500/10 text-purple-500",
    },
    {
      href: "/console/billing",
      icon: Wallet,
      label: t("overview.quickActionWallet"),
      desc: t("overview.quickActionWalletDesc"),
      iconClass: "bg-amber-500/10 text-amber-500",
    },
  ];

  const usageStats: Array<{
    icon: LucideIcon;
    label: string;
    value: string;
    hint: string;
    iconClass: string;
  }> = [
    {
      icon: Flame,
      label: t("overview.todayConsumption"),
      value: formatYuan(detail.usage.settled_amount),
      hint: t("overview.todayConsumptionHint"),
      iconClass: "bg-sky-500/10 text-sky-500",
    },
    {
      icon: TrendingUp,
      label: t("overview.totalUsage"),
      value: formatYuan(detail.wallet.usage),
      hint: t("overview.totalUsageHint"),
      iconClass: "bg-teal-500/10 text-teal-500",
    },
    {
      icon: Activity,
      label: t("overview.requestCount"),
      value: String(detail.usage.total_count),
      hint: t("overview.requestCountHint"),
      iconClass: "bg-purple-500/10 text-purple-500",
    },
  ];

  const messageTotalPages = Math.max(
    1,
    Math.ceil(detail.messages.total / MESSAGE_PAGE_SIZE)
  );

  return (
    <div className="flex w-full flex-col gap-6">
      {/* 页头 */}
      <h1 className="text-lg font-semibold">{t("overview.title")}</h1>

      {/* 用量概览：左侧指标卡 + 右侧钱包卡 */}
      <Card>
        <CardContent className="flex flex-col gap-4">
          <div>
            <h2 className="text-base font-semibold">{t("overview.usageTitle")}</h2>
            <p className="mt-0.5 text-sm text-muted-foreground">
              {t("overview.usageSubtitle")}
            </p>
          </div>
          <div className="grid gap-4 lg:grid-cols-[1fr_300px]">
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
              {usageStats.map((stat) => (
                <div
                  key={stat.label}
                  className="rounded-xl border border-border/60 p-4"
                >
                  <span
                    className={cn(
                      "flex size-8 items-center justify-center rounded-lg",
                      stat.iconClass
                    )}
                  >
                    <stat.icon className="size-4" />
                  </span>
                  <p className="mt-3 text-sm text-muted-foreground">{stat.label}</p>
                  <p className="mt-1 truncate text-2xl font-semibold tracking-tight">
                    {stat.value}
                  </p>
                  <p className="mt-1 text-xs text-muted-foreground">{stat.hint}</p>
                </div>
              ))}
            </div>

            {/* 钱包卡 */}
            <div className="flex flex-col rounded-xl border border-primary/20 bg-gradient-to-br from-primary/15 via-primary/5 to-transparent p-4">
              <div className="flex items-center justify-between">
                <p className="text-sm text-muted-foreground">
                  {t("overview.walletBalance")}
                </p>
                <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
                  <span className="size-1.5 rounded-full bg-emerald-500" />
                  {t("overview.walletNormal")}
                </span>
              </div>
              <p className="mt-2 truncate text-3xl font-semibold tracking-tight">
                {formatYuan(detail.wallet.balance)}
              </p>
              <div className="mt-3 flex items-center gap-2 text-xs text-muted-foreground">
                <Flame className="size-3.5" />
                <span>{t("overview.walletTodayConsumption")}</span>
                <span className="font-medium text-foreground">
                  {formatYuan(detail.usage.settled_amount)}
                </span>
              </div>
              <LocaleLink href="/console/billing" className="mt-auto pt-4">
                <Button className="w-full gap-1.5">
                  {t("overview.walletButton")}
                  <ArrowRight className="size-4" />
                </Button>
              </LocaleLink>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* 快捷操作 + API 信息 + 公告 */}
      <div className="grid gap-6 lg:grid-cols-3">
        {/* 快捷操作 */}
        <Card>
          <CardContent className="flex flex-col gap-4">
            <h2 className="text-base font-semibold">
              {t("overview.quickActionsTitle")}
            </h2>
            <ul className="flex flex-col gap-2">
              {quickActions.map((action) => (
                <li key={action.href}>
                  <LocaleLink
                    href={action.href}
                    className="group flex items-center gap-4 rounded-xl border border-border/60 px-4 py-3.5 transition-colors hover:border-primary/30 hover:bg-muted/40"
                  >
                    <span
                      className={cn(
                        "flex size-10 shrink-0 items-center justify-center rounded-lg",
                        action.iconClass
                      )}
                    >
                      <action.icon className="size-5" />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block text-sm font-medium">
                        {action.label}
                      </span>
                      <span className="mt-0.5 block text-xs text-muted-foreground">
                        {action.desc}
                      </span>
                    </span>
                    <ChevronRight className="size-4 shrink-0 text-muted-foreground/60 transition-transform group-hover:translate-x-0.5 group-hover:text-foreground" />
                  </LocaleLink>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>

        {/* API 信息 */}
        <Card>
          <CardContent className="flex flex-col gap-4">
            <div className="flex items-center gap-2.5">
              <span className="flex size-8 items-center justify-center rounded-lg bg-sky-500/10 text-sky-500">
                <Globe className="size-4" />
              </span>
              <div>
                <h2 className="text-base font-semibold">
                  {t("overview.apiInfoTitle")}
                </h2>
                <p className="text-xs text-muted-foreground">
                  {t("overview.apiInfoSubtitle")}
                </p>
              </div>
            </div>
            {detail.site_infos.length === 0 ? (
              <p className="py-10 text-center text-sm text-muted-foreground">
                {t("overview.apiInfoEmpty")}
              </p>
            ) : (
              <ul className="divide-y divide-border/60">
                {detail.site_infos.map((info) => (
                  <li
                    key={info.id}
                    className="flex items-center justify-between gap-4 py-4 first:pt-0 last:pb-0"
                  >
                    <div className="flex min-w-0 items-start gap-3">
                      <span
                        className={cn(
                          "mt-1.5 size-2 shrink-0 rounded-full",
                          badgeDotClass(info.badge_color)
                        )}
                        aria-hidden
                      />
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-baseline gap-x-2">
                          <p className="text-sm font-medium">{info.route_name}</p>
                          {info.description && (
                            <p className="text-xs text-muted-foreground">
                              {info.description}
                            </p>
                          )}
                        </div>
                        <p className="mt-0.5 truncate text-xs text-muted-foreground">
                          {info.api_url}
                        </p>
                      </div>
                    </div>
                    <div className="flex shrink-0 items-center gap-1">
                      <button
                        type="button"
                        onClick={() => copyUrl(info.api_url)}
                        title={t("overview.copyUrl")}
                        aria-label={t("overview.copyUrl")}
                        className="flex size-7 cursor-pointer items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                      >
                        <Copy className="size-3.5" />
                      </button>
                      <a
                        href={info.api_url}
                        target="_blank"
                        rel="noreferrer"
                        title={t("overview.openUrl")}
                        aria-label={t("overview.openUrl")}
                        className="flex size-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                      >
                        <ExternalLink className="size-3.5" />
                      </a>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        {/* 公告 */}
        <Card>
          <CardContent className="flex flex-col gap-4">
            <div className="flex items-center gap-2.5">
              <span className="flex size-8 items-center justify-center rounded-lg bg-amber-500/10 text-amber-500">
                <Megaphone className="size-4" />
              </span>
              <div>
                <h2 className="text-base font-semibold">
                  {t("overview.announcementTitle")}
                </h2>
                <p className="text-xs text-muted-foreground">
                  {t("overview.announcementSubtitle")}
                </p>
              </div>
            </div>
            {detail.messages.items.length === 0 ? (
              <p className="py-10 text-center text-sm text-muted-foreground">
                {t("overview.announcementEmpty")}
              </p>
            ) : (
              <ul className="-mx-2 flex flex-col">
                {detail.messages.items.map((item) => (
                  <li key={item.id}>
                    <button
                      type="button"
                      onClick={() => onOpenMessage(item)}
                      className="group flex w-full cursor-pointer items-center gap-3 rounded-lg px-2 py-3 text-left transition-colors hover:bg-muted/50"
                    >
                      <span
                        className={cn(
                          "size-2 shrink-0 rounded-full",
                          MESSAGE_DOT[item.type],
                          item.is_read && "opacity-40"
                        )}
                        aria-hidden
                      />
                      <span className="min-w-0 flex-1">
                        <span
                          className={cn(
                            "block truncate text-sm",
                            item.is_read
                              ? "text-muted-foreground"
                              : "font-medium text-foreground"
                          )}
                        >
                          {item.title}
                        </span>
                        <span className="mt-1 flex items-center gap-1 text-xs text-muted-foreground">
                          <Clock className="size-3" />
                          {new Date(item.created_at ?? item.start_at).toLocaleString(
                            locale,
                            { hour12: false }
                          )}
                        </span>
                      </span>
                      <Badge
                        variant={MESSAGE_BADGE_VARIANT[item.type]}
                        className="shrink-0"
                      >
                        {t(`messages.type.${item.type}`)}
                      </Badge>
                      <ChevronRight className="size-4 shrink-0 text-muted-foreground/60 opacity-0 transition-all group-hover:translate-x-0.5 group-hover:opacity-100" />
                    </button>
                  </li>
                ))}
              </ul>
            )}
            {messageTotalPages > 1 && (
              <Pagination
                page={detail.messages.page}
                totalPages={messageTotalPages}
                loading={messageLoading}
                onChange={setMessagePage}
                className="mt-auto"
              />
            )}
          </CardContent>
        </Card>
      </div>

      {activeMessage && (
        <MessageDetailDialog
          item={
            detail.messages.items.find((m) => m.id === activeMessage.id) ??
            activeMessage
          }
          onClose={() => setActiveMessage(null)}
        />
      )}
    </div>
  );
}
