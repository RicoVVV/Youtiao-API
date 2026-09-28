import type { Metadata } from "next";

import { MonitoringPanel } from "@/components/console/monitoring/user-panel";

export const metadata: Metadata = { title: "分组监控" };

export default function MonitoringPage() {
  return <MonitoringPanel />;
}
