"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { Loading } from "@/components/ui/loading";
import { Card, CardContent } from "@/components/ui/card";
import { toast } from "@/components/ui/toaster";
import { cn } from "@/lib/utils";
import { get, post } from "@/lib/request";

import { ComplianceBanner, ComplianceModal } from "./compliance-confirm";

import type {
  PaymentMethodItem,
  ProviderSettings,
  PaymentSettingsResponse,
  TabKey,
} from "./types";
import { TABS } from "./types";
import { GeneralTab } from "./general-tab";
import { EpayTab } from "./epay-tab";
import { StripeTab } from "./stripe-tab";

const DEFAULT_EPAY_CONFIG: ProviderSettings = {
  provider: "epay",
  gateway_url: "",
  payment_methods: ['alipay', 'wxpay'],
  app_id: null,
  partner_id: null,
  seller_id: null,
  merchant_private_key_configured: false,
  public_key_configured: null,
  platform_public_key_configured: null,
  api_key_configured: null,
  webhook_secret_configured: null,
};

const DEFAULT_STRIPE_CONFIG: ProviderSettings = {
  provider: "stripe",
  gateway_url: "",
  payment_methods: ["card"],
  app_id: null,
  partner_id: null,
  seller_id: null,
  merchant_private_key_configured: false,
  public_key_configured: null,
  platform_public_key_configured: null,
  api_key_configured: false,
  webhook_secret_configured: false,
};

