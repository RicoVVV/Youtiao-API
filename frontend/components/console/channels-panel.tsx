"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Activity,
  CheckCircle2,
  Copy,
  Eye,
  Layers,
  Loader2,
  Minus,
  Pencil,
  PlugZap,
  Plus,
  Power,
  RefreshCw,
  Search,
  Trash2,
  Waypoints,
  X,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Loading } from "@/components/ui/loading";
import { MultiSelect } from "@/components/ui/multi-select";
import { Pagination } from "@/components/ui/pagination";
import { Select } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { toast } from "@/components/ui/toaster";
import { cn } from "@/lib/utils";
import { get, post } from "@/lib/request";
import type { ModelOption } from "@/components/console/models-panel";

/** 渠道最新测试摘要：覆盖式快照，不含文本内容、图片 URL、Base64 等敏感数据 */
type ChannelLatestTestSnapshot = {
  tested_at: string;
  status: "succeeded" | "failed";
  model: string;
  model_type: "text" | "image";
  duration_ms: number;
  amount: string;
  error_code?: string | null;
  message?: string | null;
  usage?: Record<string, number | string>;
};

type Channel = {
  id: string;
  name: string;
  base_url: string;
  config?: Record<string, unknown>;
  supported_models?: string[];
  token_group_ids?: number[];
  token_groups?: { id: number; name: string }[];
  model_mapping?: Record<string, string>;
  param_override?: Record<string, unknown>;
  header_override?: Record<string, unknown>;
  priority: number;
  weight: number;
  active: boolean;
  healthy: boolean;
  created_at?: string;
  updated_at?: string;
  latest_test_snapshot?: ChannelLatestTestSnapshot | null;
};

type GroupOption = {
  id: number;
  name: string;
};

/** KV 条目编辑态：用于参数覆写与 Header 覆写 */
type KvRow = { key: string; value: string };

/** 渠道上游连通性测试结果：上游失败与超时由后端以 HTTP 200 返回，需判断 success */
type ChannelTestResult = {
  success: boolean;
  message: string;
  time: number;
  /** 成功测试按模型正式价格结算的金额；失败与超时固定为零 */
  amount: string;
  /** 即时预览内容，仅在当前弹窗展示，后端不持久化 */
  result?:
    | { type: "text"; content: string }
    | { type: "image"; items: Array<{ url?: string; b64_json?: string }> }
    | null;
};

type ChannelFormState = {
  name: string;
  baseUrl: string;
  apiKey: string;
  supportedModels: string[];
  tokenGroupIds: string[];
  /** 公开模型名 → 上游模型名；留空表示按公开模型名原样透传 */
  modelMapping: Record<string, string>;
  paramOverride: KvRow[];
  headerOverride: KvRow[];
  configText: string;
  priority: string;
  weight: string;
  active: boolean;
};

const PAGE_SIZE = 20;

const JSON_TEXTAREA_CLASS =
  "placeholder:text-muted-foreground dark:bg-input/30 border-input w-full min-w-0 rounded-md border bg-transparent px-3 py-2 font-mono text-sm shadow-xs transition-[color,box-shadow] outline-none focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px]";

/** 渠道表单分区导航 */
const FORM_SECTIONS = [
  { id: "basic" },
  { id: "scope" },
  { id: "mapping" },
  { id: "advanced" },
] as const;

type Translate = (key: string, options?: Record<string, unknown>) => string;

/** 兼容多种分页响应：数组 / { items, total } / { channels, total } */
function normalize(data: unknown): { channels: Channel[]; total: number } {
  if (Array.isArray(data)) return { channels: data, total: data.length };
  if (data && typeof data === "object") {
    const d = data as Record<string, unknown>;
    const list = (d.items ?? d.channels ?? d.list ?? []) as Channel[];
    const total = typeof d.total === "number" ? d.total : list.length;
    return { channels: list, total };
  }
  return { channels: [], total: 0 };
}

/** 兼容多种列表响应：数组 / { items } / { groups } / { list } */
function normalizeOptions<T>(data: unknown): T[] {
  if (Array.isArray(data)) return data as T[];
  if (data && typeof data === "object") {
    const d = data as Record<string, unknown>;
    return ((d.items ?? d.models ?? d.groups ?? d.list ?? []) as T[]) ?? [];
  }
  return [];
}

/** 时间戳 → 本地化展示 */
const formatTime = (locale: string, s?: string) =>
  s ? new Date(s).toLocaleString(locale) : "-";

/** 覆写对象 → KV 编辑行 */
function kvFromObject(obj?: Record<string, unknown>): KvRow[] {
  if (!obj) return [];
  return Object.entries(obj).map(([key, v]) => ({
    key,
    value: typeof v === "string" ? v : JSON.stringify(v),
  }));
}

/** 渠道详情 → 表单编辑态；未配置上游模型名的模型表示按公开模型名原样透传 */
function formStateFromChannel(channel: Channel): ChannelFormState {
  const supported = channel.supported_models ?? [];
  const modelMapping: Record<string, string> = {};
  for (const model of supported) {
    modelMapping[model] = channel.model_mapping?.[model] ?? "";
  }
  return {
    name: channel.name,
    baseUrl: channel.base_url,
    apiKey: "",
    supportedModels: supported,
    tokenGroupIds: (channel.token_group_ids ?? []).map(String),
    modelMapping,
    paramOverride: kvFromObject(channel.param_override),
    headerOverride: kvFromObject(channel.header_override),
    configText:
      channel.config && Object.keys(channel.config).length > 0
        ? JSON.stringify(channel.config, null, 2)
        : "",
    priority: String(channel.priority ?? 0),
    weight: String(channel.weight ?? 100),
    active: channel.active ?? true,
  };
}

/** 新建渠道初始编辑态：MiniMax H3 示例结构 */
function emptyFormState(): ChannelFormState {
  return {
    name: "",
    baseUrl: "",
    apiKey: "",
    supportedModels: [],
    tokenGroupIds: [],
    modelMapping: {},
    paramOverride: [],
    headerOverride: [],
    configText: "",
    priority: "0",
    weight: "100",
    active: true,
  };
}

/** 卡片内联数值步进器：连续点击乐观更新，队列化串行保存 */
function InlineStepper({
  label,
  value,
  min,
  onStep,
}: {
  label: string;
  value: number;
  /** 最小值（优先级 0，权重 1） */
  min: number;
  onStep: (delta: number) => void;
}) {
  const btnClass =
    "inline-flex size-5 cursor-pointer items-center justify-center rounded text-muted-foreground transition-colors hover:bg-accent hover:text-foreground disabled:pointer-events-none disabled:opacity-40";
  return (
    <span className="inline-flex items-center gap-1.5">
      {label}
      <span className="inline-flex items-center gap-0.5 rounded-md border border-border/60 bg-background/60 px-0.5">
        <button
          type="button"
          className={btnClass}
          disabled={value <= min}
          onClick={() => onStep(-1)}
          aria-label={`${label}减一`}
        >
          <Minus className="size-3" />
        </button>
        <span className="min-w-7 px-0.5 text-center font-mono text-xs font-medium tabular-nums text-foreground">
          {value}
        </span>
        <button
          type="button"
          className={btnClass}
          onClick={() => onStep(1)}
          aria-label={`${label}加一`}
        >
          <Plus className="size-3" />
        </button>
      </span>
    </span>
  );
}

