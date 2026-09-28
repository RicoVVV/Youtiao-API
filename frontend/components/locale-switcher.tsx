"use client";

import { useEffect, useRef, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useTranslation } from "react-i18next";
import { Check, Globe } from "lucide-react";

import { cn } from "@/lib/utils";
import { isLocale, locales, type Locale } from "@/i18n/config";
import { setLocaleCookie } from "@/i18n/settings";
import { beginLocaleTransition } from "@/i18n/transition";

/** 语言切换：图标按钮 + 下拉菜单，更新 URL 前缀 + cookie 并刷新服务端组件 */
export function LocaleSwitcher() {
  const router = useRouter();
  const pathname = usePathname();
  const { t, i18n } = useTranslation("common");
  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  const seg = pathname.split("/")[1] ?? "";
  const current: Locale = isLocale(seg) ? seg : "zh";

  // 点击菜单外部时收起下拉
  useEffect(() => {
    const onClickOutside = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, []);

  const switchTo = async (next: Locale) => {
    setOpen(false);
    if (next === current) return;
    const rest = pathname.replace(/^\/(zh|en)/, "");
    beginLocaleTransition();
    try {
      // 预加载目标语言资源，避免切换后内容闪烁
      await i18n.loadLanguages(next);
    } finally {
      setLocaleCookie(next);
      // push 到不同 locale 前缀已会重渲染该 segment，无需再 refresh；scroll:false 保持滚动位置
      router.push(`/${next}${rest}`, { scroll: false });
    }
  };

  return (
    <div ref={menuRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-label={t("language.label")}
        suppressHydrationWarning
        className="relative flex size-8 cursor-pointer items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
      >
        <Globe className="size-4" />
        {/* 当前语言角标 */}
        <span className="absolute -bottom-0.5 -right-1.5 rounded-sm border bg-background px-0.5 text-[9px] font-semibold leading-3 text-muted-foreground">
          {current === "zh" ? "中" : "EN"}
        </span>
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-2 w-36 overflow-hidden rounded-xl border bg-background shadow-lg">
          <div className="p-1.5">
            {locales.map((l) => (
              <button
                key={l}
                type="button"
                onClick={() => switchTo(l)}
                aria-current={l === current ? "true" : undefined}
                className={cn(
                  "flex w-full cursor-pointer items-center justify-between rounded-md px-2.5 py-2 text-sm text-muted-foreground transition-colors hover:bg-muted hover:text-foreground",
                  l === current && "font-medium text-foreground"
                )}
              >
                {t(`language.${l}`)}
                {l === current && <Check className="size-4 text-primary" />}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
