import type { Metadata } from "next";

import { GroupsPanel } from "@/components/console/groups-panel";

export const metadata: Metadata = { title: "分组" };

export default function GroupsPage() {
  return <GroupsPanel />;
}
