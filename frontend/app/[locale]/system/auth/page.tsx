import type { Metadata } from "next";

import { AuthSettingsPanel } from "@/components/system/auth-settings-panel";

export const metadata: Metadata = { title: "邮箱验证" };

export default function SystemAuthPage() {
  return <AuthSettingsPanel />;
}
