import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { Geist, Geist_Mono } from "next/font/google";
import { SetupGuard } from "@/components/setup-guard";
import { Toaster } from "@/components/ui/toaster";
import { I18nProvider } from "@/i18n/client";
import { locales, isLocale, namespaces, type Locale } from "@/i18n/config";
import { getServerT } from "@/i18n/server";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export function generateStaticParams() {
  return locales.map((locale) => ({ locale }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const { locale } = await params;
  if (!isLocale(locale)) return {};
  const { t } = await getServerT(locale, "common");
  return {
    title: { default: t("meta.title"), template: "%s · Youtiao API" },
    description: t("meta.description"),
    icons: { icon: "/youtiao.svg" },
  };
}

export default async function LocaleLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  if (!isLocale(locale)) notFound();

  // 服务端预载当前语言全部命名空间，作为 resources 同步注入客户端 i18n 实例，
  // 避免首次渲染时语言包尚未就绪导致先显示英文再切换为中文
  const resourcePairs = await Promise.all(
    namespaces.map(async (ns) => {
      const mod = (await import(`@/i18n/locales/${locale}/${ns}.json`)) as {
        default: Record<string, unknown>;
      };
      return [ns, mod.default] as const;
    })
  );
  const resources = { [locale]: Object.fromEntries(resourcePairs) };

  return (
    <html
      lang={locale === "zh" ? "zh-CN" : "en"}
      suppressHydrationWarning
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        <script
          dangerouslySetInnerHTML={{
            __html: `
              try {
                if (localStorage.getItem("theme") === "dark") {
                  document.documentElement.classList.add("dark");
                }
              } catch {}
            `,
          }}
        />
        <I18nProvider locale={locale as Locale} resources={resources}>
          <SetupGuard />
          {children}
          <Toaster />
        </I18nProvider>
      </body>
    </html>
  );
}
