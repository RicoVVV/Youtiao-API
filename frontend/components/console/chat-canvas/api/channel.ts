import axios from 'axios';

import type { ApiCallFormat } from '@/stores/use-canvas-config-store';

export type FetchChannelModelsParams = {
    baseUrl: string;
    apiKey: string;
    apiFormat: ApiCallFormat;
};

/** 拼接 OpenAI 兼容接口地址：baseUrl 末尾自动补 /v1 */
function buildApiUrl(baseUrl: string, path: string) {
    const normalizedBaseUrl = baseUrl.trim().replace(/\/+$/, '');
    const apiBaseUrl = normalizedBaseUrl.toLowerCase().endsWith('/v1') ? normalizedBaseUrl : `${normalizedBaseUrl}/v1`;
    return `${apiBaseUrl}${path}`;
}

/** 拼接 Gemini 模型列表地址：baseUrl 末尾自动补 /v1beta */
function geminiModelsUrl(baseUrl: string) {
    const normalizedBaseUrl = baseUrl.trim().replace(/\/+$/, '');
    const lowerBaseUrl = normalizedBaseUrl.toLowerCase();
    const apiBaseUrl = lowerBaseUrl.endsWith('/v1') || lowerBaseUrl.endsWith('/v1beta') ? normalizedBaseUrl : `${normalizedBaseUrl}/v1beta`;
    return `${apiBaseUrl}/models`;
}

/** 从响应体中提取接口返回的错误信息 */
function readApiError(data: unknown): string {
    if (!data || typeof data !== 'object') return '';
    const payload = data as { error?: { message?: unknown } | string; message?: unknown; msg?: unknown };
    const errorMsg = typeof payload.error === 'string' ? payload.error : payload.error?.message;
    return [errorMsg, payload.message, payload.msg].find((v): v is string => typeof v === 'string' && v !== '') ?? '';
}

/** 从请求错误中提取可读信息 */
function readRequestError(error: unknown): string {
    if (axios.isAxiosError(error)) {
        const apiMsg = readApiError(error.response?.data);
        if (apiMsg) return apiMsg;
        if (error.response?.status === 401 || error.response?.status === 403) return 'API Key 无效或没有权限';
        if (!error.response && error.code === 'ERR_NETWORK') return '网络请求失败，可能存在跨域限制';
        if (error.response) return `请求失败（HTTP ${error.response.status}）`;
        return error.message;
    }
    return error instanceof Error ? error.message : '请求失败';
}

/** 拉取渠道模型列表，返回模型 id 列表（升序）；openai / minimax 走 OpenAI 兼容的 /models 接口 */
export async function fetchChannelModels({ baseUrl, apiKey, apiFormat }: FetchChannelModelsParams): Promise<string[]> {
    try {
        if (apiFormat === 'gemini') {
            const response = await axios.get<{ models?: Array<{ name?: string }>; error?: { message?: string } }>(geminiModelsUrl(baseUrl), {
                headers: { 'x-goog-api-key': apiKey, 'Content-Type': 'application/json' },
            });
            if (response.data.error?.message) throw new Error(response.data.error.message);
            return (response.data.models || [])
                .map(model => model.name?.replace(/^models\//, ''))
                .filter((id): id is string => Boolean(id))
                .sort((a, b) => a.localeCompare(b));
        }
        const response = await axios.get<{ data?: Array<{ id?: string }> }>(buildApiUrl(baseUrl, '/models'), {
            headers: { Authorization: `Bearer ${apiKey}` },
        });
        console.log(response.data);
        return (response.data.data || [])
            .map(model => model.id)
            .filter((id): id is string => Boolean(id))
            .sort((a, b) => a.localeCompare(b));
    } catch (error) {
        throw new Error(readRequestError(error));
    }
}
