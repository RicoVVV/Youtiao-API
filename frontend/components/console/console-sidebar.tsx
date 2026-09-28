"use client";

import { usePathname, useParams } from "next/navigation";
import {
  Activity,
  BarChart3,
  BellRing,
  Clapperboard,
  Cpu,
  KeyRound,
  Layers,
  LayoutDashboard,
  MessageSquare,
  Receipt,
  ScrollText,
  Settings,
  Ticket,
  UserRound,
  Users,
  Waypoints,
  ChartScatter,
} from "lucide-react";

import { useTranslation } from "react-i18next";

import { cn } from "@/lib/utils";
import { useEffect, useState } from "react";
import { get, getCachedProfile, getToken, setCachedProfile } from "@/lib/request";
import { stripLocale } from "@/lib/path-utils";
import { isLocale } from "@/i18n/config";
import { LocaleLink } from "@/components/locale-link";

/** 鎺у埗鍙拌彍鍗曪細鍒嗙粍閰嶇疆 */
const MENU_GROUPS = [
   {
    titleKey: "nav.chat",
    items: [
      { href: "/console/playground", labelKey: "nav.playground", icon: MessageSquare },
      { href: "/console/canvas", labelKey: "nav.canvas", icon: ChartScatter },
    ],
  },
  {
    titleKey: "nav.general",
    items: [
      { href: "/console/usage", labelKey: "nav.usage", icon: BarChart3 },
      { href: "/console/monitoring", labelKey: "nav.monitoring", icon: Activity },
      { href: "/console/api-keys", labelKey: "nav.apiKeys", icon: KeyRound },
      { href: "/console/usage-records", labelKey: "nav.usageRecords", icon: ScrollText },
    ],
  },
  {
    titleKey: "nav.account",
    items: [
      { href: "/console/billing", labelKey: "nav.billing", icon: Receipt },
      { href: "/console/profile", labelKey: "nav.profile", icon: UserRound },
    ],
  },
  {
    titleKey: "nav.admin",
    adminOnly: true,
    items: [
      { href: "/console/users", labelKey: "nav.users", icon: Users },
      { href: "/console/groups", labelKey: "nav.groups", icon: Layers },
      { href: "/console/models", labelKey: "nav.models", icon: Cpu },
      { href: "/console/channels", labelKey: "nav.channels", icon: Waypoints },
      { href: "/console/monitoring-admin", labelKey: "nav.monitoringAdmin", icon: BellRing },
      { href: "/console/redemption-codes", labelKey: "nav.redemptionCodes", icon: Ticket },
      { href: "/system", labelKey: "nav.systemSettings", icon: Settings },
    ],
  },
];

export function ConsoleSidebar() {
  const { t } = useTranslation("console");
  const pathname = usePathname();
  const params = useParams<{ locale?: string }>();
  const locale = params?.locale && isLocale(params.locale) ? params.locale : "zh";
  const bare = stripLocale(pathname);
  // mounted 鍓嶄笉娓叉煋瑙掕壊鐩稿叧鍒嗙粍锛氬垵濮嬪€煎繀椤讳笌鏈嶅姟绔覆鏌撲竴鑷达紝閬垮厤姘村悎涓嶅尮閰?
  const [mounted, setMounted] = useState(false);
  const [isAdmin, setIsAdmin] = useState(false);

  // 姘村悎鍚庡厛璇?localStorage 缂撳瓨锛岄伩鍏嶅垏鍏ユ帶鍒跺彴鏃?绠＄悊鍛?鍒嗙粍闂儊
  useEffect(() => {
    setIsAdmin(getCachedProfile()?.is_admin ?? false);
    setMounted(true);
  }, []);

  // 鎷夊彇褰撳墠鐢ㄦ埛淇℃伅鏍″噯瑙掕壊锛屼粎绠＄悊鍛樺彲瑙?绠＄悊鍛?鍒嗙粍
  useEffect(() => {
    if (!getToken()) return;
    get<{ username: string; is_admin: boolean }>("/user/info")
      .then((p) => {
        setIsAdmin(p.is_admin);
        setCachedProfile({ username: p.username, is_admin: p.is_admin });
      })
      .catch(() => {});
  }, []);

  const groups = MENU_GROUPS.filter(
    (g) => !("adminOnly" in g) || (mounted && isAdmin)
  );

  return (
    <aside className="fixed bottom-0 left-0 top-14 z-40 flex w-60 flex-col border-r border-border bg-background/80 text-foreground backdrop-blur-sm">
      {/* 鑿滃崟鍖?*/}
      <nav className="flex-1 space-y-6 overflow-y-auto px-3 py-5">
        {groups.map((group) => (
          <div key={group.titleKey}>
            <p className="mb-1.5 px-3 text-[11px] font-medium uppercase tracking-wider text-muted-foreground/70">
              {t(group.titleKey)}
            </p>
            <ul className="space-y-1">
              {group.items.map((item) => {
                const active =
                  item.href === "/console"
                    ? bare === "/console"
                    : bare === item.href ||
                      bare.startsWith(item.href + "/");
                return (
                  <li key={item.href}>
                    <LocaleLink
                      href={item.href}
                      aria-current={active ? "page" : undefined}
                      className={cn(
                        "group relative flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm text-muted-foreground transition-all duration-200 hover:bg-accent/60 hover:text-foreground",
                        active &&
                          "bg-accent font-medium text-accent-foreground shadow-sm"
                      )}
                    >
                      {/* 閫変腑鎬佸乏渚ф寚绀烘潯 */}
                      <span
                        className={cn(
                          "absolute left-0 top-1/2 h-4 w-[3px] -translate-y-1/2 rounded-full bg-gradient-to-b from-[#4c6fff] to-[#7c5cff] transition-all duration-200",
                          active
                            ? "opacity-100"
                            : "opacity-0 group-hover:opacity-40"
                        )}
                      />
                      <item.icon
                        className={cn(
                          "size-4 shrink-0 transition-colors",
                          active && "text-primary"
                        )}
                      />
                      {t(item.labelKey)}
                    </LocaleLink>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>
    </aside>
  );
}
