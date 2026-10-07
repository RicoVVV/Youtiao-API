/**
 * 用户模型并发覆盖（/api/admin/user-model-concurrency）
 * 并发按 user_id + model_id 独立统计：启用的用户覆盖值直接替代模型默认值
 */

import { get, post } from "@/lib/request";

export type UserModelConcurrencyOverride = {
  id: string;
  user_id: string;
  model_id: string;
  concurrency_limit: number;
  active: boolean;
};

export type UserModelConcurrencyUsage = {
  user_id: string;
  /** 仅包含已创建的用户覆盖记录；模型默认值不会展开成列表项 */
  items: UserModelConcurrencyOverride[];
  /** 键为模型 ID，值为该用户该模型的活跃任务数；缺失时表示 0 */
  active_lease_counts: Record<string, number>;
};

export type UpdateUserModelConcurrencyPayload = {
  user_id: string;
  model_id: string;
  /** 0 表示禁止该用户创建该模型任务，1-10000 为允许的最大在途任务数 */
  concurrency_limit: number;
  /** 停用后回退到模型默认值 */
  active: boolean;
};

export function getUserModelConcurrency(userId: string) {
  return get<UserModelConcurrencyUsage>("/admin/user-model-concurrency/list", {
    params: { user_id: userId },
  });
}

/** 创建或更新覆盖：同一接口；停用即传 active: false，恢复为模型默认值 */
export function updateUserModelConcurrency(
  payload: UpdateUserModelConcurrencyPayload
) {
  return post<UserModelConcurrencyOverride>(
    "/admin/user-model-concurrency/update",
    payload
  );
}
