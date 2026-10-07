/**
 * chat-canvas 节点内容生成（平台 /v1 调用面，OpenAI 兼容格式，与操练场同链路）
 *
 * - 鉴权：节点 data.apiKeyId（空取密钥列表第一个）→ resolveApiKeyToken 解析出 sk- 明文作为 Bearer Token
 * - 模型：节点 data.model 为 `供应商ID::原始模型名`（空取该能力在模型广场的第一个）
 * - image：无参考图 POST /images/generations；有参考图 POST /images/edits（multipart，image 重复字段）
 * - text：/chat/completions SSE 流式（streamChatCompletion），count > 1 时并发多路
 * - video：POST /videos 创建任务 → 轮询至终态 → 拉取成品转 dataURL（任务 ID 持久化，中断后可恢复轮询）
 * - audio：POST /audio/speech，二进制转 dataURL
 * - 运行控制：每节点一个 AbortController，对应"运行中点击停止、否则提交"
 *
 * 约定：
 * - image 返回全部结果（urls，url 为首个）
 * - 二进制结果（图/视/音）统一转成 dataURL，与节点上传行为保持一致
 * - image / video 支持 referenceImages：多上游图片节点的参考图（dataURL / URL）
 */
import { ApiError, post } from '@/lib/request';
import { streamChatCompletion } from '@/lib/chat';
import { createVideoTask as createPlatformVideoTask, isSuccessStatus, pollVideoTask } from '@/lib/videos';
import { resolveApiKeyToken, type ApiKeyOption } from '@/lib/api-keys';
import type { ModelInfo } from '@/lib/types';
import { CHANNEL_MODEL_SEPARATOR, type ModelCapability } from '@/stores/use-canvas-config-store';
import { CANVAS_ERROR, CanvasApiError } from './errors';

/* ---------------- 节点输入（各节点 data 的结构子集，调用方直接传 data 即可） ---------------- */

export type GenerateImageInput = {
    prompt: string;
    model: string;
    /** 选中的 API 密钥 id（空则取密钥列表第一个） */
    apiKeyId?: string;
    ratio: string;
    width: number;
    height: number;
    transparent: boolean;
    count: number;
    /** 上游图片节点参考图（dataURL / http URL），多张 */
    referenceImages?: string[];
};

export type GenerateTextInput = {
    prompt: string;
    model: string;
    apiKeyId?: string;
    reasoning: string;
    count: number;
};

export type GenerateVideoInput = {
    prompt: string;
    model: string;
    apiKeyId?: string;
    ratio: string;
    width: number;
    height: number;
    seconds: number;
    /** 上游图片节点参考图（dataURL / http URL），多张 */
    referenceImages?: string[];
    /** 上游视频节点参考视频（dataURL / http URL），多张 */
    referenceVideos?: string[];
    /** 上游音频节点参考音频（dataURL / http URL），多张 */
    referenceAudios?: string[];
};

export type GenerateAudioInput = {
    prompt: string;
    model: string;
    apiKeyId?: string;
    voice: string;
    format: string;
    speed: number;
    instructions: string;
};

export type NodeGenerateResult =
    | { capability: 'image'; url: string; urls: string[] }
    | { capability: 'text'; text: string; texts: string[] }
    | { capability: 'video'; url: string }
    | { capability: 'audio'; url: string };

/* ---------------- 模型与密钥解析 ---------------- */

/** 模型选项值（与节点下拉一致）：`供应商ID::原始模型名` */
const modelValueOf = (m: ModelInfo) => `${m.providerId ?? 'marketplace'}${CHANNEL_MODEL_SEPARATOR}${m.provider}`;

/** 解析节点模型：空值回退到该能力在模型广场的第一个；返回原始模型名（/v1 请求的 model 字段） */
function resolveModelName(capability: ModelCapability, models: ModelInfo[], modelValue: string): string {
    const value = modelValue || models.filter(m => m.category === capability).map(modelValueOf)[0] || '';
    return value.split(CHANNEL_MODEL_SEPARATOR).pop() || '';
}

