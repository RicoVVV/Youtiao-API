"use client";

import { ChevronRight, Lock, Plus, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Input } from "@/components/ui/input";
import { JsonEditor } from "@/components/ui/json-editor";
import { Select } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { toast } from "@/components/ui/toaster";
import { cn } from "@/lib/utils";

/** 输入 Schema 字段行：编辑态（约束以字符串暂存，提交时按类型解析） */
export type SchemaFieldRow = {
  name: string;
  type: "string" | "integer" | "number" | "boolean" | "array";
  required: boolean;
  /** 枚举值，逗号分隔；integer/number 提交时解析为数字 */
  enumText: string;
  minLength: string;
  maxLength: string;
  /** 数值范围，仅 integer/number 有效；留空表示不约束（交由上游校验） */
  minimum: string;
  maximum: string;
  /** 数组数量，仅 array 有效；留空表示不限制数组长度 */
  minItems: string;
  maxItems: string;
  /** 类型由模板提供，锁定后仅可通过重新应用模板变更 */
  typeLocked?: boolean;
  /** 编辑器未覆盖的 schema 键（如 array 的 items），组装时原样保留 */
  extraProps?: Record<string, unknown>;
  /** 仅 UI 状态：可选约束区是否展开，不参与契约组装 */
  showConstraints?: boolean;
};

/** 字段投影行：公开字段 → 内部字段，可选枚举值转换 */
export type ProjectionRow = {
  /** 内部字段名（projection 的键） */
  target: string;
  /** 公开字段名 */
  source: string;
  /** 枚举转换，格式 "公开值=内部值"，逗号分隔 */
  valuesText: string;
};

export type ContractFormState = {
  mode: "form" | "json";
  schemaRows: SchemaFieldRow[];
  projectionRows: ProjectionRow[];
  jsonText: string;
};

const emptySchemaRow = (): SchemaFieldRow => ({
  name: "",
  type: "string",
  required: false,
  enumText: "",
  minLength: "",
  maxLength: "",
  minimum: "",
  maximum: "",
  minItems: "",
  maxItems: "",
  showConstraints: false,
});

/** 该行是否存在任一可选约束，用于编辑还原时决定是否展开约束区 */
function hasAnyConstraint(row: SchemaFieldRow): boolean {
  return Boolean(
    row.enumText.trim() ||
      row.minLength.trim() ||
      row.maxLength.trim() ||
      row.minimum.trim() ||
      row.maximum.trim() ||
      row.minItems.trim() ||
      row.maxItems.trim()
  );
}

const emptyProjectionRow = (): ProjectionRow => ({
  target: "",
  source: "",
  valuesText: "",
});

/** 空契约编辑态 */
export function emptyContractState(): ContractFormState {
  return { mode: "form", schemaRows: [], projectionRows: [], jsonText: "" };
}

/** 常用公开字段的语义标签与枚举示例 i18n 键（按字段名推断），仅覆盖模型/视频类公开字段 */
const FIELD_SEMANTIC_KEYS: Record<string, { label: string; enumHint?: string }> = {
  model: { label: "semModel" },
  prompt: { label: "semPrompt" },
  seconds: { label: "semSeconds", enumHint: "semEnumSeconds" },
  duration: { label: "semSeconds", enumHint: "semEnumSeconds" },
  size: { label: "semSize", enumHint: "semEnumSize" },
  aspect_ratio: { label: "semAspectRatio", enumHint: "semEnumAspectRatio" },
  workflow_id: { label: "semWorkflow", enumHint: "semEnumWorkflow" },
  workflow: { label: "semWorkflow", enumHint: "semEnumWorkflow" },
  images: { label: "semImages" },
  reference_video: { label: "semReferenceVideo" },
  reference_audio: { label: "semReferenceAudio" },
  seed: { label: "semSeed" },
  n: { label: "semN" },
  quality: { label: "semQuality" },
};

type TFunc = (key: string, options?: Record<string, unknown>) => string;

