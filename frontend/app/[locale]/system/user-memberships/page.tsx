import type { Metadata } from "next";

import { UserMembershipsPanel } from "@/components/system/user-memberships";

export const metadata: Metadata = { title: "用户会员" };

export default function UserMembershipsPage() {
  return <UserMembershipsPanel />;
}
