import type { Metadata } from "next";

import { SiteInfoPanel } from "@/components/system/site-info";

export const metadata: Metadata = { title: "站点信息" };

export default function SiteInfoPage() {
  return <SiteInfoPanel />;
}
