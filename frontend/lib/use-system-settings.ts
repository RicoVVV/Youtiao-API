"use client";

import { useEffect, useState } from "react";

import { getPublicSystemSettings, type SystemSettings } from "@/lib/system-settings";

/** 站点级公开设置缓存（同页多组件共享一次请求） */
let cache: SystemSettings | null = null;
let inflight: Promise<SystemSettings> | null = null;

/** 使公开设置缓存失效：管理员保存后调用，公开组件下次挂载时重新拉取 */
export function invalidatePublicSystemSettingsCache() {
  cache = null;
}

export function usePublicSystemSettings() {
  const [settings, setSettings] = useState<SystemSettings | null>(cache);

  useEffect(() => {
    if (cache) return;
    if (!inflight) {
      inflight = getPublicSystemSettings().finally(() => {
        inflight = null;
      });
    }
    inflight
      .then((data) => {
        cache = data;
        setSettings(data);
      })
      .catch(() => {
        // 公开设置失败时保持默认占位，不阻塞页面
      });
  }, []);

  return settings;
}
