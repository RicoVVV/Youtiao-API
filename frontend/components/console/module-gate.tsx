"use client";

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { useTranslation } from "react-i18next";
import { ShieldOff } from "lucide-react";

import { LocaleLink } from "@/components/locale-link";
import { Button } from "@/components/ui/button";
import { moduleKeyFromPath } from "@/lib/sidebar-modules";
import { useSidebarModules } from "@/lib/use-sidebar-modules";
import { get, getCachedProfile, getToken, setCachedProfile } from "@/lib/request";
import { stripLocale } from "@/lib/path-utils";

/**
 * 模块门禁：当前路由对应的侧边栏模块被管理员隐藏时，
 * 非管理员看到的是「功能已关闭」提示而非页面内容（其接口本就会返回 403）。
 * 管理员豁免拦截，仅隐藏菜单，不阻断页面。
 */
export function ModuleGate({ children }: { children: React.ReactNode }) {
  const { t } = useTranslation("console");
  const pathname = usePathname();
  const visibleModules = useSidebarModules();
  // 惰性初始化读取缓存，避免水合后再 setState 造成级联渲染
  const [isAdmin, setIsAdmin] = useState(
    () => getCachedProfile()?.is_admin ?? false
  );

  // 拉取当前用户信息校准角色（与侧边栏同一数据源）
  useEffect(() => {
    if (!getToken()) return;
    get<{ username: string; is_admin: boolean }>("/user/info")
      .then((p) => {
        setIsAdmin(p.is_admin);
        setCachedProfile({ username: p.username, is_admin: p.is_admin });
      })
      .catch(() => {});
  }, []);

  const moduleKey = moduleKeyFromPath(stripLocale(pathname));
  const blocked =
    !isAdmin &&
    moduleKey !== null &&
    visibleModules !== null &&
    !visibleModules.includes(moduleKey);

  if (blocked) {
    return (
      <div className="flex min-h-[60vh] flex-col items-center justify-center gap-4 text-center">
        <ShieldOff className="size-10 text-muted-foreground/60" />
        <div className="space-y-1.5">
          <p className="text-lg font-medium">{t("sidebarModules.disabledTitle")}</p>
          <p className="text-sm text-muted-foreground">
            {t("sidebarModules.disabledDesc")}
          </p>
        </div>
        <LocaleLink href="/console">
          <Button variant="outline">{t("sidebarModules.backToConsole")}</Button>
        </LocaleLink>
      </div>
    );
  }

  return <>{children}</>;
}
