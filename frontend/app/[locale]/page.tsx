import { LocaleLink } from "@/components/locale-link";
import {
  ArrowRight,
  Gauge,
  KeyRound,
  Layers,
  ShieldCheck,
  Wallet,
  Zap,
} from "lucide-react";

import { Reveal } from "@/components/reveal";
import { AuthCta } from "@/components/home/auth-cta";
import { StatsPanel } from "@/components/home/stats-panel";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { getServerT } from "@/i18n/server";
import { isLocale, type Locale } from "@/i18n/config";

const FEATURE_ICONS = [Layers, Gauge, Wallet, ShieldCheck];
const STEP_ICONS = [Zap, KeyRound, ArrowRight];

export default async function HomePage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale: rawLocale } = await params;
  const locale: Locale = isLocale(rawLocale) ? rawLocale : "zh";
  const { t } = await getServerT(locale, "home");

  const features = FEATURE_ICONS.map((icon, i) => ({
    icon,
    title: t(`features.items.${i}.title`),
    description: t(`features.items.${i}.description`),
  }));

  const steps = STEP_ICONS.map((icon, i) => ({
    icon,
    title: t(`quickstart.steps.${i}.title`),
    description: t(`quickstart.steps.${i}.description`),
  }));

  return (
    <>
      <SiteHeader />

      <main className="flex-1">
        {/* Hero */}
        <section className="relative overflow-hidden">
          {/* 极光流体背景 */}
          <div className="animate-float-a absolute -left-32 -top-16 size-96 rounded-full bg-[#4c6fff]/20 blur-3xl" />
          <div className="animate-float-b absolute -right-32 top-40 size-[26rem] rounded-full bg-[#129dc2]/20 blur-3xl" />
          <div className="animate-float-a absolute left-1/3 top-72 size-80 rounded-full bg-[#7c5cff]/15 blur-3xl [animation-delay:2s]" />
          <div className="bg-grid absolute inset-0 [mask-image:radial-gradient(ellipse_60%_50%_at_50%_0%,black,transparent)]" />
          <div className="relative mx-auto max-w-6xl px-4 pb-16 pt-20 text-center sm:px-6 sm:pt-28">
            <Reveal>
              <Badge variant="secondary" className="mx-auto mb-6">
                {t("hero.badge")}
              </Badge>
              <h1 className="mx-auto max-w-3xl text-4xl font-semibold tracking-tight text-foreground/90 sm:text-5xl lg:text-6xl">
                {t("hero.titleLine1")}
                <br />
                <span className="text-gradient relative mt-2 inline-block pb-2 text-5xl font-bold sm:text-6xl lg:text-7xl">
                  {t("hero.titleHighlight")}
                  <span
                    aria-hidden
                    className="absolute inset-0 -z-10 bg-gradient-to-r from-[#4c6fff]/25 via-[#7c5cff]/25 to-[#129dc2]/25 blur-2xl"
                  />
                </span>
              </h1>
              {/* 标题下方渐变光带 */}
              <div
                aria-hidden
                className="mx-auto mt-3 h-px w-56 bg-gradient-to-r from-transparent via-[#7c5cff]/70 to-transparent sm:w-72"
              />
            </Reveal>
            <Reveal delay={120}>
              <p className="mx-auto mt-6 max-w-xl text-base text-muted-foreground sm:text-lg">
                {t("hero.subtitle")}
              </p>
            </Reveal>
            <Reveal delay={240}>
              <div className="mt-8 flex items-center justify-center gap-3">
                <AuthCta label={t("hero.ctaPrimary")} />
                <Button size="lg" variant="outline" asChild>
                  <LocaleLink href="/models">{t("hero.ctaSecondary")}</LocaleLink>
                </Button>
              </div>
            </Reveal>

            {/* 实时数据面板 */}
            <Reveal delay={360}>
              <StatsPanel />
            </Reveal>
          </div>
        </section>

        {/* 特性 */}
        <section id="features" className="border-t bg-muted/40 py-20">
          <div className="mx-auto max-w-6xl px-4 sm:px-6">
            <Reveal className="mx-auto max-w-2xl text-center">
              <h2 className="text-3xl font-bold tracking-tight">{t("features.title")}</h2>
              <p className="mt-3 text-muted-foreground">
                {t("features.subtitle")}
              </p>
            </Reveal>
            <div className="mt-12 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
              {features.map((feature, index) => (
                <Reveal key={index} delay={index * 90} className="h-full">
                  <Card className="card-hover h-full">
                    <CardHeader>
                      <span className="mb-2 flex size-10 items-center justify-center rounded-lg bg-accent text-accent-foreground">
                        <feature.icon className="size-5" />
                      </span>
                      <CardTitle className="text-base">{feature.title}</CardTitle>
                      <CardDescription
                        className="line-clamp-4"
                        title={feature.description}
                      >
                        {feature.description}
                      </CardDescription>
                    </CardHeader>
                  </Card>
                </Reveal>
              ))}
            </div>
          </div>
        </section>

        {/* 三步接入 */}
        <section id="quickstart" className="py-20">
          <div className="mx-auto max-w-6xl px-4 sm:px-6">
            <Reveal className="mx-auto max-w-2xl text-center">
              <h2 className="text-3xl font-bold tracking-tight">{t("quickstart.title")}</h2>
              <p className="mt-3 text-muted-foreground">
                {t("quickstart.subtitle")}
              </p>
            </Reveal>
            <div className="mt-12 grid gap-6 md:grid-cols-3">
              {steps.map((step, index) => (
                <Reveal key={index} delay={index * 120}>
                  <div className="relative">
                    <div className="flex items-center gap-3">
                      <span className="flex size-10 items-center justify-center rounded-lg bg-primary text-primary-foreground">
                        <step.icon className="size-5" />
                      </span>
                      <span className="text-sm font-medium text-muted-foreground">
                        {t("quickstart.stepLabel", { number: index + 1 })}
                      </span>
                    </div>
                    <h3 className="mt-4 text-lg font-semibold">{step.title}</h3>
                    <p className="mt-2 text-sm text-muted-foreground">
                      {step.description}
                    </p>
                  </div>
                </Reveal>
              ))}
            </div>

            <Reveal delay={200}>
              <div className="mx-auto mt-12 max-w-2xl overflow-hidden rounded-xl border bg-zinc-950 text-sm">
                <div className="border-b border-white/10 px-4 py-2 text-xs text-zinc-400">
                  {t("quickstart.codeHeader")}
                </div>
                <pre className="overflow-x-auto p-4 font-mono text-zinc-100">
                  {`from openai import OpenAI

client = OpenAI(
    api_key="sk-xxx",                          ${t("quickstart.codeCommentCreate")}
    base_url="https://api.youtiao.dev/v1",  ${t("quickstart.codeCommentBaseUrl")}
)

${t("quickstart.codeCommentChat")}
chat = client.chat.completions.create(
    model="gpt-5",
    messages=[{"role": "user", "content": "${t("quickstart.codePromptChat")}"}],
)

${t("quickstart.codeCommentImage")}
img = client.images.generate(
    model="flux-1.1-pro",
    prompt="${t("quickstart.codePromptImage")}",
)

${t("quickstart.codeCommentVideo")}
task = client.videos.generate(
    model="minimax-h3",
    prompt="${t("quickstart.codePromptVideo")}",
    duration=8,
)`}
                </pre>
              </div>
            </Reveal>
          </div>
        </section>

        {/* CTA */}
        <section className="border-t bg-gradient-to-br from-[#4c6fff] to-[#129dc2] py-16 text-white">
          <div className="mx-auto flex max-w-6xl flex-col items-center gap-6 px-4 text-center sm:px-6">
            <Reveal className="flex flex-col items-center gap-6">
              <h2 className="text-3xl font-bold tracking-tight">
                {t("cta.title")}
              </h2>
              <p className="max-w-xl text-white/80">
                {t("cta.subtitle")}
              </p>
              <AuthCta
                label={t("cta.button")}
                variant="secondary"
                className="bg-white text-[#435bd0] hover:bg-white/90"
              />
            </Reveal>
          </div>
        </section>
      </main>

      <SiteFooter />
    </>
  );
}
