import type { Metadata } from "next";

import { ChannelAutomationPanel } from "@/components/system/channel-automation-panel";

export const metadata: Metadata = { title: "渠道测试" };

export default function ChannelAutomationPage() {
  return <ChannelAutomationPanel />;
}