/** 解析生效密钥的 sk- 明文：空值回退到密钥列表第一个（resolveApiKeyToken 内部带内存缓存） */
function resolveToken(apiKeys: ApiKeyOption[], apiKeyId?: string): Promise<string> {
    return resolveApiKeyToken(apiKeyId || apiKeys[0]?.value || '', apiKeys);
}

/* ---------------- 提交校验 ---------------- */

/** 提示词非空且未在运行中（对应面板 submit 的拦截逻辑） */
export function canSubmitGenerate(prompt: string, isRunning: boolean): boolean {
    return Boolean(prompt.trim()) && !isRunning;
}

/* ---------------- 请求工具 ---------------- */

/** 从请求错误中提取可读信息（CanvasApiError 携带错误代码，其余原样透传 message） */
function readRequestError(error: unknown): CanvasApiError | Error {
    if (error instanceof CanvasApiError) return error;
    if (error instanceof ApiError) {
        if (error.status === 401 || error.status === 403) return new CanvasApiError(CANVAS_ERROR.API_KEY_INVALID);
        return new Error(error.message);
    }
    return error instanceof Error ? error : new CanvasApiError(CANVAS_ERROR.REQUEST_FAILED);
}

/** 判断是否为"用户停止/中断"导致的错误（取消时不作为失败提示） */
export function isGenerateCancel(error: unknown): boolean {
    return error instanceof Error && (error.name === 'AbortError' || error.message === 'canceled' || error.message === 'Aborted');
}

function blobToDataUrl(blob: Blob): Promise<string> {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result as string);
        reader.onerror = () => reject(reader.error ?? new CanvasApiError(CANVAS_ERROR.READ_RESULT_FAILED));
        reader.readAsDataURL(blob);
    });
}

/** 参考素材转 Blob：dataURL 直接转换；http(s) URL 拉取 */
async function referenceToBlob(ref: string, signal?: AbortSignal): Promise<Blob> {
    const res = await fetch(ref, { signal });
    if (!res.ok) throw new CanvasApiError(CANVAS_ERROR.REFERENCE_IMAGE_FAILED);
    return res.blob();
}

/* ---------------- 各能力生成 ---------------- */

/** 文生图：无参考图走 POST /images/generations；有参考图走 POST /images/edits（multipart，image 重复字段）。返回全部结果（b64_json 转 dataURL） */
export async function generateImage(
    model: string,
    token: string,
    input: GenerateImageInput,
    signal?: AbortSignal,
): Promise<string[]> {
    const pickAll = (data?: Array<{ b64_json?: string; url?: string }>) => {
        const urls = (data ?? []).map(d => (d.b64_json ? `data:image/png;base64,${d.b64_json}` : d.url)).filter((u): u is string => Boolean(u));
        if (!urls.length) throw new CanvasApiError(CANVAS_ERROR.NO_IMAGE_RETURNED);
        return urls;
    };
    try {
        const references = (input.referenceImages ?? []).filter(Boolean);
        if (references.length) {
            const form = new FormData();
            form.set('model', model);
            form.set('prompt', input.prompt.trim());
            form.set('n', String(Math.max(1, input.count || 1)));
            form.set('size', `${input.width}x${input.height}`);
            form.set('response_format', 'b64_json');
            if (input.transparent) form.set('background', 'transparent');
            const blobs = await Promise.all(references.map(ref => referenceToBlob(ref, signal)));
            blobs.forEach((blob, i) => form.append('image', blob, `reference-${i + 1}.png`));
            const data = await post<{ data?: Array<{ b64_json?: string; url?: string }> }>('/images/edits', form, {
                apiKind: 'v1',
                bearerToken: token,
                timeoutMs: 300_000,
                signal,
            });
            return pickAll(data.data);
        }
        const data = await post<{ data?: Array<{ b64_json?: string; url?: string }> }>(
            '/images/generations',
            {
                model,
                prompt: input.prompt.trim(),
                n: Math.max(1, input.count || 1),
                size: `${input.width}x${input.height}`,
                ...(input.transparent ? { background: 'transparent' } : {}),
            },
            { apiKind: 'v1', bearerToken: token, timeoutMs: 300_000, signal },
        );
        return pickAll(data.data);
    } catch (error) {
        if (isGenerateCancel(error)) throw error;
        throw readRequestError(error);
    }
}

