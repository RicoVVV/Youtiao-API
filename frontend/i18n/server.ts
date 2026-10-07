import { createInstance, type i18n as I18nInstance } from "i18next";
import resourcesToBackend from "i18next-resources-to-backend";
import { initReactI18next } from "react-i18next/initReactI18next";
import { defaultLocale, namespaces, type Locale, type Namespace } from "./config";

const importBackend = resourcesToBackend(
  (language: string, namespace: string) =>
    import(`./locales/${language}/${namespace}.json`)
);

/**
 * 服务端按 locale 创建独立 i18n 实例（避免跨请求污染）。
 * 用法：const { t } = await getServerT(locale, "home");
 */
export async function getServerT(locale: Locale, ns: Namespace = "common") {
  const instance: I18nInstance = createInstance();
  await instance
    .use(initReactI18next)
    .use(importBackend)
    .init({
      lng: locale,
      fallbackLng: defaultLocale,
      ns: namespaces,
      defaultNS: ns,
      fallbackNS: "common",
      interpolation: { escapeValue: false },
    });
  return { t: instance.getFixedT(locale, ns), i18n: instance };
}
