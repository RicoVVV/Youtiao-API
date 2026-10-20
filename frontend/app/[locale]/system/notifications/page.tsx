import type { Metadata } from "next";

import { NotificationsPanel } from "@/components/system/messages";

export const metadata: Metadata = { title: "通知管理" };

export default function NotificationsPage() {
  return <NotificationsPanel />;
}
