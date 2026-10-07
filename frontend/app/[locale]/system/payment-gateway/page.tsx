import type { Metadata } from "next";

import { PaymentGatewayPanel } from "@/components/system/payment-gateway";

export const metadata: Metadata = { title: "支付网关" };

export default function PaymentGatewayPage() {
  return <PaymentGatewayPanel />;
}