/** 字段语义：标签与枚举示例占位符（经 i18n） */
function fieldSemantics(t: TFunc, name: string): { label: string; enumHint?: string } {
  const keys = FIELD_SEMANTIC_KEYS[name];
  if (!keys) return { label: "" };
  return {
    label: t(`models.contract.${keys.label}`),
    ...(keys.enumHint ? { enumHint: t(`models.contract.${keys.enumHint}`) } : {}),
  };
}

/** 枚举占位符：优先字段语义，其次按类型 */
function enumPlaceholder(t: TFunc, name: string, type: SchemaFieldRow["type"]): string {
  const sem = fieldSemantics(t, name).enumHint;
  if (sem) return sem;
  return type === "string"
    ? t("models.contract.enumPlaceholderString")
    : t("models.contract.enumPlaceholderNumber");
}

/** 按 "a=b, c=d" 文本解析枚举转换表，值保持字符串 */
function parseValuePairs(text: string): Record<string, string> | null {
  const trimmed = text.trim();
  if (!trimmed) return {};
  const values: Record<string, string> = {};
  for (const pair of trimmed.split(/[,，]/)) {
    const idx = pair.indexOf("=");
    if (idx <= 0) return null;
    const k = pair.slice(0, idx).trim();
    const v = pair.slice(idx + 1).trim();
    if (!k || !v) return null;
    values[k] = v;
  }
  return values;
}

/** 枚举文本按字段类型解析为数组 */
function parseEnumValues(
  text: string,
  type: SchemaFieldRow["type"]
): unknown[] | null {
  const trimmed = text.trim();
  if (!trimmed) return [];
  const parts = trimmed.split(/[,，]/).map((s) => s.trim()).filter(Boolean);
  if (type === "integer" || type === "number") {
    const nums = parts.map(Number);
    if (nums.some((n) => !Number.isFinite(n))) return null;
    return nums;
  }
  if (type === "boolean") return null;
  return parts;
}

/** 表单可编辑的基础类型；模板返回的其他类型回退到 JSON 模式编辑，避免静默改型 */
const KNOWN_TYPES = ["string", "integer", "number", "boolean", "array"];

/** 表单直接编辑的 schema 键，其余键（如 items）原样保留在 extraProps */
const KNOWN_PROP_KEYS = new Set([
  "type",
  "enum",
  "minLength",
  "maxLength",
  "minimum",
  "maximum",
  "minItems",
  "maxItems",
]);

/** 从已有契约对象还原为表单编辑态；结构不符时回退到 JSON 模式 */
export function stateFromContract(
  contract: Record<string, unknown>,
  opts?: { lockTypes?: boolean }
): ContractFormState {
  const jsonText = JSON.stringify(contract, null, 2);
  try {
    const schema = contract.input_schema as Record<string, unknown>;
    const projection = contract.projection as Record<string, unknown>;
    if (!schema || !projection) throw new Error();
    const properties = (schema.properties ?? {}) as Record<
      string,
      Record<string, unknown>
    >;
    const requiredList = Array.isArray(schema.required)
      ? (schema.required as string[])
      : [];
    const schemaRows: SchemaFieldRow[] = Object.entries(properties).map(
      ([name, prop]) => {
        const type = String(prop.type);
        if (!KNOWN_TYPES.includes(type)) throw new Error();
        const extraProps = Object.fromEntries(
          Object.entries(prop).filter(([k]) => !KNOWN_PROP_KEYS.has(k))
        );
        const row: SchemaFieldRow = {
          name,
          type: type as SchemaFieldRow["type"],
          required: requiredList.includes(name),
          enumText: Array.isArray(prop.enum) ? prop.enum.join(", ") : "",
          minLength:
            prop.minLength !== undefined ? String(prop.minLength) : "",
          maxLength:
            prop.maxLength !== undefined ? String(prop.maxLength) : "",
          minimum: prop.minimum !== undefined ? String(prop.minimum) : "",
          maximum: prop.maximum !== undefined ? String(prop.maximum) : "",
          minItems: prop.minItems !== undefined ? String(prop.minItems) : "",
          maxItems: prop.maxItems !== undefined ? String(prop.maxItems) : "",
          ...(opts?.lockTypes ? { typeLocked: true } : {}),
          ...(Object.keys(extraProps).length > 0 ? { extraProps } : {}),
          // 可选约束默认折叠；已配置约束的行在折叠摘要中标注
          showConstraints: false,
        };
        return row;
      }
    );
    const projectionRows: ProjectionRow[] = Object.entries(projection).map(
      ([target, raw]) => {
        const p = raw as { source?: string; values?: Record<string, string> };
        return {
          target,
          source: p.source ?? "",
          valuesText: p.values
            ? Object.entries(p.values)
                .map(([k, v]) => `${k}=${v}`)
                .join(", ")
            : "",
        };
      }
    );
    return { mode: "form", schemaRows, projectionRows, jsonText };
  } catch {
    return { mode: "json", schemaRows: [], projectionRows: [], jsonText };
  }
}

