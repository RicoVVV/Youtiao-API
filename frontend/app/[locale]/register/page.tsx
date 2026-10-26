import { redirect } from "next/navigation";

import { isLocale, type Locale } from "@/i18n/config";

/**
 * 注册页兼容入口：邀请链接格式为 {server_url}/register?aff={aff_code}，
 * 实际注册复用 /login?mode=register 页面，此处原样转发查询参数。
 */
export default async function RegisterPage({
  params,
  searchParams,
}: {
  params: Promise<{ locale: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { locale: rawLocale } = await params;
  const locale: Locale = isLocale(rawLocale) ? rawLocale : "en";
  const query = await searchParams;

  // 强制注册模式，并透传 aff / aff_code 等邀请参数
  const qs = new URLSearchParams();
  qs.set("mode", "register");
  for (const [key, value] of Object.entries(query)) {
    if (key === "mode" || value === undefined) continue;
    if (Array.isArray(value)) {
      value.forEach((v) => qs.append(key, v));
    } else {
      qs.set(key, value);
    }
  }

  redirect(`/${locale}/login?${qs.toString()}`);
}
