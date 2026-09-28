import type { Metadata } from "next";

import { RedemptionCodesPanel } from "@/components/console/redemption-codes-panel";

export const metadata: Metadata = { title: "兑换码" };

export default function RedemptionCodesPage() {
  return <RedemptionCodesPanel />;
}
