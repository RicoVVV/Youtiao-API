"use client";

import { usePathname } from "next/navigation";

import { ConsoleSidebar } from "@/components/console/console-sidebar";
import { ErrorBoundary } from "@/components/error-boundary";
import { SiteHeader } from "@/components/site-header";
import { stripLocale } from "@/lib/path-utils";

// 不需要外层容器（padding）的路径前缀
const BARE_PATHS = ["/console/canvas"];

export default function ConsoleLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const bare = BARE_PATHS.some((p) => stripLocale(pathname).startsWith(p));

  return (
    <div className="min-h-screen">
      <SiteHeader />
      <ConsoleSidebar />
      {/* 主内容区：让出侧边栏宽度，高度扣除顶部 Header(h-14)；BARE_PATHS 路径下不渲染内层容器 */}
      <main className="min-h-[calc(100vh-3.5rem)] pl-60">
        <ErrorBoundary resetKey={pathname}>
          {bare ? (
            children
          ) : (
            <div className="w-full px-6 py-8 lg:px-10">{children}</div>
          )}
        </ErrorBoundary>
      </main>
    </div>
  );
}