/** 模板 input_schema → 表单编辑态：投影留空按需配置，字段类型锁定 */
export function stateFromTemplate(
  inputSchema: Record<string, unknown>
): ContractFormState {
  return stateFromContract(
    { input_schema: inputSchema, projection: {} },
    { lockTypes: true }
  );
}

/** 投影枚举转换示例：按公开字段语义给出（经 i18n） */
function projectionValuesPlaceholder(t: TFunc, source: string): string {
  const key: Record<string, string> = {
    size: "models.contract.projSize",
    workflow: "models.contract.projWorkflow",
    workflow_id: "models.contract.projWorkflow",
    seconds: "models.contract.projSeconds",
    aspect_ratio: "models.contract.projAspectRatio",
  };
  return t(key[source] ?? "models.contract.projDefault");
}

/** 校验并组装请求契约，失败时 toast 并返回 null */
export function buildContract(
  state: ContractFormState,
  t: TFunc
): Record<string, unknown> | null {
  if (state.mode === "json") {
    try {
      const v = JSON.parse(state.jsonText || "{}");
      if (!v || typeof v !== "object" || Array.isArray(v)) throw new Error();
      if (!v.input_schema || !v.projection) {
        toast.warning(t("models.contract.errNeedSchemaAndProjection"));
        return null;
      }
      return v as Record<string, unknown>;
    } catch {
      toast.warning(t("models.contract.errInvalidJsonObject"));
      return null;
    }
  }

  const properties: Record<string, Record<string, unknown>> = {};
  const required: string[] = [];
  for (let i = 0; i < state.schemaRows.length; i++) {
    const row = state.schemaRows[i];
    const label = t("models.contract.fieldRowLabel", { index: i + 1 });
    const name = row.name.trim();
    if (!name) {
      toast.warning(t("models.contract.errFieldNameRequired", { label }));
      return null;
    }
    if (properties[name]) {
      toast.warning(t("models.contract.errFieldNameDup", { label, name }));
      return null;
    }
    const prop: Record<string, unknown> = {
      ...(row.extraProps ?? {}),
      type: row.type,
    };
    // 枚举仅适用于字符串与数值字段；数组的元素约束通过 items 保留
    if (row.type !== "array" && row.type !== "boolean") {
      const enumValues = parseEnumValues(row.enumText, row.type);
      if (enumValues === null) {
        toast.warning(t("models.contract.errEnumTypeMismatch", { label }));
        return null;
      }
      if (enumValues.length > 0) prop.enum = enumValues;
    }
    if (row.type === "string") {
      if (row.minLength.trim()) {
        const n = Number(row.minLength);
        if (!Number.isInteger(n) || n < 0) {
          toast.warning(t("models.contract.errMinLength", { label }));
          return null;
        }
        prop.minLength = n;
      }
      if (row.maxLength.trim()) {
        const n = Number(row.maxLength);
        if (!Number.isInteger(n) || n < 1) {
          toast.warning(t("models.contract.errMaxLength", { label }));
          return null;
        }
        prop.maxLength = n;
      }
    }
    // 数值范围为可选约束：未填写时不写入 input_schema，取值交由上游校验
    if (row.type === "integer" || row.type === "number") {
      const isInt = row.type === "integer";
      if (row.minimum.trim()) {
        const n = Number(row.minimum);
        if (!Number.isFinite(n) || (isInt && !Number.isInteger(n))) {
          toast.warning(
            t(isInt ? "models.contract.errMinimumInt" : "models.contract.errMinimumNum", { label })
          );
          return null;
        }
        prop.minimum = n;
      }
      if (row.maximum.trim()) {
        const n = Number(row.maximum);
        if (!Number.isFinite(n) || (isInt && !Number.isInteger(n))) {
          toast.warning(
            t(isInt ? "models.contract.errMaximumInt" : "models.contract.errMaximumNum", { label })
          );
          return null;
        }
        prop.maximum = n;
      }
      if (
        prop.minimum !== undefined &&
        prop.maximum !== undefined &&
        (prop.maximum as number) < (prop.minimum as number)
      ) {
        toast.warning(t("models.contract.errMaxLessThanMin", { label }));
        return null;
      }
    }
    // 数组数量为可选约束：未填写时不写入 input_schema
    if (row.type === "array") {
      if (row.minItems.trim()) {
        const n = Number(row.minItems);
        if (!Number.isInteger(n) || n < 0) {
          toast.warning(t("models.contract.errMinItems", { label }));
          return null;
        }
        prop.minItems = n;
      }
      if (row.maxItems.trim()) {
        const n = Number(row.maxItems);
        if (!Number.isInteger(n) || n < 0) {
          toast.warning(t("models.contract.errMaxItems", { label }));
          return null;
        }
        prop.maxItems = n;
      }
      if (
        prop.minItems !== undefined &&
        prop.maxItems !== undefined &&
        (prop.maxItems as number) < (prop.minItems as number)
      ) {
        toast.warning(t("models.contract.errMaxItemsLessThanMin", { label }));
        return null;
      }
    }
    properties[name] = prop;
    if (row.required) required.push(name);
  }
  if (Object.keys(properties).length === 0) {
    toast.warning(t("models.contract.errNoFields"));
    return null;
  }

  const projection: Record<string, Record<string, unknown>> = {};
  for (let i = 0; i < state.projectionRows.length; i++) {
    const row = state.projectionRows[i];
    const label = t("models.contract.projectionRowLabel", { index: i + 1 });
    const target = row.target.trim();
    const source = row.source.trim();
    if (!target || !source) {
      toast.warning(t("models.contract.errProjectionFieldsRequired", { label }));
      return null;
    }
    if (!properties[source]) {
      toast.warning(t("models.contract.errProjectionSourceUndefined", { label, source }));
      return null;
    }
    if (projection[target]) {
      toast.warning(t("models.contract.errProjectionTargetDup", { label, target }));
      return null;
    }
    const values = parseValuePairs(row.valuesText);
    if (values === null) {
      toast.warning(t("models.contract.errProjectionValuesFormat", { label }));
      return null;
    }
    projection[target] = {
      source,
      ...(Object.keys(values).length > 0 ? { values } : {}),
    };
  }
  // 投影按需配置：无投影行时提交空的 projection 对象，公开字段默认原样透传

  return {
    input_schema: {
      type: "object",
      ...(required.length > 0 ? { required } : {}),
      properties,
    },
    projection,
  };
}