export function PaymentGatewayPanel() {
  const { t } = useTranslation("console");
  const [activeTab, setActiveTab] = useState<TabKey>("general");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [complianceOpen, setComplianceOpen] = useState(false);
  const [complianceConfirmed, setComplianceConfirmed] = useState(false);
  const [complianceSubmitting, setComplianceSubmitting] = useState(false);

  /* ── 常规 Tab 状态 ── */
  const [minTopup, setMinTopup] = useState("1.00");
  const [amountOptions, setAmountOptions] = useState<string[]>([]);
  const [amountDiscount, setAmountDiscount] = useState<Record<string, string>>(
    {}
  );
  const [payments, setPayments] = useState<PaymentMethodItem[]>([]);

  /* ── Epay Tab 状态 ── */
  const [epayConfig, setEpayConfig] =
    useState<ProviderSettings>(DEFAULT_EPAY_CONFIG);
  const [merchantKey, setMerchantKey] = useState("");
  const [platformKey, setPlatformKey] = useState("");

  /* ── Stripe Tab 状态 ── */
  const [stripeConfig, setStripeConfig] =
    useState<ProviderSettings>(DEFAULT_STRIPE_CONFIG);
  const [stripeApiKey, setStripeApiKey] = useState("");
  const [stripeWebhookSecret, setStripeWebhookSecret] = useState("");

  /* ── 原子保存时需要原样回传的只读数据 ── */
  const [maxTopup, setMaxTopup] = useState("5000.00");
  const [groupRatios, setGroupRatios] = useState<Record<string, string>>({});

  /* ── 加载配置 ── */
  const loadingRef = useRef(false);
  const load = useCallback(async () => {
    if (loadingRef.current) return;
    loadingRef.current = true;
    try {
      const data = await get<PaymentSettingsResponse>(
        "/admin/payments/settings/detail"
      );

      setMinTopup(data.pricing.min_topup);
      setMaxTopup(data.pricing.max_topup);
      setAmountOptions(data.pricing.amount_options);
      setAmountDiscount(data.pricing.amount_discount);
      setGroupRatios(data.pricing.group_ratios);

      setEpayConfig(data.providers?.epay ?? DEFAULT_EPAY_CONFIG);
      setStripeConfig(data.providers?.stripe ?? DEFAULT_STRIPE_CONFIG);
      setPayments(data.payments ?? []);
      setComplianceConfirmed(data.compliance_confirmed ?? false);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t("paymentGateway.loadFailed"));
    } finally {
      loadingRef.current = false;
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    load();
  }, [load]);

  /* ── 合规确认 ── */
  const handleComplianceConfirm = async () => {
    setComplianceSubmitting(true);
    try {
      await post("/admin/payments/compliance/confirm", { confirmed: true });
      setComplianceConfirmed(true);
      setComplianceOpen(false);
      toast.success(t("paymentGateway.complianceConfirmSuccess"));
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t("paymentGateway.complianceConfirmFailed"));
    } finally {
      setComplianceSubmitting(false);
    }
  };

  /* ── 分开保存配置 ── */
  const saveGeneral = async () => {
    setSaving(true);
    try {
      await post("/admin/payments/settings/update", {
        pricing: {
          min_topup: minTopup,
          max_topup: maxTopup,
          amount_options: amountOptions,
          amount_discount: amountDiscount,
          group_ratios: groupRatios,
        },
        payments,
      });
      toast.success(t("paymentGateway.generalSaved"));
      await load();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t("paymentGateway.saveFailed"));
    } finally {
      setSaving(false);
    }
  };

  const saveEpay = async () => {
    setSaving(true);
    try {
      const epayProvider: Record<string, unknown> = {
        ...epayConfig,
        payment_methods: ['alipay', 'wxpay'],
      };
      delete epayProvider.merchant_private_key_configured;
      delete epayProvider.platform_public_key_configured;
      delete epayProvider.api_key_configured;
      delete epayProvider.webhook_secret_configured;
      delete epayProvider.public_key_configured;
      if (merchantKey) epayProvider.merchant_private_key = merchantKey;
      if (platformKey) epayProvider.platform_public_key = platformKey;

      await post("/admin/payments/settings/update", {
        providers: { epay: epayProvider },
      });

      toast.success(t("paymentGateway.epaySaved"));
      setMerchantKey("");
      setPlatformKey("");
      await load();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t("paymentGateway.saveFailed"));
    } finally {
      setSaving(false);
    }
  };

  const saveStripe = async () => {
    setSaving(true);
    try {
      const stripeProvider: Record<string, unknown> = {
        ...stripeConfig,
        payment_methods: ["card"],
      };
      delete stripeProvider.merchant_private_key_configured;
      delete stripeProvider.platform_public_key_configured;
      delete stripeProvider.api_key_configured;
      delete stripeProvider.webhook_secret_configured;
      delete stripeProvider.public_key_configured;
      if (stripeApiKey) stripeProvider.api_key = stripeApiKey;
      if (stripeWebhookSecret) stripeProvider.webhook_secret = stripeWebhookSecret;

      await post("/admin/payments/settings/update", {
        providers: { stripe: stripeProvider },
      });

      toast.success(t("paymentGateway.stripeSaved"));
      setStripeApiKey("");
      setStripeWebhookSecret("");
      await load();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t("paymentGateway.saveFailed"));
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Loading size="lg" text={t("paymentGateway.loading")} />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">{t("paymentGateway.title")}</h1>
      </div>

      {!complianceConfirmed && (
        <ComplianceBanner onOpen={() => setComplianceOpen(true)} />
      )}

      <ComplianceModal
        open={complianceOpen}
        onClose={() => setComplianceOpen(false)}
        onConfirm={handleComplianceConfirm}
        submitting={complianceSubmitting}
      />

      <div
        className={cn(
          "inline-flex gap-0.5 rounded-lg border border-border/60 bg-muted/60 p-0.5",
          !complianceConfirmed && "pointer-events-none opacity-60"
        )}
      >
        {TABS.map((tab) => (
          <button
            key={tab.key}
            type="button"
            onClick={() => setActiveTab(tab.key)}
            className={cn(
              "min-w-28 rounded-md px-5 py-1.5 text-sm font-medium transition-all",
              activeTab === tab.key
                ? "bg-card text-foreground shadow-[0_1px_3px_rgb(0_0_0/8%),0_1px_2px_rgb(0_0_0/4%)]"
                : "text-muted-foreground hover:text-foreground"
            )}
          >
            {t(`paymentGateway.tab.${tab.key}`)}
          </button>
        ))}
      </div>

      <Card
        className={cn(
          "border-none shadow-none",
          !complianceConfirmed && "pointer-events-none opacity-60"
        )}
      >
        <CardContent className="pt-0">
          {activeTab === "general" ? (
            <GeneralTab
              minTopup={minTopup}
              setMinTopup={setMinTopup}
              maxTopup={maxTopup}
              setMaxTopup={setMaxTopup}
              amountOptions={amountOptions}
              setAmountOptions={setAmountOptions}
              amountDiscount={amountDiscount}
              setAmountDiscount={setAmountDiscount}
              payments={payments}
              setPayments={setPayments}
              onSave={saveGeneral}
              saving={saving}
              disabled={!complianceConfirmed}
            />
          ) : activeTab === "stripe" ? (
            <StripeTab
              stripeConfig={stripeConfig}
              setStripeConfig={setStripeConfig}
              apiKey={stripeApiKey}
              setApiKey={setStripeApiKey}
              webhookSecret={stripeWebhookSecret}
              setWebhookSecret={setStripeWebhookSecret}
              onSave={saveStripe}
              saving={saving}
              disabled={!complianceConfirmed}
            />
          ) : (
            <EpayTab
              epayConfig={epayConfig}
              setEpayConfig={setEpayConfig}
              merchantKey={merchantKey}
              setMerchantKey={setMerchantKey}
              platformKey={platformKey}
              setPlatformKey={setPlatformKey}
              onSave={saveEpay}
              saving={saving}
              disabled={!complianceConfirmed}
            />
          )}
        </CardContent>
      </Card>
    </div>
  );
}