/** 新建 / 编辑渠道抽屉（channel 为 null 时新建） */
function ChannelFormDialog({
  channel,
  modelOptions,
  groupOptions,
  onClose,
  onSaved,
}: {
  channel: Channel | null;
  modelOptions: ModelOption[];
  groupOptions: GroupOption[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const isEdit = channel !== null;
  const { t } = useTranslation("console");
  const [form, setForm] = useState<ChannelFormState>(() =>
    channel ? formStateFromChannel(channel) : emptyFormState()
  );
  const [submitting, setSubmitting] = useState(false);
  const [activeSection, setActiveSection] =
    useState<(typeof FORM_SECTIONS)[number]["id"]>("basic");
  /** 记录 mousedown 是否发生在遮罩上：避免从面板内拖选文本、在遮罩上松手时误关闭抽屉 */
  const overlayMouseDown = useRef(false);

  const patch = (p: Partial<ChannelFormState>) =>
    setForm((prev) => ({ ...prev, ...p }));

  /** 勾选模型：登记映射条目（留空=按公开模型名透传），取消勾选移除其映射 */
  const onModelsChange = (models: string[]) => {
    setForm((prev) => {
      const modelMapping: Record<string, string> = {};
      for (const m of models) {
        modelMapping[m] = prev.modelMapping[m] ?? "";
      }
      return { ...prev, supportedModels: models, modelMapping };
    });
  };

  /** KV 行 → 对象，校验重复键与空键 */
  const buildKvObject = (
    rows: KvRow[],
    label: string
  ): Record<string, string> | null => {
    const obj: Record<string, string> = {};
    for (let i = 0; i < rows.length; i++) {
      const key = rows[i].key.trim();
      if (!key) {
        toast.warning(t("channels.kvKeyRequired", { label, index: i + 1 }));
        return null;
      }
      if (obj[key] !== undefined) {
        toast.warning(t("channels.kvKeyDuplicate", { label, key }));
        return null;
      }
      obj[key] = rows[i].value;
    }
    return obj;
  };

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.name.trim()) {
      toast.warning(t("channels.nameRequired"));
      return;
    }
    if (!/^https?:\/\//.test(form.baseUrl.trim())) {
      toast.warning(t("channels.baseUrlInvalid"));
      return;
    }
    if (!isEdit && !form.apiKey.trim()) {
      toast.warning(t("channels.apiKeyRequired"));
      return;
    }
    if (form.supportedModels.length === 0) {
      toast.warning(t("channels.modelsRequired"));
      return;
    }
    const groupIds = form.tokenGroupIds.map(Number);
    if (new Set(groupIds).size !== groupIds.length) {
      toast.warning(t("channels.groupsDuplicate"));
      return;
    }
    const priority = Number(form.priority);
    if (!Number.isInteger(priority) || priority < 0) {
      toast.warning(t("channels.priorityInvalid"));
      return;
    }
    const weight = Number(form.weight);
    if (!Number.isInteger(weight) || weight <= 0) {
      toast.warning(t("channels.weightInvalid"));
      return;
    }
    const paramOverride = buildKvObject(form.paramOverride, t("channels.kvParamOverride"));
    if (paramOverride === null) return;
    const headerOverride = buildKvObject(form.headerOverride, t("channels.kvHeaderOverride"));
    if (headerOverride === null) return;
    let config: Record<string, unknown> = {};
    if (form.configText.trim()) {
      try {
        const v = JSON.parse(form.configText);
        if (!v || typeof v !== "object" || Array.isArray(v)) throw new Error();
        config = v;
      } catch {
        toast.warning(t("channels.configInvalid"));
        return;
      }
    }
    // 模型名称映射：只提交填写了上游模型名的公开模型，留空表示按公开模型名原样透传
    const modelMapping: Record<string, string> = {};
    for (const model of form.supportedModels) {
      const upstreamModel = form.modelMapping[model]?.trim();
      if (upstreamModel) modelMapping[model] = upstreamModel;
    }

    setSubmitting(true);
    try {
      await post(
        isEdit ? "/admin/channels/update" : "/admin/channels/create",
        {
          ...(isEdit ? { channel_id: channel.id } : {}),
          name: form.name.trim(),
          base_url: form.baseUrl.trim(),
          // API Key 不回显；编辑时留空表示保留旧值
          ...(form.apiKey.trim() ? { api_key: form.apiKey.trim() } : {}),
          config,
          supported_models: form.supportedModels,
          token_group_ids: groupIds,
          model_mapping: modelMapping,
          param_override: paramOverride,
          header_override: headerOverride,
          priority,
          weight,
          active: form.active,
        }
      );
      toast.success(t("channels.saveSuccess"));
      onSaved();
      onClose();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t("channels.saveFailed"));
    } finally {
      setSubmitting(false);
    }
  };

  const scrollTo = (id: (typeof FORM_SECTIONS)[number]["id"]) => {
    setActiveSection(id);
    document
      .querySelector(`[data-channel-section="${id}"]`)
      ?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  const updateKvRow = (
    key: "paramOverride" | "headerOverride",
    i: number,
    p: Partial<KvRow>
  ) => patch({ [key]: form[key].map((r, idx) => (idx === i ? { ...r, ...p } : r)) });

  /** KV 编辑区块：参数覆写与 Header 覆写共用 */
  const kvSection = (
    key: "paramOverride" | "headerOverride",
    title: string,
    description: string,
    valuePlaceholder: string
  ) => (
    <div className="space-y-2.5">
      <div>
        <p className="text-sm font-medium">{title}</p>
        <p className="text-xs text-muted-foreground">{description}</p>
      </div>
      {form[key].map((row, i) => (
        <div key={i} className="flex items-center gap-2">
          <Input
            aria-label={t("channels.kvKeyAria", { title, index: i + 1 })}
            value={row.key}
            onChange={(e) => updateKvRow(key, i, { key: e.target.value })}
            placeholder={t("channels.kvKeyPlaceholder")}
            autoComplete="off"
            className="w-44 shrink-0 font-mono text-xs"
          />
          <Input
            aria-label={t("channels.kvValueAria", { title, index: i + 1 })}
            value={row.value}
            onChange={(e) => updateKvRow(key, i, { value: e.target.value })}
            placeholder={valuePlaceholder}
            autoComplete="off"
            className="flex-1 font-mono text-xs"
          />
          <button
            type="button"
            onClick={() =>
              patch({ [key]: form[key].filter((_, idx) => idx !== i) })
            }
            aria-label={t("channels.kvDeleteAria", { title, index: i + 1 })}
            className="shrink-0 rounded-md p-1 text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive"
          >
            <Trash2 className="size-3.5" />
          </button>
        </div>
      ))}
      <button
        type="button"
        onClick={() => patch({ [key]: [...form[key], { key: "", value: "" }] })}
        className="flex w-full cursor-pointer items-center justify-center gap-1.5 rounded-lg border border-dashed border-border/70 py-2 text-xs text-muted-foreground transition-colors hover:border-primary/40 hover:bg-primary/5 hover:text-primary"
      >
        <Plus className="size-3.5" />
        {t("channels.kvAdd", { title })}
      </button>
    </div>
  );

  return (
    <div
      className="fixed inset-0 z-[80] flex justify-end bg-black/50 backdrop-blur-sm animate-in fade-in-0 duration-200"
      onMouseDown={(e) => {
        overlayMouseDown.current = e.target === e.currentTarget;
      }}
      onClick={(e) => {
        // 只有按下和抬起都在遮罩自身上才关闭；从面板内拖选文本到遮罩松手不关闭
        if (overlayMouseDown.current && e.target === e.currentTarget) onClose();
      }}
    >
      <div
        className="flex h-full w-full max-w-2xl flex-col border-l border-border/80 bg-background shadow-2xl animate-in slide-in-from-right duration-300"
        onClick={(e) => e.stopPropagation()}
      >
        <>
            {/* 抽屉头部：固定吸顶 */}
            <div className="flex items-center justify-between border-b border-border/60 px-6 py-4">
              <div>
                <h2 className="text-base font-semibold">
                  {isEdit ? t("channels.formEditTitle") : t("channels.formCreateTitle")}
                </h2>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  {isEdit
                    ? t("channels.formEditDesc", { name: channel.name })
                    : t("channels.formCreateDesc")}
                </p>
              </div>
              <button
                type="button"
                onClick={onClose}
                aria-label={t("channels.close")}
                className="rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
              >
                <X className="size-4" />
              </button>
            </div>

            {/* 分区导航 */}
            <nav className="flex gap-1 border-b border-border/60 px-6 py-2">
              {FORM_SECTIONS.map((s) => (
                <button
                  key={s.id}
                  type="button"
                  onClick={() => scrollTo(s.id)}
                  className={cn(
                    "cursor-pointer rounded-full px-3 py-1.5 text-xs transition-all duration-200",
                    activeSection === s.id
                      ? "bg-primary/10 font-medium text-primary shadow-[inset_0_0_0_1px_rgb(76_111_255/30%)]"
                      : "text-muted-foreground hover:bg-accent/70 hover:text-foreground"
                  )}
                >
                  {t(`channels.section.${s.id}`)}
                </button>
              ))}
            </nav>

            {/* 抽屉表单区：可滚动 */}
            <form
              onSubmit={onSubmit}
              className="flex min-h-0 flex-1 flex-col overflow-hidden"
            >
              <div className="min-h-0 flex-1 space-y-6 overflow-y-auto p-6">
                {/* 基础信息 */}
                <section data-channel-section="basic" className="space-y-4">
                  <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground/70">
                    {t("channels.section.basic")}
                  </p>
                  <div className="space-y-1.5">
                    <label
                      htmlFor="channel-name"
                      className="text-sm font-medium"
                    >
                      {t("channels.nameLabel")}
                    </label>
                    <Input
                      id="channel-name"
                      value={form.name}
                      onChange={(e) => patch({ name: e.target.value })}
                      placeholder={t("channels.namePlaceholder")}
                      autoComplete="off"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <label
                      htmlFor="channel-base-url"
                      className="text-sm font-medium"
                    >
                      {t("channels.baseUrlLabel")}
                    </label>
                    <Input
                      id="channel-base-url"
                      value={form.baseUrl}
                      onChange={(e) => patch({ baseUrl: e.target.value })}
                      placeholder={t("channels.baseUrlPlaceholder")}
                      autoComplete="off"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <label
                      htmlFor="channel-api-key"
                      className="text-sm font-medium"
                    >
                      API Key
                    </label>
                    <Input
                      id="channel-api-key"
                      type="password"
                      value={form.apiKey}
                      onChange={(e) => patch({ apiKey: e.target.value })}
                      placeholder={
                        isEdit ? t("channels.apiKeyEditPlaceholder") : "sk-..."
                      }
                      autoComplete="new-password"
                    />
                    <p className="text-xs text-muted-foreground">
                      {t("channels.apiKeyHint")}
                    </p>
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div className="flex items-center justify-between rounded-lg border border-border/60 bg-muted/20 p-3">
                      <div>
                        <p className="text-sm font-medium">{t("channels.enableLabel")}</p>
                        <p className="text-xs text-muted-foreground">
                          {t("channels.enableHint")}
                        </p>
                      </div>
                      <Switch
                        checked={form.active}
                        onCheckedChange={(v) => patch({ active: v })}
                      />
                    </div>
                    <div className="flex items-center justify-between rounded-lg border border-border/60 bg-muted/20 p-3">
                      <div>
                        <p className="text-sm font-medium">{t("channels.healthLabel")}</p>
                        <p className="text-xs text-muted-foreground">
                          {t("channels.healthHint")}
                        </p>
                      </div>
                      {isEdit ? (
                        <Badge
                          variant="outline"
                          className={
                            channel.healthy
                              ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
                              : "border-amber-500/30 bg-amber-500/10 text-amber-600 dark:text-amber-400"
                          }
                        >
                          {channel.healthy ? t("channels.healthHealthy") : t("channels.healthDrained")}
                        </Badge>
                      ) : (
                        <span className="text-xs text-muted-foreground">
                          {t("channels.healthPending")}
                        </span>
                      )}
                    </div>
                  </div>
                </section>

                {/* 服务范围 */}
                <section data-channel-section="scope" className="space-y-4">
                  <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground/70">
                    {t("channels.section.scope")}
                  </p>
                  <div className="space-y-1.5">
                    <span className="text-sm font-medium">{t("channels.modelsLabel")}</span>
                    <MultiSelect
                      aria-label={t("channels.modelsLabel")}
                      values={form.supportedModels}
                      onValuesChange={onModelsChange}
                      options={modelOptions.map((m) => ({
                        value: m.name,
                        label: m.name,
                      }))}
                      placeholder={t("channels.modelsPlaceholder")}
                      emptyText={t("channels.modelsEmpty")}
                      searchable
                      searchPlaceholder={t("channels.modelsSearchPlaceholder")}
                      noResultText={t("channels.modelsSearchEmpty")}
                    />
                    <p className="text-xs text-muted-foreground">
                      {t("channels.modelsHint")}
                    </p>
                  </div>
                  <div className="space-y-1.5">
                    <span className="text-sm font-medium">{t("channels.groupsLabel")}</span>
                    <MultiSelect
                      aria-label={t("channels.groupsLabel")}
                      values={form.tokenGroupIds}
                      onValuesChange={(v) => patch({ tokenGroupIds: v })}
                      options={groupOptions.map((g) => ({
                        value: String(g.id),
                        label: g.name,
                      }))}
                      placeholder={t("channels.groupsPlaceholder")}
                      emptyText={t("channels.groupsEmpty")}
                    />
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div className="space-y-1.5">
                      <label
                        htmlFor="channel-priority"
                        className="text-sm font-medium"
                      >
                        {t("channels.priorityLabel")}
                      </label>
                      <Input
                        id="channel-priority"
                        type="number"
                        min={0}
                        step={1}
                        value={form.priority}
                        onChange={(e) => patch({ priority: e.target.value })}
                      />
                    </div>
                    <div className="space-y-1.5">
                      <label
                        htmlFor="channel-weight"
                        className="text-sm font-medium"
                      >
                        {t("channels.weightLabel")}
                      </label>
                      <Input
                        id="channel-weight"
                        type="number"
                        min={1}
                        step={1}
                        value={form.weight}
                        onChange={(e) => patch({ weight: e.target.value })}
                      />
                    </div>
                  </div>
                </section>

                {/* 模型名称映射：默认按公开模型名透传，仅在上游模型名不同时填写 */}
                <section data-channel-section="mapping" className="space-y-4">
                  <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground/70">
                    {t("channels.section.mapping")}
                  </p>
                  <p className="rounded-lg border border-border/60 bg-muted/20 px-3 py-2 text-xs text-muted-foreground">
                    {t("channels.mappingNote")}
                  </p>
                  {form.supportedModels.length === 0 ? (
                    <p className="rounded-lg border border-dashed border-border/70 py-6 text-center text-xs text-muted-foreground">
                      {t("channels.mappingEmpty")}
                    </p>
                  ) : (
                    <div className="space-y-2">
                      {form.supportedModels.map((model) => (
                        <div
                          key={model}
                          className="flex items-center gap-2 rounded-lg border border-border/60 bg-muted/10 p-3"
                        >
                          <span className="w-40 shrink-0 truncate text-xs font-medium">
                            {model}
                          </span>
                          <span className="shrink-0 text-muted-foreground">
                            →
                          </span>
                          <Input
                            aria-label={t("channels.mappingAria", { model })}
                            value={form.modelMapping[model] ?? ""}
                            onChange={(e) =>
                              patch({
                                modelMapping: {
                                  ...form.modelMapping,
                                  [model]: e.target.value,
                                },
                              })
                            }
                            placeholder={t("channels.mappingPlaceholder")}
                            autoComplete="off"
                            className="flex-1"
                          />
                        </div>
                      ))}
                    </div>
                  )}
                </section>

                {/* 高级配置 */}
                <section data-channel-section="advanced" className="space-y-4">
                  <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground/70">
                    {t("channels.section.advanced")}
                  </p>
                  {kvSection(
                    "paramOverride",
                    t("channels.kvParamOverride"),
                    t("channels.paramOverrideDesc"),
                    t("channels.paramOverridePlaceholder")
                  )}
                  {kvSection(
                    "headerOverride",
                    t("channels.kvHeaderOverride"),
                    t("channels.headerOverrideDesc"),
                    t("channels.headerOverridePlaceholder")
                  )}
                  <div className="space-y-1.5">
                    <label
                      htmlFor="channel-config"
                      className="text-sm font-medium"
                    >
                      {t("channels.providerConfigLabel")}
                    </label>
                    <textarea
                      id="channel-config"
                      value={form.configText}
                      onChange={(e) => patch({ configText: e.target.value })}
                      placeholder="{}"
                      rows={4}
                      className={JSON_TEXTAREA_CLASS}
                    />
                  </div>
                </section>
              </div>

              {/* 抽屉底部操作栏：固定吸底 */}
              <div className="flex justify-end gap-2 border-t border-border/60 bg-background/80 px-6 py-3.5 backdrop-blur-sm">
                <Button type="button" variant="outline" onClick={onClose}>
                  {t("channels.cancel")}
                </Button>
                <Button type="submit" disabled={submitting}>
                  {submitting && <Loading size="sm" />}
                  {isEdit ? t("channels.saveChanges") : t("channels.createChannel")}
                </Button>
              </div>
            </form>
          </>
      </div>
    </div>
  );
}

