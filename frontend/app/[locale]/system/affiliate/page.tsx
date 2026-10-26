import type { Metadata } from "next";

import { AffiliateSettingsPanel } from "@/components/system/affiliate-settings-panel";

export const metadata: Metadata = { title: "邀请返利" };

export default function AffiliateSettingsPage() {
  return <AffiliateSettingsPanel />;
}
