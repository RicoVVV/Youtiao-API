"use client";

import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  Bot,
  CheckCircle2,
  Clapperboard,
  Cpu,
  Download,
  ImageIcon,
  KeyRound,
  Loader2,
  Pencil,
  RotateCcw,
  SendHorizonal,
  SlidersHorizontal,
  Sparkles,
  Trash2,
  Upload,
  X,
} from "lucide-react";

import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { toast } from "@/components/ui/toaster";
import { getModelDetail, getModels } from "@/lib/models";
import { get, post } from "@/lib/request";
import { streamChatCompletion, type StreamDelta } from "@/lib/chat";
import { createVideoTask, fetchVideoContentUrl, isSuccessStatus, isTerminalStatus, pollVideoTask, type VideoTask } from "@/lib/videos";
import type { ModelInfo, ModelTemplate, TemplateMaterialField, TemplateParameterProperty } from "@/lib/types";

type MessageUsage = {
  prompt: number;
  completion: number;
  total: number;
};

type Message = {
  role: "user" | "assistant";
  content: string;
  time: string;
  /** 实际出参模型（上游返回），如 gpt-5.6-terra */
  model?: string;
  /** 思考过程（reasoning_content），可折叠展示 */
  reasoning?: string;
  usage?: MessageUsage;
  finishReason?: string;
};

type ImageResponse = {
  data?: Array<{ url?: string; b64_json?: string }>;
};

/** 助手回复的有效载荷：正文 + 元信息（历史只保留 role/content） */
type AssistantPayload = {
  content: string;
  model?: string;
  reasoning?: string;
  usage?: MessageUsage;
  finishReason?: string;
};

type ApiKeyOption = { value: string; label: string; token: string };

type PlaygroundMode = "text" | "image" | "video";
type MediaType = Exclude<PlaygroundMode, "text">;

const now = () => new Date().toLocaleTimeString("zh-CN", { hour12: false });

/** 归一化用户密钥列表：仅保留生效中的密钥；列表不含明文，发送时按需调用 /user/token/copy */
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
    return [{
      value: String(d.id ?? d.token_id ?? ""),
      label,
      token: (d.token ?? d.api_key ?? d.key ?? "") as string,
    }];
  });
}

function getImageUrls(response: ImageResponse) {
  return (response.data ?? []).flatMap((image) => {
    if (image.url) return [image.url];
    if (image.b64_json) return [`data:image/png;base64,${image.b64_json}`];
    return [];
  });
}

/* ---------------- 模型模板动态参数 ---------------- */

type ParamField = {
  name: string;
  schema: TemplateParameterProperty;
  required: boolean;
  /** 素材声明：存在时该字段按文件上传渲染，值随 multipart 提交 */
  material?: TemplateMaterialField;
};

/** 由专属 UI 承载的字段：模型选择器与主提示词输入框，不进入动态参数区 */
const DEDICATED_PARAMS = new Set(["model", "prompt"]);

/** 从模型详情模板提取全部可渲染参数：逐字段跟随 parameters.properties 与 required */
function getParamFields(template: ModelTemplate | null | undefined): ParamField[] {
  const parameters = template?.parameters;
  if (!parameters?.properties) return [];
  const required = new Set(parameters.required ?? []);
  const materials: Record<string, TemplateMaterialField> = template?.material_fields ?? {};
  return Object.entries(parameters.properties)
    .filter(([name]) => !DEDICATED_PARAMS.has(name))
    .map(([name, schema]) => ({
      name,
      schema,
      required: required.has(name),
      ...(materials[name] ? { material: materials[name] } : {}),
    }));
}

/** 参数编辑态：文本值（标量原文、数组与对象为 JSON 文本）与素材已选文件分开保存 */
type ParamTextValues = Record<string, string>;
type ParamFiles = Record<string, File[]>;

/** 素材类别 → input accept，避免用户选到后端会拒绝的格式 */
const MATERIAL_ACCEPT: Record<string, string> = {
  image: "image/*",
  video: "video/*",
  audio: "audio/*",
};

function materialAccept(categories: string[]): string {
  return categories.map((category) => MATERIAL_ACCEPT[category]).filter(Boolean).join(",");
}

/** 参数初值：取调用示例与 schema 默认值；数组与对象序列化为 JSON 文本，素材字段留空待上传 */
function initParamValues(
  template: ModelTemplate | null | undefined,
  fields: ParamField[]
): ParamTextValues {
  const values: ParamTextValues = {};
  const example = template?.example ?? {};
  for (const field of fields) {
    if (field.material) continue;
    const raw = example[field.name] ?? field.schema.default;
    if (raw === undefined || raw === null) continue;
    values[field.name] =
      typeof raw === "object" ? JSON.stringify(raw, null, 2) : String(raw);
  }
  return values;
}

/** 字符串数组字段（如素材地址列表）按「每行一个值」编辑，其余数组与对象走 JSON 文本 */
function isLineList(schema: TemplateParameterProperty): boolean {
  return schema.type === "array" && schema.items?.type === "string";
}

/** 按 schema 类型把编辑态文本转换为请求值；格式与类型不符时返回 null */
function coerceParamValue(field: ParamField, text: string): unknown {
  const { type } = field.schema;
  if (type === "integer" || type === "number") {
    const num = Number(text);
    if (!Number.isFinite(num) || (type === "integer" && !Number.isInteger(num))) return null;
    return num;
  }
  if (type === "boolean") return text === "true";
  if (isLineList(field.schema)) {
    return text
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean);
  }
  if (type === "array" || type === "object") {
    let parsed: unknown;
    try {
      parsed = JSON.parse(text);
    } catch {
      return null;
    }
    if (type === "array") {
      if (!Array.isArray(parsed)) return null;
    } else if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
      return null;
    }
    return parsed;
  }
  return text;
}