/** 渠道详情弹窗：打开时按 channel_id 拉取详情 */
function ChannelDetailDialog({
  channelId,
  onClose,
}: {
  channelId: string;
  onClose: () => void;
}) {
  const [detail, setDetail] = useState<Channel | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const { t, i18n } = useTranslation("console");
  const locale = i18n.language === "zh" ? "zh-CN" : "en-US";

  useEffect(() => {
    get<Channel>("/admin/channels/detail", {
      params: { channel_id: channelId },
    })
      .then(setDetail)
      .catch((err) =>
        setError(err instanceof Error ? err.message : t("channels.loadFailed"))
      )
      .finally(() => setLoading(false));
  }, [channelId, t]);

  const jsonBlock = (label: string, value: unknown) => {
    if (value === undefined || value === null) return null;
    if (typeof value === "object" && Object.keys(value).length === 0)
      return null;
    if (Array.isArray(value) && value.length === 0) return null;
    return (
      <div className="space-y-1.5">
        <dt className="text-muted-foreground">{label}</dt>
        <dd>
          <pre className="max-h-48 overflow-auto rounded-md border border-border/60 bg-muted/40 p-2.5 font-mono text-xs">
            {JSON.stringify(value, null, 2)}
          </pre>
        </dd>
      </div>
    );
  };

  return (
    <div
      className="fixed inset-0 z-[80] flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="max-h-[85vh] w-full max-w-lg overflow-y-auto rounded-xl border bg-background p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-base font-semibold">{t("channels.detailTitle")}</h2>
        {loading ? (
          <div className="flex justify-center py-10">
            <Loading size="lg" />
          </div>
        ) : error || !detail ? (
          <p className="py-10 text-center text-sm text-muted-foreground">
            {error || t("channels.detailEmpty")}
          </p>
        ) : (
          <dl className="mt-5 space-y-3 text-sm">
            <div className="flex items-start justify-between gap-4">
              <dt className="shrink-0 text-muted-foreground">{t("channels.detailName")}</dt>
              <dd className="text-right font-medium">{detail.name}</dd>
            </div>
            <div className="flex items-start justify-between gap-4">
              <dt className="shrink-0 text-muted-foreground">{t("channels.detailStatus")}</dt>
              <dd className="space-x-1.5">
                <Badge variant={detail.active ? "default" : "destructive"}>
                  {detail.active ? t("channels.statusActive") : t("channels.statusInactive")}
                </Badge>
                <Badge variant={detail.healthy ? "outline" : "destructive"}>
                  {detail.healthy ? t("channels.statusHealthy") : t("channels.statusUnhealthy")}
                </Badge>
              </dd>
            </div>
            <div className="flex items-start justify-between gap-4">
              <dt className="shrink-0 text-muted-foreground">{t("channels.detailBaseUrl")}</dt>
              <dd className="break-all text-right font-mono text-xs">
                {detail.base_url}
              </dd>
            </div>
            <div className="flex items-start justify-between gap-4">
              <dt className="shrink-0 text-muted-foreground">{t("channels.detailPriorityWeight")}</dt>
              <dd className="text-right font-mono text-xs">
                {detail.priority} / {detail.weight}
              </dd>
            </div>
            <div className="flex items-start justify-between gap-4">
              <dt className="shrink-0 text-muted-foreground">{t("channels.detailModels")}</dt>
              <dd className="break-all text-right text-xs">
                {detail.supported_models?.length
                  ? detail.supported_models.join(", ")
                  : "-"}
              </dd>
            </div>
            <div className="flex items-start justify-between gap-4">
              <dt className="shrink-0 text-muted-foreground">{t("channels.detailGroups")}</dt>
              <dd className="flex flex-wrap justify-end gap-1 text-right text-xs">
                {detail.token_groups?.length
                  ? detail.token_groups.map((g) => (
                      <Badge key={g.id} variant="secondary" className="font-normal">
                        {g.name}
                      </Badge>
                    ))
                  : detail.token_group_ids?.length
                    ? detail.token_group_ids.join(", ")
                    : "-"}
              </dd>
            </div>
            {jsonBlock(t("channels.detailMapping"), detail.model_mapping)}
            {jsonBlock(t("channels.detailParamOverride"), detail.param_override)}
            {jsonBlock(t("channels.detailHeaderOverride"), detail.header_override)}
            {jsonBlock(t("channels.detailProviderConfig"), detail.config)}
            {/* 最近测试快照：usage 字段不固定，整体作为只读 JSON 展示 */}
            {jsonBlock(t("channels.detailLatestTest"), detail.latest_test_snapshot)}
            <div className="flex items-start justify-between gap-4">
              <dt className="shrink-0 text-muted-foreground">{t("channels.detailCreatedAt")}</dt>
              <dd className="text-right text-xs text-muted-foreground">
                {formatTime(locale, detail.created_at)}
              </dd>
            </div>
            <div className="flex items-start justify-between gap-4">
              <dt className="shrink-0 text-muted-foreground">{t("channels.detailUpdatedAt")}</dt>
              <dd className="text-right text-xs text-muted-foreground">
                {formatTime(locale, detail.updated_at)}
              </dd>
            </div>
          </dl>
        )}
        <div className="mt-6 flex justify-end">
          <Button variant="outline" onClick={onClose}>
            {t("channels.close")}
          </Button>
        </div>
      </div>
    </div>
  );
}

