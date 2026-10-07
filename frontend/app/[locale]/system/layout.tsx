"use client";

import { SystemSidebar } from "@/components/system/system-sidebar";
import { SiteHeader } from "@/components/site-header";

export default function SystemLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-screen">
      <SiteHeader />
      <SystemSidebar />
      {/* 主内容区：让出侧边栏宽度，高度扣除顶部 Header(h-14) */}
      <main className="min-h-[calc(100vh-3.5rem)] pl-60">
        <div className="w-full px-6 py-8 lg:px-10">{children}</div>
      </main>
    </div>
  );
}
