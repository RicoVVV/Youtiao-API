"use client";

import { useTranslation } from "react-i18next";
import { AlertTriangle, Save } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

import { SectionHeader, FieldLabel } from "./form-helpers";
import type { ProviderSettings } from "./types";

export function EpayTab({
  epayConfig,
  setEpayConfig,
  merchantKey,
  setMerchantKey,
  platformKey,
  setPlatformKey,
  onSave,
  saving,
  disabled,
}: {
  epayConfig: ProviderSettings;
  setEpayConfig: (v: ProviderSettings) => void;
  merchantKey: string;
  setMerchantKey: (v: string) => void;
  platformKey: string;
  setPlatformKey: (v: string) => void;
  onSave: () => void;
  saving: boolean;
  disabled: boolean;
}) {
  const { t } = useTranslation("console");
  const patch = (partial: Partial<ProviderSettings>) =>
    setEpayConfig({ ...epayConfig, ...partial });

  return (
    <div className="space-y-6 max-w-3xl">
      {/* 安全提醒 */}
      <div className="flex items-start gap-3 rounded-lg border border-warning/40 bg-warning/5 px-4 py-3">
        <AlertTriangle className="mt-0.5 size-5 shrink-0 text-warning" />
        <div>
          <p className="text-sm font-medium">{t("paymentGateway.epay.securityTitle")}</p>
          <p className="mt-0.5 text-sm text-muted-foreground">
            {t("paymentGateway.epay.securityDesc")}
          </p>
        </div>
      </div>

      {/* 网关配置 */}
      <section className="space-y-4">
        <SectionHeader title={t("paymentGateway.epay.sectionTitle")} description={t("paymentGateway.epay.sectionDesc")} />
        <div className="grid gap-6 md:grid-cols-2">
          <div>
            <FieldLabel label={t("paymentGateway.epay.endpoint")} />
            <Input
              value={epayConfig.gateway_url}
              onChange={(e) => patch({ gateway_url: e.target.value })}
              placeholder=""
              className="mt-1.5"
            />
            <p className="mt-1 text-xs text-muted-foreground">
              {t("paymentGateway.epay.endpointHint")}
            </p>
          </div>
          <div>
            <FieldLabel label={t("paymentGateway.epay.merchantId")} />
            <Input
              value={epayConfig.partner_id ?? ""}
              onChange={(e) => patch({ partner_id: e.target.value })}
              placeholder=""
              className="mt-1.5"
            />
          </div>
          <div>
            <FieldLabel
              label={t("paymentGateway.epay.merchantKey")}
              tag={epayConfig.merchant_private_key_configured ? t("paymentGateway.epay.configured") : t("paymentGateway.epay.notConfigured")}
              tagVariant={epayConfig.merchant_private_key_configured ? "primary" : "default"}
            />
            <Input
              type="password"
              value={merchantKey}
              onChange={(e) => setMerchantKey(e.target.value)}
              placeholder={
                epayConfig.merchant_private_key_configured ? t("paymentGateway.epay.keepConfigured") : t("paymentGateway.epay.merchantKeyPlaceholder")
              }
              className="mt-1.5"
            />
            <p className="mt-1 text-xs text-muted-foreground">
              {t("paymentGateway.epay.merchantKeyHint")}
            </p>
          </div>
          <div>
            <FieldLabel
              label={t("paymentGateway.epay.platformKey")}
              tag={epayConfig.platform_public_key_configured ? t("paymentGateway.epay.configured") : t("paymentGateway.epay.notConfigured")}
              tagVariant={epayConfig.platform_public_key_configured ? "primary" : "default"}
            />
            <Input
              type="password"
              value={platformKey}
              onChange={(e) => setPlatformKey(e.target.value)}
              placeholder={
                epayConfig.platform_public_key_configured
                  ? t("paymentGateway.epay.keepConfigured")
                  : t("paymentGateway.epay.platformKeyPlaceholder")
              }
              className="mt-1.5"
            />
            <p className="mt-1 text-xs text-muted-foreground">
              {t("paymentGateway.epay.platformKeyHint")}
            </p>
          </div>
        </div>

      </section>

      <div className="flex justify-end pt-2">
        <Button onClick={onSave} disabled={saving || disabled}>
          <Save className="size-4" />
          {saving ? t("paymentGateway.epay.saving") : t("paymentGateway.epay.save")}
        </Button>
      </div>
    </div>
  );
}
