"use client";

import { useTranslation } from "react-i18next";
import { Info, Save } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

import { SectionHeader, FieldLabel } from "./form-helpers";
import type { ProviderSettings } from "./types";

export function StripeTab({
  stripeConfig,
  setStripeConfig,
  apiKey,
  setApiKey,
  webhookSecret,
  setWebhookSecret,
  onSave,
  saving,
  disabled,
}: {
  stripeConfig: ProviderSettings;
  setStripeConfig: (v: ProviderSettings) => void;
  apiKey: string;
  setApiKey: (v: string) => void;
  webhookSecret: string;
  setWebhookSecret: (v: string) => void;
  onSave: () => void;
  saving: boolean;
  disabled: boolean;
}) {
  const { t } = useTranslation("console");
  return (
    <div className="space-y-6 max-w-3xl">
      {/* Webhook 配置提示 */}
      <div className="flex items-start gap-3 rounded-lg border border-primary/30 bg-primary/5 px-4 py-3">
        <Info className="mt-0.5 size-5 shrink-0 text-primary" />
        <div className="text-sm">
          <p className="font-medium text-primary">{t("paymentGateway.stripe.webhookTitle")}</p>
          <ul className="mt-1 list-disc space-y-1 pl-5 text-muted-foreground">
            <li>
              {t("paymentGateway.stripe.webhookUrl")}
              <code className="rounded bg-muted px-1.5 py-0.5 text-xs">
                {stripeConfig.notify_url || t("paymentGateway.stripe.notConfigured")}
              </code>
            </li>
            <li>
              {t("paymentGateway.stripe.requiredEvents")}
              <code className="rounded bg-muted px-1.5 py-0.5 text-xs">
                checkout.session.completed
              </code>{" "}
              {t("paymentGateway.stripe.and")}{" "}
              <code className="rounded bg-muted px-1.5 py-0.5 text-xs">
                checkout.session.expired
              </code>
            </li>
            <li>
              {t("paymentGateway.stripe.configLocation")}
              <a
                href="https://dashboard.stripe.com/webhooks"
                target="_blank"
                rel="noreferrer"
                className="text-primary underline underline-offset-2"
              >
                {t("paymentGateway.stripe.stripeDashboard")}
              </a>
            </li>
          </ul>
        </div>
      </div>

      {/* 网关配置 */}
      <section className="space-y-4">
        <SectionHeader
          title={t("paymentGateway.stripe.sectionTitle")}
          description={t("paymentGateway.stripe.sectionDesc")}
        />
        <div className="grid gap-6 md:grid-cols-2">
          <div>
            <FieldLabel
              label={t("paymentGateway.stripe.apiKey")}
              tag={
                stripeConfig.api_key_configured ? t("paymentGateway.stripe.configured") : t("paymentGateway.stripe.notConfigured")
              }
              tagVariant={
                stripeConfig.api_key_configured ? "primary" : "default"
              }
            />
            <Input
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder={
                stripeConfig.api_key_configured
                  ? t("paymentGateway.stripe.keepConfigured")
                  : "sk_xxx 或 rk_xxx"
              }
              className="mt-1.5"
            />
            <p className="mt-1 text-xs text-muted-foreground">
              {t("paymentGateway.stripe.apiKeyHint")}
            </p>
          </div>
          <div>
            <FieldLabel
              label={t("paymentGateway.stripe.webhookSecret")}
              tag={
                stripeConfig.webhook_secret_configured ? t("paymentGateway.stripe.configured") : t("paymentGateway.stripe.notConfigured")
              }
              tagVariant={
                stripeConfig.webhook_secret_configured ? "primary" : "default"
              }
            />
            <Input
              type="password"
              value={webhookSecret}
              onChange={(e) => setWebhookSecret(e.target.value)}
              placeholder={
                stripeConfig.webhook_secret_configured
                  ? t("paymentGateway.stripe.keepConfigured")
                  : "whsec_xxx"
              }
              className="mt-1.5"
            />
            <p className="mt-1 text-xs text-muted-foreground">
              {t("paymentGateway.stripe.webhookSecretHint")}
            </p>
          </div>
        </div>
      </section>

      <div className="flex justify-end pt-2">
        <Button onClick={onSave} disabled={saving || disabled}>
          <Save className="size-4" />
          {saving ? t("paymentGateway.stripe.saving") : t("paymentGateway.stripe.save")}
        </Button>
      </div>
    </div>
  );
}
