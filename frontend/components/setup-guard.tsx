"use client";

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";

import { get } from "@/lib/request";
import { stripLocale } from "@/lib/path-utils";
import { useLocale } from "@/i18n/client";

/** 兼容多种响应字段：needs_setup / setup_required / initialized / has_admin */
function needsSetup(data: unknown): boolean {
  if (!data || typeof data !== "object") return false;
  const d = data as Record<string, unknown>;
  if (typeof d.needs_setup === "boolean") return d.needs_setup;
  if (typeof d.setup_required === "boolean") return d.setup_required;
  if (typeof d.initialized === "boolean") return !d.initialized;
  if (typeof d.has_admin === "boolean") return !d.has_admin;
  return false;
}

/**
 * 首次安装引导：应用初始化时检测管理员账号是否已创建，
 * 未创建则跳转到 /{locale}/setup 初始化页面
 *
 * 单飞 Promise：仅复用进行中的请求（防 StrictMode/并发重复调用），
 * 请求完成后立即失效，保证下次拿到最新状态
 */
let inflight: Promise<unknown> | null = null;

function fetchStatus(): Promise<unknown> {
  if (!inflight) {
    inflight = get<unknown>("/auth/setup-status").finally(() => {
      inflight = null;
    });
  }
  return inflight;
}

export function SetupGuard() {
  const router = useRouter();
  const pathname = usePathname();
  const locale = useLocale();

  useEffect(() => {
    // 初始化页面自身不触发跳转，避免死循环
    if (stripLocale(pathname) === "/setup") return;
    let cancelled = false;
    fetchStatus()
      .then((data) => {
        if (!cancelled && needsSetup(data)) {
          router.replace(`/${locale}/setup`);
        }
      })
      .catch(() => {
        // 接口异常（如后端未就绪）时不阻塞正常使用
      });
    return () => {
      cancelled = true;
    };
  }, [pathname, router, locale]);

  return null;
}
