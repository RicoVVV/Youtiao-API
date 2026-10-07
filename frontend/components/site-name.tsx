"use client";

import { usePublicSystemSettings } from "@/lib/use-system-settings";

/** 站点名称文本：使用公开系统设置中的 system_name，未加载时显示默认名称 */
export function SiteName({ fallback = "Youtiao API" }: { fallback?: string }) {
  const settings = usePublicSystemSettings();
  return <>{settings?.system_name || fallback}</>;
}
