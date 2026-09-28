"use client";

import { useTranslation } from "react-i18next";

import { LocaleLink } from "./locale-link";

import { FooterLoginLink } from "./footer-login-link";
import { SiteLogo } from "./site-logo";
import { SiteName } from "./site-name";
import { usePublicSystemSettings } from "@/lib/use-system-settings";
import { sanitizeHtml } from "@/lib/sanitize";

export function SiteFooter() {
  const settings = usePublicSystemSettings();
  const { t } = useTranslation("home");
  const footerHtml = settings?.footer_text
    ? sanitizeHtml(settings.footer_text)
    : "";

  return (
    <footer className="border-t">
      <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-4 px-4 py-8 sm:flex-row sm:px-6">
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <SiteLogo className="size-5" />
          {footerHtml ? (
            // footer_text 支持 HTML（如备案链接），净化后渲染
            <span
              className="[&_a]:transition-colors [&_a]:hover:text-foreground"
              dangerouslySetInnerHTML={{ __html: footerHtml }}
            />
          ) : (
            <SiteName />
          )}
        </div>
        <nav className="flex items-center gap-6 text-sm text-muted-foreground">
          <LocaleLink href="/models" className="transition-colors hover:text-foreground">
            {t("footer.models")}
          </LocaleLink>
          <LocaleLink href="/console" className="transition-colors hover:text-foreground">
            {t("footer.console")}
          </LocaleLink>
          <FooterLoginLink />
        </nav>
      </div>
    </footer>
  );
}