/** 文本生成：/chat/completions SSE 流式聚合；count > 1 时并发多路流 */
export async function generateText(
    model: string,
    token: string,
    input: GenerateTextInput,
    signal?: AbortSignal,
): Promise<string[]> {
    const count = Math.max(1, input.count || 1);
    const once = async () => {
        let content = '';
        await streamChatCompletion(
            {
                model,
                messages: [{ role: 'user', content: input.prompt.trim() }]
            },
            { bearerToken: token, onDelta: d => { if (d.content) content += d.content; }, signal },
        );
        return content.trim();
    };
    try {
        const texts = (await Promise.all(Array.from({ length: count }, once))).filter(Boolean);
        if (!texts.length) throw new CanvasApiError(CANVAS_ERROR.NO_TEXT_RETURNED);
        return texts;
    } catch (error) {
        if (isGenerateCancel(error)) throw error;
        throw readRequestError(error);
    }
}

/** 语音合成：POST /audio/speech，二进制转 dataURL */
export async function generateAudio(
    model: string,
    token: string,
    input: GenerateAudioInput,
    signal?: AbortSignal,
): Promise<string> {
    try {
        const res = await fetch('/v1/audio/speech', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
            body: JSON.stringify({
                model,
                input: input.prompt.trim(),
                voice: input.voice,
                response_format: input.format,
                speed: input.speed,
                ...(input.instructions.trim() ? { instructions: input.instructions.trim() } : {}),
            }),
            signal,
        });
        if (!res.ok) {
            if (res.status === 401 || res.status === 403) throw new CanvasApiError(CANVAS_ERROR.API_KEY_INVALID);
            throw new CanvasApiError(CANVAS_ERROR.HTTP_ERROR, { status: res.status });
        }
        return await blobToDataUrl(await res.blob());
    } catch (error) {
        if (isGenerateCancel(error)) throw error;
        throw readRequestError(error);
    }
}

/* ---------------- minimax_h3 视频尺寸表 ---------------- */

/** minimax_h3 标准画布尺寸表：比例 → 清晰度 → [宽, 高]（与官方对比图一致） */
export const H3_SIZE_TABLE: Record<string, Record<string, [number, number]>> = {
    '16:9': { '480P': [864, 480], '768P': [1376, 768], '1080P': [1920, 1088] },
    '9:16': { '480P': [480, 864], '768P': [768, 1376], '1080P': [1088, 1920] },
    '1:1': { '480P': [640, 640], '768P': [1024, 1024], '1080P': [1440, 1440] },
    '2:3': { '480P': [544, 800], '768P': [832, 1248], '1080P': [1184, 1760] },
    '3:2': { '480P': [800, 544], '768P': [1248, 832], '1080P': [1760, 1184] },
    '3:4': { '480P': [576, 736], '768P': [896, 1184], '1080P': [1248, 1664] },
    '4:3': { '480P': [736, 576], '768P': [1184, 896], '1080P': [1664, 1248] },
    '21:9': { '480P': [992, 416], '768P': [1568, 672], '1080P': [2208, 960] },
};

/** 反查宽高在表中的清晰度与比例；不在表内返回 null */
export function findH3Size(w: number, h: number): { q: string; r: string } | null {
    for (const [r, qs] of Object.entries(H3_SIZE_TABLE)) {
        for (const [q, wh] of Object.entries(qs)) {
            if (wh[0] === w && wh[1] === h) return { q, r };
        }
    }
    return null;
}

/* ---------------- 视频任务 ---------------- */