/** 删除渠道确认弹窗 */
function DeleteChannelDialog({
  channel,
  onClose,
  onDeleted,
}: {
  channel: Channel;
  onClose: () => void;
  onDeleted: () => void;
}) {
  const [submitting, setSubmitting] = useState(false);
  const { t } = useTranslation("console");

  const onConfirm = async () => {
    setSubmitting(true);
    try {
      await post("/admin/channels/delete", { channel_id: channel.id });
      toast.success(t("channels.deleteSuccess"));
      onDeleted();
      onClose();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t("channels.deleteFailed"));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-[80] flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="w-full max-w-sm rounded-xl border bg-background p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-base font-semibold">{t("channels.deleteTitle")}</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          {t("channels.deleteConfirm", { name: channel.name })}
        </p>
        <div className="mt-6 flex justify-end gap-2">
          <Button variant="outline" onClick={onClose}>
            {t("channels.cancel")}
          </Button>
          <Button
            variant="destructive"
            onClick={onConfirm}
            disabled={submitting}
          >
            {submitting && <Loading size="sm" />}
            {t("channels.confirmDelete")}
          </Button>
        </div>
      </div>
    </div>
  );
}

/** 单张测试图片预览：渲染失败时显示占位，不打印媒体数据 */
function TestImageItem({ item }: { item: { url?: string; b64_json?: string } }) {
  const { t } = useTranslation("console");
  const [failed, setFailed] = useState(false);
  const [zoomed, setZoomed] = useState(false);
  const src = item.url ?? (item.b64_json ? `data:image/png;base64,${item.b64_json}` : null);
  if (!src) return null;
  if (failed) {
    return (
      <p className="col-span-2 text-xs text-zinc-500">{t("channels.testImageFailed")}</p>
    );
  }
  return (
    <>
      <button
        type="button"
        onClick={() => setZoomed(true)}
        className="group block w-fit cursor-zoom-in overflow-hidden rounded-lg transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
        title={t("channels.testZoomHint")}
      >
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={src}
          alt={t("channels.testImageAlt")}
          onError={() => setFailed(true)}
          className="max-h-32 w-auto rounded-lg object-contain transition group-hover:brightness-95"
        />
      </button>

      {zoomed && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label={t("channels.testZoomAria")}
          className="fixed inset-0 z-[100] flex items-center justify-center bg-black/80 p-4 backdrop-blur-sm"
          onClick={() => setZoomed(false)}
        >
          <button
            type="button"
            aria-label={t("channels.close")}
            onClick={() => setZoomed(false)}
            className="absolute right-4 top-4 rounded-full bg-white/10 p-2 text-white transition hover:bg-white/20"
          >
            <X className="size-5" />
          </button>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={src}
            alt={t("channels.testImageAltLarge")}
            onClick={(e) => e.stopPropagation()}
            className="max-h-[90vh] max-w-[90vw] cursor-default rounded-lg object-contain shadow-2xl"
          />
        </div>
      )}
    </>
  );
}

