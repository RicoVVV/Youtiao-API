"use client";

import { usePathname } from "next/navigation";
import { useTranslation } from "react-i18next";

import { cn } from "@/lib/utils";
import { LocaleLink } from "@/components/locale-link";
import { stripLocale } from "@/lib/path-utils";

const navItems = [
  { href: "/", key: "nav.home" },
  { href: "/console", key: "nav.console" },
  { href: "/models", key: "nav.models" },
  { href: "/docs", key: "nav.docs" },
];

export function MainNav() {
  const pathname = usePathname();
  const bare = stripLocale(pathname);
  const { t } = useTranslation("home");

  return (
    <nav className="hidden items-center gap-1 rounded-full border bg-background/60 p-1 text-sm shadow-sm md:flex">
      {navItems.map((item) => {
        // 锚点链接（/#xxx）不参与选中态；控制台子路径保持选中
        const active =
          !item.href.includes("#") &&
          (item.href === "/console"
            ? bare.startsWith("/console") || bare.startsWith("/system")
            : bare === item.href);
        return (
          <LocaleLink
            key={item.href}
            href={item.href}
            aria-current={active ? "page" : undefined}
            className={cn(
              "rounded-full px-4 py-1.5 text-muted-foreground transition-all duration-200 hover:text-foreground",
              active &&
                "bg-accent font-medium text-accent-foreground shadow-sm"
            )}
          >
            {t(item.key)}
          </LocaleLink>
        );
      })}
    </nav>
  );
}
