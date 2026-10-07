/**
 * 用户 API 密钥（与操练场同源）：列表 + 按需解析明文。
 * - 列表不含明文，明文通过 /user/token/copy 按需获取，仅缓存在内存（不落盘）
 * - /v1 调用面仅接受 sk- 开头的长期 API Token（登录 JWT 会 401）
 */
import { get } from "@/lib/request";

export type ApiKeyOption = { value: string; label: string; token: string };

/** 归一化密钥列表：仅保留生效中的密钥 */
function normalizeKeys(data: unknown): ApiKeyOption[] {
  const raw: unknown[] = Array.isArray(data)
    ? data
    : (((data as Record<string, unknown>)?.items ??
        (data as Record<string, unknown>)?.list ??
        (data as Record<string, unknown>)?.tokens ??
        []) as unknown[]);
  return raw.flatMap((item) => {
    const d = (item ?? {}) as Record<string, unknown>;
    const enabled = Boolean(
      d.is_active ?? d.enabled ?? (d.disabled_at ? false : true)
    );
    if (!enabled || d.is_del === true) return [];
    const prefix = (d.key_prefix as string) || "";
    const label = (d.label as string) || (prefix ? `${prefix}…` : "");
    return [
      {
        value: String(d.id ?? d.token_id ?? ""),
        label,
        token: (d.token ?? d.api_key ?? d.key ?? "") as string,
      },
    ];
  });
}

/** 拉取当前用户的可用密钥列表 */
export async function getApiKeys(): Promise<ApiKeyOption[]> {
  try {
    const data = await get<unknown>("/user/token/list", {
      params: { page: 1, page_size: 100 },
    });
    return normalizeKeys(data);
  } catch {
    return [];
  }
}

/** 已解析的密钥明文缓存：key id → token（仅内存） */
const tokenCache = new Map<string, string>();

/** 按需解析密钥明文：优先列表自带/内存缓存，否则调用 /user/token/copy */
export async function resolveApiKeyToken(
  keyId: string,
  keys: ApiKeyOption[]
): Promise<string> {
  const key = keys.find((item) => item.value === keyId);
  if (!key) throw new Error("请选择 API 密钥");
  if (key.token) return key.token;
  const cached = tokenCache.get(keyId);
  if (cached) return cached;
  const data = await get<{ token?: string }>("/user/token/copy", {
    params: { token_id: key.value },
  });
  const token = data?.token ?? "";
  if (!token) throw new Error("未获取到 API 密钥");
  tokenCache.set(keyId, token);
  return token;
}
