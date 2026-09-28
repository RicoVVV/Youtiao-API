import type { Metadata } from "next";

import { ChatCanvas } from "@/components/console/chat-canvas/index";

export const metadata: Metadata = {
    title: "画布",
};

export default function CanvasPage() {
  return <ChatCanvas />;
}