/** 视频生成第一步：POST /videos 创建任务，返回任务 ID（供节点持久化，中断后可凭此恢复轮询） */
async function startVideoTask(
    model: string,
    token: string,
    input: GenerateVideoInput,
    signal?: AbortSignal,
): Promise<string> {
    try {
        // 视频统一按 minimax_h3 工作流模型处理（当前模型广场视频模型均为 H3，不再按模型名区分）：
        // 需指定文生视频工作流；同时校验尺寸，不在支持表内时自动对齐到 768P·16:9
        let { width, height } = input;
        if (!findH3Size(width, height)) {
            width = 1376;
            height = 768;
        }
        // 有参考素材时按 multipart 提交
        const references = (input.referenceImages ?? []).filter(Boolean);
        const refVideos = (input.referenceVideos ?? []).filter(Boolean);
        const refAudios = (input.referenceAudios ?? []).filter(Boolean);
        if (references.length || refVideos.length || refAudios.length) {
            const form = new FormData();
            form.set('model', model);
            form.set('prompt', input.prompt.trim());
            form.set('size', `${width}x${height}`);
            form.set('seconds', String(Math.max(1, input.seconds || 1)));
            // 参考图：单张/多张统一走 images[] 重复字段
            const blobs = await Promise.all(references.slice(0, 7).map(ref => referenceToBlob(ref, signal)));
            blobs.forEach((blob, i) => form.append('images[]', blob, `reference-${i + 1}.png`));
            // 参考视频：reference_videos 重复字段
            const videoRefs = refVideos.slice(0, 3);
            if (videoRefs.length) {
                const videoBlobs = await Promise.all(videoRefs.map(ref => referenceToBlob(ref, signal)));
                videoBlobs.forEach((blob, i) => form.append('reference_videos', blob, `reference-video-${i + 1}.mp4`));
            }
            // 参考音频：reference_audios 重复字段
            const audioRefs = refAudios.slice(0, 3);
            if (audioRefs.length) {
                const audioBlobs = await Promise.all(audioRefs.map(ref => referenceToBlob(ref, signal)));
                audioBlobs.forEach((blob, i) => form.append('reference_audios', blob, `reference-audio-${i + 1}.mp3`));
            }
            const task = await createPlatformVideoTask(token, form);
            if (!task.id) throw new CanvasApiError(CANVAS_ERROR.NO_TASK_ID_RETURNED);
            return task.id;
        }
        const task = await createPlatformVideoTask(token, {
            model,
            prompt: input.prompt.trim(),
            size: `${width}x${height}`,
            seconds: String(Math.max(1, input.seconds || 1)),
        });
        if (!task.id) throw new CanvasApiError(CANVAS_ERROR.NO_TASK_ID_RETURNED);
        return task.id;
    } catch (error) {
        if (isGenerateCancel(error)) throw error;
        throw readRequestError(error);
    }
}

/** 拉取视频成品并转 dataURL（原生 <video src> 无法携带 Authorization，fetch 成 Blob 后转换） */
async function fetchVideoDataUrl(taskId: string, token: string, signal?: AbortSignal): Promise<string> {
    const res = await fetch(`/v1/videos/${taskId}/content`, { headers: { Authorization: `Bearer ${token}` }, signal });
    if (!res.ok) throw new CanvasApiError(CANVAS_ERROR.VIDEO_NO_CONTENT);
    return blobToDataUrl(await res.blob());
}

/** 视频生成：创建任务 → 轮询至终态 → 拉取内容转 dataURL；onTaskCreated 在拿到任务 ID 时回调（供节点持久化） */
export async function generateVideo(
    model: string,
    token: string,
    input: GenerateVideoInput,
    signal?: AbortSignal,
    onTaskCreated?: (taskId: string) => void,
): Promise<string> {
    const taskId = await startVideoTask(model, token, input, signal);
    onTaskCreated?.(taskId);
    const task = await pollVideoTask(taskId, { bearerToken: token, signal });
    if (!isSuccessStatus(task.status)) {
        throw task.error ? new Error(task.error) : new CanvasApiError(CANVAS_ERROR.VIDEO_FAILED);
    }
    return fetchVideoDataUrl(taskId, token, signal);
}

