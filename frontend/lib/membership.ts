/**
 * 会员系统 API 封装
 *
 * 对应后端会员接口：
 * - 用户端：套餐列表、购买（复用支付接口）、会员状态随用户资料返回
 * - 管理端：等级维护、套餐维护、用户会员授予/撤销、会员流水
 */

import { get, post } from "@/lib/request";

/* ---------------- 用户端：会员套餐 ---------------- */

/** 会员套餐（对外售卖） */
export type MembershipPlan = {
  id: string;
  /** 周期：week=7 天，month=30 天 */
  period: "week" | "month";
  /** 售价，两位小数字符串 */
  price: string;
  /** 购买成功后赠送的钱包余额 */
  bonus_amount: string;
};

/** 会员等级（对外售卖） */
export type MembershipLevel = {
  id: string;
  code: string;
  name: string;
  description: string;
  /** 等级高低，数值越大越高 */
  rank: number;
  /** 会员专享令牌分组 */
  groups: { id: number; name: string }[];
  /** 等级下的启用套餐 */
  plans: MembershipPlan[];
};

/** 查询会员套餐列表 */
export const listMembershipPlans = () =>
  get<{ items: MembershipLevel[] }>("/membership-plans/list");

/* ---------------- 用户端：当前会员状态（随 /user/info 返回） ---------------- */

/** 用户资料中的会员状态 */
export type UserMembership = {
  is_active: boolean;
  level: MembershipLevel | null;
  started_at: string | null;
  expires_at: string | null;
  groups: { id: number; name: string }[];
};

/* ---------------- 管理端：会员等级 ---------------- */

/** 等级下的套餐（管理端视图） */
export type AdminMembershipPlan = {
  id: string;
  period: "week" | "month";
  price: string;
  bonus_amount: string;
  level_id: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

/** 会员等级（管理端视图） */
export type AdminMembershipLevel = {
  id: string;
  code: string;
  name: string;
  description: string;
  rank: number;
  is_public: boolean;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  plans: AdminMembershipPlan[];
  groups: { id: number; name: string }[];
};

/** 查询等级列表 */
export const listMembershipLevels = (params?: {
  is_public?: boolean;
  is_active?: boolean;
  page?: number;
  page_size?: number;
}) =>
  get<{ items: AdminMembershipLevel[]; total: number; page: number; page_size: number }>(
    "/admin/membership-levels/list",
    { params }
  );

/** 创建等级 */
export const createMembershipLevel = (body: {
  code: string;
  name: string;
  description?: string;
  rank: number;
  is_public?: boolean;
  is_active?: boolean;
  plans?: { period: "week" | "month"; price: string; bonus_amount?: string; is_active?: boolean }[];
  group_ids?: number[];
}) => post<AdminMembershipLevel>("/admin/membership-levels/create", body);

/** 更新等级 */
export const updateMembershipLevel = (body: {
  level_id: string;
  name?: string;
  description?: string;
  rank?: number;
  is_public?: boolean;
  is_active?: boolean;
  group_ids?: number[];
}) => post<AdminMembershipLevel>("/admin/membership-levels/update", body);

/** 启用或停用等级 */
export const updateMembershipLevelStatus = (body: { level_id: string; is_active: boolean }) =>
  post<AdminMembershipLevel>("/admin/membership-levels/update-status", body);

/** 删除等级 */
export const deleteMembershipLevel = (body: { level_id: string }) =>
  post<{ success: boolean }>("/admin/membership-levels/delete", body);

/* ---------------- 管理端：会员套餐 ---------------- */

/** 创建套餐 */
export const createMembershipPlan = (body: {
  level_id: string;
  period: "week" | "month";
  price: string;
  bonus_amount?: string;
  is_active?: boolean;
}) => post<AdminMembershipPlan>("/admin/membership-plans/create", body);

/** 更新套餐 */
export const updateMembershipPlan = (body: {
  plan_id: string;
  price?: string;
  bonus_amount?: string;
}) => post<AdminMembershipPlan>("/admin/membership-plans/update", body);

/** 启用或停用套餐 */
export const updateMembershipPlanStatus = (body: { plan_id: string; is_active: boolean }) =>
  post<AdminMembershipPlan>("/admin/membership-plans/update-status", body);

/** 删除套餐 */
export const deleteMembershipPlan = (body: { plan_id: string }) =>
  post<{ success: boolean }>("/admin/membership-plans/delete", body);

/* ---------------- 管理端：用户会员 ---------------- */

/** 用户会员列表项 */
export type UserMembershipItem = {
  id: string;
  user_id: string;
  level_id: string;
  level_code: string;
  level_name: string;
  started_at: string;
  expires_at: string;
  is_active: boolean;
};

/** 查询用户会员列表 */
export const listUserMemberships = (params?: {
  user_id?: string;
  level_id?: string;
  is_active?: boolean;
  page?: number;
  page_size?: number;
}) =>
  get<{ items: UserMembershipItem[]; total: number; page: number; page_size: number }>(
    "/admin/user-memberships/list",
    { params }
  );

/** 会员流水记录 */
export type MembershipRecord = {
  id: string;
  user_id: string;
  source: "purchase" | "purchase_converted" | "admin_grant" | "admin_revoke";
  level_id: string;
  level_name: string;
  plan_id: string | null;
  quantity: number;
  expires_before: string | null;
  expires_after: string | null;
  bonus_amount: string;
  recharge_order_id: string | null;
  operator_id: string | null;
  reason: string;
  created_at: string;
};

/** 查询会员流水 */
export const listMembershipRecords = (params?: {
  user_id?: string;
  page?: number;
  page_size?: number;
}) =>
  get<{ items: MembershipRecord[]; total: number; page: number; page_size: number }>(
    "/admin/user-memberships/records/list",
    { params }
  );

/** 授予会员 */
export const grantMembership = (body: {
  user_id: string;
  plan_id: string;
  quantity?: number;
  grant_bonus?: boolean;
  reason?: string;
}) => post<UserMembershipItem>("/admin/user-memberships/grant", body);

/** 撤销会员 */
export const revokeMembership = (body: { user_id: string; reason?: string }) =>
  post<UserMembershipItem>("/admin/user-memberships/revoke", body);

/* ---------------- 支付订单相关（会员字段） ---------------- */

/** 已支付订单中的会员购买结果 */
export type OrderMembershipResult = {
  source: "purchase" | "purchase_converted";
  level_id: string;
  level_name: string;
  expires_before: string | null;
  expires_after: string | null;
  bonus_amount: string;
};

/** 已支付订单列表项（含会员字段） */
export type PaidOrderWithMembership = {
  order_no: string;
  order_type: "recharge" | "membership";
  membership_plan_id: string | null;
  membership: OrderMembershipResult | null;
  topup_amount: string;
  pay_amount: string;
  payment_channel: string;
  payment_method: string;
  paid_at: string;
};

/** 查询订单状态（含会员字段） */
export type OrderDetail = {
  order_no: string;
  status: string;
  topup_amount: string;
  pay_amount: string;
  currency: string;
  order_type: "recharge" | "membership";
  membership_plan_id: string | null;
};