/** 请求契约编辑器：表单模式与高级 JSON 模式互切换 */
export function InputContractEditor({
  value,
  onChange,
}: {
  value: ContractFormState;
  onChange: (patch: Partial<ContractFormState>) => void;
}) {
  const { t } = useTranslation("console");
  /** 表单 → JSON：先组装校验，成功后带出文本 */
  const switchToJson = () => {
    const contract = buildContract({ ...value, mode: "form" }, t);
    if (contract === null) return;
    onChange({ mode: "json", jsonText: JSON.stringify(contract, null, 2) });
  };

  /** JSON → 表单：解析失败时停留在 JSON 模式 */
  const switchToForm = () => {
    try {
      const v = JSON.parse(value.jsonText || "{}");
      if (!v || typeof v !== "object" || Array.isArray(v)) throw new Error();
      onChange(stateFromContract(v as Record<string, unknown>));
    } catch {
      toast.warning(t("models.contract.errJsonParseStay"));
    }
  };

  const updateSchemaRow = (i: number, patch: Partial<SchemaFieldRow>) =>
    onChange({
      schemaRows: value.schemaRows.map((r, idx) =>
        idx === i ? { ...r, ...patch } : r
      ),
    });

  const updateProjectionRow = (i: number, patch: Partial<ProjectionRow>) =>
    onChange({
      projectionRows: value.projectionRows.map((r, idx) =>
        idx === i ? { ...r, ...patch } : r
      ),
    });

  return (
    <div className="space-y-4">
      {/* 模式切换 */}
      <div className="inline-flex rounded-lg border border-border/60 bg-muted/30 p-0.5">
        {(
          [
            { key: "form", label: t("models.contract.modeForm") },
            { key: "json", label: t("models.contract.modeJson") },
          ] as const
        ).map((m) => (
          <button
            key={m.key}
            type="button"
            onClick={() =>
              m.key === value.mode
                ? undefined
                : m.key === "json"
                  ? switchToJson()
                  : switchToForm()
            }
            aria-pressed={value.mode === m.key}
            className={cn(
              "cursor-pointer rounded-md px-3 py-1 text-xs transition-all duration-200",
              value.mode === m.key
                ? "bg-background font-medium text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground"
            )}
          >
            {m.label}
          </button>
        ))}
      </div>

      {value.mode === "json" ? (
        <JsonEditor
          aria-label={t("models.contract.jsonAriaLabel")}
          value={value.jsonText}
          onChange={(v) => onChange({ jsonText: v })}
          placeholder='{"input_schema": {...}, "projection": {...}}'
          rows={14}
        />
      ) : (
        <>
          {/* 输入字段（input_schema） */}
          <div className="space-y-3">
            <p className="text-xs font-medium text-muted-foreground">
              {t("models.contract.schemaHint")}
            </p>
            {value.schemaRows.map((row, i) => (
              <div
                key={i}
                className="space-y-2.5 rounded-lg border border-border/60 bg-muted/10 p-3"
              >
                <div className="flex items-center gap-2">
                  <Input
                    aria-label={t("models.contract.fieldNameAria", { index: i + 1 })}
                    value={row.name}
                    onChange={(e) =>
                      updateSchemaRow(i, { name: e.target.value })
                    }
                    placeholder={t("models.contract.fieldNamePlaceholder")}
                    autoComplete="off"
                    className="flex-1"
                  />
                  {fieldSemantics(t, row.name).label && (
                    <span className="shrink-0 text-xs text-muted-foreground">
                      {fieldSemantics(t, row.name).label}
                    </span>
                  )}
                  <div className="w-28">
                    <Select
                      aria-label={t("models.contract.fieldTypeAria", { index: i + 1 })}
                      value={row.type}
                      disabled={row.typeLocked}
                      onValueChange={(v) =>
                        updateSchemaRow(i, {
                          type: v as SchemaFieldRow["type"],
                        })
                      }
                      options={[
                        { value: "string", label: t("models.contract.typeString") },
                        { value: "integer", label: t("models.contract.typeInteger") },
                        { value: "number", label: t("models.contract.typeNumber") },
                        { value: "boolean", label: t("models.contract.typeBoolean") },
                        { value: "array", label: t("models.contract.typeArray") },
                      ]}
                    />
                  </div>
                  {row.typeLocked && (
                    <span
                      className="shrink-0 text-muted-foreground/70"
                      title={t("models.contract.typeLockedHint")}
                    >
                      <Lock className="size-3.5" />
                    </span>
                  )}
                  <label className="flex shrink-0 items-center gap-1.5 text-xs font-medium">
                    {t("models.contract.required")}
                    <Switch
                      checked={row.required}
                      onCheckedChange={(v) =>
                        updateSchemaRow(i, { required: v })
                      }
                    />
                  </label>
                  <button
                    type="button"
                    onClick={() =>
                      onChange({
                        schemaRows: value.schemaRows.filter(
                          (_, idx) => idx !== i
                        ),
                      })
                    }
                    aria-label={t("models.contract.deleteFieldAria", { index: i + 1 })}
                    className="shrink-0 rounded-md p-1 text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive"
                  >
                    <Trash2 className="size-3.5" />
                  </button>
                </div>
                {/* 可选约束：默认折叠，展开后按需配置；未填写的约束不写入契约 */}
                {row.type !== "boolean" && (
                  <div className="space-y-2">
                    <button
                      type="button"
                      onClick={() =>
                        updateSchemaRow(i, {
                          showConstraints: !row.showConstraints,
                        })
                      }
                      aria-expanded={row.showConstraints ?? false}
                      className="flex w-full cursor-pointer items-center gap-1 text-xs text-muted-foreground transition-colors hover:text-foreground"
                    >
                      <ChevronRight
                        className={cn(
                          "size-3.5 transition-transform duration-200",
                          row.showConstraints && "rotate-90"
                        )}
                      />
                      {t("models.contract.optionalConstraints")}
                      {!row.showConstraints && hasAnyConstraint(row) && (
                        <span className="text-muted-foreground/70">
                          {t("models.contract.constraintsConfigured")}
                        </span>
                      )}
                      {!row.showConstraints && !hasAnyConstraint(row) && (
                        <span className="text-muted-foreground/60">
                          {t("models.contract.constraintsEmpty")}
                        </span>
                      )}
                    </button>
                    {row.showConstraints && (
                      <div className="grid grid-cols-3 gap-2">
                        {row.type !== "array" && (
                          <Input
                            aria-label={t("models.contract.enumAria", { index: i + 1 })}
                            value={row.enumText}
                            onChange={(e) =>
                              updateSchemaRow(i, { enumText: e.target.value })
                            }
                            placeholder={enumPlaceholder(t, row.name, row.type)}
                            autoComplete="off"
                            className="col-span-1"
                          />
                        )}
                        {row.type === "string" && (
                          <>
                            <Input
                              aria-label={t("models.contract.minLengthAria", { index: i + 1 })}
                              type="number"
                              min={0}
                              step={1}
                              value={row.minLength}
                              onChange={(e) =>
                                updateSchemaRow(i, {
                                  minLength: e.target.value,
                                })
                              }
                              placeholder={t("models.contract.minLengthPlaceholder")}
                            />
                            <Input
                              aria-label={t("models.contract.maxLengthAria", { index: i + 1 })}
                              type="number"
                              min={1}
                              step={1}
                              value={row.maxLength}
                              onChange={(e) =>
                                updateSchemaRow(i, {
                                  maxLength: e.target.value,
                                })
                              }
                              placeholder={t("models.contract.maxLengthPlaceholder")}
                            />
                          </>
                        )}
                        {(row.type === "integer" || row.type === "number") && (
                          <>
                            <Input
                              aria-label={t("models.contract.minimumAria", { index: i + 1 })}
                              type="number"
                              step={row.type === "integer" ? 1 : "any"}
                              value={row.minimum}
                              onChange={(e) =>
                                updateSchemaRow(i, {
                                  minimum: e.target.value,
                                })
                              }
                              placeholder={t("models.contract.minimumPlaceholder")}
                            />
                            <Input
                              aria-label={t("models.contract.maximumAria", { index: i + 1 })}
                              type="number"
                              step={row.type === "integer" ? 1 : "any"}
                              value={row.maximum}
                              onChange={(e) =>
                                updateSchemaRow(i, {
                                  maximum: e.target.value,
                                })
                              }
                              placeholder={t("models.contract.maximumPlaceholder")}
                            />
                          </>
                        )}
                        {row.type === "array" && (
                          <>
                            <Input
                              aria-label={t("models.contract.minItemsAria", { index: i + 1 })}
                              type="number"
                              min={0}
                              step={1}
                              value={row.minItems}
                              onChange={(e) =>
                                updateSchemaRow(i, {
                                  minItems: e.target.value,
                                })
                              }
                              placeholder={t("models.contract.minItemsPlaceholder")}
                            />
                            <Input
                              aria-label={t("models.contract.maxItemsAria", { index: i + 1 })}
                              type="number"
                              min={0}
                              step={1}
                              value={row.maxItems}
                              onChange={(e) =>
                                updateSchemaRow(i, {
                                  maxItems: e.target.value,
                                })
                              }
                              placeholder={t("models.contract.maxItemsPlaceholder")}
                            />
                          </>
                        )}
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))}
            <button
              type="button"
              onClick={() =>
                onChange({
                  schemaRows: [...value.schemaRows, emptySchemaRow()],
                })
              }
              className="flex w-full cursor-pointer items-center justify-center gap-1.5 rounded-lg border border-dashed border-border/70 py-2 text-xs text-muted-foreground transition-colors hover:border-primary/40 hover:bg-primary/5 hover:text-primary"
            >
              <Plus className="size-3.5" />
              {t("models.contract.addField")}
            </button>
          </div>

          {/* 字段投影（projection） */}
          <div className="space-y-3">
            <p className="text-xs font-medium text-muted-foreground">
              {t("models.contract.projectionHint")}
            </p>
            {value.projectionRows.map((row, i) => (
              <div
                key={i}
                className="flex items-center gap-2 rounded-lg border border-border/60 bg-muted/10 p-3"
              >
                <Input
                  aria-label={t("models.contract.projectionSourceAria", { index: i + 1 })}
                  value={row.source}
                  onChange={(e) =>
                    updateProjectionRow(i, { source: e.target.value })
                  }
                  placeholder={t("models.contract.projectionSourcePlaceholder")}
                  autoComplete="off"
                  className="w-32 shrink-0"
                />
                <span className="shrink-0 text-muted-foreground">→</span>
                <Input
                  aria-label={t("models.contract.projectionTargetAria", { index: i + 1 })}
                  value={row.target}
                  onChange={(e) =>
                    updateProjectionRow(i, { target: e.target.value })
                  }
                  placeholder={t("models.contract.projectionTargetPlaceholder")}
                  autoComplete="off"
                  className="w-40 shrink-0"
                />
                <Input
                  aria-label={t("models.contract.projectionValuesAria", { index: i + 1 })}
                  value={row.valuesText}
                  onChange={(e) =>
                    updateProjectionRow(i, { valuesText: e.target.value })
                  }
                  placeholder={projectionValuesPlaceholder(t, row.source.trim())}
                  autoComplete="off"
                  className="flex-1"
                />
                <button
                  type="button"
                  onClick={() =>
                    onChange({
                      projectionRows: value.projectionRows.filter(
                        (_, idx) => idx !== i
                      ),
                    })
                  }
                  aria-label={t("models.contract.deleteProjectionAria", { index: i + 1 })}
                  className="shrink-0 rounded-md p-1 text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive"
                >
                  <Trash2 className="size-3.5" />
                </button>
              </div>
            ))}
            <button
              type="button"
              onClick={() =>
                onChange({
                  projectionRows: [...value.projectionRows, emptyProjectionRow()],
                })
              }
              className="flex w-full cursor-pointer items-center justify-center gap-1.5 rounded-lg border border-dashed border-border/70 py-2 text-xs text-muted-foreground transition-colors hover:border-primary/40 hover:bg-primary/5 hover:text-primary"
            >
              <Plus className="size-3.5" />
              {t("models.contract.addProjection")}
            </button>
          </div>
        </>
      )}
    </div>
  );
}