/** 恢复视频任务：离开画布中断轮询后，凭节点保存的任务 ID 继续查询生成结果 */
export async function resumeVideoTask(options: {
    taskId: string;
    apiKeys: ApiKeyOption[];
    apiKeyId?: string;
    signal?: AbortSignal;
}): Promise<string> {
    const token = await resolveToken(options.apiKeys, options.apiKeyId);
    const task = await pollVideoTask(options.taskId, { bearerToken: token, signal: options.signal });
    if (!isSuccessStatus(task.status)) {
        throw task.error ? new Error(task.error) : new CanvasApiError(CANVAS_ERROR.VIDEO_FAILED);
    }
    return fetchVideoDataUrl(options.taskId, token, options.signal);
}

/* ---------------- 统一入口 ---------------- */

/** 根据提示词生成节点内容：校验 → 解析模型/密钥 → 按能力分发，结果由调用方回写节点 data */
export async function generateNodeContent(options: {
    capability: ModelCapability;
    data: GenerateImageInput | GenerateTextInput | GenerateVideoInput | GenerateAudioInput;
    /** 模型广场列表（模型未选时回退到该能力第一个模型） */
    models: ModelInfo[];
    /** 用户 API 密钥列表（密钥未选时回退到第一个） */
    apiKeys: ApiKeyOption[];
    signal?: AbortSignal;
    /** 视频任务创建成功回调：任务 ID 由调用方持久化到节点 data，用于中断后恢复轮询 */
    onVideoTaskId?: (taskId: string) => void;
}): Promise<NodeGenerateResult> {
    const { capability, data, models, apiKeys, signal } = options;
    if (!canSubmitGenerate(data.prompt, Boolean(signal?.aborted))) throw new CanvasApiError(CANVAS_ERROR.PROMPT_REQUIRED);
    const model = resolveModelName(capability, models, data.model);
    if (!model) throw new CanvasApiError(CANVAS_ERROR.MISSING_CHANNEL);
    const token = await resolveToken(apiKeys, data.apiKeyId);

    switch (capability) {
        case 'image': {
            const urls = await generateImage(model, token, data as GenerateImageInput, signal);
            return { capability, url: urls[0], urls };
        }
        case 'text': {
            const texts = await generateText(model, token, data as GenerateTextInput, signal);
            return { capability, text: texts[0], texts };
        }
        case 'video':
            return { capability, url: await generateVideo(model, token, data as GenerateVideoInput, signal, options.onVideoTaskId) };
        case 'audio':
            return { capability, url: await generateAudio(model, token, data as GenerateAudioInput, signal) };
    }
}

/* ---------------- 运行控制（对应"运行中点击停止、否则提交"） ---------------- */

export type NodeGenerateController = {
    isRunning: (nodeId: string) => boolean;
    stop: (nodeId: string) => void;
    run: (nodeId: string, task: (signal: AbortSignal) => Promise<void>) => Promise<void>;
    toggle: (nodeId: string, task: (signal: AbortSignal) => Promise<void>) => void;
};

/** 每节点一个 AbortController；toggle 对应原面板 isRunning ? onStop : submit 的交互 */
export function createNodeGenerateController(): NodeGenerateController {
    const running = new Map<string, AbortController>();
    const stop = (nodeId: string) => {
        running.get(nodeId)?.abort();
        running.delete(nodeId);
    };
    const controller: NodeGenerateController = {
        isRunning: nodeId => running.has(nodeId),
        stop,
        async run(nodeId, task) {
            if (running.has(nodeId)) return; // 运行中重复提交直接忽略
            const aborter = new AbortController();
            running.set(nodeId, aborter);
            try {
                await task(aborter.signal);
            } finally {
                if (running.get(nodeId) === aborter) running.delete(nodeId);
            }
        },
        toggle(nodeId, task) {
            if (running.has(nodeId)) stop(nodeId);
            else void controller.run(nodeId, task);
        },
    };
    return controller;
}
