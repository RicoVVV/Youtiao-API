"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Copy,
  Pencil,
  Plus,
  Trash2,
  X,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Loading } from "@/components/ui/loading";
import { Select } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { toast } from "@/components/ui/toaster";
import { get, post } from "@/lib/request";
import {
  pricingFieldCandidates,
  type ModelOption,
} from "@/components/console/models-panel";
import zhConsole from "@/i18n/locales/zh/console.json";
import enConsole from "@/i18n/locales/en/console.json";

/** 价格规则条件：字段 + 运算符 + 值 */
export type PricingCondition = {
  field: string;
  operator: "eq" | "in" | "gte" | "lte" | "between";
  value: string | number | (string | number)[];
};

export type PricingModifierEffectType = "multiplier" | "fixed_price";
export type PricingModifierScopeType = "item_ids" | "item_kind" | "all_items";

export type PricingModifier = {
  id: string;
  pricing_rule_id: string;
  name: string;
  priority: number;
  conditions: PricingCondition[];
  effect_type: PricingModifierEffectType;
  effect_payload: Record<string, unknown>;
  scope_type: PricingModifierScopeType;
  scope_item_ids: string[];
  scope_item_kinds: PricingItemKind[];
  active: boolean;
};

export type DefaultPricingRule = Pick<
  PricingRule,
  "name" | "priority" | "conditions" | "items"
>;

/** 条件编辑行：值以字符串暂存，提交时按字段类型解析 */
export type ConditionRow = {
  field: string;
  operator: string;
  value: string;
};

/** 计费项类型：与后端 PricingItemKind 对齐 */
export type PricingItemKind =
  | "output_video_duration"
  | "input_video_duration"
  | "input_image_fixed"
  | "output_image_count"
  | "input_image_tokens"
  | "output_image_tokens"
  | "input_text_tokens"
  | "cache_write_input_text_tokens"
  | "cached_input_text_tokens"
  | "output_text_tokens"
  | "request_fixed";

/** 计费项（表单/列表共用） */
export type PricingRuleItem = {
  id: string;
  label: string;
  position: number;
  kind: PricingItemKind;
  source_fields: string[];
  free_quantity: number;
  unit_amount: string;
  price_source_item_id: string | null;
  active: boolean;
};

/** 接口返回的计费项：unit_amount 为 null 表示未定价（表单内统一归一化为空串） */
export type PricingRuleItemView = Omit<PricingRuleItem, "unit_amount"> & {
  unit_amount: string | null;
};

export type Translate = (key: string, options?: Record<string, unknown>) => string;

/** 计费项类型标签（i18n） */
export function itemKindLabel(t: Translate, kind: string): string {
  return t(`itemKind.${kind}`);
}

/** 名称比较归一化：忽略空白与大小写差异 */
function normalizeLabel(s: string): string {
  return s.replace(/\s+/g, "").toLowerCase();
}

/** 中英两种语言的计费类型标签（静态导入，避免 i18n 跨语言懒加载失效） */
const ITEM_KIND_LABELS_ALL: Record<string, string[]> = (() => {
  const zh = (zhConsole as { pricing?: { itemKind?: Record<string, string> } })
    .pricing?.itemKind ?? {};
  const en = (enConsole as { pricing?: { itemKind?: Record<string, string> } })
    .pricing?.itemKind ?? {};
  const kinds = new Set([...Object.keys(zh), ...Object.keys(en)]);
  const out: Record<string, string[]> = {};
  kinds.forEach((k) => {
    out[k] = [zh[k], en[k]].filter((v): v is string => typeof v === "string");
  });
  return out;
})();

/** 判断名称是否等于某个 kind 的中英任一类型标签 */
function labelMatchesKind(label: string, kind: string): boolean {
  const n = normalizeLabel(label);
  return (ITEM_KIND_LABELS_ALL[kind] ?? []).some(
    (v) => normalizeLabel(v) === n
  );
}

export const ALL_ITEM_KINDS: PricingItemKind[] = [
  "output_video_duration",
  "input_video_duration",
  "input_image_fixed",
  "output_image_count",
  "input_image_tokens",
  "output_image_tokens",
  "input_text_tokens",
  "cache_write_input_text_tokens",
  "cached_input_text_tokens",
  "output_text_tokens",
  "request_fixed",
];

/** 各模型类型建议优先使用的计费项类型 */
export const RECOMMENDED_ITEM_KINDS_BY_MODEL_TYPE: Record<string, PricingItemKind[]> = {
  video: ["output_video_duration", "input_video_duration", "input_image_fixed"],
  image: [
    "input_image_tokens",
    "output_image_tokens",
    "output_image_count",
    "input_image_fixed",
    "request_fixed",
  ],
  text: [
    "input_text_tokens",
    "cache_write_input_text_tokens",
    "cached_input_text_tokens",
    "output_text_tokens",
    "request_fixed",
  ],
};

/** 各模型类型必须保留的计费主体项类型，与后端校验一致 */
export const REQUIRED_SUBJECT_KINDS: Record<string, PricingItemKind[]> = {
  video: ["output_video_duration"],
  image: [
    "input_image_tokens",
    "output_image_tokens",
    "output_image_count",
    "request_fixed",
  ],
  text: [
    "input_text_tokens",
    "cache_write_input_text_tokens",
    "cached_input_text_tokens",
    "output_text_tokens",
    "request_fixed",
  ],
};

/** 主体计费项文案（i18n） */
export function subjectKindLabel(t: Translate, modelType: string): string {
  return t(`subjectKind.${modelType}`);
}

/** 计量来源可留空的计费项类型：token 类与按次固定项由系统计量 */
export const OPTIONAL_SOURCE_KINDS = new Set<PricingItemKind>([
  "input_text_tokens",
  "cache_write_input_text_tokens",
  "cached_input_text_tokens",
  "output_text_tokens",
  "input_image_tokens",
  "output_image_tokens",
  "request_fixed",
]);

/**
 * Token 计费项：unit_amount 单位为 USD / 1M Token，
 * 前端直接读写接口返回的数值，不做每 Token 与每百万 Token 之间的换算。
 */
export const TOKEN_ITEM_KINDS = new Set<PricingItemKind>([
  "input_text_tokens",
  "cache_write_input_text_tokens",
  "cached_input_text_tokens",
  "output_text_tokens",
  "input_image_tokens",
  "output_image_tokens",
]);

export type PricingRule = {
  id: string;
  model_id: string;
  token_group_id: number;
  name: string;
  priority: number;
  conditions: PricingCondition[];
  items: PricingRuleItemView[];
  currency: string;
  active: boolean;
  created_at?: string;
  updated_at?: string;
};

export type GroupOption = {
  id: number;
  name: string;
};

/** 数值型条件字段：提交时解析为数字 */
export const NUMERIC_FIELDS = new Set([
  "duration_seconds",
  "prompt_tokens",
  "completion_tokens",
  "total_tokens",
  "n",
  "seconds",
  "characters",
  "input_image_count",
  "input_video_seconds",
  "image_pixel_count",
]);

export const PLATFORM_PRICING_FIELDS = [
  "shanghai_time",
  "input_image_count",
  "input_video_seconds",
];

/**
 * 读取派生计费字段类型（如由 size 派生的 image_pixel_count）。
 * 入参可为模型请求契约对象，或模板详情中的 derived_pricing_fields 数组。
 */
