import type { Metadata } from "next";

import { AdminMonitoringPanel } from "@/components/console/monitoring/admin";

export const metadata: Metadata = { title: "监控告警" };

export default function MonitoringAdminPage() {
  return <AdminMonitoringPanel />;
}
