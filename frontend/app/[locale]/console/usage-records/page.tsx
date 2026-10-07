import type { Metadata } from "next";

import { UsageRecordsPanel } from "@/components/console/usage-records-panel";

export const metadata: Metadata = { title: "使用记录" };

export default function UsageRecordsPage() {
  return <UsageRecordsPanel />;
}
