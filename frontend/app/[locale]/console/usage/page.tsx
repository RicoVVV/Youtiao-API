import type { Metadata } from "next";

import { UsageStatisticsPanel } from "@/components/console/usage-statistics-panel";

export const metadata: Metadata = { title: "用量统计" };

export default function UsagePage() {
  return <UsageStatisticsPanel />;
}
