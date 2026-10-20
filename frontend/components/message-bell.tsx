"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { Bell, CheckCheck } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Loading } from "@/components/ui/loading";
import { Select } from "@/components/ui/select";
import { toast } from "@/components/ui/toaster";
import { cn } from "@/lib/utils";
import { getToken } from "@/lib/request";
import {
  MESSAGE_TYPES,
  dismissNotification,
  getMessageUnreadCount,
  listInboxMessages,
  listInboxNotifications,
  markAllMessagesRead,
  markMessageRead,
  type InboxMessage,
  type InboxNotification,
  type MessageType,
  type UnreadCount,
} from "@/lib/messages";

/** 未读数轮询间隔（毫秒） */
const POLL_INTERVAL = 60_000;
const PAGE_SIZE = 20;

const TYPE_VARIANT: Record<
  MessageType,
  "default" | "secondary" | "destructive" | "outline"
> = {
  notice: "default",
  maintenance: "destructive",
  update: "secondary",
  activity: "outline",
};

type Tab = "message" | "notification";

/** 详情弹窗：markdown 渲染正文（消息带类型徽标，历史通知不带） */
function InboxDetailDialog({
  item,
  onClose,
}: {
  item: InboxMessage | InboxNotification;
  onClose: () => void;
}) {
  const { t, i18n } = useTranslation("console");
  const locale = i18n.language === "zh" ? "zh-CN" : "en-US";
  const type = "type" in item ? item.type : null;

  // Portal 到 body：顶栏的 backdrop-blur 会让后代 fixed 元素相对顶栏而非视口定位，导致弹窗被裁切
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
          {type && (
            <Badge variant={TYPE_VARIANT[type]} className="shrink-0">
              {t(`messages.type.${type}`)}
            </Badge>
          )}
        </div>
        <p className="mt-1 text-xs text-muted-foreground">
          {new Date(item.start_at).toLocaleString(locale, { hour12: false })}
        </p>
        <div className="markdown-body mt-4 flex-1 overflow-y-auto border-t border-border/60 pt-4">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{item.content}</ReactMarkdown>
        </div>
        <div className="mt-6 flex justify-end">
          <Button variant="outline" onClick={onClose}>
            {t("messages.close")}
          </Button>
        </div>
      </div>
    </div>,
    document.body
  );
}

