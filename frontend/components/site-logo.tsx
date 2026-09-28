"use client";

import Image from "next/image";
import { useState } from "react";

import { cn } from "@/lib/utils";
import { usePublicSystemSettings } from "@/lib/use-system-settings";

const DEFAULT_LOGO = "/youtiao.svg";

/** 站点 Logo 图标：优先使用系统设置的徽标，未设置或加载失败时回退默认图标 */
export function SiteLogo({ className }: { className?: string }) {
  const settings = usePublicSystemSettings();
  const [failed, setFailed] = useState(false);
  const src = !failed && settings?.logo_url ? settings.logo_url : DEFAULT_LOGO;

  return (
    <Image
      src={src}
      alt={settings?.system_name || "站点 Logo"}
      width={28}
      height={28}
      className={cn("size-7", className)}
      priority
      unoptimized={src !== DEFAULT_LOGO}
      onError={() => setFailed(true)}
    />
  );
}
