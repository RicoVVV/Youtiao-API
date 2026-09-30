/**
 * 统一请求封装
 * - 浏览器端走同源 /api 前缀，由 next.config.ts 重写代理到后端，避免跨域
 * - 服务端（RSC / Route Handler）直连 API_BASE_URL
 * - 自动携带 JSON 头与访问令牌（Authorization: Bearer）
 * - 401 时自动无感刷新访问令牌并重试一次；刷新失败则清空登录态并跳转登录页
 *
 * 使用方式：
 *   import { get, post } from "@/lib/request";
 *   const models = await get<ModelInfo[]>("/models");
 *   const res = await post<TokenResponse>("/auth/login", { username, password });
 */

export const USE_MOCK = process.env.NEXT_PUBLIC_USE_MOCK === "true";

/** 后端接口统一前缀，调用方只写 / 开头的资源路径 */
const API_PREFIX = "/api";

const BASE = typeof window === "undefined" ? `${process.env.API_BASE_URL}${API_PREFIX}` : API_PREFIX;

/* ---------------- 访问令牌管理 ---------------- */

const TOKEN_KEY = "token";
/** 用户名缓存 key：首屏即时渲染头像，避免闪烁登录按钮 */
const USERNAME_KEY = "username";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

/** 保存访问令牌：localStorage 供请求头使用，cookie 供服务端/中间件判断登录态 */
export function setToken(token: string) {
  if (typeof window === "undefined") return;
  localStorage.setItem(TOKEN_KEY, token);
  document.cookie = `${TOKEN_KEY}=${token}; path=/`;
}

/** 清空登录态：令牌 + 用户名/用户信息缓存 */
export function clearToken() {
  if (typeof window === "undefined") return;
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USERNAME_KEY);
  localStorage.removeItem(PROFILE_KEY);
  document.cookie = `${TOKEN_KEY}=; path=/; max-age=0`;
}

export function getCachedUsername(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(USERNAME_KEY);
}

export function setCachedUsername(username: string) {
  if (typeof window === "undefined") return;
  localStorage.setItem(USERNAME_KEY, username);
}

/* ---------------- 当前用户信息缓存（首屏免请求） ---------------- */

/** 缓存的用户信息：切换进入控制台时侧边栏即时渲染管理员分组，避免闪烁 */
export type CachedProfile = {
  username: string;
  is_admin: boolean;
};

const PROFILE_KEY = "profile";

/** 读取缓存的用户信息；仅客户端可访问 */
export function getCachedProfile(): CachedProfile | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = localStorage.getItem(PROFILE_KEY);
    return raw ? (JSON.parse(raw) as CachedProfile) : null;
  } catch {
    return null;
  }
}

export function setCachedProfile(profile: CachedProfile) {
  if (typeof window === "undefined") return;
  localStorage.setItem(PROFILE_KEY, JSON.stringify(profile));
}

function clearCachedProfile() {
  if (typeof window === "undefined") return;
  localStorage.removeItem(PROFILE_KEY);
}

/* ---------------- 超时辅助 ---------------- */

/** 带超时的 fetch，防止服务端无响应时请求永远挂起 */
function fetchWithTimeout(
  input: RequestInfo | URL,
  init?: RequestInit,
  ms = 15_000
): Promise<Response> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), ms);
  return fetch(input, { ...init, signal: ctrl.signal }).finally(() =>
    clearTimeout(timer)
  );
}

/* ---------------- 无感刷新（单飞：并发 401 共享同一次刷新） ---------------- */

let refreshPromise: Promise<void> | null = null;

async function doRefresh(): Promise<void> {
  const url = `${BASE}/auth/refresh`;
  const res = await fetchWithTimeout(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: "{}",
    credentials: "include",
  });
  if (!res.ok) throw new Error(`刷新失败: ${res.status}`);
  const data = unwrap<{ access_token: string }>(await res.json());
  setToken(data.access_token);
}

