import type { Metadata } from "next";

import { BillingOverview } from "@/components/console/billing/billing-overview";
import { WalletTopup } from "@/components/console/billing/wallet-topup";

export const metadata: Metadata = { title: "账单中心" };

export default function BillingPage() {
  return (
    <div className="space-y-6">
      <BillingOverview />
      <WalletTopup />
    </div>
  );
}
