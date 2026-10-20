"use client";

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { Bell, CalendarClock, Megaphone, Sparkles } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { Button } from "@/components/ui/button";
import { getToken } from "@/lib/request";
import {
  dismissNotification,
  getCurrentNotification,
  type InboxNotification,
} from "@/lib/messages";

/**
 * 进入网站时的弹窗通知：全局同一时刻仅一条生效中，
 * 关闭（dismiss）后不再弹出，可在消息中心的「历史通知」回看。
 * 仅登录后展示。
 */
export function NotificationPopup() {
  const { t, i18n } = useTranslation("console");
  const [notification, setNotification] = useState<InboxNotification | null>(
    null
  );
  const [closing, setClosing] = useState(false);

  useEffect(() => {
    if (!getToken()) return;
    let cancelled = false;
    getCurrentNotification()
      .then((data) => {
        if (!cancelled && data.notification) {
          setNotification(data.notification);
        }
      })
      .catch(() => {
        // 拉取失败静默，不打断用户
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const onDismiss = async () => {
    if (!notification || closing) return;
    setClosing(true);
    try {
      await dismissNotification(notification.id);
    } catch {
      // 关闭失败也收起弹窗，状态下次刷新自动校准
    } finally {
      setNotification(null);
    }
  };

  if (!notification) return null;

  return createPortal(
    <div className="fixed inset-0 z-[90] flex items-center justify-center bg-black/60 p-4 backdrop-blur-md">
      <div
        role="dialog"
        aria-modal="true"
        aria-label={notification.title}
        className="animate-pop-in relative max-h-[88vh] w-full max-w-2xl rounded-3xl bg-gradient-to-b from-primary/50 via-border/60 to-border/60 p-px shadow-2xl"
      >
        <div className="relative flex max-h-[calc(88vh-2px)] w-full flex-col overflow-hidden rounded-[calc(1.5rem-1px)] bg-background">
          {/* 通栏主题横幅：渐变底 + 网格纹理 + 呼吸辉光 */}
          <div className="relative overflow-hidden bg-gradient-to-br from-primary/[0.08] via-primary/[0.04] to-transparent px-6 pb-6 pt-8">
            <div
              aria-hidden
              className="bg-grid absolute inset-0 opacity-60 [mask-image:linear-gradient(to_bottom,black,transparent)]"
            />
            <div
              aria-hidden
              className="animate-glow-pulse pointer-events-none absolute -top-16 left-1/3 h-40 w-1/2 rounded-full bg-primary/20 blur-3xl"
            />
            <Sparkles
              aria-hidden
              className="animate-twinkle pointer-events-none absolute right-8 top-7 size-4 text-primary/40"
            />
            <Bell
              aria-hidden
              className="animate-twinkle pointer-events-none absolute right-16 top-14 size-3.5 text-primary/30 [animation-delay:0.9s]"
            />

            <div className="relative flex flex-col items-center">
              {/* 喇叭 + 声波弧线作为一个整体居中 */}
              <div className="flex items-center">
                <Megaphone className="size-10 shrink-0 text-primary" strokeWidth={1.8} />
                <svg
                  aria-hidden
                  viewBox="0 0 32 32"
                  className="-ml-1 size-8 text-primary/70"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth={2.5}
                  strokeLinecap="round"
                >
                  {["M4 10 Q 10 16 4 22", "M10 6 Q 20 16 10 26", "M16 2 Q 30 16 16 30"].map(
                    (d, i) => (
                      <path
                        key={d}
                        d={d}
                        className="animate-sound-wave"
                        style={{ animationDelay: `${i * 0.35}s` }}
                      />
                    )
                  )}
                </svg>
              </div>
              <p className="mt-4 inline-flex items-center gap-1.5 rounded-full border border-primary/25 bg-background/70 px-2.5 py-0.5 text-[11px] font-medium tracking-[0.18em] text-primary uppercase backdrop-blur">
                <Sparkles className="size-3" />
                {t("messages.popup.badge")}
              </p>
              <h2 className="mt-2.5 text-center text-xl font-semibold leading-snug">
                {notification.title}
              </h2>
              <p className="mt-1.5 flex items-center gap-1.5 text-xs text-muted-foreground">
                <CalendarClock className="size-3.5" />
                {new Date(notification.start_at).toLocaleString(
                  i18n.language === "zh" ? "zh-CN" : "en-US",
                  { hour12: false }
                )}
              </p>
            </div>
          </div>

          <div className="relative mx-6 mt-5 flex-1 overflow-hidden rounded-2xl border border-border/60 bg-muted/30">
            <div className="no-scrollbar markdown-body h-full max-h-[38vh] overflow-y-auto px-5 py-4">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {notification.content}
              </ReactMarkdown>
            </div>
          </div>

          <div className="relative px-6 pb-6 pt-5">
            <Button
              size="lg"
              className="w-full rounded-xl"
              onClick={onDismiss}
              disabled={closing}
            >
              {t("messages.popup.markRead")}
            </Button>
          </div>
        </div>
      </div>
    </div>,
    document.body
  );
}