type BuiltParams =
  | { ok: true; values: Record<string, unknown>; uploads: Array<{ name: string; file: File }> }
  | { ok: false; error: { name: string; reason: "missing" | "invalid" } };

/** 按字段契约组装请求参数：缺失必填或格式不合法时返回出错字段，交由调用方提示 */
function buildParams(
  fields: ParamField[],
  texts: ParamTextValues,
  files: ParamFiles
): BuiltParams {
  const values: Record<string, unknown> = {};
  const uploads: Array<{ name: string; file: File }> = [];
  for (const field of fields) {
    const selected = files[field.name] ?? [];
    // 素材字段选中文件时以文件提交，忽略同名字段的地址文本（UI 已保证二者互斥）
    if (field.material && selected.length > 0) {
      for (const file of selected) uploads.push({ name: field.name, file });
      continue;
    }
    const text = (texts[field.name] ?? "").trim();
    // 未填写的可选参数不随请求发送，是否必填只由契约声明决定
    if (!text) {
      if (field.required) return { ok: false, error: { name: field.name, reason: "missing" } };
      continue;
    }
    const value = coerceParamValue(field, text);
    if (value === null) return { ok: false, error: { name: field.name, reason: "invalid" } };
    values[field.name] = value;
  }
  return { ok: true, values, uploads };
}

/** multipart 提交：标量按原文写入，数组与对象序列化为 JSON 文本，与后端字段归一化一致 */
function appendFormValues(form: FormData, values: Record<string, unknown>) {
  for (const [name, value] of Object.entries(values)) {
    form.append(
      name,
      typeof value === "object" && value !== null ? JSON.stringify(value) : String(value)
    );
  }
}

/** 契约字段的文本控件：枚举/布尔走 Select，数组与对象走 JSON 文本，数值与字符串按类型输入 */
function ParamTextControl({
  field,
  value,
  ariaLabel,
  onChange,
}: {
  field: ParamField;
  value: string;
  ariaLabel: string;
  onChange: (value: string) => void;
}) {
  const { t } = useTranslation("console");
  const { schema } = field;
  if (schema.type === "array" || schema.type === "object") {
    const lineList = isLineList(schema);
    return (
      <textarea
        aria-label={ariaLabel}
        rows={3}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={
          lineList
            ? t("playground.lineListPlaceholder")
            : schema.type === "array"
              ? t("playground.jsonArrayPlaceholder")
              : t("playground.jsonObjectPlaceholder")
        }
        className={
          lineList
            ? "border-input dark:bg-input/30 w-full resize-y rounded-md border bg-transparent px-3 py-2 text-sm leading-6 shadow-xs outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50"
            : "border-input dark:bg-input/30 w-full resize-y rounded-md border bg-transparent px-3 py-2 font-mono text-xs leading-5 shadow-xs outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50"
        }
      />
    );
  }
  if (schema.enum?.length || schema.type === "boolean") {
    const isBool = schema.type === "boolean";
    const options = (schema.enum ?? ["true", "false"]).map((item) => ({
      value: String(item),
      label: isBool
        ? String(item) === "true"
          ? t("playground.paramTrue")
          : t("playground.paramFalse")
        : String(item),
    }));
    // 可选参数允许清空回「不设置」，避免一旦选择就无法移除
    if (!field.required) options.unshift({ value: "", label: t("playground.paramUnset") });
    return (
      <Select aria-label={ariaLabel} value={value} onValueChange={onChange} options={options} placeholder={t("playground.paramUnset")} />
    );
  }
  const isNumber = schema.type === "integer" || schema.type === "number";
  return (
    <Input
      aria-label={ariaLabel}
      type={isNumber ? "number" : "text"}
      value={value}
      onChange={(event) => onChange(event.target.value)}
      min={schema.minimum}
      max={schema.maximum}
      step={schema.type === "integer" ? 1 : undefined}
      maxLength={schema.maxLength}
      placeholder={
        field.material
          ? t("playground.materialUrlPlaceholder")
          : schema.default !== undefined && schema.default !== null
            ? String(schema.default)
            : undefined
      }
    />
  );
}

