import type { Metadata } from "next";

import { OverviewPanel } from "@/components/console/overview-panel";

export const metadata: Metadata = { title: "概览" };

export default function OverviewPage() {
  return <OverviewPanel />;
}
