import type { Metadata } from "next";

import { MembershipLevelsPanel } from "@/components/system/membership-levels";

export const metadata: Metadata = { title: "会员等级" };

export default function MembershipLevelsPage() {
  return <MembershipLevelsPanel />;
}
