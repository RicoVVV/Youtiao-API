import { NextRequest, NextResponse } from "next/server";
import { defaultLocale, locales, isLocale } from "@/i18n/config";

/** 与 lib/request.ts 中 setToken 写入的 Cookie 名保持一致 */
const TOKEN_COOKIE = "token";
const PUBLIC_FILE = /\.[^/]+$/;

/**
 * 路由守卫 + locale 前缀管理：
 * - 无 locale 前缀的路径 → 重定向到默认语言
 * - 未登录访问受保护页面 → 重定向到登录页（带 locale 前缀）
 * - 已登录访问 /login → 重定向到控制台
 */
export function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;

  // 跳过静态资源与 API
  if (
    pathname.startsWith("/api") ||
    pathname.startsWith("/v1") ||
    pathname.startsWith("/_next") ||
    PUBLIC_FILE.test(pathname)
  ) {
    return NextResponse.next();
  }

  // 已带合法 locale 前缀
  const seg = pathname.split("/")[1] ?? "";
  const hasLocale = isLocale(seg);

  if (!hasLocale) {
    // 根路径或无前缀 → 重定向到默认语言，保留原路径
    const url = req.nextUrl.clone();
    url.pathname = `/${defaultLocale}${pathname === "/" ? "" : pathname}`;
    return NextResponse.redirect(url);
  }

  const locale = seg;
  const rest = pathname.slice(locale.length + 1) || "/";
  const token = req.cookies.get(TOKEN_COOKIE)?.value;

  // 个人资料与钱包需要登录；系统设置还需要管理员权限，具体角色由页面/API 校验
  if ((rest.startsWith("/console") || rest === "/system/settings") && !token) {
    const url = new URL(`/${locale}/login`, req.url);
    url.searchParams.set("redirect", pathname);
    return NextResponse.redirect(url);
  }
  if (rest === "/login" && token) {
    return NextResponse.redirect(new URL(`/${locale}/console`, req.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!api|v1|_next|.*\\..*).*)"],
};