/** 测试渠道上游弹窗：选择渠道已配置模型，发起测试并以终端日志形式即时预览执行过程与结果 */
function ChannelTestDialog({
  channel,
  modelOptions,
  onClose,
  onCompleted,
}: {
  channel: Channel;
  modelOptions: ModelOption[];
  onClose: () => void;
  onCompleted: () => void;
}) {
  const models = channel.supported_models ?? [];
  const { t } = useTranslation("console");
  const [model, setModel] = useState(models[0] ?? "");
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<ChannelTestResult | null>(null);
  const [error, setError] = useState("");

  const onTest = async () => {
    if (!model || submitting) return;
    setSubmitting(true);
    setResult(null);
    setError("");
    try {
      const res = await post<ChannelTestResult>(
        "/admin/channels/test",
        { channel_id: channel.id, model },
        // 与后端读取上游的超时对齐，避免浏览器提前中止
        { timeoutMs: 180_000, apiKind: "admin" }
      );
      setResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("channels.testNetworkFailed"));
    } finally {
      setSubmitting(false);
      // 成功、失败或超时后端都会覆盖渠道快照，刷新列表展示最新摘要
      onCompleted();
    }
  };

  const started = submitting || !!result || !!error;
  const textContent =
    result?.result?.type === "text" ? result.result.content : null;
  const imageItems =
    result?.result?.type === "image" ? result.result.items : null;
  const modelType = modelOptions.find((m) => m.name === model)?.model_type;
  const testPrompt = modelType === "image" ? "a cute cat" : "hi";

  return (
    <div
      className="fixed inset-0 z-[80] flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="flex max-h-[85vh] w-full max-w-xl flex-col overflow-hidden rounded-xl border bg-background shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* 头部：标题 + 关闭 */}
        <div className="flex items-center justify-between px-5 pt-4">
          <h2 className="text-base font-semibold">{t("channels.testTitle")}</h2>
          <button
            type="button"
            aria-label={t("channels.close")}
            onClick={onClose}
            className="rounded-md p-1 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          >
            <X className="size-4" />
          </button>
        </div>

        {/* 账号卡片 */}
        <div className="px-5 pt-4">
          <div className="flex items-center justify-between gap-3 rounded-lg border bg-muted/40 px-3.5 py-3">
            <div className="flex min-w-0 items-center gap-3">
              <span
                className={cn(
                  "flex size-10 shrink-0 items-center justify-center rounded-md",
                  channel.active
                    ? "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400"
                    : "bg-muted text-muted-foreground"
                )}
              >
                <PlugZap className="size-4" />
              </span>
              <div className="min-w-0">
                <p className="truncate text-sm font-medium">{channel.name}</p>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  <span className="mr-1.5 inline-flex items-center rounded bg-amber-500/15 px-1.5 py-0.5 font-mono text-[10px] font-medium tracking-wide text-amber-600 dark:text-amber-400">
                    APIKEY
                  </span>
                  {t("channels.testChannelTag")}
                </p>
              </div>
            </div>
            <Badge
              variant="outline"
              className={cn(
                "shrink-0 border-transparent",
                channel.active
                  ? "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400"
                  : "bg-muted text-muted-foreground"
              )}
            >
              {channel.active ? t("channels.testActive") : t("channels.testInactive")}
            </Badge>
          </div>
        </div>

        {/* 选择测试模型 */}
        <div className="space-y-1.5 px-5 pt-4">
          <span className="text-sm font-medium">{t("channels.testModelLabel")}</span>
          {models.length === 0 ? (
            <p className="rounded-lg border border-dashed border-border/70 py-4 text-center text-xs text-muted-foreground">
              {t("channels.testModelEmpty")}
            </p>
          ) : (
            <Select
              aria-label={t("channels.testModelAria")}
              value={model}
              onValueChange={setModel}
              options={models.map((m) => ({ value: m, label: m }))}
              placeholder={t("channels.testModelPlaceholder")}
              disabled={submitting}
            />
          )}
        </div>

        {/* 终端日志 */}
        <div className="px-5 pt-4">
          <div className="overflow-hidden rounded-lg border border-zinc-800 bg-zinc-950 font-mono text-xs leading-relaxed text-zinc-300 shadow-inner">
            <div className="max-h-80 min-h-44 space-y-1 overflow-y-auto px-3.5 py-3">
              {!started ? (
                <p className="text-zinc-500">
                  <span className="mr-2 text-zinc-600">$</span>
                  {t("channels.testIdleHint")}
                </p>
              ) : (
                <>
                  <p>
                    <span className="text-zinc-500">{t("channels.testStartLabel")}</span>
                    <span className="text-zinc-100">{channel.name}</span>
                  </p>
                  <p>
                    <span className="text-zinc-500">{t("channels.testAddressLabel")}</span>
                    <span className="break-all text-sky-400">
                      {channel.base_url}
                    </span>
                  </p>
                  <p>
                    <span className="text-zinc-500">{t("channels.testModelPrefix")}</span>
                    <span className="text-emerald-400">{model}</span>
                  </p>
                  <p>
                    <span className="text-zinc-500">{t("channels.testMessageLabel")}</span>
                    <span className="text-zinc-100">"{testPrompt}"</span>
                  </p>

                  {submitting && (
                    <p className="flex items-center gap-2 text-zinc-400">
                      <Loader2 className="size-3.5 animate-spin" />
                      {t("channels.testWaiting")}
                    </p>
                  )}

                  {!submitting && result?.success && textContent !== null && (
                    <>
                      <p className="text-zinc-500">{t("channels.testResponseLabel")}</p>
                      <pre className="whitespace-pre-wrap break-all rounded bg-zinc-900/60 px-2.5 py-2 text-zinc-100">
                        {textContent}
                      </pre>
                    </>
                  )}

                  {!submitting && result?.success && imageItems && (
                    <>
                      <p className="text-zinc-500">{t("channels.testResponseImageLabel")}</p>
                      <div className="grid grid-cols-2 gap-2 pt-1">
                        {imageItems.map((item, i) => (
                          <TestImageItem key={i} item={item} />
                        ))}
                      </div>
                    </>
                  )}

                  {!submitting && result && !result.success && (
                    <p className="text-rose-400">
                      ✗ {result.message || t("channels.testFailedDefault")}
                    </p>
                  )}

                  {!submitting && error && (
                    <p className="text-rose-400">✗ {error}</p>
                  )}

                  {!submitting && result?.success && (
                    <p className="flex items-center gap-1.5 border-t border-zinc-800/80 pt-2 text-emerald-400">
                      <CheckCircle2 className="size-3.5" />
                      {t("channels.testDone", {
                        time: result.time.toFixed(2),
                        amount: result.amount,
                      })}
                    </p>
                  )}
                  {!submitting && result && !result.success && (
                    <p className="text-zinc-500">
                      {t("channels.testElapsed", { time: result.time.toFixed(2) })}
                    </p>
                  )}
                </>
              )}
            </div>
          </div>
        </div>

        {/* 底部：meta + 操作 */}
        <div className="mt-4 flex items-center justify-between gap-3 border-t bg-muted/30 px-5 py-3">
          <div className="flex items-center gap-4 text-xs text-muted-foreground">
            <span className="inline-flex items-center gap-1.5">
              <Waypoints className="size-3.5" />
              {t("channels.testModelTag")}
            </span>
            <span className="inline-flex items-center gap-1.5">
              <Activity className="size-3.5" />
              {t("channels.testPromptTag", { prompt: testPrompt })}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" onClick={onClose}>
              {t("channels.close")}
            </Button>
            <Button
              onClick={onTest}
              disabled={submitting || models.length === 0 || !model}
              className="min-w-28"
            >
              {submitting ? (
                <>
                  <Loader2 className="animate-spin" />
                  {t("channels.testingButton")}
                </>
              ) : started ? (
                <>
                  <RefreshCw />
                  {t("channels.retryButton")}
                </>
              ) : (
                t("channels.startTest")
              )}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}

