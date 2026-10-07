import { defaultLocale, isLocale, type Locale } from "./config";

export const LOCALE_COOKIE = "NEXT_LOCALE";
const ONE_YEAR = 60 * 60 * 24 * 365;

/** 服务端（Server Component / middleware 外）读取语言 cookie */
export function getLocaleFromCookieHeader(
  cookieHeader: string | null
): Locale | undefined {
  if (!cookieHeader) return undefined;
  const match = cookieHeader.match(new RegExp(`(?:^|;\\s*)${LOCALE_COOKIE}=([^;]+)`));
  const value = match?.[1];
  return value && isLocale(value) ? value : undefined;
}

/** 客户端写入语言 cookie（配合路由跳转生效） */
export function setLocaleCookie(locale: Locale = defaultLocale) {
  if (typeof document === "undefined") return;
  document.cookie = `${LOCALE_COOKIE}=${locale}; path=/; max-age=${ONE_YEAR}; samesite=lax`;
}
