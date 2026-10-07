"use client";

import { useEffect, useState } from "react";
import { ArrowRight } from "lucide-react";

import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { getToken } from "@/lib/request";
import { LocaleLink } from "@/components/locale-link";

/** 登录态感知的 CTA：未登录引导注册，已登录改为进入控制台 */
export function AuthCta({
  label,
  variant,
  className,
}: {
  /** 未登录态的按钮文案 */
  label: string;
  variant?: "default" | "secondary";
  className?: string;
}) {
  const [loggedIn, setLoggedIn] = useState(false);
  const { t } = useTranslation("home");

  // 令牌存于 localStorage，仅客户端可读
  useEffect(() => setLoggedIn(!!getToken()), []);

  return (
    <Button size="lg" variant={variant} className={className} asChild>
      <LocaleLink href={loggedIn ? "/console" : "/login?mode=register"}>
        {loggedIn ? t("auth.enterConsole") : label} <ArrowRight className="size-4" />
      </LocaleLink>
    </Button>
  );
}
