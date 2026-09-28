/* ── API 类型 ── */

export interface ProviderSettings {
  provider: string;
  gateway_url: string;
  payment_methods: string[];
  app_id: string | null;
  partner_id: string | null;
  seller_id: string | null;
  merchant_private_key_configured: boolean;
  public_key_configured: boolean | null;
  platform_public_key_configured: boolean | null;
  api_key_configured: boolean | null;
  webhook_secret_configured: boolean | null;
  cancel_url?: string;
  notify_url?: string;
  /** PUT 时传入的敏感字段，GET 不返回 */
  merchant_private_key?: string;
  platform_public_key?: string;
  api_key?: string;
  webhook_secret?: string;
}

export interface PricingSettings {
  min_topup: string;
  max_topup: string;
  amount_options: string[];
  amount_discount: Record<string, string>;
  group_ratios: Record<string, string>;
}

export interface PaymentMethodItem {
  payment_name: string;
  payment_channel: string;
  payment_method: string;
  payment_icon: string;
  min_topup: string;
  max_topup: string;
  enabled: boolean;
}

export interface PaymentSettingsResponse {
  providers: Record<string, ProviderSettings>;
  payments: PaymentMethodItem[];
  pricing: PricingSettings;
  compliance_confirmed: boolean;
}

/* ── Tab ── */

export const TABS = [
  { key: "general" },
  { key: "epay" },
  { key: "stripe" },
] as const;

export type TabKey = (typeof TABS)[number]["key"];

export type Translate = (key: string, options?: Record<string, unknown>) => string;

export const PROCESSOR_PRESETS = [
  { key: "alipay", channel: "epay", method: "alipay" },
  { key: "wxpay", channel: "epay", method: "wxpay" },
  { key: "card", channel: "stripe", method: "card" },
] as const;

export function formatProcessorLabel(t: Translate, channel: string, method: string): string {
  if (!channel || !method) return "";
  let item = PROCESSOR_PRESETS.find((p) => p.channel === channel && p.method === method);
  if (!item) return "";
  return `${t(`paymentGateway.processor.${item.key}`)} (${channel}${method ? `: ${method}` : ""})`
}
