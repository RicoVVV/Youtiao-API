import type { Metadata } from "next";

import { SetupPanel } from "@/components/auth/setup-panel";
import { isLocale, type Locale } from "@/i18n/config";
import { getServerT } from "@/i18n/server";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const { locale: rawLocale } = await params;
  const locale: Locale = isLocale(rawLocale) ? rawLocale : "zh";
  const { t } = await getServerT(locale, "auth");
  return {
    title: t("setupMetaTitle"),
    description: t("setupMetaDescription"),
  };
}

export default function SetupPage() {
  return <SetupPanel />;
}
