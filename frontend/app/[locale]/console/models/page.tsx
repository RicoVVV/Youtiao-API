import type { Metadata } from "next";

import { ModelsPanel } from "@/components/console/models-panel";

export const metadata: Metadata = { title: "模型" };

export default function ModelsPage() {
  return <ModelsPanel />;
}
