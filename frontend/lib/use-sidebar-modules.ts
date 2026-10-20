"use client";

import { useEffect, useState } from "react";

import { getVisibleSidebarModules } from "@/lib/sidebar-modules";

/** 可见模块缓存（同页多组件共享一次请求）；null 表示未知，未知时按全部可见处理 */
let cache: string[] | null = null;
let inflight: Promise<string[]> | null = null;

/** 使可见模块缓存失效：管理员保存配置后调用，下次挂载时重新拉取 */
export function invalidateSidebarModulesCache() {
  cache = null;
}

/**
 * 读取全站生效的可见侧边栏模块 key 列表。
 * 返回 null 表示尚未加载或加载失败（调用方应按全部可见兜底，避免菜单闪烁）；
 * 返回数组后，未出现在数组中的模块必须隐藏。
 */
export function useSidebarModules(): string[] | null {
  const [modules, setModules] = useState<string[] | null>(cache);

  useEffect(() => {
    if (cache) return;
    if (!inflight) {
      inflight = getVisibleSidebarModules()
        .then((data) => data.modules ?? [])
        .finally(() => {
          inflight = null;
        });
    }
    inflight
      .then((list) => {
        cache = list;
        setModules(list);
      })
      .catch(() => {
        // 拉取失败时保持 null（全部可见），不阻塞页面渲染
      });
  }, []);

  return modules;
}
