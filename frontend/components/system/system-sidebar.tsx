"use client";

import { usePathname, useParams } from "next/navigation";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  ArrowLeft,
  ChevronRight,
  CreditCard,
  FileText,
  Route,
  Settings,
  Shield,
  ShieldCheck,
  Wrench,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { stripLocale } from "@/lib/path-utils";
import { isLocale } from "@/i18n/config";
import { LocaleLink } from "@/components/locale-link";

/** 系统管理菜单：父级可展开/收起 */
const MENU_ITEMS = [
  {
    key: "branding",
    icon: Settings,
    children: [{ href: "/system/settings", labelKey: "settings" }],
  },
  {
    key: "auth",
    icon: ShieldCheck,
    children: [{ href: "/system/auth", labelKey: "emailVerification" }],
  },
  {
    key: "billing",
    icon: CreditCard,
    children: [
      { href: "/system/payment-gateway", labelKey: "paymentGateway" },
      { href: "/system/payment-records", labelKey: "paymentRecords" },
    ],
  },
  { key: "models", icon: Route, children: [] },
  { key: "security", icon: Shield, children: [] },
  { key: "consoleContent", icon: FileText, children: [] },
  { key: "ops", icon: Wrench, children: [] },
] as const;

export function SystemSidebar() {
  const { t } = useTranslation("console");
  const pathname = usePathname();
  const params = useParams<{ locale?: string }>();
  const locale = params?.locale && isLocale(params.locale) ? params.locale : "zh";
  const bare = stripLocale(pathname);
  const [expanded, setExpanded] = useState<Set<string>>(
    // 默认展开包含当前激活子菜单的父级
    () =>
      new Set(
        MENU_ITEMS.filter((item) =>
          item.children.some(
            (c) =>
              bare === c.href || bare.startsWith(c.href + "/")
          )
        ).map((item) => item.key)
      )
  );

  const toggle = (key: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  };

  return (
    <aside className="fixed bottom-0 left-0 top-14 z-40 flex w-60 flex-col border-r border-border bg-background/80 text-foreground backdrop-blur-sm">
      {/* 返回控制台 */}
      <div className="border-b border-border px-3 py-3">
        <LocaleLink
          href="/console"
          className="flex items-center gap-2 rounded-lg px-3 py-2 text-sm text-muted-foreground transition-colors hover:bg-accent/60 hover:text-foreground"
        >
          <ArrowLeft className="size-4 shrink-0" />
          {t("systemSidebar.back")}
        </LocaleLink>
      </div>

      {/* 菜单区 */}
      <nav className="flex-1 overflow-y-auto px-3 py-5">
        <p className="mb-1.5 px-3 text-[11px] font-medium uppercase tracking-wider text-muted-foreground/70">
          {t("systemSidebar.section")}
        </p>
        <ul className="space-y-1">
          {MENU_ITEMS.map((item) => {
            const isExpanded = expanded.has(item.key);
            return (
              <li key={item.key}>
                <button
                  type="button"
                  onClick={() => toggle(item.key)}
                  aria-expanded={isExpanded}
                  className="group flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-sm text-muted-foreground transition-all duration-200 hover:bg-accent/60 hover:text-foreground"
                >
                  <item.icon className="size-4 shrink-0" />
                  <span className="flex-1 text-left">{t(`systemSidebar.${item.key}`)}</span>
                  <ChevronRight
                    className={cn(
                      "size-4 shrink-0 text-muted-foreground/60 transition-transform duration-200",
                      isExpanded && "rotate-90"
                    )}
                  />
                </button>
                {isExpanded && item.children.length > 0 && (
                  <ul className="mt-1 space-y-1">
                    {item.children.map((child) => {
                      const active =
                        bare === child.href ||
                        bare.startsWith(child.href + "/");
                      return (
                        <li key={child.href}>
                          <LocaleLink
                            href={child.href}
                            aria-current={active ? "page" : undefined}
                            className={cn(
                              "group relative flex items-center gap-2.5 rounded-lg py-2 pl-6 pr-3 text-sm transition-all duration-200",
                              active
                                ? "bg-accent font-medium text-primary shadow-sm"
                                : "text-muted-foreground hover:bg-accent/60 hover:text-foreground"
                            )}
                          >
                            {t(`systemSidebar.${child.labelKey}`)}
                          </LocaleLink>
                        </li>
                      );
                    })}
                  </ul>
                )}
              </li>
            );
          })}
        </ul>
      </nav>
    </aside>
  );
}
