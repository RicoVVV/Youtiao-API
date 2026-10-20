/**
 * 控制台概览与站点信息 API 封装
 *
 * 对应接口文档：docs/USER_OVERVIEW_FRONTEND_INTEGRATION.md
 * - 用户端：/overview/detail 一次请求聚合当日用量、钱包、可见消息与站点信息
 * - 管理端：/admin/site-info/* 站点信息（API 快捷线路）的 CRUD
 */

import { get, post } from "@/lib/request";
import type { InboxMessage, Paged } from "@/lib/messages";

/** 概览用量统计（固定为当日，Asia/Shanghai 自然日） */
export type OverviewUsage = {
  total_count: number;
  settled_amount: string;
  success_rate: string;
  total_tokens: number;
  average_rpm: string;
  average_tpm: string;
};

export type OverviewWallet = {
  balance: string;
  usage: string;
};

/** 用户端站点信息（API 快捷线路） */
export type SiteInfo = {
  id: string;
  api_url: string;
  route_name: string;
  description: string;
  /** 颜色名称（如 blue），前端负责映射为具体颜色 */
  badge_color: string;
};

/** 管理端站点信息 */
export type AdminSiteInfo = SiteInfo & {
  sort_order: number;
  is_active: boolean;
  created_at: string | null;
  updated_at: string | null;
};

export type OverviewDetail = {
  usage: OverviewUsage;
  wallet: OverviewWallet;
  messages: Paged<InboxMessage>;
  site_infos: SiteInfo[];
};

/* ---------------- 用户端 ---------------- */

/** 查询控制台概览（消息分页通过 message_page / message_page_size 控制） */
export const getOverviewDetail = (params?: {
  message_page?: number;
  message_page_size?: number;
}) => get<OverviewDetail>("/overview/detail", { params });

/* ---------------- 管理端 ---------------- */

/** 查询站点信息列表 */
export const listAdminSiteInfos = (params?: {
  keyword?: string;
  is_active?: boolean;
  page?: number;
  page_size?: number;
}) => get<Paged<AdminSiteInfo>>("/admin/site-info/list", { params });

/** 创建站点信息 */
export const createSiteInfo = (body: {
  api_url: string;
  route_name: string;
  description?: string;
  badge_color?: string;
  sort_order?: number;
  is_active?: boolean;
}) => post<AdminSiteInfo>("/admin/site-info/create", body);

/** 更新站点信息 */
export const updateSiteInfo = (body: {
  site_info_id: string;
  api_url?: string;
  route_name?: string;
  description?: string;
  badge_color?: string;
  sort_order?: number;
  is_active?: boolean;
}) => post<AdminSiteInfo>("/admin/site-info/update", body);

/** 启用/停用站点信息 */
export const updateSiteInfoStatus = (body: {
  site_info_id: string;
  is_active: boolean;
}) => post<AdminSiteInfo>("/admin/site-info/update-status", body);

/** 删除站点信息（逻辑删除） */
export const deleteSiteInfo = (siteInfoId: string) =>
  post<{ success: boolean }>("/admin/site-info/delete", {
    site_info_id: siteInfoId,
  });

/* ---------------- 徽标颜色映射 ---------------- */

/** 预设徽标颜色：管理端可选项，用户端据此渲染圆点 */
export const BADGE_COLORS = [
  "blue",
  "green",
  "orange",
  "red",
  "purple",
  "teal",
  "gray",
] as const;

const BADGE_DOT_CLASSES: Record<string, string> = {
  blue: "bg-blue-500",
  green: "bg-emerald-500",
  orange: "bg-orange-500",
  red: "bg-red-500",
  purple: "bg-purple-500",
  teal: "bg-teal-500",
  gray: "bg-gray-400",
};

/** 颜色名称 → 圆点样式；未知名称回退蓝色 */
export const badgeDotClass = (name: string) =>
  BADGE_DOT_CLASSES[name] ?? BADGE_DOT_CLASSES.blue;
