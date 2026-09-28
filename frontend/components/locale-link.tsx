"use client";

import Link, { type LinkProps } from "next/link";
import { useParams } from "next/navigation";
import { isLocale } from "@/i18n/config";

/**
 * 自动为站内路径补上当前 locale 前缀的 Link。
 * 迁移期安全：外链、hash、已带前缀的路径原样透传。
 */
export function LocaleLink({
  href,
  ...rest
}: LinkProps & React.AnchorHTMLAttributes<HTMLAnchorElement>) {
  const params = useParams<{ locale?: string }>();
  const locale = params?.locale;

  const resolved =
    typeof href === "string" &&
    href.startsWith("/") &&
    !href.match(/^\/(zh|en)(\/|$)/) &&
    locale &&
    isLocale(locale)
      ? `/${locale}${href}`
      : href;

  return <Link href={resolved} {...rest} />;
}
