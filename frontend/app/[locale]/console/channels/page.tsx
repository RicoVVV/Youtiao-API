import type { Metadata } from "next";

import { ChannelsPanel } from "@/components/console/channels-panel";

export const metadata: Metadata = { title: "渠道管理" };

export default function ChannelsPage() {
  return <ChannelsPanel />;
}