/** 顶栏消息铃铛：未读角标 + 下拉收件箱（消息 / 历史通知），仅登录后展示 */
export function MessageBell() {
  const { t, i18n } = useTranslation("console");
  const locale = i18n.language === "zh" ? "zh-CN" : "en-US";
  const [mounted, setMounted] = useState(false);
  const [loggedIn, setLoggedIn] = useState(false);
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState<Tab>("message");
  const [unread, setUnread] = useState<UnreadCount>({
    message_unread_count: 0,
    notification_pending_count: 0,
  });
  const [messages, setMessages] = useState<InboxMessage[]>([]);
  const [notifications, setNotifications] = useState<InboxNotification[]>([]);
  const [loading, setLoading] = useState(false);
  const [unreadOnly, setUnreadOnly] = useState(false);
  const [typeFilter, setTypeFilter] = useState<"" | MessageType>("");
  const [detail, setDetail] = useState<InboxMessage | InboxNotification | null>(
    null
  );
  const menuRef = useRef<HTMLDivElement>(null);

  const badgeCount =
    unread.message_unread_count + unread.notification_pending_count;

  const refreshUnread = useCallback(async () => {
    if (!getToken()) return;
    try {
      const data = await getMessageUnreadCount();
      setUnread(data);
    } catch {
      // 未读数失败静默，不打断用户
    }
  }, []);

  const loadList = useCallback(async () => {
    if (!getToken()) return;
    setLoading(true);
    try {
      if (tab === "message") {
        const data = await listInboxMessages({
          page: 1,
          page_size: PAGE_SIZE,
          unread_only: unreadOnly || undefined,
          type: typeFilter || undefined,
        });
        setMessages(data.items);
      } else {
        const data = await listInboxNotifications({
          page: 1,
          page_size: PAGE_SIZE,
        });
        setNotifications(data.items);
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t("messages.loadFailed"));
    } finally {
      setLoading(false);
    }
  }, [t, tab, unreadOnly, typeFilter]);

  // 仅客户端挂载后读取令牌，避免水合不匹配
  useEffect(() => {
    setMounted(true);
    if (!getToken()) return;
    setLoggedIn(true);
    refreshUnread();
    const timer = setInterval(refreshUnread, POLL_INTERVAL);
    return () => clearInterval(timer);
  }, [refreshUnread]);

  // 打开弹层/切换 tab/筛选变化时拉取列表与最新未读数
  useEffect(() => {
    if (!open) return;
    loadList();
    refreshUnread();
  }, [open, loadList, refreshUnread]);

  // 点击菜单外部时收起下拉
  useEffect(() => {
    const onClickOutside = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, []);

  /** 打开消息详情并乐观标记已读 */
  const onOpenMessage = async (item: InboxMessage) => {
    setDetail(item);
    if (item.is_read) return;
    setMessages((prev) =>
      prev.map((m) => (m.id === item.id ? { ...m, is_read: true } : m))
    );
    setUnread((u) => ({
      ...u,
      message_unread_count: Math.max(0, u.message_unread_count - 1),
    }));
    try {
      await markMessageRead(item.id);
    } catch {
      // 已读标记失败静默，下次刷新自动校准
    }
  };

  /** 打开历史通知详情并乐观标记已读（dismiss） */
  const onOpenNotification = async (item: InboxNotification) => {
    setDetail(item);
    if (item.is_dismissed) return;
    setNotifications((prev) =>
      prev.map((n) => (n.id === item.id ? { ...n, is_dismissed: true } : n))
    );
    setUnread((u) => ({
      ...u,
      notification_pending_count: Math.max(0, u.notification_pending_count - 1),
    }));
    try {
      await dismissNotification(item.id);
    } catch {
      // 已读标记失败静默，下次刷新自动校准
    }
  };

  const onMarkAllRead = async () => {
    try {
      const data = await markAllMessagesRead();
      setUnread((u) => ({ ...u, message_unread_count: 0 }));
      setMessages((prev) => prev.map((m) => ({ ...m, is_read: true })));
      if (data.marked_count > 0) {
        toast.success(t("messages.markedAll", { count: data.marked_count }));
      }
      if (unreadOnly) loadList();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t("messages.loadFailed"));
    }
  };

  if (!mounted || !loggedIn) return null;

  return (
    <div ref={menuRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-label={t("messages.bellLabel")}
        title={t("messages.bellLabel")}
        className="relative flex size-8 cursor-pointer items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
      >
        <Bell className="size-4" />
        {badgeCount > 0 && (
          <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-destructive px-1 text-[10px] font-semibold leading-none text-white ring-2 ring-background">
            {badgeCount > 99 ? "99+" : badgeCount}
          </span>
        )}
      </button>

      {open && (
        // 不使用 overflow-hidden，避免裁切筛选 Select 的弹层；圆角由内部元素各自处理
        <div className="absolute right-0 top-full mt-2 flex max-h-[70vh] w-96 flex-col rounded-xl border bg-background shadow-lg">
          {/* tab 切换：消息 / 历史通知 */}
          <div className="flex rounded-t-[11px] border-b border-border/60 bg-background px-2 pt-2">
            {(["message", "notification"] as Tab[]).map((tb) => {
              const count =
                tb === "message"
                  ? unread.message_unread_count
                  : unread.notification_pending_count;
              return (
                <button
                  key={tb}
                  type="button"
                  onClick={() => setTab(tb)}
                  className={cn(
                    "flex cursor-pointer items-center gap-1.5 border-b-2 px-3 pb-2 text-sm transition-colors",
                    tab === tb
                      ? "border-primary font-medium text-foreground"
                      : "border-transparent text-muted-foreground hover:text-foreground"
                  )}
                >
                  {t(`messages.tab.${tb}`)}
                  {count > 0 && (
                    <span className="flex h-4 min-w-4 items-center justify-center rounded-full bg-destructive px-1 text-[10px] font-semibold leading-none text-white">
                      {count > 99 ? "99+" : count}
                    </span>
                  )}
                </button>
              );
            })}
          </div>

          {/* 消息 tab 的工具栏：类型筛选 + 仅未读 + 全部已读 */}
          {tab === "message" && (
            <div className="flex items-center justify-end gap-2 border-b border-border/60 bg-background px-4 py-2">
              <Select
                value={typeFilter}
                onValueChange={(v) => setTypeFilter(v as "" | MessageType)}
                options={[
                  { value: "", label: t("messages.typeAll") },
                  ...MESSAGE_TYPES.map((tp) => ({
                    value: tp,
                    label: t(`messages.type.${tp}`),
                  })),
                ]}
                className="w-auto"
                aria-label={t("messages.typeFilterAria")}
              />
              <button
                type="button"
                onClick={() => setUnreadOnly((v) => !v)}
                className={cn(
                  "cursor-pointer rounded-full border px-2.5 py-1 text-xs transition-colors",
                  unreadOnly
                    ? "border-primary bg-primary/10 text-primary"
                    : "border-border text-muted-foreground hover:text-foreground"
                )}
              >
                {t("messages.unreadOnly")}
              </button>
              <button
                type="button"
                onClick={onMarkAllRead}
                disabled={unread.message_unread_count === 0}
                title={t("messages.markAllRead")}
                className="cursor-pointer text-muted-foreground transition-colors hover:text-foreground disabled:cursor-not-allowed disabled:opacity-40"
              >
                <CheckCheck className="size-4" />
              </button>
            </div>
          )}

          {/* 列表 */}
          <div className="flex-1 overflow-y-auto rounded-b-[11px]">
            {loading ? (
              <div className="flex items-center justify-center py-12">
                <Loading size="md" />
              </div>
            ) : tab === "message" ? (
              messages.length === 0 ? (
                <p className="py-12 text-center text-sm text-muted-foreground">
                  {t("messages.empty")}
                </p>
              ) : (
                <ul className="divide-y divide-border/60">
                  {messages.map((item) => (
                    <li key={item.id}>
                      <button
                        type="button"
                        onClick={() => onOpenMessage(item)}
                        className="flex w-full cursor-pointer items-start gap-3 px-4 py-3 text-left transition-colors hover:bg-muted/60"
                      >
                        <span
                          className={cn(
                            "mt-1.5 size-2 shrink-0 rounded-full",
                            item.is_read ? "bg-transparent" : "bg-primary"
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
                          <span className="mt-1 flex items-center gap-2">
                            <Badge variant={TYPE_VARIANT[item.type]}>
                              {t(`messages.type.${item.type}`)}
                            </Badge>
                            <span className="text-xs text-muted-foreground">
                              {new Date(item.start_at).toLocaleString(locale, {
                                hour12: false,
                              })}
                            </span>
                          </span>
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              )
            ) : notifications.length === 0 ? (
              <p className="py-12 text-center text-sm text-muted-foreground">
                {t("messages.emptyNotification")}
              </p>
            ) : (
              <ul className="divide-y divide-border/60">
                {notifications.map((item) => (
                  <li key={item.id}>
                    <button
                      type="button"
                      onClick={() => onOpenNotification(item)}
                      className="flex w-full cursor-pointer items-start gap-3 px-4 py-3 text-left transition-colors hover:bg-muted/60"
                    >
                      <span
                        className={cn(
                          "mt-1.5 size-2 shrink-0 rounded-full",
                          item.is_dismissed ? "bg-transparent" : "bg-primary"
                        )}
                      />
                      <span className="min-w-0 flex-1">
                        <span
                          className={cn(
                            "block truncate text-sm",
                            item.is_dismissed
                              ? "text-muted-foreground"
                              : "font-medium text-foreground"
                          )}
                        >
                          {item.title}
                        </span>
                        <span className="mt-1 flex items-center gap-2">
                          <Badge
                            variant={item.is_dismissed ? "outline" : "default"}
                          >
                            {item.is_dismissed
                              ? t("messages.dismissed")
                              : t("messages.pending")}
                          </Badge>
                          <span className="text-xs text-muted-foreground">
                            {new Date(item.start_at).toLocaleString(locale, {
                              hour12: false,
                            })}
                          </span>
                        </span>
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}

      {detail && (
        <InboxDetailDialog
          item={
            // 详情中同步最新已读状态
            "type" in detail
              ? (messages.find((m) => m.id === detail.id) ?? detail)
              : detail
          }
          onClose={() => setDetail(null)}
        />
      )}
    </div>
  );
}