function refreshOnce(): Promise<void> {
  if (!refreshPromise) {
    refreshPromise = doRefresh().finally(() => {
      refreshPromise = null;
    });
  }
  return refreshPromise;
}

/* ---------------- 请求核心 ---------------- */

export type RequestOptions = Omit<RequestInit, "method" | "body"> & {
  /** URL 查询参数，自动拼接到 path 后（undefined 会被忽略） */
  params?: Record<string, string | number | boolean | undefined>;
  /** Next.js 服务端缓存配置 */
  next?: { revalidate?: number };
  /** OpenAI 兼容调用面（/v1 前缀）；默认走管理/账户面（/api 前缀）；admin 走 /v1 手动代理规避 30s dev 超时 */
  apiKind?: "api" | "v1" | "admin";
  /** 覆盖默认登录 JWT 的 Bearer 令牌（如用户 API Token），不传则使用登录态 */
  bearerToken?: string;
  /** 请求级超时（毫秒）；未传入时使用默认 15 秒，图片生成等慢请求可覆盖 */
  timeoutMs?: number;
};

/** 请求失败错误：附带 HTTP 状态码与响应体，便于按字段定位（如 422 校验错误 data[].loc） */
export class ApiError extends Error {
  /** HTTP 状态码 */
  status: number;
  /** 后端响应体（统一信封结构） */
  data: unknown;
  /** 请求关联标识 */
  requestId?: string;
  /** 429 限流时响应头 Retry-After 的秒数（无该头时为 undefined） */
  retryAfter?: number;

  constructor(
    message: string,
    status: number,
    data: unknown,
    requestId?: string,
    retryAfter?: number
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.data = data;
    this.requestId = requestId;
    this.retryAfter = retryAfter;
  }
}

/** 兼容 FastAPI 错误体：{ message } / { detail: string } / { detail: [{ msg }] } / OpenAI 风格 { error: { message } } */
export function pickErrorMessage(data: unknown, fallback: string): string {
  if (data && typeof data === "object") {
    const d = data as Record<string, unknown>;
    if (typeof d.message === "string") return d.message;
    if (typeof d.detail === "string") return d.detail;
    if (Array.isArray(d.detail)) {
      const first = d.detail[0] as { msg?: string } | undefined;
      if (first?.msg) return first.msg;
    }
    // OpenAI 兼容错误信封：{ error: { message, code } }，附带 code 便于定位
    if (d.error && typeof d.error === "object") {
      const e = d.error as { message?: unknown; code?: unknown };
      if (typeof e.message === "string") {
        return typeof e.code === "string" && e.code ? `${e.message} (${e.code})` : e.message;
      }
    }
  }
  return fallback;
}