export function ChannelsPanel() {
  const { t, i18n } = useTranslation("console");
  const locale = i18n.language === "zh" ? "zh-CN" : "en-US";
  const [channels, setChannels] = useState<Channel[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingChannel, setEditingChannel] = useState<Channel | null>(null);
  const [detailChannelId, setDetailChannelId] = useState<string | null>(null);
  const [deletingChannel, setDeletingChannel] = useState<Channel | null>(null);
  const [testingChannel, setTestingChannel] = useState<Channel | null>(null);
  const [updatingKey, setUpdatingKey] = useState<string | null>(null);
  const [fetchingId, setFetchingId] = useState<string | null>(null);
  const [modelOptions, setModelOptions] = useState<ModelOption[]>([]);
  const [groupOptions, setGroupOptions] = useState<GroupOption[]>([]);
  // 三个搜索框为输入实时值，applied* 为已提交的筛选条件
  const [channelNameInput, setChannelNameInput] = useState("");
  const [modelNameInput, setModelNameInput] = useState("");
  const [groupNameInput, setGroupNameInput] = useState("");
  const [appliedChannelName, setAppliedChannelName] = useState("");
  const [appliedModelName, setAppliedModelName] = useState("");
  const [appliedGroupName, setAppliedGroupName] = useState("");

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const load = useCallback(
    async (p: number, channelName: string, modelName: string, groupName: string) => {
      setLoading(true);
      setError("");
      try {
        const data = await get<unknown>("/admin/channels/list", {
          params: {
            page: p,
            page_size: PAGE_SIZE,
            ...(channelName ? { channel_name: channelName } : {}),
            ...(modelName ? { model_name: modelName } : {}),
            ...(groupName ? { token_group_name: groupName } : {}),
          },
        });
        const { channels, total } = normalize(data);
        setChannels(channels);
        setTotal(total);
      } catch (err) {
        setError(err instanceof Error ? err.message : t("channels.loadFailed"));
      } finally {
        setLoading(false);
      }
    },
    [t]
  );

  useEffect(() => {
    load(page, appliedChannelName, appliedModelName, appliedGroupName);
  }, [load, page, appliedChannelName, appliedModelName, appliedGroupName]);

  const onSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setPage(1);
    setAppliedChannelName(channelNameInput.trim());
    setAppliedModelName(modelNameInput.trim());
    setAppliedGroupName(groupNameInput.trim());
  };

  const onClearSearch = () => {
    setChannelNameInput("");
    setModelNameInput("");
    setGroupNameInput("");
    setPage(1);
    setAppliedChannelName("");
    setAppliedModelName("");
    setAppliedGroupName("");
  };

  const hasFilterInput = Boolean(channelNameInput || modelNameInput || groupNameInput);

  // 拉取表单选项：模型、令牌分组
  useEffect(() => {
    get<unknown>("/admin/models/list", {
      params: { page: 1, page_size: 100 },
    })
      .then((data) => setModelOptions(normalizeOptions<ModelOption>(data)))
      .catch(() => {});
    get<unknown>("/admin/token/groups/list", {
      params: { page: 1, page_size: 100 },
    })
      .then((data) => setGroupOptions(normalizeOptions<GroupOption>(data)))
      .catch(() => {});
  }, []);

  /** 启用/停用：乐观更新，失败回滚（健康状态由健康检查驱动，不在此切换） */
  const toggleActive = async (channel: Channel, value: boolean) => {
    const key = `${channel.id}:active`;
    setUpdatingKey(key);
    setChannels((prev) =>
      prev.map((c) => (c.id === channel.id ? { ...c, active: value } : c))
    );
    try {
      await post("/admin/channels/update-status", {
        channel_id: channel.id,
        active: value,
      });
      toast.success(value ? t("channels.enabledToast") : t("channels.disabledToast"));
    } catch (err) {
      setChannels((prev) =>
        prev.map((c) =>
          c.id === channel.id ? { ...c, active: channel.active } : c
        )
      );
      toast.error(err instanceof Error ? err.message : t("channels.statusUpdateFailed"));
    } finally {
      setUpdatingKey(null);
    }
  };

  /** 卡片内联调整：点击立即乐观更新；每个渠道字段一条串行队列，在途请求期间继续点击只更新目标值，结束后自动续发 */
  const channelsRef = useRef<Channel[]>(channels);
  useEffect(() => {
    channelsRef.current = channels;
  }, [channels]);
  const adjustState = useRef<
    Record<string, { target: number; base: number; sending: boolean }>
  >({});

  const scheduleAdjust = (channel: Channel, field: "priority" | "weight", delta: number) => {
    const key = `${channel.id}:${field}`;
    const min = field === "priority" ? 0 : 1;
    const entry = adjustState.current[key];
    // 连击时基于未保存的目标值累加，避免与渲染竞争
    const currentTarget = entry ? entry.target : channel[field];
    const next = Math.max(min, currentTarget + delta);
    if (next === currentTarget) return;
    if (entry) {
      entry.target = next;
    } else {
      adjustState.current[key] = { base: channel[field], target: next, sending: false };
    }
    setChannels((prev) =>
      prev.map((c) => (c.id === channel.id ? { ...c, [field]: next } : c))
    );
    void flushAdjust(channel.id, field);
  };

  const flushAdjust = async (channelId: string, field: "priority" | "weight") => {
    const key = `${channelId}:${field}`;
    const entry = adjustState.current[key];
    // 已有在途请求：新目标值会在请求结束后的 finally 中续发
    if (!entry || entry.sending) return;
    if (entry.target === entry.base) {
      delete adjustState.current[key];
      return;
    }
    entry.sending = true;
    const channel = channelsRef.current.find((c) => c.id === channelId);
    if (!channel) {
      delete adjustState.current[key];
      return;
    }
    const label = field === "priority" ? t("channels.priority") : t("channels.weight");
    const value = entry.target;
    try {
      await post("/admin/channels/update", {
        channel_id: channel.id,
        name: channel.name,
        base_url: channel.base_url,
        config: channel.config ?? {},
        supported_models: channel.supported_models ?? [],
        token_group_ids: channel.token_group_ids ?? [],
        model_mapping: channel.model_mapping ?? {},
        param_override: channel.param_override ?? {},
        header_override: channel.header_override ?? {},
        priority: field === "priority" ? value : channel.priority,
        weight: field === "weight" ? value : channel.weight,
        active: channel.active,
      });
      entry.base = value; // 确认值推进
      // 中间结果不打扰，仅在到达最新目标值时提示
      if (entry.target === value) toast.success(t("channels.adjustUpdated", { label, value }));
    } catch (err) {
      entry.target = entry.base; // 丢弃未保存的目标值
      setChannels((prev) =>
        prev.map((c) => (c.id === channelId ? { ...c, [field]: entry.base } : c))
      );
      toast.error(err instanceof Error ? err.message : t("channels.adjustUpdateFailed", { label }));
    } finally {
      entry.sending = false;
      if (entry.target !== entry.base) void flushAdjust(channelId, field);
      else delete adjustState.current[key];
    }
  };

  /** 编辑前先拉取详情，确保表单拿到完整模型名称映射与覆写配置 */
  const openEdit = async (channel: Channel) => {
    setFetchingId(channel.id);
    try {
      const detail = await get<Channel>("/admin/channels/detail", {
        params: { channel_id: channel.id },
      });
      setEditingChannel(detail);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t("channels.getDetailFailed"));
    } finally {
      setFetchingId(null);
    }
  };

  const onDeleted = () => {
    // 删除当前页最后一条时回退到上一页
    if (channels.length === 1 && page > 1) {
      setPage(page - 1);
    } else {
      load(page, appliedChannelName, appliedModelName, appliedGroupName);
    }
  };

  return (
    <div className="flex min-h-[calc(100vh-7.5rem)] w-full flex-col gap-6">
      {/* 页头 */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold">{t("channels.title")}</h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            {t("channels.totalChannels", { total })}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <form onSubmit={onSearch} className="flex flex-wrap items-center gap-2">
            <div className="relative">
              <Search className="absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={channelNameInput}
                onChange={(e) => setChannelNameInput(e.target.value)}
                placeholder={t("channels.filterChannelPlaceholder")}
                className="h-8 w-44 pl-9"
              />
            </div>
            <div className="relative">
              <Search className="absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={modelNameInput}
                onChange={(e) => setModelNameInput(e.target.value)}
                placeholder={t("channels.filterModelPlaceholder")}
                className="h-8 w-44 pl-9"
              />
            </div>
            <div className="relative">
              <Search className="absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={groupNameInput}
                onChange={(e) => setGroupNameInput(e.target.value)}
                placeholder={t("channels.filterGroupPlaceholder")}
                className="h-8 w-44 pl-9"
              />
            </div>
            <Button type="submit" variant="outline" size="sm" aria-label={t("channels.search")}>
              <Search className="size-4" />
              {t("channels.search")}
            </Button>
            {hasFilterInput && (
              <Button type="button" variant="ghost" size="sm" onClick={onClearSearch} aria-label={t("channels.clearFilters")}>
                <X className="size-4" />
                {t("channels.clearButton")}
              </Button>
            )}
          </form>
          <Button
            variant="outline"
            size="sm"
            onClick={() => load(page, appliedChannelName, appliedModelName, appliedGroupName)}
            disabled={loading}
          >
            <RefreshCw className={cn("size-4", loading && "animate-spin")} />
            {t("channels.refresh")}
          </Button>
          <Button size="sm" onClick={() => setDialogOpen(true)}>
            <Plus className="size-4" />
            {t("channels.createButton")}
          </Button>
        </div>
      </div>

      {/* 渠道卡片网格 */}
      <div className="relative">
        {error && channels.length === 0 ? (
          <div className="flex flex-col items-center gap-2 rounded-xl border border-border/60 bg-card/40 py-16 text-sm text-muted-foreground">
            <p>{t("channels.loadFailedWithReason", { error })}</p>
            <Button variant="outline" size="sm" onClick={() => load(page, appliedChannelName, appliedModelName, appliedGroupName)}>
              {t("channels.retry")}
            </Button>
          </div>
        ) : channels.length === 0 ? (
          <div className="flex items-center justify-center rounded-xl border border-border/60 bg-card/40 py-16 text-muted-foreground">
            {loading ? (
              <Loading size="lg" />
            ) : (
              <div className="flex flex-col items-center gap-2">
                <Waypoints className="size-8 text-muted-foreground/50" />
                <p className="text-sm">{t("channels.empty")}</p>
              </div>
            )}
          </div>
        ) : (
          <>
            {/* 加载中保留旧数据并降低透明度，避免卡片整体闪烁 */}
            <div
              className={cn(
                "grid gap-4 sm:grid-cols-2 xl:grid-cols-3 transition-opacity duration-300",
                loading && "pointer-events-none opacity-40"
              )}
            >
              {channels.map((c) => {
                // 状态条/状态点三态：健康（启用且健康）/ 已摘流 / 已停用
                const status = !c.active
                  ? "disabled"
                  : c.healthy
                    ? "running"
                    : "drained";
                const statusMeta = {
                  running: {
                    bar: "bg-emerald-500",
                    dot: "bg-emerald-500",
                  },
                  drained: {
                    bar: "bg-amber-500",
                    dot: "bg-amber-500",
                  },
                  disabled: {
                    bar: "bg-destructive",
                    dot: "bg-destructive",
                  },
                }[status];
                return (
                  <div
                    key={c.id}
                    className={cn(
                      "group relative flex flex-col gap-4 overflow-hidden rounded-xl border bg-card/60 p-5 transition-all duration-200 hover:-translate-y-0.5 hover:shadow-lg hover:shadow-black/5",
                      status === "running" &&
                        "border-emerald-500/25 hover:border-emerald-500/50",
                      status === "drained" &&
                        "border-amber-500/25 hover:border-amber-500/50",
                      status === "disabled" &&
                        "border-destructive/25 hover:border-destructive/50"
                    )}
                  >
                    {/* 顶部状态条 */}
                    <span
                      className={cn(
                        "absolute inset-x-0 top-0 h-[3px]",
                        statusMeta.bar
                      )}
                    />

                    {/* 头部：名称 + 适配器 + 状态徽章 */}
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <span
                            className={cn(
                              "size-2 shrink-0 rounded-full",
                              statusMeta.dot,
                              status === "running" &&
                                "shadow-[0_0_8px] shadow-emerald-500/60"
                            )}
                          />
                          <h3 className="truncate font-semibold">{c.name}</h3>
                        </div>
                        <p
                          className="mt-1 truncate font-mono text-xs text-muted-foreground"
                          title={c.base_url}
                        >
                          {c.base_url}
                        </p>
                      </div>
                      <div className="flex shrink-0 items-center gap-1.5">
                        <Badge
                          variant="outline"
                          className={cn(
                            c.active
                              ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
                              : "border-destructive/30 bg-destructive/10 text-destructive"
                          )}
                        >
                          {c.active ? t("channels.cardEnabled") : t("channels.cardDisabled")}
                        </Badge>
                        <Badge
                          variant="outline"
                          className={cn(
                            c.healthy
                              ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
                              : "border-amber-500/30 bg-amber-500/10 text-amber-600 dark:text-amber-400"
                          )}
                        >
                          {c.healthy ? t("channels.cardHealthy") : t("channels.cardDrained")}
                        </Badge>
                      </div>
                    </div>

                    {/* 模型 */}
                    <div className="space-y-2.5">
                      <div className="flex flex-wrap gap-1.5">
                        {c.supported_models?.length ? (
                          <>
                            {c.supported_models.slice(0, 3).map((m) => (
                              <Badge
                                key={m}
                                variant="outline"
                                className="max-w-full whitespace-normal break-all text-left font-normal text-muted-foreground"
                              >
                                {m}
                              </Badge>
                            ))}
                            {c.supported_models.length > 3 && (
                              <Badge
                                variant="outline"
                                className="font-normal text-muted-foreground"
                              >
                                +{c.supported_models.length - 3}
                              </Badge>
                            )}
                          </>
                        ) : (
                          <span className="text-xs text-muted-foreground/70">
                            {t("channels.cardNoModels")}
                          </span>
                        )}
                      </div>
                    </div>

                    {/* 元信息：优先级/权重支持卡片内直接加减 */}
                    <div className="flex items-center gap-4 text-xs text-muted-foreground">
                      <InlineStepper
                        label={t("channels.priority")}
                        value={c.priority}
                        min={0}
                        onStep={(d) => scheduleAdjust(c, "priority", d)}
                      />
                      <InlineStepper
                        label={t("channels.weight")}
                        value={c.weight}
                        min={1}
                        onStep={(d) => scheduleAdjust(c, "weight", d)}
                      />
                      <span
                        className="ml-auto inline-flex min-w-0 items-center gap-1"
                        title={
                          c.token_groups?.length
                            ? c.token_groups.map((g) => g.name).join(", ")
                            : undefined
                        }
                      >
                        <Layers className="size-3.5 shrink-0" />
                        {c.token_groups?.length ? (
                          <>
                            <span className="truncate">
                              {c.token_groups
                                .slice(0, 2)
                                .map((g) => g.name)
                                .join(", ")}
                            </span>
                            {c.token_groups.length > 2 && (
                              <span className="shrink-0">
                                +{c.token_groups.length - 2}
                              </span>
                            )}
                          </>
                        ) : (
                          t("channels.cardGroupsCount", { count: c.token_group_ids?.length ?? 0 })
                        )}
                      </span>
                    </div>

                    {/* 最近测试摘要：分开展示的标签，覆盖式快照不含文本内容与图片 */}
                    <div className="flex flex-wrap items-center gap-1.5">
                      {c.latest_test_snapshot ? (
                        <>
                          <Badge
                            variant="outline"
                            className={cn(
                              "max-w-40 truncate font-normal",
                              c.latest_test_snapshot.status === "succeeded"
                                ? "border-emerald-500/30 text-emerald-600 dark:text-emerald-400"
                                : "border-destructive/30 text-destructive"
                            )}
                          >
                            {c.latest_test_snapshot.model}
                          </Badge>
                          <Badge
                            variant="outline"
                            className={cn(
                              "font-normal",
                              c.latest_test_snapshot.status === "succeeded"
                                ? "border-emerald-500/30 text-emerald-600 dark:text-emerald-400"
                                : "border-destructive/30 text-destructive"
                            )}
                          >
                            {(c.latest_test_snapshot.duration_ms / 1000).toFixed(2)}s
                          </Badge>
                          {c.latest_test_snapshot.status === "succeeded" && (
                            <Badge
                              variant="outline"
                              className="border-emerald-500/30 font-normal text-emerald-600 dark:text-emerald-400"
                            >
                              {c.latest_test_snapshot.amount}
                            </Badge>
                          )}
                          {c.latest_test_snapshot.status === "failed" &&
                            c.latest_test_snapshot.message && (
                              <Badge
                                variant="outline"
                                className="max-w-72 shrink truncate border-destructive/30 font-normal text-destructive"
                                title={c.latest_test_snapshot.message}
                              >
                                {c.latest_test_snapshot.message}
                              </Badge>
                            )}
                        </>
                      ) : (
                        <span className="text-xs text-muted-foreground/70">
                          {t("channels.cardNotTested")}
                        </span>
                      )}
                    </div>

                    {/* 底部：启停按钮 + 健康状态 + 操作 */}
                    <div className="mt-auto flex items-center justify-between gap-2 border-t border-border/60 pt-3.5">
                      <div className="flex items-center gap-2.5">
                        <Button
                          variant="ghost"
                          size="icon"
                          className={cn(
                            "size-8 rounded-full border",
                            c.active
                              ? "border-emerald-500/40 text-emerald-500 hover:bg-emerald-500/10 hover:text-emerald-600"
                              : "border-destructive/40 text-destructive hover:bg-destructive/10 hover:text-destructive"
                          )}
                          disabled={updatingKey === `${c.id}:active`}
                          onClick={() => toggleActive(c, !c.active)}
                          aria-label={c.active ? t("channels.deactivateAria") : t("channels.activateAria")}
                          title={c.active ? t("channels.deactivateTitle") : t("channels.activateTitle")}
                        >
                          {updatingKey === `${c.id}:active` ? (
                            <Loading size="sm" />
                          ) : (
                            <span className="relative inline-flex">
                              <Power className="size-4" />
                              {/* 停用状态叠加斜杠禁用标志 */}
                              {!c.active && (
                                <span
                                  aria-hidden
                                  className="absolute left-1/2 top-1/2 h-px w-[135%] -translate-x-1/2 -translate-y-1/2 rotate-45 bg-current"
                                />
                              )}
                            </span>
                          )}
                        </Button>
                      </div>
                      <div className="flex items-center gap-1">
                        <Button
                          variant="ghost"
                          size="sm"
                          className="size-8 px-0"
                          onClick={() => setTestingChannel(c)}
                          aria-label={t("channels.testAria")}
                          title={t("channels.testTitle_")}
                        >
                          <Activity className="size-4" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="size-8 px-0"
                          onClick={() => setDetailChannelId(c.id)}
                          aria-label={t("channels.viewDetailAria")}
                          title={t("channels.detailTitle_")}
                        >
                          <Eye className="size-4" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="size-8 px-0"
                          onClick={() => {
                            void post("/admin/channels/copy", { channel_id: c.id })
                              .then(() => {
                                toast.success(t("channels.copySuccess"));
                                load(page, appliedChannelName, appliedModelName, appliedGroupName);
                              })
                              .catch((err) => toast.error(err instanceof Error ? err.message : t("channels.copyFailed")));
                          }}
                          aria-label={t("channels.copyAria")}
                          title={t("channels.copyTitle_")}
                        >
                          <Copy className="size-4" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="size-8 px-0"
                          onClick={() => openEdit(c)}
                          disabled={fetchingId === c.id}
                          aria-label={t("channels.editAria")}
                          title={t("channels.editTitle_")}
                        >
                          {fetchingId === c.id ? (
                            <Loading size="sm" />
                          ) : (
                            <Pencil className="size-4" />
                          )}
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="size-8 px-0 text-destructive hover:bg-destructive/10 hover:text-destructive"
                          onClick={() => setDeletingChannel(c)}
                          aria-label={t("channels.deleteAria")}
                          title={t("channels.deleteTitle_")}
                        >
                          <Trash2 className="size-4" />
                        </Button>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
            {loading && (
              <div className="pointer-events-none absolute inset-x-0 top-0 flex justify-center pt-20">
                <Loading size="md" />
              </div>
            )}
          </>
        )}
      </div>

      {/* 分页：mt-auto 固定吸底，不随列表高度跳动 */}
      {!error && channels.length > 0 && (
        <Pagination
          page={page}
          totalPages={totalPages}
          loading={loading}
          onChange={setPage}
          className="mt-auto"
        />
      )}

      {dialogOpen && (
        <ChannelFormDialog
          channel={null}
          modelOptions={modelOptions}
          groupOptions={groupOptions}
          onClose={() => setDialogOpen(false)}
          onSaved={() => load(page, appliedChannelName, appliedModelName, appliedGroupName)}
        />
      )}
      {editingChannel && (
        <ChannelFormDialog
          channel={editingChannel}
          modelOptions={modelOptions}
          groupOptions={groupOptions}
          onClose={() => setEditingChannel(null)}
          onSaved={() => load(page, appliedChannelName, appliedModelName, appliedGroupName)}
        />
      )}
      {detailChannelId && (
        <ChannelDetailDialog
          channelId={detailChannelId}
          onClose={() => setDetailChannelId(null)}
        />
      )}
      {deletingChannel && (
        <DeleteChannelDialog
          channel={deletingChannel}
          onClose={() => setDeletingChannel(null)}
          onDeleted={onDeleted}
        />
      )}
      {testingChannel && (
        <ChannelTestDialog
          channel={testingChannel}
          modelOptions={modelOptions}
          onClose={() => setTestingChannel(null)}
          onCompleted={() => load(page, appliedChannelName, appliedModelName, appliedGroupName)}
        />
      )}
    </div>
  );
}
