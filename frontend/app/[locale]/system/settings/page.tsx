import type { Metadata } from "next";

import { SystemSettingsPanel } from "@/components/system/system-settings-panel";

export const metadata: Metadata = { title: "系统设置" };

export default function SystemSettingsPage() {
  return <SystemSettingsPanel />;
}