/** 后端统一响应信封 {code, message, data}：解出业务数据，未包装时原样返回 */
function unwrap<T>(data: unknown): T {
  if (data && typeof data === "object" && "code" in data && "data" in data) {
    return (data as { data: T }).data;
  }
  return data as T;
}

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
  options?: RequestOptions
): Promise<T> {
  const { params, headers: initHeaders, apiKind = "api", bearerToken, timeoutMs, ...rest } = options ?? {};

  // FormData 由浏览器自动带 multipart 边界，不能手动设 Content-Type
  const isFormData = body instanceof FormData;
  const headers = new Headers(initHeaders);
  if (!isFormData && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  // 浏览器端自动携带访问令牌；显式传入 bearerToken（如用户 API Token）时优先
  const token = bearerToken ?? getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  // 携带当前站点语言，后端按 X-Locale > Accept-Language > zh 优先级解析
  if (typeof window !== "undefined" && !headers.has("X-Locale")) {
    const seg = window.location.pathname.split("/")[1];
    headers.set("X-Locale", seg === "en" ? "en" : "zh");
  }

  // 拼接查询参数
  const query = params
    ? Object.entries(params)
        .filter(([, v]) => v !== undefined)
        .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`)
        .join("&")
    : "";
  // 控制面 /api 由 next.config.ts rewrite 代理；/v1 与 /admin 由 app/v1/[...path]/route.ts 手动代理（规避 dev 代理 30s 超时）
  const prefix = apiKind === "v1" ? "/v1" : apiKind === "admin" ? "/v1/admin" : API_PREFIX;
  const base = typeof window === "undefined" ? `${process.env.API_BASE_URL}${prefix}` : prefix;
  const url = `${base}${path}${query ? (path.includes("?") ? "&" : "?") + query : ""}`;

  const exec = () =>
    fetchWithTimeout(
      url,
      {
        ...rest,
        method,
        headers,
        body: body === undefined ? undefined : isFormData ? body : JSON.stringify(body),
        credentials: "include",
      },
      timeoutMs
    );

  let res: Response;
  try {
    res = await exec();
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      // 外部 signal 主动取消（如画布节点停止生成）与内部超时同为 AbortError，需区分
      if (rest.signal?.aborted) throw err;
      throw new Error("请求超时，请检查网络或稍后重试");
    }
    throw err;
  }

  // 访问令牌过期：无感刷新后重试一次（登录/注册等未持令牌的请求不触发；API Token 调用不刷新登录态）
  if (res.status === 401 && token && !bearerToken && typeof window !== "undefined") {
    try {
      await refreshOnce();
    } catch {
      clearToken();
      // 动态引入避免服务端渲染时加载客户端组件
      const { toast } = await import("@/components/ui/toaster");
      toast.warning("登录已过期，请重新登录");
      // 稍作延迟，让用户看到过期提示再跳转；携带来源路径供登录后跳回
      setTimeout(() => {
        const from = encodeURIComponent(window.location.pathname);
        window.location.href = `/login?redirect=${from}`;
      }, 1200);
      throw new Error("登录已过期，请重新登录");
    }
    headers.set("Authorization", `Bearer ${getToken()}`);
    try {
      res = await exec();
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") {
        if (rest.signal?.aborted) throw err;
        throw new Error("请求超时，请检查网络或稍后重试");
      }
      throw err;
    }
  }

  if (!res.ok) {
    const data = await res.json().catch(() => null);
    // 错误日志保留接口响应的 request_id，便于后端定位
    const requestId =
      data && typeof data === "object"
        ? (data as Record<string, unknown>).request_id
        : undefined;
    if (typeof requestId === "string" && requestId) {
      console.error(
        `[API] ${method} ${path} 失败 status=${res.status} request_id=${requestId}`
      );
    }
    throw new ApiError(
      pickErrorMessage(data, `请求失败: ${res.status}`),
      res.status,
      data,
      typeof requestId === "string" && requestId ? requestId : undefined,
      // 429 限流可能带 Retry-After（秒），供调用方做冷却倒计时
      Number(res.headers.get("Retry-After")) || undefined
    );
  }
  // 204 No Content 等空响应
  if (res.status === 204 || res.headers.get("content-length") === "0") {
    return undefined as T;
  }
  return unwrap<T>(await res.json());
}

/** GET 查询 */
export const get = <T>(path: string, options?: RequestOptions) =>
  request<T>("GET", path, undefined, options);

/** POST 创建 / 提交 */
export const post = <T>(path: string, body?: unknown, options?: RequestOptions) =>
  request<T>("POST", path, body, options);

/** PUT 全量更新 */
export const put = <T>(path: string, body?: unknown, options?: RequestOptions) =>
  request<T>("PUT", path, body, options);

/** PATCH 局部更新 */
export const patch = <T>(path: string, body?: unknown, options?: RequestOptions) =>
  request<T>("PATCH", path, body, options);

/** DELETE 删除 */
export const del = <T>(path: string, options?: RequestOptions) =>
  request<T>("DELETE", path, undefined, options);
