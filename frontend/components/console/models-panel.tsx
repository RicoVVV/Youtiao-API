"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Check, CircleDollarSign, Copy, Cpu, Eye, Pencil, Plus, RefreshCw, Search, Trash2, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Loading } from "@/components/ui/loading";
import { MultiSelect } from "@/components/ui/multi-select";
import { Pagination } from "@/components/ui/pagination";
import { ProviderLogo } from "@/components/ui/provider-logo";
import { Select } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { toast } from "@/components/ui/toaster";
import { cn } from "@/lib/utils";
import { get, post } from "@/lib/request";
import {
  buildContract,
  emptyContractState,
  InputContractEditor,
  stateFromContract,
  stateFromTemplate,
  type ContractFormState,
} from "@/components/console/input-contract-editor";
import { ModelPricingDrawer } from "@/components/console/pricing-panel";

/** 模型类型：文本 / 图片 / 视频 */
export type ModelType = "text" | "image" | "video";

export type ModelOption = {
  id: string;
  name: string;
  model_type: ModelType;
};

type PublicModel = ModelOption & {
  input_contract?: Record<string, unknown>;
  pricing_fields?: string[];
  template_id?: string;
  /** 模型介绍（最长 512 字符）；null 表示未填写 */
  description?: string | null;
  /** 厂商标识（筛选键），无明确厂商时为 null */
  provider_id?: string | null;
  /** 厂商展示名，无明确厂商时为 null */
  provider_name?: string | null;
  /** 厂商图标地址（相对路径，可直接作为 img src）；null 表示不渲染图标 */
  provider_logo_url?: string | null;
  material_fields?: Record<string, { categories?: string[]; multiple?: boolean }>;
  /** 默认每用户并发上限：null 不限制，0 禁止创建，1-10000 为每用户最大在途任务数 */
  default_concurrency_limit?: number | null;
  active: boolean;
  created_at?: string;
  updated_at?: string;
};

type Translate = (key: string, options?: Record<string, unknown>) => string;

/** 默认每用户并发上限的展示文案 */
function defaultConcurrencyLabel(
  t: Translate,
  limit: number | null | undefined
): string {
  if (limit === null || limit === undefined) return t("models.concurrencyUnlimited");
  if (limit === 0) return t("models.concurrencyBanned");
  return String(limit);
}

/** Provider 模板摘要：渲染模板选择器，前端不硬编码 Provider 类型或模板名 */
export type ProviderTemplateSummary = {
  template_id: string;
  provider_type: string;
  label: string;
  model_type: string;
  /** 供应商标识，无明确供应商时为 null */
  provider_id?: string | null;
  /** 供应商展示名，随 X-Locale 切换 */
  provider_name?: string | null;
  /** 供应商图标地址（相对路径，可直接作为 img src）；null 表示不渲染图标 */
  provider_logo_url?: string | null;
};

/** 模板默认价格规则中的命中条件 */
export type TemplatePricingCondition = {
  field: string;
  operator: string;
  value: unknown;
};

/** 模板默认价格规则中的计费项 */
export type TemplatePricingItem = {
  label: string;
  position: number;
  kind: string;
  source_fields: string[];
  free_quantity: number;
  unit_amount: string | null;
  active?: boolean;
};

/** 模板提供的默认价格规则，用于新建模型时由服务端自动播种。 */
export type TemplatePricingRule = {
  name: string;
  priority: number;
  conditions: TemplatePricingCondition[];
  items: TemplatePricingItem[];
  currency?: string;
  active?: boolean;
};

/** 模板派生计费字段声明：type 为系统派生的内部计价字段，size_source 为其来源公开字段 */
export type ProviderTemplateDerivedPricingField = {
  type: string;
  size_source: string;
};

/**
 * Provider 模板详情：input_schema 初始化公开输入字段，
 * material_fields 提供素材字段类型声明，
 * derived_pricing_fields 声明由系统派生的内部计价字段（如由 size 派生的 image_pixel_count），
 * default_pricing_rules 提供新建模型时自动播种的默认价格规则。
 * 模板不返回 projection / model_mapping / pricing_fields / api_key / base_url /
 * 请求头或渠道运行配置；若接口异常返回 api_key，视为安全异常，不渲染、不缓存。
 */
export type ProviderTemplateDetail = ProviderTemplateSummary & {
  input_schema: Record<string, unknown>;
  material_fields?: Record<string, { categories?: string[]; multiple?: boolean }>;
  derived_pricing_fields?: ProviderTemplateDerivedPricingField[];
  default_pricing_rules?: TemplatePricingRule[];
};

/** match-preview 返回的价格修正项，与管理员价格修正接口的请求体形状一致 */
export type PreviewPricingModifier = {
  name: string;
  priority: number;
  conditions: TemplatePricingCondition[];
  effect_type: "multiplier" | "fixed_price";
  effect_payload: { factor?: string; amount?: string };
  scope_type: "item_ids" | "item_kind" | "all_items";
  scope_item_kinds: string[];
};

/** 按模型名预览匹配结果：回显创建时将套用的模板、目录价与修正项 */
export type ModelMatchPreview = {
  model_name: string;
  normalized_name: string;
  match_type: "exact" | "provider_fallback" | "none";
  matched: boolean;
  template_id: string | null;
  model_type: string | null;
  provider_id: string | null;
  provider_name: string | null;
  /** 供应商图标地址；null 表示不渲染图标 */
  provider_logo_url?: string | null;
  currency: string | null;
  source_url: string | null;
  price_updated_at: string | null;
  note: string | null;
  pricing_rules: TemplatePricingRule[];
  pricing_modifiers: PreviewPricingModifier[];
  pricing_fields: string[];
  input_schema: Record<string, unknown> | null;
};

/** 模板列表响应归一化：数组 / { items } / { templates } / { list } */
function normalizeTemplates(data: unknown): ProviderTemplateSummary[] {
  if (Array.isArray(data)) return data as ProviderTemplateSummary[];
  if (data && typeof data === "object") {
    const d = data as Record<string, unknown>;
    return (
      ((d.items ?? d.templates ?? d.list ?? []) as ProviderTemplateSummary[]) ??
      []
    );
  }
  return [];
}

/** 复制文本：优先 Clipboard API，非安全上下文时降级 execCommand */
async function copyText(value: string): Promise<boolean> {
  if (navigator.clipboard && window.isSecureContext) {
    await navigator.clipboard.writeText(value);
    return true;
  }
  const textarea = document.createElement("textarea");
  textarea.value = value;
  textarea.style.position = "fixed";
  textarea.style.left = "-9999px";
  document.body.appendChild(textarea);
  textarea.select();
  try {
    document.execCommand("copy");
    return true;
  } catch {
    return false;
  } finally {
    document.body.removeChild(textarea);
  }
}