/** 单个契约参数输入：按 type 渲染控件；素材字段额外提供文件上传，与地址文本二选一 */
function ParamFieldInput({
  field,
  value,
  files,
  onValueChange,
  onFilesChange,
}: {
  field: ParamField;
  value: string;
  files: File[];
  onValueChange: (value: string) => void;
  onFilesChange: (files: File[]) => void;
}) {
  const { t } = useTranslation("console");
  const { required } = field;
  const wide = field.schema.type === "array" || field.schema.type === "object";
  const label = (
    <span className="text-xs font-medium text-muted-foreground">
      {field.name}
      {required && <span className="ml-0.5 text-destructive">*</span>}
    </span>
  );

  if (!field.material) {
    return (
      <label className={wide ? "space-y-1 sm:col-span-2 xl:col-span-3" : "space-y-1"}>
        {label}
        <ParamTextControl field={field} value={value} ariaLabel={field.name} onChange={onValueChange} />
      </label>
    );
  }

  // 素材字段：容器不能再是 label，否则点击上传区会激活容器内第一个控件（地址输入框）
  const { categories, multiple } = field.material;
  const maxItems = typeof field.schema.maxItems === "number" ? field.schema.maxItems : null;
  /** 单值素材字段只允许一个文件；数组字段按契约 maxItems 限制继续追加 */
  const canAddMore = (multiple || files.length === 0) && (maxItems === null || files.length < maxItems);
  return (
    <div className={wide ? "space-y-1 sm:col-span-2 xl:col-span-3" : "space-y-1"}>
      {label}
      <span className="block text-[11px] leading-4 text-muted-foreground">
        {t("playground.materialHint")}
      </span>
      <ParamTextControl
        field={field}
        value={value}
        ariaLabel={field.name}
        onChange={(next) => {
          onValueChange(next);
          onFilesChange([]);
        }}
      />
      {files.map((file, index) => (
        <span
          key={`${file.name}-${index}`}
          className="flex items-center gap-2 rounded-lg border border-border/70 bg-muted/20 px-3 py-1.5"
        >
          <span className="min-w-0 flex-1 truncate text-xs">{file.name}</span>
          <button
            type="button"
            onClick={() => onFilesChange(files.filter((_, current) => current !== index))}
            aria-label={t("playground.removeMaterial")}
            className="shrink-0 rounded-md p-1 text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive"
          >
            <Trash2 className="size-3.5" />
          </button>
        </span>
      ))}
      {canAddMore && (
        <label className="flex cursor-pointer items-center justify-center gap-1.5 rounded-lg border border-dashed border-border/70 bg-muted/10 px-3 py-1.5 text-xs text-muted-foreground transition hover:border-ring/60 hover:text-foreground">
          <Upload className="size-3.5" />
          {files.length > 0
            ? t("playground.addMaterial")
            : t("playground.selectMaterial", { categories: categories.join(" / ") })}
          <input
            type="file"
            accept={materialAccept(categories)}
            multiple={multiple}
            className="hidden"
            onChange={(event) => {
              const selected = Array.from(event.target.files ?? []);
              // 上传控件在选择后保持挂载，清空 value 才能重复选择同一个文件
              event.target.value = "";
              if (selected.length === 0) return;
              const merged = multiple ? [...files, ...selected] : selected;
              onFilesChange(maxItems === null ? merged : merged.slice(0, maxItems));
              onValueChange("");
            }}
          />
        </label>
      )}
    </div>
  );
}

