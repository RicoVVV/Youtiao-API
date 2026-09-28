"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2, Info, X, XCircle } from "lucide-react";

import { cn } from "@/lib/utils";

/**
 * 全局轻提示
 * - 任意位置直接调用：toast.success("已保存") / toast.error("请求失败") / toast.warning("请注意")
 * - 无需 Provider，<Toaster /> 只需在根布局挂载一次
 */

type ToastType = "success" | "error" | "warning" | "info";

type ToastItem = {
  id: number;
  type: ToastType;
  message: string;
  /** 消失动画进行中 */
  leaving?: boolean;
};

const DURATION = 3000;
const EXIT_DURATION = 250;

let push: ((type: ToastType, message: string) => void) | null = null;

export const toast = {
  success: (message: string) => push?.("success", message),
  error: (message: string) => push?.("error", message),
  warning: (message: string) => push?.("warning", message),
  info: (message: string) => push?.("info", message),
};

const styles: Record<ToastType, { icon: typeof CheckCircle2; className: string }> = {
  success: { icon: CheckCircle2, className: "border-success/40 text-success" },
  error: { icon: XCircle, className: "border-destructive/40 text-destructive" },
  warning: { icon: AlertTriangle, className: "border-warning/40 text-warning" },
  info: { icon: Info, className: "border-primary/40 text-primary" },
};

export function Toaster() {
  const [items, setItems] = useState<ToastItem[]>([]);

  useEffect(() => {
    push = (type, message) => {
      const id = Date.now() + Math.random();
      setItems((prev) => [...prev, { id, type, message }]);
      // 先播放退场动画，再真正移除
      setTimeout(
        () => setItems((prev) => prev.map((t) => (t.id === id ? { ...t, leaving: true } : t))),
        DURATION
      );
      setTimeout(() => setItems((prev) => prev.filter((t) => t.id !== id)), DURATION + EXIT_DURATION);
    };
    return () => {
      push = null;
    };
  }, []);

  const dismiss = (id: number) => setItems((prev) => prev.filter((t) => t.id !== id));

  return (
    <div className="pointer-events-none fixed left-1/2 top-4 z-[100] flex w-80 -translate-x-1/2 flex-col gap-2">
      {items.map((item) => {
        const { icon: Icon, className } = styles[item.type];
        return (
          <div
            key={item.id}
            className={cn(
              "pointer-events-auto flex items-start gap-2.5 rounded-lg border bg-background px-3.5 py-3 shadow-lg",
              item.leaving ? "animate-toast-out" : "animate-toast-in",
              className
            )}
          >
            <Icon className="mt-0.5 size-4 shrink-0" />
            <p className="flex-1 text-sm leading-snug text-foreground">{item.message}</p>
            <button
              type="button"
              onClick={() => dismiss(item.id)}
              className="cursor-pointer text-muted-foreground transition-colors hover:text-foreground"
              aria-label="关闭提示"
            >
              <X className="size-3.5" />
            </button>
          </div>
        );
      })}
    </div>
  );
}
