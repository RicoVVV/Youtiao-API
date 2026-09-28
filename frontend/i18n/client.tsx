"use client";

import { useEffect, useRef } from "react";
import { useParams } from "next/navigation";
import { I18nextProvider } from "react-i18next";
import { createInstance, type i18n as I18nInstance } from "i18next";
import { initReactI18next } from "react-i18next";
import resourcesToBackend from "i18next-resources-to-backend";
import { defaultLocale, namespaces, isLocale, type Locale } from "./config";
import { endLocaleTransition } from "./transition";

/**
 * 客户端 hook：从路由 params 中获取当前 locale，
 * 用于 client 组件拼接 locale 前缀路由。
 */
export function useLocale(): Locale {
  const params = useParams<{ locale?: string }>();
  return params?.locale && isLocale(params.locale) ? params.locale : defaultLocale;
}

/**
 * 客户端 i18n Provider：按当前 locale 初始化实例，locale 变化时切换语言。
 * 挂载于 [locale]/layout.tsx，下游客户端组件用 useTranslation(ns) 取文案。
 * 服务端会把当前语言的全部命名空间作为 resources 传入，初始化后立即可用，
 * 避免首屏先渲染占位/英文再异步切换为中文。
 */
export function I18nProvider({
  locale,
  resources,
  children,
}: {
  locale: Locale;
  resources?: Record<string, Record<string, Record<string, unknown>>>;
  children: React.ReactNode;
}) {
  const ref = useRef<I18nInstance | null>(null);
  if (!ref.current) {
    const instance = createInstance();
    instance
      .use(initReactI18next)
      .use(
        resourcesToBackend(
          (language: string, namespace: string) =>
            import(`./locales/${language}/${namespace}.json`)
        )
      )
      .init({
        lng: locale,
        fallbackLng: defaultLocale,
        // 预载资源已覆盖当前语言，初始化同步完成，语言包即刻可用
        resources,
        ns: namespaces,
        defaultNS: "common",
        fallbackNS: "common",
        interpolation: { escapeValue: false },
        react: { useSuspense: false },
      });
    ref.current = instance;
  }

  useEffect(() => {
    let cancelled = false;
    void ref.current?.changeLanguage(locale).finally(() => {
      // 新语言资源就绪后再淡出遮罩，避免内容闪变
      if (!cancelled) endLocaleTransition();
    });
    return () => {
      cancelled = true;
    };
  }, [locale]);

  return <I18nextProvider i18n={ref.current}>{children}</I18nextProvider>;
}
