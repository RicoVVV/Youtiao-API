import type { Metadata } from "next";

import { MessagesPanel } from "@/components/system/messages";

export const metadata: Metadata = { title: "消息管理" };

export default function MessagesPage() {
  return <MessagesPanel />;
}
