/**
 * OpenAI 兼容视频任务接入（/v1 前缀）
 *
 * 路由边界：
 * - 创建任务：POST /v1/videos，使用用户长期 API Token
 * - 查询/轮询/播放：GET /v1/videos/{id}、GET /v1/videos/{id}/content，使用登录态 JWT
 *
 * 安全约束：不得把 API Token 写入日志、埋点、错误消息或浏览器存储。
 */

import { get, getToken, post } from "@/lib/request";

/* ---------------- 类型 ---------------- */

export type VideoTaskStatus =
  | "submit_pending"
  | "queued"
  | "running"
  | "succeeded"
  /** OpenAI 兼容接口返回的成功终态写法 */
  | "completed"
  | "failed"
  | "canceled"
  | string;

export type VideoTask = {
  id: string;
  model: string;
  status: VideoTaskStatus;
  progress: number;
  created_at?: string;
  completed_at?: string | null;
  /** 终态成功时后端返回的成品相对路径，如 /v1/videos/{id}/content */
  media_url?: string | null;
  /** OpenAI 兼容任务查询返回的成品地址（公开或受控路径） */
  result_url?: string | null;
  error?: string | null;
};

/** 成功终态：succeeded / completed（OpenAI 兼容写法） */
export function isSuccessStatus(status: VideoTaskStatus): boolean {
  return status === "succeeded" || status === "completed";
}

/** 判断任务是否已终态（成功 / 失败 / 取消） */
export function isTerminalStatus(status: VideoTaskStatus): boolean {
  return isSuccessStatus(status) || ["failed", "canceled"].includes(status);
}

/* ---------------- 创建任务（API Token） ---------------- */

export type CreateVideoPayload = {
  /** 顶层必填：公开模型名，如 minimax_h3 */
  model: string;
  /** 其余字段必须遵循后台为该模型配置的输入契约 */
  [key: string]: unknown;
};

/**
 * 创建视频任务
 * - apiToken：用户长期 API Token（非登录 JWT），仅作请求头，不存储、不记录
 * - 支持 JSON 或 multipart/FormData（图生视频需上传参考素材字段，如 input_reference）
 * - 创建接口会同步提交上游并做素材归一化/上传，慢于普通接口，超时放宽到 5 分钟
 */
export function createVideoTask(
  apiToken: string,
  payload: CreateVideoPayload | FormData
) {
  return post<VideoTask>("/videos", payload, {
    apiKind: "v1",
    bearerToken: apiToken,
    timeoutMs: 300_000,
  });
}

/* ---------------- 查询与轮询（API Token） ---------------- */

/** 当前用户的视频任务列表 */
export function listVideoTasks(bearerToken?: string) {
  return get<VideoTask[]>("/videos", { apiKind: "v1", bearerToken });
}

/** 单个视频任务详情；/v1 仅接受 sk- API Token，必须传入 bearerToken */
export function getVideoTask(taskId: string, bearerToken?: string) {
  return get<VideoTask>(`/videos/${taskId}`, { apiKind: "v1", bearerToken });
}

export type PollOptions = {
  /** 轮询间隔毫秒，文档建议 2000–5000，默认 3000 */
  intervalMs?: number;
  /** 每次任务快照回调 */
  onUpdate?: (task: VideoTask) => void;
  /** 外部取消信号（页面卸载 / 用户取消） */
  signal?: AbortSignal;
  /** 用户长期 API Token（/v1 仅接受 sk-，登录 JWT 会 401） */
  bearerToken?: string;
};

/**
 * 轮询任务详情直到终态；页面卸载、任务终态或请求取消后停止。
 * 终态任务作为最终结果返回；取消时抛 AbortError。
 */
export async function pollVideoTask(
  taskId: string,
  options?: PollOptions
): Promise<VideoTask> {
  const interval = Math.min(5000, Math.max(2000, options?.intervalMs ?? 3000));
  for (;;) {
    if (options?.signal?.aborted) {
      throw new DOMException("轮询已取消", "AbortError");
    }
    const task = await getVideoTask(taskId, options?.bearerToken);
    options?.onUpdate?.(task);
    if (isTerminalStatus(task.status)) return task;
    await new Promise((resolve, reject) => {
      const timer = setTimeout(resolve, interval);
      options?.signal?.addEventListener(
        "abort",
        () => {
          clearTimeout(timer);
          reject(new DOMException("轮询已取消", "AbortError"));
        },
        { once: true }
      );
    });
  }
}

/* ---------------- 成品播放（fetch + Blob） ---------------- */

/**
 * 拉取需要 Bearer 鉴权的视频成品并转换为 Object URL。
 * 原生 <video src> 无法携带 Authorization，必须 fetch 成 Blob 后播放；
 * 调用方负责在组件卸载时 URL.revokeObjectURL。
 * media_url 为相对路径时使用当前 API 域名（同源代理）拼接。
 */
export async function fetchVideoObjectUrl(mediaUrl: string): Promise<string> {
  const token = getToken();
  const res = await fetch(mediaUrl, {
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
  });
  if (!res.ok) {
    throw new Error("视频成品暂不可用");
  }
  return URL.createObjectURL(await res.blob());
}

/**
 * 按任务 ID 经 /v1 手动代理拉取视频成品，返回 Object URL。
 * /v1 仅接受 sk- API Token；调用方负责卸载时 URL.revokeObjectURL。
 */
export async function fetchVideoContentUrl(taskId: string, bearerToken?: string): Promise<string> {
  const token = bearerToken ?? getToken();
  const res = await fetch(`/v1/videos/${taskId}/content`, {
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
  });
  if (!res.ok) {
    throw new Error("视频成品暂不可用");
  }
  return URL.createObjectURL(await res.blob());
}