export function derivedPricingFieldTypes(source: unknown): string[] {
  const declarations = Array.isArray(source)
    ? source
    : source && typeof source === "object"
      ? (source as Record<string, unknown>).derived_pricing_fields
      : undefined;
  if (!Array.isArray(declarations)) return [];
  return declarations
    .map((d) =>
      d && typeof d === "object"
        ? (d as Record<string, unknown>).type
        : undefined
    )
    .filter((t): t is string => typeof t === "string" && t.length > 0);
}

export const OPERATOR_VALUES = ["eq", "in", "gte", "lte", "between"] as const;

/** 运算符下拉选项（i18n） */
export function operatorOptions(t: Translate) {
  return OPERATOR_VALUES.map((v) => ({ value: v, label: t(`operator.${v}`) }));
}

/** 运算符符号展示（i18n，仅 between 有文本） */
export function operatorSymbol(t: Translate, operator: string): string {
  if (operator === "between") return t("operator.between");
  const symbols: Record<string, string> = { eq: "=", in: "∈", gte: "≥", lte: "≤" };
  return symbols[operator] ?? operator;
}

/** 兼容多种分页响应：数组 / { items, total } / { rules, total } */
export function normalize(data: unknown): { rules: PricingRule[]; total: number } {
  if (Array.isArray(data)) return { rules: data, total: data.length };
  if (data && typeof data === "object") {
    const d = data as Record<string, unknown>;
    const list = (d.items ?? d.rules ?? d.list ?? []) as PricingRule[];
    const total = typeof d.total === "number" ? d.total : list.length;
    return { rules: list, total };
  }
  return { rules: [], total: 0 };
}

/** 拉取模型与分组列表，供表单选择与列表名称展示 */
export function useOptions() {
  const [models, setModels] = useState<ModelOption[]>([]);
  const [groups, setGroups] = useState<GroupOption[]>([]);
  const [modelsLoaded, setModelsLoaded] = useState(false);

  useEffect(() => {
    get<unknown>("/admin/models/list", {
      params: { page: 1, page_size: 100 },
    })
      .then((data) => {
        const list = Array.isArray(data)
          ? data
          : (((data as Record<string, unknown>).items ??
              (data as Record<string, unknown>).models ??
              (data as Record<string, unknown>).list ??
              []) as ModelOption[]);
        setModels(list);
      })
      .catch(() => {})
      .finally(() => setModelsLoaded(true));
    get<unknown>("/admin/token/groups/list", {
      params: { page: 1, page_size: 100 },
    })
      .then((data) => {
        const list = Array.isArray(data)
          ? data
          : (((data as Record<string, unknown>).items ??
              (data as Record<string, unknown>).groups ??
              (data as Record<string, unknown>).list ??
              []) as GroupOption[]);
        setGroups(list);
      })
      .catch(() => {});
  }, []);

  return { models, groups, modelsLoaded };
}

/** 条件的可读展示：duration_seconds = 6 */
export function conditionLabel(t: Translate, c: PricingCondition): string {
  const value = Array.isArray(c.value) ? c.value.join(", ") : String(c.value);
  return `${c.field} ${operatorSymbol(t, c.operator)} ${value}`;
}

export function conditionRowsOf(conditions: PricingCondition[]): ConditionRow[] {
  return conditions.map((condition) => ({
    field: condition.field,
    operator: condition.operator,
    value: Array.isArray(condition.value)
      ? condition.value.join(", ")
      : String(condition.value),
  }));
}

export function timeValue(parts: string[]): string {
  return `${parts[0] ?? "00"}:${parts[1] ?? "00"}:00.000000`;
}

export function timeParts(value: string | undefined): [string, string] {
  const [hour = "00", minute = "00"] = (value ?? "00:00").split(":");
  return [hour.padStart(2, "0"), minute.padStart(2, "0")];
}

export function parseConditions(rows: ConditionRow[], t: Translate): PricingCondition[] | null {
  const conditions: PricingCondition[] = [];
  for (let i = 0; i < rows.length; i++) {
    const row = rows[i];
    const n = i + 1;
    if (!row.field) {
      toast.warning(t("condSelectField", { n }));
      return null;
    }
    if (row.field === "shanghai_time") {
      const values = row.value.split(",").map((value) => value.trim());
      if (values.length !== 2 || values.some((value) => !/^\d{2}:\d{2}:00\.000000$/.test(value))) {
        toast.warning(t("condTimeRange", { n }));
        return null;
      }
      conditions.push({ field: row.field, operator: "between", value: values });
      continue;
    }
    const values = row.value.split(",").map((value) => value.trim()).filter(Boolean);
    if (values.length === 0) {
      toast.warning(t("condFillValue", { n }));
      return null;
    }
    if (row.operator === "between" && values.length !== 2) {
      toast.warning(t("condBetweenTwo", { n }));
      return null;
    }
    const parsedValues = values.map((value) =>
      NUMERIC_FIELDS.has(row.field) ? Number(value) : value
    );
    if (parsedValues.some((value) => typeof value === "number" && !Number.isFinite(value))) {
      toast.warning(t("condNumeric", { n }));
      return null;
    }
    conditions.push({
      field: row.field,
      operator: row.operator as PricingCondition["operator"],
      value: row.operator === "in" || row.operator === "between" ? parsedValues : parsedValues[0],
    });
  }
  return conditions;
}

