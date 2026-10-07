import type { Metadata } from "next";

import { ModelExplorer } from "@/components/models/model-explorer";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";
import { Badge } from "@/components/ui/badge";
import { getServerT } from "@/i18n/server";
import { isLocale, type Locale } from "@/i18n/config";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const { locale: rawLocale } = await params;
  const locale: Locale = isLocale(rawLocale) ? rawLocale : "zh";
  const { t } = await getServerT(locale, "models");
  return {
    title: t("meta.title"),
    description: t("meta.description"),
  };
}

export default async function ModelsPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale: rawLocale } = await params;
  const locale: Locale = isLocale(rawLocale) ? rawLocale : "zh";
  const { t } = await getServerT(locale, "models");

  return (
    <>
      <SiteHeader />
      <main className="flex-1">
        {/* 页头：极光背景 + 数据条 */}
        <section className="relative overflow-hidden border-b">
          <div className="animate-float-a absolute -left-24 -top-24 size-72 rounded-full bg-[#4c6fff]/15 blur-3xl" />
          <div className="animate-float-b absolute -right-24 top-10 size-72 rounded-full bg-[#129dc2]/15 blur-3xl" />
          <div className="bg-grid absolute inset-0 opacity-60 [mask-image:radial-gradient(ellipse_70%_60%_at_50%_0%,black,transparent)]" />

          <div className="relative mx-auto max-w-6xl px-4 py-14 text-center sm:px-6">
            <Badge variant="secondary" className="mx-auto mb-4">
              {t("hero.badge")}
            </Badge>
            <h1 className="text-4xl font-bold tracking-tight">
              <span className="text-gradient">{t("hero.titlePrefix")}</span>{t("hero.titleSuffix")}
            </h1>
            <p className="mx-auto mt-3 max-w-xl text-muted-foreground">
              {t("hero.subtitle")}
            </p>
            <div className="mt-6 flex flex-wrap items-center justify-center gap-2 font-mono text-xs text-muted-foreground">
              <span className="rounded-full border bg-card px-3 py-1.5">
                {t("hero.tag1")}
              </span>
              <span className="rounded-full border bg-card px-3 py-1.5">
                {t("hero.tag2")}
              </span>
            </div>
          </div>
        </section>

        <div className="mx-auto max-w-6xl px-4 py-10 sm:px-6">
          <ModelExplorer />
        </div>
      </main>
      <SiteFooter />
    </>
  );
}
