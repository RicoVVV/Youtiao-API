/**
 * 邀请返利（Affiliate）接口封装
 * - 用户查询：GET  /api/affiliate/detail
 * - 被邀请人列表：GET /api/affiliate/invitees/list
 * - 返利流水：GET /api/affiliate/records/list
 * - 转入余额：POST /api/affiliate/quota/transfer
 *
 * 详见 docs/AFFILIATE_FRONTEND_INTEGRATION.md
 */

import { get, post } from "@/lib/request";

/** 被邀请人摘要 */
export type AffiliateInvitee = {
  user_id: string;
  /** 脱敏后的用户名 */
  username: string;
  created_at: string;
  /** 该被邀请人累计贡献的返利 */
  total_rebate: string;
};

/** 邀请详情（首次访问会懒创建邀请档案） */
export type AffiliateDetail = {
  /** 邀请返利总开关 */
  enabled: boolean;
  /** 当前用户邀请码 */
  aff_code: string;
  /** 邀请链接；站点未配置公开地址时为相对路径 */
  invite_url: string;
  /** 当前用户作为邀请人的有效比例（百分比字符串，如 "20.00"） */
  effective_rebate_rate_percent: string;
  /** 已绑定被邀请人数量 */
  aff_count: number;
  /** 可转入余额的返利额度 */
  available_quota: string;
  /** 冻结中的返利额度 */
  frozen_quota: string;
  /** 累计返利总额 */
  history_quota: string;
  /** 被邀请人注册可得的赠送额度（USD 字符串），0 表示不赠送 */
  signup_bonus: string;
  /** 最近 20 个被邀请人摘要 */
  invitees: AffiliateInvitee[];
};

export type AffiliateListResponse<T> = {
  items: T[];
  total: number;
  page: number;
  page_size: number;
};

/** 返利流水 */
export type AffiliateRecord = {
  id: string;
  /** accrue 返利产生，transfer 转入余额 */
  action: "accrue" | "transfer";
  amount: string;
  /** 脱敏后的被邀请人用户名；transfer 为空 */
  source_username: string | null;
  /** 来源充值/会员订单号；transfer 为空 */
  order_no: string | null;
  created_at: string;
};

/** 转入余额响应 */
export type AffiliateTransferResult = {
  transferred_quota: string;
  balance: string;
};

/** 查询邀请详情 */
export function getAffiliateDetail() {
  return get<AffiliateDetail>("/affiliate/detail");
}

/** 被邀请人列表 */
export function getAffiliateInvitees(page: number, pageSize: number) {
  return get<AffiliateListResponse<AffiliateInvitee>>(
    `/affiliate/invitees/list?page=${page}&page_size=${pageSize}`
  );
}

/** 返利流水 */
export function getAffiliateRecords(page: number, pageSize: number) {
  return get<AffiliateListResponse<AffiliateRecord>>(
    `/affiliate/records/list?page=${page}&page_size=${pageSize}`
  );
}

/** 全部可用返利转入余额 */
export function transferAffiliateQuota() {
  return post<AffiliateTransferResult>("/affiliate/quota/transfer");
}
