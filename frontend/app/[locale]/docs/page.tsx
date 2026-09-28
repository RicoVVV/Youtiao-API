import type { Metadata } from "next";

import { DocsExplorer } from "@/components/api-docs/docs-explorer";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";
import { getServerT } from "@/i18n/server";
import { isLocale, type Locale } from "@/i18n/config";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const { locale: rawLocale } = await params;
  const locale: Locale = isLocale(rawLocale) ? rawLocale : "zh";
  const { t } = await getServerT(locale, "api-docs");
  return {
    title: t("meta.title"),
    description: t("meta.description"),
  };
}

export default async function DocsPage() {
  return (
    <>
      <SiteHeader />
      <main className="flex-1">
        <div className="px-4 py-8 sm:px-6 lg:px-8">
          <DocsExplorer />
        </div>
      </main>
      <SiteFooter />
    </>
  );
}
