import type { Metadata } from "next";

import { ProfilePanel } from "@/components/console/profile-panel";

export const metadata: Metadata = { title: "个人资料" };

export default function ProfilePage() {
  return <ProfilePanel />;
}
