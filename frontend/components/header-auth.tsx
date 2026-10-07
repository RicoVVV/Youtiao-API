"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { LogOut, Receipt, Settings, ShieldCheck, UserRound } from "lucide-react";

import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { toast } from "@/components/ui/toaster";
import {
  clearToken,
  get,
  getCachedUsername,
  getToken,
  post,
  setCachedProfile,
  setCachedUsername,
} from "@/lib/request";
import { useLocale } from "@/i18n/client";
import { LocaleLink } from "@/components/locale-link";

type Profile = {
  id: string;
  username: string;
  is_active: boolean;
  is_admin: boolean;
  created_at: string;
};

export function HeaderAuth() {
  const router = useRouter();
  const locale = useLocale();
  const { t } = useTranslation("home");
  // mounted 前渲染中立骨架占位（与服务端 HTML 一致，避免水合不匹配），
  // 挂载后若有令牌立即用缓存用户名渲染头像，不再闪"登录/注册"按钮
  const [mounted, setMounted] = useState(false);
  const [loggedIn, setLoggedIn] = useState(false);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  // 令牌存于 localStorage，仅客户端可读；登录后拉取用户信息校准头像与角色
  useEffect(() => {
    setMounted(true);
    if (!getToken()) return;
    setLoggedIn(true);
    const cached = getCachedUsername();
    if (cached) {
      setProfile({
        id: "",
        username: cached,
        is_active: true,
        is_admin: false,
        created_at: "",
      });
    }
    get<Profile>("/user/info")
      .then((data) => {
        setProfile(data);
        setCachedUsername(data.username);
        setCachedProfile({ username: data.username, is_admin: data.is_admin });
      })
      .catch(() => {});
  }, []);

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

  const onLogout = async () => {
    try {
      await post("/auth/logout");
    } catch {
      // 接口失败也照常清空本地登录态
    }
    clearToken();
    setProfile(null);
    setLoggedIn(false);
    setOpen(false);
    toast.success(t("auth.logoutSuccess"));
    router.push(`/${locale}`);
    router.refresh();
  };

  // 未挂载（SSR/水合中）或已登录但资料未返回：渲染骨架占位，避免闪烁登录按钮
  if (!mounted || (loggedIn && !profile)) {
    return (
      <span className="size-8 animate-pulse rounded-full bg-muted" aria-hidden />
    );
  }

  if (!profile) {
    return (
      <>
        <Button variant="ghost" size="sm" asChild>
          <LocaleLink href="/login">{t("auth.login")}</LocaleLink>
        </Button>
        <Button size="sm" asChild>
          <LocaleLink href="/login?mode=register">{t("auth.register")}</LocaleLink>
        </Button>
      </>
    );
  }

  return (
    <div ref={menuRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-label={t("auth.accountMenu")}
        className="flex cursor-pointer rounded-full transition-shadow hover:ring-2 hover:ring-primary/30"
      >
        <span className="flex size-8 items-center justify-center rounded-full bg-primary text-sm font-semibold text-primary-foreground">
          {profile.username.charAt(0).toUpperCase()}
        </span>
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-2 w-60 overflow-hidden rounded-xl border bg-background shadow-lg">
          {/* 用户信息头 */}
          <div className="flex items-center gap-3 border-b px-4 py-3.5">
            <span className="flex size-9 shrink-0 items-center justify-center rounded-md bg-primary/15 text-sm font-semibold text-primary">
              {profile.username.charAt(0).toUpperCase()}
            </span>
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold">{profile.username}</p>
              <span
                className={`mt-0.5 inline-flex items-center gap-1 rounded px-1.5 py-px text-[11px] leading-4 ${
                  profile.is_admin
                    ? "bg-primary/10 text-primary"
                    : "bg-muted text-muted-foreground"
                }`}
              >
                {profile.is_admin ? (
                  <ShieldCheck className="size-3" />
                ) : (
                  <UserRound className="size-3" />
                )}
                {profile.is_admin ? t("auth.admin") : t("auth.user")}
              </span>
            </div>
          </div>
          {/* 操作项 */}
          <div className="p-1.5">
            <LocaleLink
              href="/console/profile"
              onClick={() => setOpen(false)}
              className="flex w-full items-center gap-2.5 rounded-md px-2.5 py-2 text-sm transition-colors hover:bg-muted"
            >
              <UserRound className="size-4 text-muted-foreground" />
              {t("auth.profile")}
            </LocaleLink>
            <LocaleLink
              href="/console/billing"
              onClick={() => setOpen(false)}
              className="flex w-full items-center gap-2.5 rounded-md px-2.5 py-2 text-sm transition-colors hover:bg-muted"
            >
              <Receipt className="size-4 text-muted-foreground" />
              {t("auth.wallet")}
            </LocaleLink>
            {profile.is_admin && (
              <LocaleLink
                href="/system/settings"
                onClick={() => setOpen(false)}
                className="flex w-full items-center gap-2.5 rounded-md px-2.5 py-2 text-sm transition-colors hover:bg-muted"
              >
                <Settings className="size-4 text-muted-foreground" />
                {t("auth.systemSettings")}
              </LocaleLink>
            )}
            <button
              type="button"
              onClick={onLogout}
              className="flex w-full cursor-pointer items-center gap-2.5 rounded-md px-2.5 py-2 text-sm transition-colors hover:bg-muted"
            >
              <LogOut className="size-4 text-muted-foreground" />
              {t("auth.logout")}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
