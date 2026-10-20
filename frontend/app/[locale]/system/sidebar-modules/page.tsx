import type { Metadata } from "next";

import { SidebarModulesPanel } from "@/components/system/sidebar-modules-panel";

export const metadata: Metadata = { title: "侧边栏模块" };

export default function SidebarModulesPage() {
  return <SidebarModulesPanel />;
}
