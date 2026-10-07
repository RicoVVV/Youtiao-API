import type { Metadata } from "next";

import { ChatPlayground } from "@/components/console/chat-playground";

export const metadata: Metadata = { title: "游乐场" };

export default function PlaygroundPage() {
  return <ChatPlayground />;
}
