import type { Metadata } from "next";
import { Suspense } from "react";

import { AuthPanel } from "@/components/auth/auth-panel";
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
    title: t("metaTitle"),
    description: t("metaDescription"),
  };
}

export default function LoginPage() {
  return (
    <Suspense>
      <AuthPanel />
    </Suspense>
  );
}
