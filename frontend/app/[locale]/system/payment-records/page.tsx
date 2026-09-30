import type { Metadata } from "next";

import { PaymentRecordsPanel } from "@/components/system/payment-records";

export const metadata: Metadata = { title: "支付流水" };

export default function PaymentRecordsPage() {
  return <PaymentRecordsPanel />;
}