/** 复制按钮：复制成功后短暂显示对勾 */
function CopyButton({
  value,
  className,
}: {
  value: string;
  className?: string;
}) {
  const { t } = useTranslation("console");
  const [copied, setCopied] = useState(false);

  const onCopy = async () => {
    try {
      if (!(await copyText(value))) throw new Error();
      setCopied(true);
      toast.success(t("models.copiedToast"));
      setTimeout(() => setCopied(false), 1500);
    } catch {
      toast.error(t("models.copyFailedToast"));
    }
  };

  return (
    <Button
      variant="ghost"
      size="icon"
      className={cn("size-6", className)}
      onClick={onCopy}
      title={t("models.copyModelName")}
      aria-label={t("models.copyModelName")}
    >
      {copied ? (
        <Check className="size-3.5 text-success" />
      ) : (
        <Copy className="size-3.5" />
      )}
    </Button>
  );
}

/** 计价维度上限，与后端一致 */
const MAX_PRICING_FIELDS = 64;

/** 计价维度候选：input_schema.properties 字段 ∪ projection 目标字段，去重 */
export function pricingFieldCandidates(
  contract: Record<string, unknown> | undefined
): string[] {
  if (!contract) return [];
  const schema = contract.input_schema as
    | { properties?: Record<string, unknown> }
    | undefined;
  const projection = contract.projection as
    | Record<string, unknown>
    | undefined;
  const keys = [
    ...Object.keys(schema?.properties ?? {}),
    ...Object.keys(projection ?? {}),
  ];
  return [...new Set(keys)];
}

const PAGE_SIZE = 20;

/** 模型介绍最大长度，与后端一致 */
const MAX_DESCRIPTION_LENGTH = 512;

const MODEL_TYPES: ModelType[] = ["text", "image", "video"];

/** 模型类型展示文案：text / image / video */
function modelTypeLabel(t: Translate, type: string): string {
  return MODEL_TYPES.includes(type as ModelType)
    ? t(`models.type.${type}`)
    : type;
}

/** 兼容多种分页响应：数组 / { items, total } / { models, total } */
function normalize(data: unknown): { models: PublicModel[]; total: number } {
  if (Array.isArray(data)) return { models: data, total: data.length };
  if (data && typeof data === "object") {
    const d = data as Record<string, unknown>;
    const list = (d.items ?? d.models ?? d.list ?? []) as PublicModel[];
    const total = typeof d.total === "number" ? d.total : list.length;
    return { models: list, total };
  }
  return { models: [], total: 0 };
}