export function ChatPlayground() {
  const { t } = useTranslation("console");
  const [mode, setMode] = useState<PlaygroundMode>("text");
  const [textModels, setTextModels] = useState<{ value: string; label: string }[]>([]);
  const [textModel, setTextModel] = useState("");
  const [apiKeys, setApiKeys] = useState<ApiKeyOption[]>([]);
  const [textKeyId, setTextKeyId] = useState("");
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [sending, setSending] = useState(false);
  /** 正在重新生成的消息下标：重试期间给目标气泡可见反馈 */
  const [retrying, setRetrying] = useState<number | null>(null);
  const [scrollRef, setScrollRef] = useState<HTMLDivElement | null>(null);

  const mediaType: MediaType = mode === "text" ? "image" : mode;
  const [mediaModels, setMediaModels] = useState<{ value: string; label: string }[]>([]);
  const [mediaModelInfos, setMediaModelInfos] = useState<ModelInfo[]>([]);
  const [mediaModel, setMediaModel] = useState("");
  /** 当前媒体模型的详情模板与动态参数值（选择模型后按调用示例初始化） */
  const [mediaTemplate, setMediaTemplate] = useState<ModelTemplate | null>(null);
  const [mediaParams, setMediaParams] = useState<ParamTextValues>({});
  /** 素材字段已选文件，键为契约字段名；非空时创建任务走 multipart */
  const [mediaFiles, setMediaFiles] = useState<ParamFiles>({});
  const [mediaKeyId, setMediaKeyId] = useState("");
  const [prompt, setPrompt] = useState("");
  const [referenceImage, setReferenceImage] = useState<File | null>(null);
  const [generating, setGenerating] = useState(false);
  const [images, setImages] = useState<string[]>([]);
  /** 大图预览的图片地址，非空时显示 lightbox */
  const [previewImage, setPreviewImage] = useState<string | null>(null);
  const [videoTask, setVideoTask] = useState<VideoTask | null>(null);
  /** 创建视频任务时解析出的 API Token：轮询/成品拉取复用（/v1 仅接受 sk-，仅存内存） */
  const [videoToken, setVideoToken] = useState<string | null>(null);
  /** 视频成品 Object URL（succeeded 后按任务 ID 拉取，卸载时 revoke） */
  const [videoUrl, setVideoUrl] = useState<string | null>(null);

  useEffect(() => {
    scrollRef?.scrollTo({ top: scrollRef.scrollHeight, behavior: "smooth" });
  }, [messages, sending, scrollRef]);

  // 大图预览时支持 Esc 关闭
  useEffect(() => {
    if (!previewImage) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setPreviewImage(null);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [previewImage]);

  useEffect(() => {
    getModels().then((models) => {
      const options = models
        .filter((model) => model.category === "text")
        .map((model) => ({ value: model.provider, label: model.name }));
      setTextModels(options);
      setTextModel((prev) => prev || options[0]?.value || "");
    });
    get<unknown>("/user/token/list", { params: { page: 1, page_size: 100 } })
      .then((data) => {
        const options = normalizeKeys(data);
        setApiKeys(options);
        setTextKeyId((prev) => prev || options[0]?.value || "");
        setMediaKeyId((prev) => prev || options[0]?.value || "");
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    getModels().then((models) => {
      const media = models.filter((model) => model.category === mediaType);
      const options = media.map((model) => ({ value: model.provider, label: model.name }));
      setMediaModelInfos(media);
      setMediaModels(options);
      setMediaModel(options[0]?.value ?? "");
    });
    // 参考图仅对应模式有效，切换类型时清空
    setReferenceImage(null);
  }, [mediaType]);

  /** 选择媒体模型后拉取详情，按调用示例初始化动态参数 */
  const mediaModelId = mediaModelInfos.find((model) => model.provider === mediaModel)?.id;
  useEffect(() => {
    if (!mediaModelId) {
      setMediaTemplate(null);
      setMediaParams({});
      setMediaFiles({});
      return;
    }
    let cancelled = false;
    getModelDetail(mediaModelId)
      .then((detail) => {
        if (cancelled) return;
        const template = detail._marketplace?.template ?? null;
        setMediaTemplate(template);
        setMediaParams(initParamValues(template, getParamFields(template)));
        setMediaFiles({});
      })
      .catch(() => {
        if (cancelled) return;
        setMediaTemplate(null);
        setMediaParams({});
        setMediaFiles({});
      });
    return () => {
      cancelled = true;
    };
  }, [mediaModelId]);

  const mediaParamFields = getParamFields(mediaTemplate);
  /** 主提示词由专属输入框承载：仅在契约声明 prompt 时渲染与提交 */
  const promptSchema = mediaTemplate?.parameters?.properties?.prompt;
  const promptRequired = (mediaTemplate?.parameters?.required ?? []).includes("prompt");

  const videoTaskId = videoTask?.id;
  const videoTaskStatus = videoTask?.status;

  useEffect(() => {
    if (!videoTaskId || !videoToken || isTerminalStatus(videoTaskStatus ?? "")) return;
    const controller = new AbortController();
    pollVideoTask(videoTaskId, { signal: controller.signal, onUpdate: setVideoTask, bearerToken: videoToken }).catch(() => {});
    return () => controller.abort();
  }, [videoTaskId, videoTaskStatus, videoToken]);

  // 视频任务成功后按任务 ID 拉取成品 Blob 用于播放；切换/失败时清理 Object URL
  useEffect(() => {
    if (!isSuccessStatus(videoTaskStatus ?? "") || !videoTaskId || !videoToken) {
      setVideoUrl(null);
      return;
    }
    let objectUrl: string | null = null;
    let cancelled = false;
    fetchVideoContentUrl(videoTaskId, videoToken)
      .then((url) => {
        if (cancelled) {
          URL.revokeObjectURL(url);
          return;
        }
        objectUrl = url;
        setVideoUrl(url);
      })
      .catch(() => setVideoUrl(null));
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [videoTaskId, videoTaskStatus, videoToken]);

  /** 按需解析密钥明文：列表不含明文，首次使用时调用 /user/token/copy 并缓存到内存（不落盘） */
  const resolveToken = async (keyId: string): Promise<string> => {
    const key = apiKeys.find((item) => item.value === keyId);
    if (!key) throw new Error(t("playground.selectApiKey"));
    if (key.token) return key.token;
    const data = await get<{ token?: string }>("/user/token/copy", {
      params: { token_id: key.value },
    });
    const token = data?.token ?? "";
    if (!token) throw new Error(t("playground.noToken"));
    setApiKeys((prev) => prev.map((item) => (
      item.value === key.value ? { ...item, token } : item
    )));
    return token;
  };

  /** 请求回复（流式 SSE）：history 含本次用户消息；onDelta 逐块回调增量供 UI 实时渲染 */
  const requestReply = async (
    history: Message[],
    onDelta: (delta: StreamDelta) => void
  ): Promise<AssistantPayload> => {
    if (!textModel) throw new Error(t("playground.selectModelLabel"));
    const token = await resolveToken(textKeyId);
    // 本地聚合流式增量，结束后返回完整载荷
    let content = "";
    let reasoning = "";
    const meta: AssistantPayload = { content: "" };
    await streamChatCompletion(
      {
        model: textModel,
        messages: history.map(({ role, content }) => ({ role, content })),
      },
      {
        bearerToken: token,
        onDelta: (delta) => {
          if (delta.content) content += delta.content;
          if (delta.reasoning) reasoning += delta.reasoning;
          if (delta.model) meta.model = delta.model;
          if (delta.usage) meta.usage = delta.usage;
          if (delta.finishReason) meta.finishReason = delta.finishReason;
          onDelta(delta);
        },
      }
    );
    content = content.trim();
    reasoning = reasoning.trim();
    if (!content && !reasoning) throw new Error(t("playground.noValidReply"));
    return { ...meta, content, reasoning: reasoning || undefined };
  };

  /** 流式期间就地更新最后一条助手占位消息的增量 */
  const applyStreamDelta = (delta: StreamDelta) => {
    setMessages((prev) => {
      const next = [...prev];
      const last = next[next.length - 1];
      if (!last || last.role !== "assistant") return prev;
      next[next.length - 1] = {
        ...last,
        content: delta.content ? last.content + delta.content : last.content,
        reasoning: delta.reasoning ? (last.reasoning ?? "") + delta.reasoning : last.reasoning,
        model: delta.model ?? last.model,
        usage: delta.usage ?? last.usage,
        finishReason: delta.finishReason ?? last.finishReason,
      };
      return next;
    });
  };

  const onSend = async () => {
    const content = input.trim();
    if (!content || sending) return;
    const history = [...messages, { role: "user" as const, content, time: now() }];
    setInput("");
    // 追加空助手占位消息，流式增量实时填充
    setMessages([...history, { role: "assistant" as const, content: "", time: now() }]);
    setSending(true);
    try {
      await requestReply(history, applyStreamDelta);
    } catch (error) {
      // 失败时移除空占位消息
      setMessages((prev) => (prev[prev.length - 1]?.role === "assistant" && !prev[prev.length - 1]?.content && !prev[prev.length - 1]?.reasoning) ? prev.slice(0, -1) : prev);
      toast.error(error instanceof Error ? error.message : t("playground.sendFailed"));
    } finally {
      setSending(false);
    }
  };

  const onRetry = async (index: number) => {
    if (sending) return;
    // 找到该回复对应的用户消息，作为新的一轮重新发送（上下文取该回复之前的完整对话）
    const history = messages.slice(0, index);
    const lastUser = [...history].reverse().find((m) => m.role === "user");
    if (!lastUser) return;
    setSending(true);
    setMessages((prev) => [
      ...prev,
      { role: "user" as const, content: lastUser.content, time: now() },
      { role: "assistant" as const, content: "", time: now() },
    ]);
    try {
      await requestReply(history, applyStreamDelta);
    } catch (error) {
      setMessages((prev) => (prev[prev.length - 1]?.role === "assistant" && !prev[prev.length - 1]?.content && !prev[prev.length - 1]?.reasoning) ? prev.slice(0, -1) : prev);
      toast.error(error instanceof Error ? error.message : t("playground.retryFailed"));
    } finally {
      setSending(false);
    }
  };

  const onGenerate = async () => {
    if (!mediaModel || generating) return;
    if (!mediaTemplate) {
      toast.warning(t("playground.contractUnavailable"));
      return;
    }
    if (!apiKeys.some((item) => item.value === mediaKeyId)) {
      toast.warning(t("playground.selectApiKey"));
      return;
    }
    const content = prompt.trim();
    if (promptSchema && promptRequired && !content) {
      toast.warning(t("playground.paramRequired", { name: "prompt" }));
      return;
    }
    // 输入与请求体完全由模型详情契约驱动：未声明的字段既不渲染也不提交
    const built = buildParams(mediaParamFields, mediaParams, mediaFiles);
    if (!built.ok) {
      toast.warning(
        built.error.reason === "missing"
          ? t("playground.paramRequired", { name: built.error.name })
          : t("playground.paramInvalid", { name: built.error.name })
      );
      return;
    }
    const body: Record<string, unknown> = {
      ...(promptSchema && content ? { prompt: content } : {}),
      ...built.values,
    };

    setGenerating(true);
    try {
      const token = await resolveToken(mediaKeyId);
      if (mediaType === "image") {
        // 有参考图走图生图（/images/edits，multipart），无参考图走文生图（/images/generations）
        const result = referenceImage
          ? await post<ImageResponse>(
              "/images/edits",
              (() => {
                const form = new FormData();
                form.append("model", mediaModel);
                appendFormValues(form, body);
                form.append("image", referenceImage);
                return form;
              })(),
              { apiKind: "v1", bearerToken: token, timeoutMs: 300_000 }
            )
          : await post<ImageResponse>(
              "/images/generations",
              { model: mediaModel, ...body },
              // 图像生成耗时较长，默认 15s 超时偏短，放宽到 5 分钟
              { apiKind: "v1", bearerToken: token, timeoutMs: 300_000 }
            );
        const urls = getImageUrls(result);
        if (urls.length === 0) throw new Error(t("playground.noImageReturned"));
        setImages(urls);
        toast.success(referenceImage ? t("playground.imageEdited") : t("playground.imageGenerated"));
      } else {
        setVideoTask(null);
        setVideoUrl(null);
        // 选中素材时以 multipart 提交，素材字段名即契约字段名；纯文本参数走 JSON
        let payload: Parameters<typeof createVideoTask>[1];
        if (built.uploads.length > 0) {
          const form = new FormData();
          form.append("model", mediaModel);
          appendFormValues(form, body);
          for (const { name, file } of built.uploads) form.append(name, file);
          payload = form;
        } else {
          payload = { model: mediaModel, ...body };
        }
        const task = await createVideoTask(token, payload);
        setVideoToken(token);
        setVideoTask(task);
        toast.success(t("playground.videoTaskCreated"));
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : t("playground.generateFailed"));
    } finally {
      setGenerating(false);
    }
  };

  const iconBtn = "rounded-md p-2 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground disabled:cursor-not-allowed disabled:opacity-50";
  const videoRunning = videoTask && !isTerminalStatus(videoTask.status);
  const mediaCopy = mediaType === "image"
    ? { title: t("playground.imageTitle"), description: t("playground.imageDesc"), icon: ImageIcon }
    : { title: t("playground.videoTitle"), description: t("playground.videoDesc"), icon: Clapperboard };
  const MediaIcon = mediaCopy.icon;

  return (
    <div className="flex h-[calc(100vh-7.5rem)] min-h-[560px] flex-col overflow-hidden rounded-2xl border border-border/70 bg-card/30 shadow-sm">
      <header className="flex shrink-0 flex-col gap-4 border-b border-border/60 bg-card/80 px-5 py-4 backdrop-blur sm:flex-row sm:items-center sm:justify-between sm:px-7">
        <div className="grid w-full grid-cols-3 rounded-xl bg-muted/70 p-1 sm:w-auto">
          <button type="button" onClick={() => setMode("text")} className={`flex h-9 items-center justify-center gap-2 whitespace-nowrap rounded-lg px-4 text-sm font-medium transition-all ${mode === "text" ? "bg-card text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"}`}>
            <Bot className="size-4 shrink-0" />{t("playground.modeText")}
          </button>
          <button type="button" onClick={() => setMode("image")} className={`flex h-9 items-center justify-center gap-2 whitespace-nowrap rounded-lg px-4 text-sm font-medium transition-all ${mode === "image" ? "bg-card text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"}`}>
            <ImageIcon className="size-4 shrink-0" />{t("playground.imageTab")}
          </button>
          <button type="button" onClick={() => setMode("video")} className={`flex h-9 items-center justify-center gap-2 whitespace-nowrap rounded-lg px-4 text-sm font-medium transition-all ${mode === "video" ? "bg-card text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"}`}>
            <Clapperboard className="size-4 shrink-0" />{t("playground.videoTab")}
          </button>
        </div>
      </header>

      {mode === "text" ? (
        <div className="flex min-h-0 flex-1 flex-col bg-gradient-to-b from-transparent to-muted/20">
          <div ref={setScrollRef} className="min-h-0 flex-1 overflow-y-auto">
            <div className="mx-auto flex min-h-full max-w-3xl flex-col gap-7 px-5 py-7">
              {messages.length === 0 && (
                <div className="flex flex-1 flex-col items-center justify-center pb-20 text-center">
                  <div className="mb-5 flex size-16 items-center justify-center rounded-2xl border border-primary/10 bg-primary/5 text-primary shadow-sm"><Bot className="size-8" /></div>
                  <h2 className="text-lg font-semibold">{t("playground.emptyTitle")}</h2>
                  <p className="mt-2 max-w-sm text-sm leading-6 text-muted-foreground">{t("playground.emptyDesc")}</p>
                </div>
              )}
              {messages.map((message, index) => message.role === "user" ? (
                <div key={index} className="flex flex-col items-end gap-1.5">
                  <div className="max-w-[85%] rounded-2xl rounded-br-md bg-primary px-4 py-2.5 text-sm leading-6 text-primary-foreground shadow-sm">{message.content}</div>
                  <p className="pr-1 text-[11px] text-muted-foreground">{message.time}</p>
                </div>
              ) : (
                <div key={index} className="flex max-w-[90%] flex-col gap-2">
                  <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground"><div className="flex size-5 items-center justify-center rounded-md bg-primary/10 text-primary"><Bot className="size-3" /></div>{t("playground.aiAssistant")}{message.model && <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-[10px] font-normal">{message.model}</span>}</div>
                  {message.reasoning && <details className="rounded-xl border border-border/60 bg-muted/30 px-3 py-2 text-xs leading-6 text-muted-foreground"><summary className="cursor-pointer select-none font-medium">{t("playground.thinking")}</summary><p className="mt-1 whitespace-pre-wrap">{message.reasoning}</p></details>}
                  <div className="rounded-2xl rounded-tl-md border border-border/70 bg-card px-4 py-3 text-sm leading-7 shadow-sm">
                    {message.content ? (
                      <div className="markdown-body">
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
                      </div>
                    ) : null}
                    {sending && index === messages.length - 1 && (
                      <span className="mt-1 inline-flex items-center gap-1 align-middle">
                        <span className="size-1.5 animate-bounce rounded-full bg-primary [animation-delay:-0.3s]" />
                        <span className="size-1.5 animate-bounce rounded-full bg-primary [animation-delay:-0.15s]" />
                        <span className="size-1.5 animate-bounce rounded-full bg-primary" />
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-1"><span className="mr-1 text-[11px] text-muted-foreground">{message.time}{message.usage && ` · ${t("playground.inputTokens", { prompt: message.usage.prompt, completion: message.usage.completion, total: message.usage.total })}`}{message.finishReason && ` · ${message.finishReason}`}</span><button type="button" onClick={() => onRetry(index)} className={iconBtn} aria-label={t("playground.retry")}><RotateCcw className="size-3.5" /></button><button type="button" onClick={() => setInput(message.content)} className={iconBtn} aria-label={t("playground.edit")}><Pencil className="size-3.5" /></button><button type="button" onClick={() => setMessages((prev) => prev.filter((_, i) => i !== index))} className={iconBtn} aria-label={t("playground.delete")}><Trash2 className="size-3.5" /></button></div>
                </div>
              ))}
            </div>
          </div>
          <div className="shrink-0 px-4 pb-5 sm:px-7">
            <div className="mx-auto max-w-3xl rounded-2xl border border-border/80 bg-card p-2 shadow-[0_10px_30px_rgb(0_0_0/0.06)] transition-shadow focus-within:shadow-[0_12px_32px_rgb(76_111_255/0.12)]">
              <textarea value={input} onChange={(event) => setInput(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); onSend(); } }} rows={3} placeholder={t("playground.inputPlaceholder")} className="w-full resize-none bg-transparent px-3 pt-2 text-sm leading-6 outline-none placeholder:text-muted-foreground" />
              <div className="flex items-center justify-between gap-3 border-t border-border/50 px-1 pt-2">
                <div className="flex items-center gap-1.5">
                  <Select
                    value={textModel}
                    onValueChange={setTextModel}
                    options={textModels}
                    placeholder={t("playground.selectModel")}
                    emptyText={t("playground.noTextModel")}
                    aria-label={t("playground.selectModelAria")}
                    className={`size-9 border ${textModel ? "border-border/70 bg-muted/60 text-foreground" : "border-dashed border-border/70 text-muted-foreground"} hover:bg-accent hover:text-foreground`}
                    trigger={({ selected }) => (
                      <span className="relative flex size-full items-center justify-center" title={selected ? String(selected.label) : t("playground.selectModel")}>
                        <Cpu className="size-4" />
                        <span className={`absolute right-1.5 top-1.5 size-1.5 rounded-full ${selected ? "bg-emerald-500" : "bg-muted-foreground/40"}`} />
                        <span className="sr-only">{selected ? String(selected.label) : t("playground.selectModel")}</span>
                      </span>
                    )}
                  />
                  <Select
                    value={textKeyId}
                    onValueChange={setTextKeyId}
                    options={apiKeys}
                    placeholder={t("playground.selectKey")}
                    emptyText={t("playground.noKey")}
                    aria-label={t("playground.selectKeyAria")}
                    className={`size-9 border ${textKeyId ? "border-border/70 bg-muted/60 text-foreground" : "border-dashed border-border/70 text-muted-foreground"} hover:bg-accent hover:text-foreground`}
                    trigger={({ selected }) => (
                      <span className="relative flex size-full items-center justify-center" title={selected ? String(selected.label) : t("playground.selectKey")}>
                        <KeyRound className="size-4" />
                        <span className={`absolute right-1.5 top-1.5 size-1.5 rounded-full ${selected ? "bg-emerald-500" : "bg-muted-foreground/40"}`} />
                      </span>
                    )}
                  />
                </div>
                <div className="flex items-center gap-1"><button type="button" onClick={() => setMessages([])} disabled={messages.length === 0} className={iconBtn} aria-label={t("playground.clearChat")}><Trash2 className="size-4" /></button><Button type="button" onClick={onSend} disabled={!input.trim() || !textModel || !textKeyId || sending} className="h-9 rounded-xl px-4"><SendHorizonal className="size-4" />{t("playground.send")}</Button></div>
              </div>
            </div>
          </div>
        </div>
      ) : (
        <div className="min-h-0 flex-1 overflow-y-auto bg-gradient-to-b from-transparent to-muted/20 px-5 py-4 sm:px-7">
          <div className="mx-auto grid max-w-6xl gap-4 lg:grid-cols-[minmax(0,1.15fr)_minmax(320px,0.85fr)]">
            <section className="rounded-2xl border border-border/70 bg-card p-4 shadow-sm sm:p-5">
              <div className="flex flex-col gap-3 border-b border-border/60 pb-4 sm:flex-row sm:items-start sm:justify-between">
                <div className="flex gap-3"><div className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary"><MediaIcon className="size-5" /></div><div><h2 className="font-semibold">{mediaCopy.title}</h2><p className="mt-1 text-sm text-muted-foreground">{mediaCopy.description}</p></div></div>
              </div>
              <div className="mt-4 space-y-4">
                <div className="grid gap-4 sm:grid-cols-2"><label className="space-y-1.5"><span className="text-sm font-medium">{t("playground.selectModelLabel")}</span><Select value={mediaModel} onValueChange={setMediaModel} options={mediaModels} placeholder={t("playground.selectModelPlaceholder", { type: mediaType === "image" ? t("playground.imageModel") : t("playground.videoModel") })} /></label><label className="space-y-1.5"><span className="text-sm font-medium">{t("playground.apiKeyLabel")}</span><Select value={mediaKeyId} onValueChange={setMediaKeyId} options={apiKeys} placeholder={t("playground.selectKey")} emptyText={t("playground.noKey")} /></label></div>
                {promptSchema && (
                  <label htmlFor="media-prompt" className="block space-y-1.5">
                    <span className="text-sm font-medium">{t("playground.promptLabel")}{promptRequired && <span className="ml-0.5 text-destructive">*</span>}</span>
                    <textarea id="media-prompt" rows={4} value={prompt} maxLength={promptSchema.maxLength} onChange={(event) => setPrompt(event.target.value)} placeholder={t("playground.promptPlaceholder", { type: mediaType === "image" ? t("playground.imageModel") : t("playground.videoModel") })} className="w-full resize-none rounded-xl border border-input bg-muted/20 px-3 py-2.5 text-sm leading-6 outline-none transition focus:border-ring focus:ring-[3px] focus:ring-ring/20" />
                  </label>
                )}
                {mediaType === "image" && (
                  <div className="space-y-1.5">
                    <span className="text-sm font-medium">{t("playground.referenceImage")} <span className="font-normal text-muted-foreground">{t("playground.referenceImageOptional")}</span></span>
                    {referenceImage ? (
                      <div className="flex items-center gap-3 rounded-xl border border-border/70 bg-muted/20 p-2">
                        <img src={URL.createObjectURL(referenceImage)} alt={t("playground.referenceImageAlt")} className="size-12 rounded-lg border object-cover" />
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-sm">{referenceImage.name}</p>
                          <p className="text-xs text-muted-foreground">{(referenceImage.size / 1024).toFixed(0)} KB · {t("playground.willUseImageEdit")}</p>
                        </div>
                        <button type="button" onClick={() => setReferenceImage(null)} className={iconBtn} aria-label={t("playground.removeReference")}><Trash2 className="size-4" /></button>
                      </div>
                    ) : (
                      <label className="flex cursor-pointer items-center justify-center gap-2 rounded-xl border border-dashed border-border/70 bg-muted/10 px-3 py-2.5 text-sm text-muted-foreground transition hover:border-ring/60 hover:text-foreground">
                        <ImageIcon className="size-4" />{t("playground.uploadReference")}
                        <input type="file" accept="image/*" className="hidden" onChange={(event) => setReferenceImage(event.target.files?.[0] ?? null)} />
                      </label>
                    )}
                  </div>
                )}
                {mediaParamFields.length > 0 && (
                  <div className="space-y-1.5">
                    <span className="flex items-center gap-1.5 text-sm font-medium"><SlidersHorizontal className="size-4 text-primary" />{t("playground.paramsTitle")}</span>
                    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                      {mediaParamFields.map((field) => (
                        <ParamFieldInput
                          key={field.name}
                          field={field}
                          value={mediaParams[field.name] ?? ""}
                          files={mediaFiles[field.name] ?? []}
                          onValueChange={(value) => setMediaParams((prev) => ({ ...prev, [field.name]: value }))}
                          onFilesChange={(files) => setMediaFiles((prev) => ({ ...prev, [field.name]: files }))}
                        />
                      ))}
                    </div>
                  </div>
                )}
                <Button onClick={onGenerate} disabled={!mediaModel || generating} className="h-10 w-full rounded-xl">{generating ? <Loader2 className="size-4 animate-spin" /> : <Sparkles className="size-4" />}{mediaType === "image" ? t("playground.generateImage") : t("playground.createVideoTask")}</Button>
              </div>
            </section>

            <aside className="min-h-[300px] overflow-hidden rounded-2xl border border-border/70 bg-card shadow-sm">
              <div className="flex items-center justify-between border-b border-border/60 px-4 py-3"><div><h2 className="font-semibold">{t("playground.resultTitle")}</h2><p className="mt-0.5 text-xs text-muted-foreground">{mediaType === "image" ? t("playground.imageResultDesc") : t("playground.videoResultDesc")}</p></div>{images.length > 0 && mediaType === "image" && <span className="rounded-full bg-primary/10 px-2 py-1 text-xs font-medium text-primary">{t("playground.imageCount", { count: images.length })}</span>}</div>
              <div className="p-4">{mediaType === "image" ? generating ? <div className="space-y-4"><div className="relative aspect-square w-full overflow-hidden rounded-xl border bg-muted"><div className="absolute inset-0 -translate-x-full animate-[shimmer_1.6s_infinite] bg-gradient-to-r from-transparent via-white/25 to-transparent" /><div className="absolute inset-0 flex flex-col items-center justify-center gap-3 text-muted-foreground"><Loader2 className="size-8 animate-spin text-primary" /><p className="text-sm font-medium">{t("playground.generatingImage")}</p></div></div></div> : images.length > 0 ? <div className="grid grid-cols-2 gap-3">{images.map((url, index) => <button key={`${url}-${index}`} type="button" onClick={() => setPreviewImage(url)} className="group relative aspect-square w-full overflow-hidden rounded-xl border bg-muted shadow-sm transition focus:outline-none focus:ring-2 focus:ring-ring"><img src={url} alt={t("playground.generatedImageAlt", { index: index + 1 })} className="size-full object-cover transition group-hover:scale-105" /><span className="absolute inset-0 flex items-center justify-center bg-black/0 text-xs font-medium text-white opacity-0 transition group-hover:bg-black/40 group-hover:opacity-100">{t("playground.viewLarge")}</span></button>)}</div> : <div className="flex min-h-56 flex-col items-center justify-center text-center"><div className="mb-3 flex size-12 items-center justify-center rounded-xl bg-muted text-muted-foreground"><ImageIcon className="size-6" /></div><p className="text-sm font-medium">{t("playground.waitingImage")}</p><p className="mt-1 max-w-[220px] text-xs leading-5 text-muted-foreground">{t("playground.waitingImageDesc")}</p></div> : videoTask ? <div className="space-y-5"><div className="flex items-start gap-3"><div className={`flex size-10 shrink-0 items-center justify-center rounded-xl ${videoTask.status === "failed" ? "bg-destructive/10 text-destructive" : "bg-primary/10 text-primary"}`}>{videoRunning ? <Loader2 className="size-5 animate-spin" /> : isSuccessStatus(videoTask.status) ? <CheckCircle2 className="size-5" /> : <Clapperboard className="size-5" />}</div><div className="min-w-0"><p className="truncate text-sm font-medium">{videoTask.model}</p><p className="mt-1 text-xs text-muted-foreground">{videoRunning ? t("playground.taskRunning") : isSuccessStatus(videoTask.status) ? t("playground.videoSuccess") : t("playground.taskStatus", { status: videoTask.status })}</p></div></div>{videoRunning && <div className="relative aspect-video w-full overflow-hidden rounded-xl border bg-muted"><div className="absolute inset-0 -translate-x-full animate-[shimmer_1.6s_infinite] bg-gradient-to-r from-transparent via-white/25 to-transparent" /><div className="absolute inset-0 flex flex-col items-center justify-center gap-3 text-muted-foreground"><div className="relative flex size-14 items-center justify-center"><span className="absolute inline-flex size-full animate-ping rounded-full bg-primary/20" /><div className="relative flex size-12 items-center justify-center rounded-full bg-primary/10 text-primary"><Clapperboard className="size-6 animate-pulse" /></div></div><p className="text-sm font-medium">{t("playground.generatingVideo")}</p></div></div>}{isSuccessStatus(videoTask.status) && <div className="space-y-2">{videoUrl ? <video src={videoUrl} controls playsInline className="aspect-video w-full rounded-lg bg-black" /> : <div className="flex aspect-video w-full items-center justify-center rounded-lg bg-muted text-sm text-muted-foreground"><Loader2 className="size-5 animate-spin" /></div>}{videoUrl && <Button variant="outline" size="sm" asChild><a href={videoUrl} download={`${videoTask.id}.mp4`}><Download className="size-4" />{t("playground.downloadVideo")}</a></Button>}</div>}{videoTask.status === "failed" && <p className="rounded-lg bg-destructive/10 px-3 py-2 text-xs leading-5 text-destructive">{typeof videoTask.error === "string" ? videoTask.error : (videoTask.error as Record<string, unknown> | null)?.message as string || t("playground.videoFailed")}</p>}</div> : <div className="flex min-h-56 flex-col items-center justify-center text-center"><div className="mb-3 flex size-12 items-center justify-center rounded-xl bg-muted text-muted-foreground"><Clapperboard className="size-6" /></div><p className="text-sm font-medium">{t("playground.noTask")}</p><p className="mt-1 max-w-[220px] text-xs leading-5 text-muted-foreground">{t("playground.noTaskDesc")}</p></div>}</div>
            </aside>
          </div>
        </div>
      )}

      {/* 大图预览 lightbox */}
      {previewImage && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4 backdrop-blur-sm" onClick={() => setPreviewImage(null)}>
          <button type="button" onClick={() => setPreviewImage(null)} className="absolute right-4 top-4 rounded-full bg-white/10 p-2 text-white transition hover:bg-white/20" aria-label={t("playground.closePreview")}><X className="size-5" /></button>
          <a href={previewImage} download target="_blank" rel="noreferrer" onClick={(event) => event.stopPropagation()} className="absolute right-4 top-16 rounded-full bg-white/10 p-2 text-white transition hover:bg-white/20" aria-label={t("playground.downloadImage")}><Download className="size-5" /></a>
          <img src={previewImage} alt={t("playground.previewAlt")} className="max-h-full max-w-full rounded-lg object-contain shadow-2xl" onClick={(event) => event.stopPropagation()} />
        </div>
      )}
    </div>
  );
}