/** 生效条件编辑器：字段按所选模型的类型限制 */
export function ConditionsEditor({
  rows,
  onChange,
  fieldOptions,
}: {
  rows: ConditionRow[];
  onChange: (rows: ConditionRow[]) => void;
  fieldOptions: string[];
}) {
  const { t } = useTranslation("console", { keyPrefix: "pricing" });
  const updateRow = (i: number, patch: Partial<ConditionRow>) =>
    onChange(rows.map((r, idx) => (idx === i ? { ...r, ...patch } : r)));

  const setField = (i: number, field: string) =>
    updateRow(i, field === "shanghai_time"
      ? { field, operator: "between", value: "00:00:00.000000, 00:00:00.000000" }
      : { field });

  const setTimeBoundary = (i: number, boundary: number, part: number, value: string) => {
    const current = rows[i].value.split(",").map((entry) => entry.trim());
    const times = [timeParts(current[0]), timeParts(current[1])];
    times[boundary][part] = value;
    updateRow(i, { value: `${timeValue(times[0])}, ${timeValue(times[1])}` });
  };

  return (
    <div className="space-y-2.5">
      {rows.length > 0 && (
        <div className="flex items-center gap-2 px-0.5 text-xs text-muted-foreground">
          <span className="w-40">{t("condField")}</span>
          <span className="w-24">{t("condOperator")}</span>
          <span className="flex-1">{t("condValue")}</span>
          <span className="size-6" />
        </div>
      )}
      {rows.map((row, i) => {
        const isTime = row.field === "shanghai_time";
        return (
        <div key={i} className="flex items-center gap-2">
          <div className="w-40 shrink-0">
            <Select
              aria-label={`${t("condPrefix")} ${i + 1} ${t("condField")}`}
              value={row.field}
              onValueChange={(v) => setField(i, v)}
              options={fieldOptions.map((f) => ({ value: f, label: f }))}
              placeholder={t("condFieldPlaceholder")}
            />
          </div>
          {isTime ? (
            /* 抽屉已加宽，时间条件与其他条件一样单行展示 */
            <div className="flex min-w-0 flex-1 items-center gap-2">
              <span className="shrink-0 text-xs text-muted-foreground">{t("timeRange")}</span>
              {[0, 1].map((boundary) => {
                const parts = timeParts(row.value.split(",")[boundary]?.trim());
                return (
                  <div key={boundary} className="flex min-w-0 flex-1 items-center gap-1">
                    <div className="min-w-0 flex-1">
                      <Select aria-label={`${t("condPrefix")} ${i + 1} ${t(boundary === 0 ? "pricing.timeStartHour" : "pricing.timeEndHour")}`} value={parts[0]} onValueChange={(v) => setTimeBoundary(i, boundary, 0, v)} options={Array.from({ length: 24 }, (_, hour) => ({ value: String(hour).padStart(2, "0"), label: String(hour).padStart(2, "0") }))} />
                    </div>
                    <span className="shrink-0 text-xs text-muted-foreground">:</span>
                    <div className="min-w-0 flex-1">
                      <Select aria-label={`${t("condPrefix")} ${i + 1} ${t(boundary === 0 ? "pricing.timeStartMinute" : "pricing.timeEndMinute")}`} value={parts[1]} onValueChange={(v) => setTimeBoundary(i, boundary, 1, v)} options={Array.from({ length: 60 }, (_, minute) => ({ value: String(minute).padStart(2, "0"), label: String(minute).padStart(2, "0") }))} />
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <>
              <div className="w-24 shrink-0">
                <Select aria-label={`${t("condPrefix")} ${i + 1} ${t("condOperator")}`} value={row.operator} onValueChange={(v) => updateRow(i, { operator: v })} options={operatorOptions(t)} />
              </div>
              <Input aria-label={`${t("condPrefix")} ${i + 1} ${t("condValue")}`} value={row.value} onChange={(e) => updateRow(i, { value: e.target.value })} placeholder={NUMERIC_FIELDS.has(row.field) ? t("condNumericEg") : t("condTextEg")} autoComplete="off" className="flex-1" />
            </>
          )}
          <button
            type="button"
            onClick={() => onChange(rows.filter((_, idx) => idx !== i))}
            aria-label={t("deleteCondition", { n: i + 1 })}
            className="shrink-0 rounded-md p-1 text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive"
          >
            <Trash2 className="size-3.5" />
          </button>
        </div>
        );
      })}
      <button
        type="button"
        onClick={() =>
          onChange([
            ...rows,
            fieldOptions[0] === "shanghai_time"
              ? { field: "shanghai_time", operator: "between", value: "00:00:00.000000, 00:00:00.000000" }
              : { field: fieldOptions[0] ?? "", operator: "eq", value: "" },
          ])
        }
        disabled={fieldOptions.length === 0}
        className="flex w-full cursor-pointer items-center justify-center gap-1.5 rounded-lg border border-dashed border-border/70 py-2 text-xs text-muted-foreground transition-colors enabled:hover:border-primary/40 enabled:hover:bg-primary/5 enabled:hover:text-primary disabled:cursor-not-allowed disabled:opacity-40"
      >
        <Plus className="size-3.5" />
        {t("addCondition")}
      </button>
    </div>
  );
}

/** 新建 / 编辑价格规则弹窗（rule 为 null 时新建） */
export function PricingRuleFormDialog({
  rule,
  models,
  groups,
  defaultModelId,
  onClose,
  onSaved,
}: {
  rule: PricingRule | null;
  models: ModelOption[];
  groups: GroupOption[];
  /** 新建时默认归属模型（来自当前筛选上下文），仍可在表单内切换 */
  defaultModelId?: string;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { t } = useTranslation("console", { keyPrefix: "pricing" });
  const isEdit = rule !== null;
  const [name, setName] = useState(rule?.name ?? "");
  const [modelId, setModelId] = useState(rule?.model_id ?? defaultModelId ?? "");
  const [groupId, setGroupId] = useState(
    rule ? String(rule.token_group_id) : ""
  );
  const [priority, setPriority] = useState(String(rule?.priority ?? 0));
  const [items, setItems] = useState<PricingRuleItem[]>(
    // 接口的 null 表示未定价，表单内归一化为空串，避免空值参与 trim/Input 受控判断
    () =>
      (rule?.items ?? []).map((item) => ({
        ...item,
        unit_amount: item.unit_amount ?? "",
      }))
  );
  const [currency, setCurrency] = useState(rule?.currency ?? "USD");
  const [conditionRows, setConditionRows] = useState<ConditionRow[]>(() =>
    (rule?.conditions ?? []).map((c) => ({
      field: c.field,
      operator: c.operator,
      value: String(c.value),
    }))
  );
  const [active, setActive] = useState(rule?.active ?? true);
  const [submitting, setSubmitting] = useState(false);
  /** 记录 mousedown 是否发生在遮罩上：避免从面板内拖选文本、在遮罩上松手时误关闭抽屉 */
  const overlayMouseDown = useRef(false);
  const [pricingFields, setPricingFields] = useState<string[] | null>(null);
  /** 系统派生的内部计价字段（如 image_pixel_count），可作为条件字段引用 */
  const [derivedFields, setDerivedFields] = useState<string[]>([]);
  /** 模板素材字段：校验输入图片/视频项的 source_fields 类别 */
  const [templateMaterialFields, setTemplateMaterialFields] = useState<Record<
    string,
    { categories?: string[]; multiple?: boolean } | undefined
  > | null>(null);
  /** 模板首条规则只在新建时用于预填，不会自动创建其他默认档位。 */
  const prefillTemplateRule = useCallback(
    (templateRule?: DefaultPricingRule) => {
      if (isEdit || !templateRule) return;
      setName(templateRule.name);
      setPriority(String(templateRule.priority));
      setConditionRows(
        templateRule.conditions.map((condition) => ({
          field: condition.field,
          operator: condition.operator,
          value: Array.isArray(condition.value)
            ? condition.value.join(", ")
            : String(condition.value),
        }))
      );
      setItems(
        templateRule.items.map((item, index) => ({
          ...item,
          id: "",
          position: item.position ?? index,
          source_fields: [...item.source_fields],
          unit_amount: item.unit_amount ?? "",
          price_source_item_id: null,
          active: item.active ?? true,
        }))
      );
    },
    [isEdit]
  );

  /**
   * 条件字段候选来自模型详情：优先 pricing_fields；
   * 旧数据缺失时回退到请求契约声明的字段（input_schema ∪ projection）。
   * pricingFields 为 null 表示详情尚未返回。
   */
  useEffect(() => {
    if (!modelId) return;
    let cancelled = false;
    get<{ pricing_fields?: string[]; input_contract?: Record<string, unknown>; template_id?: string; material_fields?: Record<string, { categories?: string[]; multiple?: boolean }> }>(
      "/admin/models/detail",
      { params: { model_id: modelId } }
    )
      .then((detail) => {
        if (cancelled) return;
        const fields =
          detail.pricing_fields ?? pricingFieldCandidates(detail.input_contract);
        // 派生计费字段由模型请求契约声明，属于内部计价字段，条件可直接引用
        const contractDerived = derivedPricingFieldTypes(detail.input_contract);
        setPricingFields(fields);
        setDerivedFields(contractDerived);
        // 切换模型后，移除已不属于新模型计价维度、派生字段或平台字段的条件
        const usable = new Set([
          ...fields,
          ...contractDerived,
          ...PLATFORM_PRICING_FIELDS,
        ]);
        setConditionRows((prev) => prev.filter((r) => usable.has(r.field)));
        // 若模型已绑定模板，拉取模板详情用于预填首条规则和校验素材字段
        if (detail.template_id) {
          get<{
            default_pricing_rules?: DefaultPricingRule[];
            derived_pricing_fields?: { type?: string }[];
            material_fields?: Record<
              string,
              { categories?: string[]; multiple?: boolean }
            >;
          }>("/admin/provider-templates/detail", {
            params: { template_id: detail.template_id },
          })
            .then((tpl) => {
              if (cancelled) return;
              prefillTemplateRule(tpl.default_pricing_rules?.[0]);
              setTemplateMaterialFields(tpl.material_fields ?? null);
              // 契约缺失派生声明时回退到模板声明
              setDerivedFields((prev) =>
                prev.length > 0
                  ? prev
                  : derivedPricingFieldTypes(tpl.derived_pricing_fields)
              );
            })
            .catch(() => {
              if (!cancelled) {
                setTemplateMaterialFields(null);
              }
            });
        } else {
          setTemplateMaterialFields(detail.material_fields ?? null);
        }
      })
      .catch((err) => {
        if (cancelled) return;
        setPricingFields([]);
        setDerivedFields([]);
        setTemplateMaterialFields(null);
        toast.error(
          err instanceof Error ? err.message : t("modelDimensionsFailed")
        );
      });
    return () => {
      cancelled = true;
    };
  }, [modelId, prefillTemplateRule]);

  /** 条件字段候选：模型计价维度、派生计费字段与平台内部字段 */
  const fieldOptions = Array.from(
    new Set([
      ...(pricingFields ?? []),
      ...derivedFields,
      ...PLATFORM_PRICING_FIELDS,
    ])
  );

  /** 当前模型类型：决定可选计费项类型与主体项要求 */
  const modelType = models.find((m) => m.id === modelId)?.model_type ?? "video";
  const recommendedItemKinds = new Set(
    RECOMMENDED_ITEM_KINDS_BY_MODEL_TYPE[modelType] ?? []
  );
  const itemKindOptions = ALL_ITEM_KINDS.map((kind) => ({
    value: kind,
    label: `${itemKindLabel(t, kind)}${recommendedItemKinds.has(kind) ? t("recommended") : ""}`,
  }));
  const defaultItemKind =
    RECOMMENDED_ITEM_KINDS_BY_MODEL_TYPE[modelType]?.[0] ?? "output_video_duration";

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) {
      toast.warning(t("errName"));
      return;
    }
    if (!modelId) {
      toast.warning(t("errModel"));
      return;
    }
    if (!groupId) {
      toast.warning(t("errGroup"));
      return;
    }
    const priorityNum = Number(priority);
    if (!Number.isInteger(priorityNum)) {
      toast.warning(t("errPriority"));
      return;
    }
    const requiredKinds = REQUIRED_SUBJECT_KINDS[modelType] ?? [];
    const activeSubjectItems = items.filter(
      (it) => it.active && requiredKinds.includes(it.kind)
    );
    if (activeSubjectItems.length === 0) {
      toast.warning(
        t("errSubjectItem", { subject: subjectKindLabel(t, modelType) })
      );
      return;
    }
    const activeOutputItems = items.filter(
      (it) => it.kind === "output_video_duration" && it.active
    );
    const hasActiveInputVideo = items.some(
      (it) => it.kind === "input_video_duration" && it.active
    );
    if (hasActiveInputVideo && activeOutputItems.length !== 1) {
      toast.warning(t("errOutputVideoPair"));
      return;
    }
    const positions = new Set<number>();
    for (let i = 0; i < items.length; i++) {
      const it = items[i];
      const n = i + 1;
      if (positions.has(it.position)) {
        toast.warning(t("errPositionDup"));
        return;
      }
      positions.add(it.position);
      if (!it.label.trim()) {
        toast.warning(t("errItemName", { n }));
        return;
      }
      const sourceRequired = !OPTIONAL_SOURCE_KINDS.has(it.kind);
      if (sourceRequired && it.source_fields.length === 0) {
        toast.warning(t("errItemSource", { n }));
        return;
      }
      if (
        sourceRequired &&
        pricingFields !== null &&
        it.source_fields.some((field) => !pricingFields.includes(field))
      ) {
        toast.warning(t("errItemUndeclared", { n }));
        return;
      }
      if (it.kind === "input_image_fixed" || it.kind === "input_video_duration") {
        const category = it.kind === "input_image_fixed" ? "image" : "video";
        if (
          !templateMaterialFields ||
          it.source_fields.some(
            (field) => !templateMaterialFields[field]?.categories?.includes(category)
          )
        ) {
          toast.warning(t("errItemMaterial", { n, kind: t(`material.${category}`) }));
          return;
        }
      }
      if (it.kind === "input_video_duration") continue;
      const amount = it.unit_amount.trim();
      if (!/^\d+(\.\d+)?$/.test(amount)) {
        toast.warning(t("errItemPrice", { n }));
        return;
      }
      // 输入图片张数允许为 0（免费额度型），其余计费项单价必须大于 0
      if (it.kind !== "input_image_fixed" && Number(amount) <= 0) {
        toast.warning(t("errItemPricePositive", { n }));
        return;
      }
    }
    if (!currency.trim()) {
      toast.warning(t("errCurrency"));
      return;
    }
    if (pricingFields !== null && conditionRows.some((row) => !pricingFields.includes(row.field) && !derivedFields.includes(row.field) && !PLATFORM_PRICING_FIELDS.includes(row.field))) {
      toast.warning(t("errCondUndeclared"));
      return;
    }
    const conditions = parseConditions(conditionRows, t);
    if (conditions === null) return;

    setSubmitting(true);
    try {
      await post(
        isEdit ? "/admin/pricing-rules/update" : "/admin/pricing-rules/create",
        {
          ...(isEdit ? { pricing_rule_id: rule.id } : {}),
          model_id: modelId,
          token_group_id: Number(groupId),
          name: name.trim(),
          priority: priorityNum,
          conditions,
          currency: currency.trim(),
          active,
          items: items.map((it) => ({
            ...(it.id ? { id: it.id } : {}),
            label: it.label.trim(),
            position: it.position,
            kind: it.kind,
            source_fields: it.source_fields,
            free_quantity: it.free_quantity,
            unit_amount:
              it.kind === "input_video_duration" ? null : it.unit_amount.trim(),
            active: it.active,
          })),
        }
      );
      toast.success(isEdit ? t("updateSuccess") : t("createSuccess"));
      onSaved();
      onClose();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t("saveFailed"));
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
        className="flex h-full w-full max-w-3xl flex-col border-l border-border/80 bg-background shadow-2xl animate-in slide-in-from-right duration-300"
        onClick={(e) => e.stopPropagation()}
      >
        {/* 抽屉头部：固定吸顶 */}
        <div className="flex items-center justify-between border-b border-border/60 px-6 py-4">
          <div>
            <h2 className="text-base font-semibold">
              {isEdit ? t("formEditTitle") : t("formCreateTitle")}
            </h2>
            <p className="mt-0.5 text-xs text-muted-foreground">
              {isEdit
                ? t("formEditDesc", { name: rule.name })
                : ""}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label={t("close")}
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
            <div className="space-y-1.5">
              <label htmlFor="rule-name" className="text-sm font-medium">
                {t("ruleName")}
              </label>
              <Input
                id="rule-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder={t("ruleNamePlaceholder")}
                autoComplete="off"
              />
            </div>
            <div className="space-y-1.5">
              <span className="text-sm font-medium">{t("model")}</span>
              <Select
                aria-label={t("model")}
                value={modelId}
                onValueChange={setModelId}
                options={models.map((m) => ({
                  value: m.id,
                  label: m.name,
                }))}
                placeholder={t("selectModel")}
                emptyText={t("noModel")}
              />
            </div>
            <div className="space-y-1.5">
              <span className="text-sm font-medium">{t("tokenGroup")}</span>
              <Select
                aria-label={t("tokenGroup")}
                value={groupId}
                onValueChange={setGroupId}
                options={groups.map((g) => ({
                  value: String(g.id),
                  label: g.name,
                }))}
                placeholder={t("selectGroup")}
                emptyText={t("noGroup")}
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <label htmlFor="rule-priority" className="text-sm font-medium">
                  {t("priority")}
                </label>
                <Input
                  id="rule-priority"
                  type="number"
                  step={1}
                  value={priority}
                  onChange={(e) => setPriority(e.target.value)}
                />
              </div>
              <div className="space-y-1.5">
                <label htmlFor="rule-currency" className="text-sm font-medium">
                  {t("currency")}
                </label>
                <Input
                  id="rule-currency"
                  value={currency}
                  onChange={(e) => setCurrency(e.target.value)}
                  placeholder="USD"
                  autoComplete="off"
                />
              </div>
            </div>
            <div className="space-y-1.5">
              <div className="flex items-center justify-between">
                <p className="text-sm font-medium">
                  {t("itemsLabel")}
                  <span className="ml-1 text-xs font-normal text-muted-foreground">
                    {t("itemsHint", { subject: subjectKindLabel(t, modelType) })}
                  </span>
                </p>
                <button
                  type="button"
                  onClick={() => {
                    const nextPos = items.length > 0 ? Math.max(...items.map((it) => it.position)) + 1 : 0;
                    setItems([
                      ...items,
                      {
                        id: "",
                        label: "",
                        position: nextPos,
                        kind: defaultItemKind,
                        source_fields: [],
                        free_quantity: 0,
                        unit_amount: "",
                        price_source_item_id: null,
                        active: true,
                      },
                    ]);
                  }}
                  className="flex items-center gap-1 rounded-md px-2 py-1 text-xs text-primary transition-colors hover:bg-primary/5"
                >
                  <Plus className="size-3.5" />
                  {t("addItem")}
                </button>
              </div>
              {items.length === 0 ? (
                <p className="rounded-lg border border-dashed border-border/70 py-4 text-center text-xs text-muted-foreground">
                  {t("noItemsAdd")}
                </p>
              ) : (
                <div className="space-y-3">
                  {items.map((item, idx) => {
                    return (
                      <div
                        key={idx}
                        className="rounded-lg border border-border/60 bg-muted/10 p-3 space-y-2.5"
                      >
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-medium text-muted-foreground">
                            {t("itemN", { n: idx + 1 })}
                          </span>
                          <button
                            type="button"
                            onClick={() => {
                              setItems(items.filter((_, i) => i !== idx));
                            }}
                            className="rounded-md p-1 text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive"
                          >
                            <Trash2 className="size-3.5" />
                          </button>
                        </div>
                        <div className="grid grid-cols-2 gap-2">
                          <div className="space-y-1">
                            <label className="text-xs text-muted-foreground">
                              {t("itemName")}
                            </label>
                            <Input
                              value={item.label}
                              onChange={(e) => {
                                const next = [...items];
                                next[idx] = { ...next[idx], label: e.target.value };
                                setItems(next);
                              }}
                              placeholder={t("itemNamePlaceholder")}
                              autoComplete="off"
                              className="h-8 text-xs"
                            />
                          </div>
                          <div className="space-y-1">
                            <label className="text-xs text-muted-foreground">
                              {t("itemKindLabel")}
                            </label>
                            <Select
                              aria-label={t("itemKindAria", { n: idx + 1 })}
                              value={item.kind}
                              onValueChange={(v) => {
                                const next = [...items];
                                next[idx] = { ...next[idx], kind: v as PricingItemKind };
                                setItems(next);
                              }}
                              options={
                                itemKindOptions.some((o) => o.value === item.kind)
                                  ? itemKindOptions
                                  : [
                                      {
                                        value: item.kind,
                                        label: itemKindLabel(t, item.kind),
                                      },
                                      ...itemKindOptions,
                                    ]
                              }
                            />
                          </div>
                        </div>
                        {!OPTIONAL_SOURCE_KINDS.has(item.kind) && (
                          <div className="space-y-1">
                            <label className="text-xs text-muted-foreground">
                              {t("sourceFields")}
                              <span className="ml-1 text-muted-foreground/60">
                                {item.kind === "input_image_fixed"
                                  ? t("sourceFieldsImageHint")
                                  : item.kind === "input_video_duration"
                                    ? t("sourceFieldsVideoHint")
                                    : t("sourceFieldsDefaultHint")}
                              </span>
                            </label>
                            <Input
                              value={item.source_fields.join(", ")}
                              onChange={(e) => {
                                const next = [...items];
                                next[idx] = {
                                  ...next[idx],
                                  source_fields: e.target.value
                                    .split(/[,，]/)
                                    .map((s) => s.trim())
                                    .filter(Boolean),
                                };
                                setItems(next);
                              }}
                              placeholder={
                                item.kind === "input_image_fixed"
                                  ? Object.entries(templateMaterialFields ?? {})
                                      .filter(([, v]) => v?.categories?.includes("image"))
                                      .map(([key]) => key)
                                      .join(", ") || t("sourcePlaceholderImage")
                                  : item.kind === "input_video_duration"
                                    ? Object.entries(templateMaterialFields ?? {})
                                        .filter(([, v]) => v?.categories?.includes("video"))
                                        .map(([key]) => key)
                                        .join(", ") || t("sourcePlaceholderVideo")
                                    : item.kind === "output_image_count"
                                      ? t("sourcePlaceholderN")
                                      : t("sourcePlaceholderSeconds")
                              }
                              autoComplete="off"
                              className="h-8 text-xs"
                            />
                          </div>
                        )}
                        <div className="grid grid-cols-2 gap-2">
                          {item.kind === "input_video_duration" ? (
                            <div className="space-y-1">
                              <label className="text-xs text-muted-foreground">
                                {t("unitPrice")}
                              </label>
                              <Input
                                value=""
                                disabled
                                placeholder={t("unitPriceAuto")}
                                className="h-8 text-xs"
                              />
                            </div>
                          ) : (
                            <div className="space-y-1">
                              <label className="text-xs text-muted-foreground">
                                {t("unitPrice")}
                                {TOKEN_ITEM_KINDS.has(item.kind) && (
                                  <span className="ml-1 text-muted-foreground/60">
                                    {t("unitPriceToken")}
                                  </span>
                                )}
                                {!item.unit_amount.trim() && (
                                  <span className="ml-1 text-warning">{t("unpriced")}</span>
                                )}
                              </label>
                              <Input
                                inputMode="decimal"
                                value={item.unit_amount}
                                onChange={(e) => {
                                  const next = [...items];
                                  next[idx] = { ...next[idx], unit_amount: e.target.value };
                                  setItems(next);
                                }}
                                placeholder="0.000000"
                                autoComplete="off"
                                className="h-8 text-xs"
                              />
                            </div>
                          )}
                          <div className="space-y-1">
                            <label className="text-xs text-muted-foreground">
                              {t("freeQuantity")}
                            </label>
                            <Input
                              type="number"
                              min={0}
                              step={1}
                              value={item.free_quantity}
                              onChange={(e) => {
                                const next = [...items];
                                next[idx] = {
                                  ...next[idx],
                                  free_quantity: Math.max(0, Number(e.target.value) || 0),
                                };
                                setItems(next);
                              }}
                              className="h-8 text-xs"
                            />
                          </div>
                        </div>
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-1.5">
                            <Switch
                              checked={item.active}
                              onCheckedChange={(v) => {
                                const next = [...items];
                                next[idx] = { ...next[idx], active: v };
                                setItems(next);
                              }}
                            />
                            <span className="text-xs text-muted-foreground">
                              {item.active ? t("itemActive") : t("itemInactive")}
                            </span>
                          </div>
                          <span className="font-mono text-xs text-muted-foreground">
                            position: {item.position}
                          </span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
            <div className="space-y-1.5">
              <p className="text-sm font-medium">
                {t("conditionsLabel")}
                <span className="ml-1 text-xs font-normal text-muted-foreground">
                  {t("conditionsHint")}
                </span>
              </p>
              {!modelId ? (
                <p className="rounded-lg border border-dashed border-border/70 py-4 text-center text-xs text-muted-foreground">
                  {t("selectModelFirst")}
                </p>
              ) : pricingFields === null ? (
                <p className="flex items-center justify-center gap-2 rounded-lg border border-dashed border-border/70 py-4 text-xs text-muted-foreground">
                  <Loading size="sm" />
                  {t("loadingDimensions")}
                </p>
              ) : (
                <>
                  <ConditionsEditor
                    rows={conditionRows}
                    onChange={setConditionRows}
                    fieldOptions={fieldOptions}
                  />
                  {pricingFields.length === 0 && (
                    <p className="rounded-lg border border-dashed border-border/70 py-2.5 text-center text-xs text-muted-foreground">
                      {t("noDimensions")}
                    </p>
                  )}
                </>
              )}
            </div>
            <div className="flex items-center justify-between rounded-lg border border-border/60 bg-muted/20 p-3">
              <div>
                <p className="text-sm font-medium">{t("activeStatus")}</p>
                <p className="text-xs text-muted-foreground">
                  {t("activeStatusHint")}
                </p>
              </div>
              <Switch checked={active} onCheckedChange={setActive} />
            </div>
          </div>

          {/* 抽屉底部操作栏：固定吸底 */}
          <div className="flex justify-end gap-2 border-t border-border/60 bg-background/80 px-6 py-3.5 backdrop-blur-sm">
            <Button type="button" variant="outline" onClick={onClose}>
              {t("cancel")}
            </Button>
            <Button type="submit" disabled={submitting}>
              {submitting && <Loading size="sm" />}
              {isEdit ? t("saveChanges") : t("createRuleBtn")}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}

/** 价格规则详情弹窗：打开时按 pricing_rule_id 拉取详情 */
export function PricingRuleDetailDialog({
  ruleId,
  modelName,
  groupName,
  onClose,
}: {
  ruleId: string;
  modelName: (id: string) => string;
  groupName: (id: number) => string;
  onClose: () => void;
}) {
  const { t, i18n } = useTranslation("console", { keyPrefix: "pricing" });
  const [detail, setDetail] = useState<PricingRule | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    get<PricingRule>("/admin/pricing-rules/detail", {
      params: { pricing_rule_id: ruleId },
    })
      .then(setDetail)
      .catch((err) =>
        setError(err instanceof Error ? err.message : t("loadFailed"))
      )
      .finally(() => setLoading(false));
  }, [ruleId, t]);

  const formatTime = (s?: string) =>
    s ? new Date(s).toLocaleString(i18n.language === "zh" ? "zh-CN" : "en-US") : "-";

  return (
    <div
      className="fixed inset-0 z-[80] flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="max-h-[85vh] w-full max-w-md overflow-y-auto rounded-xl border bg-background p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-base font-semibold">{t("detailTitle")}</h2>
        {loading ? (
          <div className="flex justify-center py-10">
            <Loading size="lg" />
          </div>
        ) : error || !detail ? (
          <p className="py-10 text-center text-sm text-muted-foreground">
            {error || t("detailEmpty")}
          </p>
        ) : (
          <dl className="mt-5 space-y-3 text-sm">
            <div className="flex items-start justify-between gap-4">
              <dt className="shrink-0 text-muted-foreground">{t("detailName")}</dt>
              <dd className="text-right font-medium">{detail.name}</dd>
            </div>
            <div className="flex items-start justify-between gap-4">
              <dt className="shrink-0 text-muted-foreground">{t("model")}</dt>
              <dd className="text-right font-medium">
                {modelName(detail.model_id)}
              </dd>
            </div>
            <div className="flex items-start justify-between gap-4">
              <dt className="shrink-0 text-muted-foreground">{t("tokenGroup")}</dt>
              <dd className="text-right font-medium">
                {groupName(detail.token_group_id)}
              </dd>
            </div>
            <div className="flex items-start justify-between gap-4">
              <dt className="shrink-0 text-muted-foreground">{t("priority")}</dt>
              <dd className="text-right font-mono text-xs">
                {detail.priority}
              </dd>
            </div>
            <div className="space-y-1.5">
              <dt className="text-muted-foreground">{t("itemsLabel")}</dt>
              <dd className="space-y-1.5">
                {detail.items && detail.items.length > 0 ? (
                  detail.items.map((it) => {
                    const kindText = itemKindLabel(t, it.kind);
                    const label = it.label.trim();
                    // 自定义名称与计费类型标签（任一语言）相同时不重复展示
                    const showLabel =
                      label !== "" &&
                      normalizeLabel(label) !== normalizeLabel(it.kind) &&
                      !labelMatchesKind(label, it.kind);
                    return (
                    <div
                      key={it.id}
                      className="flex items-center justify-between gap-4 rounded-md border border-border/60 bg-muted/30 px-3 py-2"
                    >
                      <div className="flex min-w-0 flex-wrap items-center gap-2">
                        <Badge variant="secondary" className="text-xs">
                          {kindText}
                        </Badge>
                        {showLabel && (
                          <span className="text-xs font-medium">
                            {it.label}
                          </span>
                        )}
                        {!it.active && (
                          <Badge variant="destructive" className="text-xs">
                            {t("itemInactive")}
                          </Badge>
                        )}
                      </div>
                      <span className="shrink-0 whitespace-nowrap font-mono text-xs text-muted-foreground">
                        {it.unit_amount != null
                          ? `${it.unit_amount} ${detail.currency}${TOKEN_ITEM_KINDS.has(it.kind) ? " / 1M Token" : ""}`
                          : it.kind === "input_video_duration"
                            ? t("followSource")
                            : t("unpriced")}
                        {it.free_quantity > 0
                          ? t("freeQtySuffix", { qty: it.free_quantity })
                          : ""}
                      </span>
                    </div>
                    );
                  })
                ) : (
                  <span className="text-xs text-muted-foreground">
                    {t("noItems")}
                  </span>
                )}
              </dd>
            </div>
            <div className="flex items-start justify-between gap-4">
              <dt className="shrink-0 text-muted-foreground">{t("colStatus")}</dt>
              <dd>
                <Badge variant={detail.active ? "default" : "destructive"}>
                  {detail.active ? t("active") : t("inactive")}
                </Badge>
              </dd>
            </div>
            {detail.conditions && detail.conditions.length > 0 && (
              <div className="space-y-1.5">
                <dt className="text-muted-foreground">{t("conditionsLabel")}</dt>
                <dd className="flex flex-wrap justify-end gap-1.5">
                  {detail.conditions.map((c, i) => (
                    <Badge key={i} variant="secondary" className="font-mono">
                      {conditionLabel(t, c)}
                    </Badge>
                  ))}
                </dd>
              </div>
            )}
            <div className="flex items-start justify-between gap-4">
              <dt className="shrink-0 text-muted-foreground">{t("createdAt")}</dt>
              <dd className="text-right text-xs text-muted-foreground">
                {formatTime(detail.created_at)}
              </dd>
            </div>
            <div className="flex items-start justify-between gap-4">
              <dt className="shrink-0 text-muted-foreground">{t("updatedAt")}</dt>
              <dd className="text-right text-xs text-muted-foreground">
                {formatTime(detail.updated_at)}
              </dd>
            </div>
          </dl>
        )}
        <div className="mt-6 flex justify-end">
          <Button variant="outline" onClick={onClose}>
            {t("close")}
          </Button>
        </div>
      </div>
    </div>
  );
}

/** 删除价格规则确认弹窗 */
export function DeletePricingRuleDialog({
  rule,
  onClose,
  onDeleted,
}: {
  rule: PricingRule;
  onClose: () => void;
  onDeleted: () => void;
}) {
  const { t } = useTranslation("console", { keyPrefix: "pricing" });
  const [submitting, setSubmitting] = useState(false);

  const onConfirm = async () => {
    setSubmitting(true);
    try {
      await post("/admin/pricing-rules/delete", { pricing_rule_id: rule.id });
      toast.success(t("deleteSuccess"));
      onDeleted();
      onClose();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t("deleteFailed"));
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
        <h2 className="text-base font-semibold">{t("deleteTitle")}</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          {t("deleteConfirm", { name: rule.name })}
        </p>
        <div className="mt-6 flex justify-end gap-2">
          <Button variant="outline" onClick={onClose}>
            {t("cancel")}
          </Button>
          <Button
            variant="destructive"
            onClick={onConfirm}
            disabled={submitting}
          >
            {submitting && <Loading size="sm" />}
            {t("confirmDelete")}
          </Button>
        </div>
      </div>
    </div>
  );
}

export function PricingModifierDrawer({ rule, onClose }: { rule: PricingRule; onClose: () => void }) {
  const { t } = useTranslation("console", { keyPrefix: "pricing" });
  const [modifiers, setModifiers] = useState<PricingModifier[]>([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<PricingModifier | null>(null);
  const [creating, setCreating] = useState(false);
  /** 记录 mousedown 是否发生在遮罩上：避免从面板内拖选文本、在遮罩上松手时误关闭抽屉 */
  const overlayMouseDown = useRef(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await get<unknown>("/admin/pricing-modifiers/list", { params: { pricing_rule_id: rule.id, page: 1, page_size: 100 } });
      const list = data && typeof data === "object" ? ((data as Record<string, unknown>).items ?? []) : [];
      setModifiers(Array.isArray(list) ? list as PricingModifier[] : []);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t("modifierLoadFailed"));
    } finally {
      setLoading(false);
    }
  }, [rule.id, t]);

  useEffect(() => { void load(); }, [load]);

  const remove = async (modifier: PricingModifier) => {
    try {
      await post("/admin/pricing-modifiers/delete", { pricing_modifier_id: modifier.id });
      toast.success(t("modifierDeleteSuccess"));
      await load();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t("deleteFailed"));
    }
  };

  const copy = async (modifier: PricingModifier) => {
    try {
      await post("/admin/pricing-modifiers/copy", { pricing_modifier_id: modifier.id });
      toast.success(t("modifierCopySuccess"));
      await load();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t("copyFailed"));
    }
  };

  return (
    <div className="fixed inset-0 z-[80] flex justify-end bg-black/50 backdrop-blur-sm" onMouseDown={(e) => { overlayMouseDown.current = e.target === e.currentTarget; }} onClick={(e) => { if (overlayMouseDown.current && e.target === e.currentTarget) onClose(); }}>
      <div className="flex h-full w-full max-w-xl flex-col border-l border-border/80 bg-background shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b border-border/60 px-6 py-4">
          <div><h2 className="text-base font-semibold">{t("modifierTitle")}</h2><p className="mt-0.5 text-xs text-muted-foreground">{t("modifierDesc", { name: rule.name })}</p></div>
          <button type="button" onClick={onClose} aria-label={t("close")} className="rounded-md p-1.5 text-muted-foreground hover:bg-accent hover:text-foreground"><X className="size-4" /></button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto p-6">
          {loading ? <div className="flex justify-center py-12"><Loading size="lg" /></div> : modifiers.length === 0 ? <p className="rounded-lg border border-dashed border-border/70 py-8 text-center text-sm text-muted-foreground">{t("noModifiers")}</p> : <div className="space-y-3">
            {modifiers.map((modifier) => <div key={modifier.id} className="rounded-lg border border-border/60 p-4">
              <div className="flex items-start justify-between gap-3"><div><div className="flex items-center gap-2"><p className="text-sm font-medium">{modifier.name}</p><Badge variant={modifier.active ? "default" : "destructive"}>{modifier.active ? t("itemActive") : t("itemInactive")}</Badge></div><p className="mt-1 text-xs text-muted-foreground">{t("modifierMeta", { priority: modifier.priority, effect: modifier.effect_type === "multiplier" ? t("effectMultiplier", { value: String(modifier.effect_payload.factor ?? "-") }) : t("effectFixed", { value: String(modifier.effect_payload.amount ?? "-") }), scope: t(`scope.${modifier.scope_type}`) })}</p>{modifier.conditions.length > 0 && <p className="mt-1 text-xs text-muted-foreground">{modifier.conditions.map((c) => conditionLabel(t, c)).join(t("condSep"))}</p>}</div><div className="flex gap-1"><Button variant="outline" size="sm" onClick={() => setEditing(modifier)}><Pencil className="size-3.5" />{t("edit")}</Button><Button variant="outline" size="sm" onClick={() => void copy(modifier)}><Copy className="size-3.5" /></Button><Button variant="outline" size="sm" className="text-destructive" onClick={() => void remove(modifier)}><Trash2 className="size-3.5" /></Button></div></div>
            </div>)}
          </div>}
        </div>
        <div className="flex justify-end border-t border-border/60 px-6 py-3.5"><Button onClick={() => setCreating(true)}><Plus className="size-4" />{t("addModifier")}</Button></div>
      </div>
      {(creating || editing) && <PricingModifierFormDialog rule={rule} modifier={editing} onClose={() => { setCreating(false); setEditing(null); }} onSaved={() => { setCreating(false); setEditing(null); void load(); }} />}
    </div>
  );
}

export function PricingModifierFormDialog({ rule, modifier, onClose, onSaved }: { rule: PricingRule; modifier: PricingModifier | null; onClose: () => void; onSaved: () => void }) {
  const { t } = useTranslation("console", { keyPrefix: "pricing" });
  const isEdit = modifier !== null;
  const [name, setName] = useState(modifier?.name ?? "");
  const [priority, setPriority] = useState(String(modifier?.priority ?? 0));
  const [effectType, setEffectType] = useState<PricingModifierEffectType>(modifier?.effect_type ?? "multiplier");
  const [amount, setAmount] = useState(String(modifier?.effect_payload[modifier?.effect_type === "multiplier" ? "factor" : "amount"] ?? ""));
  const [scopeType, setScopeType] = useState<PricingModifierScopeType>(modifier?.scope_type ?? "all_items");
  const [itemIds, setItemIds] = useState<string[]>(modifier?.scope_item_ids ?? []);
  const [itemKinds, setItemKinds] = useState<PricingItemKind[]>(modifier?.scope_item_kinds ?? []);
  const [conditions, setConditions] = useState(() => conditionRowsOf(modifier?.conditions ?? []));
  const [active, setActive] = useState(modifier?.active ?? true);
  const [submitting, setSubmitting] = useState(false);
  /** 记录 mousedown 是否发生在遮罩上：避免从面板内拖选文本、在遮罩上松手时误关闭抽屉 */
  const overlayMouseDown = useRef(false);
  const [pricingFields, setPricingFields] = useState<string[]>([]);
  const [derivedFields, setDerivedFields] = useState<string[]>([]);
  const kinds = Array.from(new Set(rule.items.map((item) => item.kind)));
  const fields = Array.from(new Set([...pricingFields, ...derivedFields, ...PLATFORM_PRICING_FIELDS, "prompt_tokens", "cached_tokens", "completion_tokens"]));

  useEffect(() => {
    get<{ pricing_fields?: string[]; input_contract?: Record<string, unknown> }>("/admin/models/detail", { params: { model_id: rule.model_id } })
      .then((detail) => {
        setPricingFields(detail.pricing_fields ?? pricingFieldCandidates(detail.input_contract));
        setDerivedFields(derivedPricingFieldTypes(detail.input_contract));
      })
      .catch((err) => toast.error(err instanceof Error ? err.message : t("modelDimensionsFailed")));
  }, [rule.model_id, t]);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!name.trim() || !Number.isInteger(Number(priority)) || !/^\d+(\.\d+)?$/.test(amount)) { toast.warning(t("errModifierForm")); return; }
    const effectiveScope = effectType === "fixed_price" ? "item_ids" : scopeType;
    if (effectiveScope === "item_ids" && (itemIds.length === 0 || (effectType === "fixed_price" && itemIds.length !== 1))) { toast.warning(effectType === "fixed_price" ? t("errFixedPriceOne") : t("errSelectItem")); return; }
    if (effectiveScope === "item_kind" && itemKinds.length === 0) { toast.warning(t("errSelectKind")); return; }
    const parsed = parseConditions(conditions, t); if (parsed === null) return;
    setSubmitting(true);
    try {
      await post(isEdit ? "/admin/pricing-modifiers/update" : "/admin/pricing-modifiers/create", {
        ...(isEdit ? { pricing_modifier_id: modifier.id } : { pricing_rule_id: rule.id }),
        name: name.trim(), priority: Number(priority), conditions: parsed, effect_type: effectType,
        effect_payload: effectType === "multiplier" ? { factor: amount } : { amount }, scope_type: effectiveScope,
        scope_item_ids: effectiveScope === "item_ids" ? itemIds : [], scope_item_kinds: effectiveScope === "item_kind" ? itemKinds : [], active,
      });
      toast.success(isEdit ? t("modifierUpdateSuccess") : t("modifierCreateSuccess")); onSaved();
    } catch (err) { toast.error(err instanceof Error ? err.message : t("saveFailed")); } finally { setSubmitting(false); }
  };

  const toggle = <T extends string,>(values: T[], value: T, setValues: (next: T[]) => void, single = false) => setValues(single ? [value] : values.includes(value) ? values.filter((item) => item !== value) : [...values, value]);
  return <div className="fixed inset-0 z-[90] flex justify-end bg-black/50" onMouseDown={(e) => { overlayMouseDown.current = e.target === e.currentTarget; }} onClick={(e) => { if (overlayMouseDown.current && e.target === e.currentTarget) onClose(); }}><div className="flex h-full w-full max-w-lg flex-col border-l bg-background shadow-2xl" onClick={(e) => e.stopPropagation()}><div className="flex items-center justify-between border-b px-6 py-4"><h2 className="text-base font-semibold">{isEdit ? t("modifierEditTitle") : t("modifierCreateTitle")}</h2><button type="button" onClick={onClose}><X className="size-4" /></button></div><form onSubmit={submit} className="flex min-h-0 flex-1 flex-col"><div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-6"><Input value={name} onChange={(e) => setName(e.target.value)} placeholder={t("modifierNamePlaceholder")} autoComplete="off" /><Input type="number" step={1} value={priority} onChange={(e) => setPriority(e.target.value)} placeholder={t("priority")} /><div className="grid grid-cols-2 gap-3"><Select value={effectType} onValueChange={(value) => { const next = value as PricingModifierEffectType; setEffectType(next); if (next === "fixed_price") setScopeType("item_ids"); }} options={[{ value: "multiplier", label: t("effectTypeMultiplier") }, { value: "fixed_price", label: t("effectTypeFixed") }]} /><Input inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} placeholder={effectType === "multiplier" ? t("amountEgMultiplier") : t("amountEgFixed")} /></div><div className="space-y-2"><p className="text-sm font-medium">{t("scopeLabel")}</p><Select value={effectType === "fixed_price" ? "item_ids" : scopeType} onValueChange={(value) => setScopeType(value as PricingModifierScopeType)} disabled={effectType === "fixed_price"} options={[{ value: "all_items", label: t("scope.all_items") }, { value: "item_kind", label: t("scope.item_kind") }, { value: "item_ids", label: t("scope.item_ids") }]} />{(effectType === "fixed_price" || scopeType === "item_ids") && <div className="space-y-1">{rule.items.map((item) => <label key={item.id} className="flex items-center gap-2 text-sm"><input type="checkbox" checked={itemIds.includes(item.id)} onChange={() => toggle(itemIds, item.id, setItemIds, effectType === "fixed_price")} />{item.label}（{itemKindLabel(t, item.kind)}）</label>)}</div>}{scopeType === "item_kind" && <div className="space-y-1">{kinds.map((kind) => <label key={kind} className="flex items-center gap-2 text-sm"><input type="checkbox" checked={itemKinds.includes(kind)} onChange={() => toggle(itemKinds, kind, setItemKinds)} />{itemKindLabel(t, kind)}</label>)}</div>}</div><div className="space-y-2"><p className="text-sm font-medium">{t("conditionsLabel")}</p><ConditionsEditor rows={conditions} onChange={setConditions} fieldOptions={fields} /></div><div className="flex items-center justify-between rounded-lg border p-3"><span className="text-sm">{t("itemActive")}</span><Switch checked={active} onCheckedChange={setActive} /></div></div><div className="flex justify-end gap-2 border-t px-6 py-3"><Button type="button" variant="outline" onClick={onClose}>{t("cancel")}</Button><Button type="submit" disabled={submitting}>{submitting && <Loading size="sm" />}{isEdit ? t("save") : t("create")}</Button></div></form></div></div>;
}