/** match-preview 回显卡片：仅展示将播种的定价规则（规则名 + 计费项价格） */
function ModelMatchPreviewCard({
  preview,
  loading,
}: {
  preview: ModelMatchPreview | null;
  loading: boolean;
}) {
  const { t } = useTranslation("console");
  if (loading) {
    return (
      <div className="rounded-lg border border-border/60 bg-muted/10 p-3">
        <p className="flex items-center gap-2 text-xs text-muted-foreground">
          <Loading size="sm" />
          {t("models.matchingPrices")}
        </p>
      </div>
    );
  }
  if (!preview) return null;
  const rules = preview.pricing_rules ?? [];
  if (rules.length === 0) return null;
  return (
    <div className="space-y-1 rounded-lg border border-border/60 bg-muted/10 p-3 text-xs">
      {preview.provider_name && (
        <p className="flex items-center gap-1.5 font-medium">
          <ProviderLogo
            src={preview.provider_logo_url}
            providerId={preview.provider_id}
            className="size-3.5"
          />
          {preview.provider_name}
        </p>
      )}
      {rules.map((rule, ri) => (
        <div key={ri} className="space-y-0.5">
          <p className="text-muted-foreground">
            {rule.name}（{rule.currency ?? preview.currency ?? "USD"}）
          </p>
          <ul className="space-y-0.5">
            {rule.items.map((item, ii) => (
              <li
                key={ii}
                className="flex items-center justify-between gap-2 font-mono"
              >
                <span>{item.label}</span>
                <span>
                  {item.unit_amount ?? "-"}
                  {item.kind.endsWith("_tokens") ? " / 1M Token" : ""}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}

/** 新建 / 编辑模型抽屉（model 为 null 时新建） */
function ModelFormDialog({
  model,
  onClose,
  onSaved,
  onUnpriced,
}: {
  model: PublicModel | null;
  onClose: () => void;
  onSaved: () => void;
  /** 新建出的模型未定价时回调，由父级弹窗提示补填单价 */
  onUnpriced?: (model: ModelOption) => void;
}) {
  const isEdit = model !== null;
  const { t } = useTranslation("console");
  const [name, setName] = useState(model?.name ?? "");
  const [modelType, setModelType] = useState<ModelType>(
    model?.model_type ?? "text"
  );
  const [contract, setContract] = useState<ContractFormState>(() =>
    model?.input_contract && Object.keys(model.input_contract).length > 0
      ? stateFromContract(model.input_contract)
      : emptyContractState()
  );
  const [active, setActive] = useState(model?.active ?? true);
  const [description, setDescription] = useState(model?.description ?? "");
  const [pricingFields, setPricingFields] = useState<string[]>(
    model?.pricing_fields ?? []
  );
  /** 默认每用户并发上限：空字符串表示 null（不限制） */
  const [concurrencyLimit, setConcurrencyLimit] = useState(
    model?.default_concurrency_limit != null
      ? String(model.default_concurrency_limit)
      : ""
  );
  const [submitting, setSubmitting] = useState(false);
  /** 令牌分组：仅新建时可选，决定模板默认价格规则的播种目标（可多选） */
  const [groups, setGroups] = useState<{ id: number; name: string; is_default?: boolean }[]>([]);
  const [groupIds, setGroupIds] = useState<string[]>([]);
  /** Provider 模板：列表、选中项、详情加载与覆盖确认 */
  const [templates, setTemplates] = useState<ProviderTemplateSummary[] | null>(
    null
  );
  const [templatesError, setTemplatesError] = useState("");
  const [selectedTemplateId, setSelectedTemplateId] = useState("");
  const [templateDetailLoading, setTemplateDetailLoading] = useState(false);
  const [templateDetailError, setTemplateDetailError] = useState("");
  /** 模型名匹配预览：仅新建时拉取，用于回显目录价与匹配状态 */
  const [preview, setPreview] = useState<ModelMatchPreview | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const previewSeq = useRef(0);
  /** 记录 mousedown 是否发生在遮罩上：避免从面板内拖选文本、在遮罩上松手时误关闭抽屉 */
  const overlayMouseDown = useRef(false);

  /** 名称失焦后预览匹配结果；响应按序号防乱序 */
  const fetchPreview = useCallback(() => {
    const trimmed = name.trim();
    if (isEdit || !trimmed || trimmed.length > 64) {
      setPreview(null);
      setPreviewLoading(false);
      return;
    }
    const seq = ++previewSeq.current;
    setPreviewLoading(true);
    get<ModelMatchPreview>("/admin/models/match-preview", {
      params: { name: trimmed },
    })
      .then((data) => {
        if (previewSeq.current !== seq) return;
        setPreview(data && typeof data === "object" ? data : null);
      })
      .catch(() => {
        if (previewSeq.current !== seq) return;
        setPreview(null);
      })
      .finally(() => {
        if (previewSeq.current === seq) setPreviewLoading(false);
      });
  }, [isEdit, name]);

  /** 拉取模板列表；失败时保留当前表单，显示重试 */
  const loadTemplates = useCallback(() => {
    setTemplatesError("");
    get<unknown>("/admin/provider-templates/list")
      .then((data) => setTemplates(normalizeTemplates(data)))
      .catch((err) => {
        setTemplates(null);
        setTemplatesError(
          err instanceof Error ? err.message : t("models.templatesLoadFailed")
        );
      });
  }, [t]);

  useEffect(() => {
    loadTemplates();
  }, [loadTemplates]);

  /** 仅新建时加载令牌分组列表，默认选中系统默认分组 */
  useEffect(() => {
    if (isEdit) return;
    get<unknown>("/admin/token/groups/list", {
      params: { page: 1, page_size: 100 },
    })
      .then((data) => {
        const list = Array.isArray(data)
          ? data
          : (((data as Record<string, unknown>).items ??
              (data as Record<string, unknown>).groups ??
              (data as Record<string, unknown>).list ??
              []) as { id: number; name: string; is_default?: boolean }[]);
        setGroups(list);
        const def = list.find((g) => g.is_default) ?? list[0];
        if (def) setGroupIds([String(def.id)]);
      })
      .catch(() => {});
  }, [isEdit]);

  /** 当前模型类型可用的模板（不硬编码 Provider 类型，按 model_type 筛选） */
  const matchingTemplates = (templates ?? []).filter(
    (t) => t.model_type === modelType
  );
  /** 当前选中的模板摘要：用于回显供应商与模板说明 */
  const selectedTemplate = matchingTemplates.find(
    (t) => t.template_id === selectedTemplateId
  );

  /**
   * 应用模板：模板 input_schema 直接覆盖当前契约，并预填默认规则引用的计价字段。
   * 派生计费字段（如由 size 派生的 image_pixel_count）由系统计算，不是用户的计价维度；
   * 预填时还原为其来源公开字段（size），避免把内部派生字段写入计价白名单。
   */
  const applyTemplateFull = (detail: ProviderTemplateDetail) => {
    setContract(stateFromTemplate(detail.input_schema));
    const derivedSources = new Map(
      (detail.derived_pricing_fields ?? []).map((d) => [d.type, d.size_source])
    );
    const declarable = (field: string) => derivedSources.get(field) ?? field;
    const pricingRuleFields = new Set<string>();
    for (const rule of detail.default_pricing_rules ?? []) {
      for (const condition of rule.conditions) {
        pricingRuleFields.add(declarable(condition.field));
      }
      for (const item of rule.items) {
        for (const sourceField of item.source_fields) {
          pricingRuleFields.add(declarable(sourceField));
        }
      }
    }
    setPricingFields([...pricingRuleFields]);
  };

  /**
   * 拉取模板详情并直接覆盖应用。
   * 详情加载失败时保留当前表单，提供重试。
   */
  const loadTemplateDetail = async (templateId: string) => {
    setTemplateDetailLoading(true);
    setTemplateDetailError("");
    try {
      const detail = await get<ProviderTemplateDetail>(
        "/admin/provider-templates/detail",
        { params: { template_id: templateId } }
      );
      if (
        !detail ||
        typeof detail.input_schema !== "object" ||
        detail.input_schema === null ||
        Array.isArray(detail.input_schema)
      ) {
        setTemplateDetailError(t("models.templateNotFound"));
        return;
      }
      // 安全边界：若接口异常返回 api_key 等敏感字段，视为安全异常，拒绝处理
      if ("api_key" in detail || "base_url" in detail) {
        setTemplateDetailError(t("models.templateSensitive"));
        return;
      }
      applyTemplateFull(detail);
    } catch (err) {
      const msg = err instanceof Error ? err.message : t("models.templateDetailFailed");
      setTemplateDetailError(
        /不存在|not\s*found/i.test(msg) ? t("models.templateNotFound") : msg
      );
    } finally {
      setTemplateDetailLoading(false);
    }
  };

  const onTemplateSelect = (templateId: string) => {
    setSelectedTemplateId(templateId);
    if (templateId) void loadTemplateDetail(templateId);
  };

  /** 切换模型类型：不预填任何契约内容；模板选择随类型失效 */
  const onModelTypeChange = (v: string) => {
    const t = v as ModelType;
    setModelType(t);
    const sel = templates?.find((x) => x.template_id === selectedTemplateId);
    if (sel && sel.model_type !== t) {
      setSelectedTemplateId("");
    }
  };

  /**
   * 新建模型时默认选中并应用当前类型的第一个模板，避免提交缺少 template_id。
   * 编辑模型不自动改写已配置的模板。
   */
  useEffect(() => {
    if (isEdit || selectedTemplateId) return;
    const first = (templates ?? []).find((t) => t.model_type === modelType);
    if (!first) return;
    setSelectedTemplateId(first.template_id);
    void loadTemplateDetail(first.template_id);
    // loadTemplateDetail 每次渲染都会重建，仅以模板列表和模型类型变化驱动
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [templates, modelType, isEdit, selectedTemplateId]);

  /** 编辑时切换模型类型或模板会按新模板重建该模型的价格规则，提示管理员 */
  const rebuildsPricing =
    model !== null &&
    (modelType !== model.model_type || selectedTemplateId !== model.template_id);

  /**
   * 计价维度候选：随契约编辑实时计算（表单模式直接取行数据，
   * JSON 模式尝试解析，解析失败时不提供候选）。
   * 已选字段被移出候选时保留展示，由提交校验拦截。
   */
  const pricingCandidates = (() => {
    if (contract.mode === "form") {
      return [
        ...new Set([
          ...contract.schemaRows.map((r) => r.name.trim()),
          ...contract.projectionRows.map((r) => r.target.trim()),
        ]),
      ].filter(Boolean);
    }
    try {
      const v = JSON.parse(contract.jsonText || "{}");
      return pricingFieldCandidates(v as Record<string, unknown>);
    } catch {
      return [];
    }
  })();

  const pricingOptions = [
    ...new Set([...pricingCandidates, ...pricingFields]),
  ].map((f) => ({
    value: f,
    label: pricingCandidates.includes(f) ? f : t("models.notInContract", { field: f }),
  }));

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) {
      toast.warning(t("models.nameRequired"));
      return;
    }
    // 创建模型必须选择 Provider 模板：后端据此构建输入契约与默认价格规则
    if (!isEdit && !selectedTemplateId) {
      toast.warning(t("models.templateRequired"));
      return;
    }
    // 默认每用户并发上限：可清空提交 null（不限制）；填写时必须是 0-10000 的整数
    let defaultConcurrency: number | null = null;
    if (concurrencyLimit.trim()) {
      const v = Number(concurrencyLimit);
      if (!Number.isInteger(v) || v < 0 || v > 10000) {
        toast.warning(t("models.concurrencyLimitRange"));
        return;
      }
      defaultConcurrency = v;
    }
    // 模型介绍：最长 512 字符，超出前端先拦截
    if (description.trim().length > MAX_DESCRIPTION_LENGTH) {
      toast.warning(t("models.descriptionTooLong", { max: MAX_DESCRIPTION_LENGTH }));
      return;
    }
    let inputContract: Record<string, unknown> | undefined;
    let pricing: string[] = [];
    {
      const built = buildContract(contract, t);
      if (built === null) return;
      inputContract = built;

      // 计价维度校验：必填（可为空数组，空表示固定价模型）、去重、限 64 项、
      // 且每个字段必须来自 input_schema.properties 或 projection
      if (pricingFields.length > MAX_PRICING_FIELDS) {
        toast.warning(t("models.pricingFieldsTooMany", { max: MAX_PRICING_FIELDS }));
        return;
      }
      const seen = new Set<string>();
      for (const f of pricingFields) {
        if (seen.has(f)) {
          toast.warning(t("models.pricingFieldDuplicate", { field: f }));
          return;
        }
        seen.add(f);
      }
      const candidates = new Set(pricingFieldCandidates(inputContract));
      for (const f of pricingFields) {
        if (!candidates.has(f)) {
          toast.warning(t("models.pricingFieldNotDeclared", { field: f }));
          return;
        }
      }
      pricing = pricingFields;
    }

    setSubmitting(true);
    try {
      const saved = await post<{ id?: string; name?: string; pricing_configured?: boolean }>(
        isEdit ? "/admin/models/update" : "/admin/models/create",
        {
          ...(isEdit ? { model_id: model.id } : {}),
          name: name.trim(),
          model_type: modelType,
          description: description.trim() || null,
          input_contract: inputContract,
          pricing_fields: pricing,
          ...(selectedTemplateId ? { template_id: selectedTemplateId } : {}),
          ...(!isEdit && groupIds.length > 0 ? { token_group_ids: groupIds.map(Number) } : {}),
          default_concurrency_limit: defaultConcurrency,
          active,
        }
      );
      toast.success(
        isEdit
          ? t("models.updateSuccess")
          : t("models.createSuccess")
      );
      onSaved();
      onClose();
      // 类型/模板变更会按新模板重建价格规则，重建后未带单价时需管理员补填
      if (saved?.pricing_configured === false && saved.id && saved.name) {
        onUnpriced?.({ id: saved.id, name: saved.name, model_type: modelType });
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t("models.saveFailed"));
    } finally {
      setSubmitting(false);
    }
  };

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
        {/* 抽屉头部：固定吸顶 */}
        <div className="flex items-center justify-between border-b border-border/60 px-6 py-4">
          <div>
            <h2 className="text-base font-semibold">
              {isEdit ? t("models.formEditTitle") : t("models.formCreateTitle")}
            </h2>
            <p className="mt-0.5 text-xs text-muted-foreground">
              {isEdit
                ? t("models.formEditDesc", { name: model.name })
                : t("models.formCreateDesc")}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label={t("models.close")}
            className="rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          >
            <X className="size-4" />
          </button>
        </div>

        {/* 抽屉表单区：可滚动 */}
        <form
          onSubmit={onSubmit}
          className="flex min-h-0 flex-1 flex-col overflow-hidden"
        >
          <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-6">
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <label htmlFor="model-name" className="text-sm font-medium">
                  {t("models.formNameLabel")}
                </label>
                <Input
                  id="model-name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  onBlur={() => fetchPreview()}
                  placeholder="gpt-5.6-terra"
                  autoComplete="off"
                />
              </div>
              <div className="space-y-1.5">
                <span className="text-sm font-medium">{t("models.formTypeLabel")}</span>
                <Select
                  aria-label={t("models.formTypeLabel")}
                  value={modelType}
                  onValueChange={onModelTypeChange}
                  options={MODEL_TYPES.map((mt) => ({
                    value: mt,
                    label: modelTypeLabel(t, mt),
                  }))}
                />
              </div>
            </div>

            <div className="space-y-1.5">
              <label htmlFor="model-description" className="text-sm font-medium">
                {t("models.descriptionLabel")}
                <span className="ml-1 text-xs font-normal text-muted-foreground">
                  {t("models.descriptionHint", { max: MAX_DESCRIPTION_LENGTH })}
                </span>
              </label>
              <textarea
                id="model-description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                maxLength={MAX_DESCRIPTION_LENGTH}
                rows={3}
                placeholder={t("models.descriptionPlaceholder")}
                className="placeholder:text-muted-foreground dark:bg-input/30 border-input w-full rounded-md border bg-transparent px-3 py-2 text-sm shadow-xs outline-none focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px] disabled:cursor-not-allowed disabled:opacity-50"
              />
            </div>

            {/* 按模型名预览匹配结果：仅新建时展示，手工模板流程不变 */}
            {!isEdit && (previewLoading || preview) && (
              <ModelMatchPreviewCard preview={preview} loading={previewLoading} />
            )}

            {/* 令牌分组：仅新建时可选，决定模板默认价格规则的播种目标（可多选） */}
            {!isEdit && groups.length > 0 && (
              <div className="space-y-1.5">
                <span className="text-sm font-medium">{t("models.groupLabel")}</span>
                <MultiSelect
                  aria-label={t("models.groupLabel")}
                  values={groupIds}
                  onValuesChange={setGroupIds}
                  options={groups.map((g) => ({
                    value: String(g.id),
                    label: g.is_default ? `${g.name}（${t("models.groupDefaultTag")}）` : g.name,
                  }))}
                  placeholder={t("models.groupPlaceholder")}
                />
                <p className="text-xs text-muted-foreground">
                  {t("models.groupHint")}
                </p>
              </div>
            )}

            <div className="space-y-2.5">
                {/* Provider 模板：自动初始化公开输入字段 */}
                <div className="space-y-2 rounded-lg border border-border/60 bg-muted/10 p-3">
                  <div>
                    <p className="text-sm font-medium">{t("models.templateSection")}</p>
                    <p className="text-xs text-muted-foreground">
                      {t("models.templateSectionDesc")}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <div className="flex-1">
                      <Select
                        aria-label={t("models.templateAriaLabel")}
                        value={selectedTemplateId}
                        onValueChange={onTemplateSelect}
                        options={matchingTemplates.map((t) => ({
                          value: t.template_id,
                          label: (
                            <span className="inline-flex items-center gap-1.5">
                              <ProviderLogo
                                src={t.provider_logo_url}
                                providerId={t.provider_id}
                                className="size-3.5"
                              />
                              {t.label}
                            </span>
                          ),
                        }))}
                        placeholder={
                          templates === null ? t("models.templateLoading") : t("models.templatePlaceholder")
                        }
                        emptyText={t("models.templateEmpty")}
                      />
                    </div>
                    {selectedTemplateId && (
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        disabled={templateDetailLoading}
                        onClick={() =>
                          void loadTemplateDetail(selectedTemplateId)
                        }
                      >
                        {t("models.reapplyTemplate")}
                      </Button>
                    )}
                  </div>
                  {rebuildsPricing && (
                    <p className="text-xs text-warning">
                      {t("models.rebuildPricingHint")}
                    </p>
                  )}
                  {selectedTemplateId && !templateDetailLoading && (
                    <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
                      <ProviderLogo
                        src={selectedTemplate?.provider_logo_url}
                        providerId={selectedTemplate?.provider_id}
                        className="size-3.5"
                      />
                      <span>
                        {selectedTemplate?.provider_name ?? selectedTemplate?.provider_type}
                        {" · "}
                        {t("models.templateNote")}
                      </span>
                    </p>
                  )}
                  {templateDetailLoading && (
                    <p className="flex items-center gap-2 text-xs text-muted-foreground">
                      <Loading size="sm" />
                      {t("models.templateDetailLoading")}
                    </p>
                  )}
                  {templatesError && (
                    <p className="flex items-center gap-2 text-xs text-destructive">
                      {templatesError}
                      <button
                        type="button"
                        className="underline underline-offset-2"
                        onClick={loadTemplates}
                      >
                        {t("models.retry")}
                      </button>
                    </p>
                  )}
                  {templateDetailError && (
                    <p className="flex items-center gap-2 text-xs text-destructive">
                      {templateDetailError}
                      <button
                        type="button"
                        className="underline underline-offset-2"
                        onClick={() =>
                          void loadTemplateDetail(selectedTemplateId)
                        }
                      >
                        {t("models.retry")}
                      </button>
                    </p>
                  )}
                </div>

                <div>
                  <p className="text-sm font-medium">{t("models.capabilitySection")}</p>
                  <p className="text-xs text-muted-foreground">
                    {t("models.capabilitySectionDesc")}
                  </p>
                </div>
                <InputContractEditor
                  value={contract}
                  onChange={(patch) =>
                    setContract((prev) => ({ ...prev, ...patch }))
                  }
                />
                <div className="space-y-1.5">
                  <p className="text-sm font-medium">
                    {t("models.pricingFieldsLabel")}
                    <span className="ml-1 text-xs font-normal text-muted-foreground">
                      {t("models.pricingFieldsHint", { max: MAX_PRICING_FIELDS })}
                    </span>
                  </p>
                  <MultiSelect
                    aria-label={t("models.pricingFieldsLabel")}
                    values={pricingFields}
                    onValuesChange={setPricingFields}
                    options={pricingOptions}
                    placeholder={t("models.pricingFieldsPlaceholder")}
                    emptyText={t("models.pricingFieldsEmpty")}
                  />
                  <p className="text-xs text-muted-foreground">
                    {t("models.pricingFieldsDesc")}
                  </p>
                </div>
              </div>

            <div className="flex items-center justify-between rounded-lg border border-border/60 bg-muted/20 p-3">
              <div>
                <p className="text-sm font-medium">{t("models.enableStatus")}</p>
                <p className="text-xs text-muted-foreground">
                  {t("models.enableStatusHint")}
                </p>
              </div>
              <Switch checked={active} onCheckedChange={setActive} />
            </div>

            <div className="space-y-1.5 rounded-lg border border-border/60 bg-muted/20 p-3">
              <label
                htmlFor="default-concurrency-limit"
                className="text-sm font-medium mr-2"
              >
                {t("models.concurrencyLabel")}
              </label>
              <Input
                id="default-concurrency-limit"
                type="number"
                min={0}
                max={10000}
                step={1}
                value={concurrencyLimit}
                onChange={(e) => setConcurrencyLimit(e.target.value)}
                placeholder={t("models.concurrencyPlaceholder")}
                className="w-40"
              />
              <p className="text-xs text-muted-foreground">
                {t("models.concurrencyHint")}
              </p>
            </div>
          </div>

          {/* 抽屉底部操作栏：固定吸底 */}
          <div className="flex justify-end gap-2 border-t border-border/60 bg-background/80 px-6 py-3.5 backdrop-blur-sm">
            <Button type="button" variant="outline" onClick={onClose}>
              {t("models.cancel")}
            </Button>
            <Button type="submit" disabled={submitting}>
              {submitting && <Loading size="sm" />}
              {isEdit ? t("models.saveChanges") : t("models.createModel")}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}

/** 模型详情弹窗：打开时按 model_id 拉取详情 */
function ModelDetailDialog({
  modelId,
  onClose,
}: {
  modelId: string;
  onClose: () => void;
}) {
  const [detail, setDetail] = useState<PublicModel | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const { t, i18n } = useTranslation("console");
  const locale = i18n.language === "zh" ? "zh-CN" : "en-US";

  useEffect(() => {
    get<PublicModel>("/admin/models/detail", {
      params: { model_id: modelId },
    })
      .then(setDetail)
      .catch((err) =>
        setError(err instanceof Error ? err.message : t("models.loadFailed"))
      )
      .finally(() => setLoading(false));
  }, [modelId, t]);

  const formatTime = (s?: string) =>
    s ? new Date(s).toLocaleString(locale) : "-";

  return (
    <div
      className="fixed inset-0 z-[80] flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="max-h-[85vh] w-full max-w-lg overflow-y-auto rounded-xl border bg-background p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-base font-semibold">{t("models.detailTitle")}</h2>
        {loading ? (
          <div className="flex justify-center py-10">
            <Loading size="lg" />
          </div>
        ) : error || !detail ? (
          <p className="py-10 text-center text-sm text-muted-foreground">
            {error || t("models.detailEmpty")}
          </p>
        ) : (
          <dl className="mt-5 space-y-3 text-sm">
            <div className="flex items-start justify-between gap-4">
              <dt className="shrink-0 text-muted-foreground">{t("models.detailName")}</dt>
              <dd className="text-right font-medium">{detail.name}</dd>
            </div>
            <div className="flex items-start justify-between gap-4">
              <dt className="shrink-0 text-muted-foreground">{t("models.detailType")}</dt>
              <dd>
                <Badge variant="secondary">
                  {modelTypeLabel(t, detail.model_type)}
                </Badge>
              </dd>
            </div>
            <div className="flex items-start justify-between gap-4">
              <dt className="shrink-0 text-muted-foreground">{t("models.detailProvider")}</dt>
              <dd>
                {detail.provider_name ? (
                  <Badge variant="outline">
                    <ProviderLogo
                      src={detail.provider_logo_url}
                      providerId={detail.provider_id}
                      className="mr-1 size-3.5"
                    />
                    {detail.provider_name}
                  </Badge>
                ) : (
                  <span className="text-xs text-muted-foreground">-</span>
                )}
              </dd>
            </div>
            <div className="flex items-start justify-between gap-4">
              <dt className="shrink-0 text-muted-foreground">{t("models.detailStatus")}</dt>
              <dd>
                <Badge variant={detail.active ? "default" : "destructive"}>
                  {detail.active ? t("models.statusActive") : t("models.statusInactive")}
                </Badge>
              </dd>
            </div>
            <div className="flex items-start justify-between gap-4">
              <dt className="shrink-0 text-muted-foreground">{t("models.detailConcurrency")}</dt>
              <dd className="text-right font-medium">
                {defaultConcurrencyLabel(t, detail.default_concurrency_limit)}
              </dd>
            </div>
            <div className="flex items-start justify-between gap-4">
              <dt className="shrink-0 text-muted-foreground">{t("models.detailDescription")}</dt>
              <dd className="max-w-[70%] whitespace-pre-wrap break-words text-right">
                {detail.description?.trim() ? detail.description : (
                  <span className="text-xs text-muted-foreground">-</span>
                )}
              </dd>
            </div>
            <div className="flex items-start justify-between gap-4">
                <dt className="shrink-0 text-muted-foreground">{t("models.detailPricing")}</dt>
                <dd className="flex flex-wrap justify-end gap-1">
                  {detail.pricing_fields && detail.pricing_fields.length > 0 ? (
                    detail.pricing_fields.map((f) => (
                      <Badge key={f} variant="outline">
                        {f}
                      </Badge>
                    ))
                  ) : (
                    <span className="text-xs text-muted-foreground">
                      {t("models.detailPricingEmpty")}
                    </span>
                  )}
                </dd>
              </div>
            {detail.input_contract &&
              Object.keys(detail.input_contract).length > 0 && (
                <div className="space-y-1.5">
                  <dt className="text-muted-foreground">{t("models.detailContract")}</dt>
                  <dd>
                    <pre className="max-h-64 overflow-auto rounded-md border border-border/60 bg-muted/40 p-2.5 font-mono text-xs">
                      {JSON.stringify(detail.input_contract, null, 2)}
                    </pre>
                  </dd>
                </div>
              )}
          </dl>
        )}
        <div className="mt-6 flex justify-end">
          <Button variant="outline" onClick={onClose}>
            {t("models.close")}
          </Button>
        </div>
      </div>
    </div>
  );
}

/** 删除模型确认弹窗 */
function DeleteModelDialog({
  model,
  onClose,
  onDeleted,
}: {
  model: PublicModel;
  onClose: () => void;
  onDeleted: () => void;
}) {
  const [submitting, setSubmitting] = useState(false);
  const { t } = useTranslation("console");

  const onConfirm = async () => {
    setSubmitting(true);
    try {
      await post("/admin/models/delete", { model_id: model.id });
      toast.success(t("models.deleteSuccess"));
      onDeleted();
      onClose();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t("models.deleteFailed"));
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
        <h2 className="text-base font-semibold">{t("models.deleteTitle")}</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          {t("models.deleteConfirm", { name: model.name })}
        </p>
        <div className="mt-6 flex justify-end gap-2">
          <Button variant="outline" onClick={onClose}>
            {t("models.cancel")}
          </Button>
          <Button
            variant="destructive"
            onClick={onConfirm}
            disabled={submitting}
          >
            {submitting && <Loading size="sm" />}
            {t("models.confirmDelete")}
          </Button>
        </div>
      </div>
    </div>
  );
}

/** 模型未定价提示弹窗：视频模板的默认单价留空，需管理员补填后才能生成 */
function UnpricedModelDialog({
  model,
  onClose,
  onGoPricing,
}: {
  model: ModelOption;
  onClose: () => void;
  onGoPricing: () => void;
}) {
  const { t } = useTranslation("console");

  return (
    <div
      className="fixed inset-0 z-[80] flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="w-full max-w-sm rounded-xl border bg-background p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-base font-semibold">{t("models.unpricedTitle")}</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          {t("models.unpricedMessage", { name: model.name })}
        </p>
        <div className="mt-6 flex justify-end gap-2">
          <Button variant="outline" onClick={onClose}>
            {t("models.unpricedLater")}
          </Button>
          <Button onClick={onGoPricing}>{t("models.unpricedGoPricing")}</Button>
        </div>
      </div>
    </div>
  );
}

export function ModelsPanel() {
  const { t, i18n } = useTranslation("console");
  const locale = i18n.language === "zh" ? "zh-CN" : "en-US";
  const [models, setModels] = useState<PublicModel[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingModel, setEditingModel] = useState<PublicModel | null>(null);
  const [updatingId, setUpdatingId] = useState<string | null>(null);
  const [detailModelId, setDetailModelId] = useState<string | null>(null);
  const [deletingModel, setDeletingModel] = useState<PublicModel | null>(null);
  const [fetchingId, setFetchingId] = useState<string | null>(null);
  const [pricingModel, setPricingModel] = useState<ModelOption | null>(null);
  /** 新建出但未定价的模型：弹窗提示管理员补填单价 */
  const [unpricedModel, setUnpricedModel] = useState<ModelOption | null>(null);
  // modelNameInput 为搜索框实时值，appliedModelName 为已提交的模型名筛选条件
  const [modelNameInput, setModelNameInput] = useState("");
  const [appliedModelName, setAppliedModelName] = useState("");
  const [providerFilter, setProviderFilter] = useState("");
  // 厂商下拉选项：跨筛选持久化去重累积，避免选中某厂商后选项集合塌缩
  const [providerOptions, setProviderOptions] = useState<{ id: string; name: string; logoUrl: string | null }[]>([]);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const load = useCallback(async (p: number, modelName: string, providerId: string) => {
    setLoading(true);
    setError("");
    try {
      const data = await get<unknown>("/admin/models/list", {
        params: {
          page: p,
          page_size: PAGE_SIZE,
          ...(modelName ? { model_name: modelName } : {}),
          ...(providerId ? { provider_id: providerId } : {}),
        },
      });
      const { models, total } = normalize(data);
      setModels(models);
      setTotal(total);
      // 从结果中提取厂商选项（provider_id 作筛选键、provider_name 作展示文案），与已有选项合并去重
      const fresh = models
        .filter((m): m is PublicModel & { provider_id: string; provider_name: string } =>
          Boolean(m.provider_id && m.provider_name))
        .map((m) => ({ id: m.provider_id, name: m.provider_name, logoUrl: m.provider_logo_url ?? null }));
      if (fresh.length > 0) {
        setProviderOptions((prev) => {
          const merged = new Map(prev.map((o) => [o.id, o]));
          for (const o of fresh) merged.set(o.id, o);
          return Array.from(merged.values());
        });
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : t("models.loadFailed"));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    load(page, appliedModelName, providerFilter);
  }, [load, page, appliedModelName, providerFilter]);

  const onSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setPage(1);
    setAppliedModelName(modelNameInput.trim());
  };

  const onClearSearch = () => {
    setModelNameInput("");
    setPage(1);
    setAppliedModelName("");
  };

  const onProviderChange = (value: string) => {
    setPage(1);
    setProviderFilter(value);
  };

  /** 启用/停用模型：乐观更新，失败回滚 */
  const toggleActive = async (model: PublicModel, active: boolean) => {
    setUpdatingId(model.id);
    setModels((prev) =>
      prev.map((m) => (m.id === model.id ? { ...m, active } : m))
    );
    try {
      await post("/admin/models/update-status", {
        model_id: model.id,
        active,
      });
      toast.success(active ? t("models.enabledToast") : t("models.disabledToast"));
    } catch (err) {
      setModels((prev) =>
        prev.map((m) =>
          m.id === model.id ? { ...m, active: model.active } : m
        )
      );
      toast.error(err instanceof Error ? err.message : t("models.statusUpdateFailed"));
    } finally {
      setUpdatingId(null);
    }
  };

  /** 编辑前先拉取详情，确保表单拿到完整请求契约 */
  const openEdit = async (model: PublicModel) => {
    setFetchingId(model.id);
    try {
      const detail = await get<PublicModel>("/admin/models/detail", {
        params: { model_id: model.id },
      });
      setEditingModel(detail);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t("models.getDetailFailed"));
    } finally {
      setFetchingId(null);
    }
  };

  const onDeleted = () => {
    // 删除当前页最后一条时回退到上一页
    if (models.length === 1 && page > 1) {
      setPage(page - 1);
    } else {
      load(page, appliedModelName, providerFilter);
    }
  };

  const formatTime = (iso?: string) =>
    iso ? new Date(iso).toLocaleString(locale) : "-";

  return (
    <div className="flex min-h-[calc(100vh-7.5rem)] w-full flex-col gap-6">
      {/* 页头 */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold">{t("models.title")}</h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            {t("models.totalModels", { total })}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <form onSubmit={onSearch} className="flex items-center gap-2">
            <div className="relative">
              <Search className="absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={modelNameInput}
                onChange={(e) => setModelNameInput(e.target.value)}
                placeholder={t("models.searchPlaceholder")}
                className="h-8 w-52 pr-8 pl-9"
              />
              {modelNameInput && (
                <button
                  type="button"
                  onClick={onClearSearch}
                  aria-label={t("models.clearSearch")}
                  className="absolute top-1/2 right-2 -translate-y-1/2 rounded-full p-0.5 text-muted-foreground hover:text-foreground"
                >
                  <X className="size-4" />
                </button>
              )}
            </div>
            <Button type="submit" variant="outline" size="sm" aria-label={t("models.search")}>
              <Search className="size-4" />
              {t("models.search")}
            </Button>
          </form>
          <Select
            value={providerFilter}
            onValueChange={onProviderChange}
            options={[
              { value: "", label: t("models.allProviders") },
              ...providerOptions.map((o) => ({
                value: o.id,
                label: (
                  <span className="inline-flex items-center gap-1.5">
                    <ProviderLogo src={o.logoUrl} providerId={o.id} className="size-3.5" />
                    {o.name}
                  </span>
                ),
              })),
            ]}
            placeholder={t("models.allProviders")}
            aria-label={t("models.providerFilter")}
            className="h-8 w-36"
          />
          <Button
            variant="outline"
            size="sm"
            onClick={() => load(page, appliedModelName, providerFilter)}
            disabled={loading}
          >
            <RefreshCw className={cn("size-4", loading && "animate-spin")} />
            {t("models.refresh")}
          </Button>
          <Button size="sm" onClick={() => setDialogOpen(true)}>
            <Plus className="size-4" />
            {t("models.createButton")}
          </Button>
        </div>
      </div>

      {/* 模型列表 */}
      <div className="relative overflow-hidden rounded-xl border border-border/60 bg-card/40">
        {error && models.length === 0 ? (
          <div className="flex flex-col items-center gap-2 py-16 text-sm text-muted-foreground">
            <p>{t("models.loadFailedWithReason", { error })}</p>
            <Button variant="outline" size="sm" onClick={() => load(page, appliedModelName, providerFilter)}>
              {t("models.retry")}
            </Button>
          </div>
        ) : models.length === 0 ? (
          <div className="flex items-center justify-center py-16 text-muted-foreground">
            {loading ? (
              <Loading size="lg" />
            ) : (
              <div className="flex flex-col items-center gap-2">
                <Cpu className="size-8 text-muted-foreground/50" />
                <p className="text-sm">{t("models.empty")}</p>
              </div>
            )}
          </div>
        ) : (
          <>
            {/* 加载中保留旧数据并降低透明度，避免表格整体闪烁 */}
            {/* 列过多时允许横向滚动，操作列固定在右侧 */}
            <div className="overflow-x-auto">
            <table
              className={cn(
                "w-full min-w-max text-sm transition-opacity duration-300",
                loading && "pointer-events-none opacity-40"
              )}
            >
              <thead>
                <tr className="border-b border-border/60 bg-muted/40 text-center text-xs text-muted-foreground">
                  <th className="px-6 py-3 text-left font-medium">{t("models.colName")}</th>
                  <th className="px-6 py-3 font-medium">{t("models.colProvider")}</th>
                  <th className="px-6 py-3 font-medium">{t("models.colType")}</th>
                  <th className="px-6 py-3 font-medium">{t("models.colContract")}</th>
                  <th className="px-6 py-3 font-medium">{t("models.colConcurrency")}</th>
                  <th className="px-6 py-3 font-medium">{t("models.colStatus")}</th>
                  <th className="sticky right-0 border-l border-border/60 bg-muted px-6 py-3 font-medium">
                    {t("models.colActions")}
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/60">
                {models.map((m) => (
                  <tr
                    key={m.id ?? m.name}
                    className="transition-colors hover:bg-accent/40"
                  >
                    <td className="px-6 py-3 font-medium">
                      <span className="inline-flex items-center gap-1">
                        {m.name}
                        <CopyButton value={m.name} className="size-5" />
                      </span>
                    </td>
                    <td className="px-6 py-3 text-center">
                      {m.provider_name ? (
                        <Badge variant="outline">
                          <ProviderLogo
                            src={m.provider_logo_url}
                            providerId={m.provider_id}
                            className="mr-1 size-3.5"
                          />
                          {m.provider_name}
                        </Badge>
                      ) : (
                        <span className="text-xs text-muted-foreground">-</span>
                      )}
                    </td>
                    <td className="px-6 py-3 text-center">
                      <Badge variant="secondary">
                        {modelTypeLabel(t, m.model_type)}
                      </Badge>
                    </td>
                    <td className="px-6 py-3 text-center text-xs text-muted-foreground">
                      {m.input_contract &&
                      Object.keys(m.input_contract).length > 0
                        ? t("models.contractConfigured")
                        : t("models.contractNotConfigured")}
                    </td>
                    <td className="px-6 py-3 text-center font-mono text-xs text-muted-foreground">
                      {defaultConcurrencyLabel(t, m.default_concurrency_limit)}
                    </td>
                    <td className="px-6 py-3 text-center">
                      <div className="flex items-center justify-center">
                        <Switch
                          checked={m.active}
                          disabled={updatingId === m.id}
                          onCheckedChange={(v) => toggleActive(m, v)}
                          checkedLabel={t("models.statusActive")}
                          uncheckedLabel={t("models.statusInactive")}
                          aria-label={m.active ? t("models.deactivateModel") : t("models.activateModel")}
                        />
                      </div>
                    </td>
                    <td className="sticky right-0 bg-card shadow-[-10px_0_12px_-10px_rgba(0,0,0,0.12)] px-6 py-3 text-center">
                      <div className="flex items-center justify-center gap-1.5">
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => setPricingModel(m)}
                          aria-label={t("models.viewPricing")}
                        >
                          <CircleDollarSign className="size-4" />
                          {t("models.pricingButton")}
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => setDetailModelId(m.id)}
                          aria-label={t("models.viewDetail")}
                        >
                          <Eye className="size-4" />
                          {t("models.detailButton")}
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => {
                            void post("/admin/models/copy", { model_id: m.id })
                              .then(() => {
                                toast.success(t("models.copySuccess"));
                                load(page, appliedModelName, providerFilter);
                              })
                              .catch((err) => toast.error(err instanceof Error ? err.message : t("models.copyFailed")));
                          }}
                          aria-label={t("models.copyModelAria")}
                        >
                          <Copy className="size-4" />
                          {t("models.copyButton")}
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => openEdit(m)}
                          disabled={fetchingId === m.id}
                          aria-label={t("models.editModelAria")}
                        >
                          {fetchingId === m.id ? (
                            <Loading size="sm" />
                          ) : (
                            <Pencil className="size-4" />
                          )}
                          {t("models.editButton")}
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          className="text-destructive hover:bg-destructive/10 hover:text-destructive"
                          onClick={() => setDeletingModel(m)}
                          aria-label={t("models.deleteModelAria")}
                        >
                          <Trash2 className="size-4" />
                          {t("models.deleteButton")}
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
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
      {!error && models.length > 0 && (
        <Pagination
          page={page}
          totalPages={totalPages}
          loading={loading}
          onChange={setPage}
          className="mt-auto"
        />
      )}

      {dialogOpen && (
        <ModelFormDialog
          model={null}
          onClose={() => setDialogOpen(false)}
          onSaved={() => load(page, appliedModelName, providerFilter)}
          onUnpriced={setUnpricedModel}
        />
      )}
      {editingModel && (
        <ModelFormDialog
          model={editingModel}
          onClose={() => setEditingModel(null)}
          onSaved={() => load(page, appliedModelName, providerFilter)}
          onUnpriced={setUnpricedModel}
        />
      )}
      {detailModelId && (
        <ModelDetailDialog
          modelId={detailModelId}
          onClose={() => setDetailModelId(null)}
        />
      )}
      {deletingModel && (
        <DeleteModelDialog
          model={deletingModel}
          onClose={() => setDeletingModel(null)}
          onDeleted={onDeleted}
        />
      )}
      {unpricedModel && (
        <UnpricedModelDialog
          model={unpricedModel}
          onClose={() => setUnpricedModel(null)}
          onGoPricing={() => {
            setPricingModel(unpricedModel);
            setUnpricedModel(null);
          }}
        />
      )}
      {pricingModel && (
        <ModelPricingDrawer
          model={pricingModel}
          onClose={() => setPricingModel(null)}
        />
      )}
    </div>
  );
}
