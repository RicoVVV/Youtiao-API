"use client";

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { getToken } from "@/lib/request";
import { LocaleLink } from "@/components/locale-link";

/** 页脚登录入口：已登录时隐藏（控制台入口已存在） */
export function FooterLoginLink() {
  const [loggedIn, setLoggedIn] = useState(false);
  const { t } = useTranslation("home");

  // 令牌存于 localStorage，仅客户端可读
  useEffect(() => setLoggedIn(!!getToken()), []);

  if (loggedIn) return null;

  return (
    <LocaleLink href="/login" className="transition-colors hover:text-foreground">
      {t("footer.login")}
    </LocaleLink>
  );
}
