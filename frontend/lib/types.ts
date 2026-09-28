/** 模型类别：视频 / 图像 / 文本 */
export type ModelCategory = "video" | "image" | "text";

/* ---------------- 模型广场 API ---------------- */

/** 计费规则的匹配条件 */
export interface MarketplacePricingCondition {
  field: string;
  value: unknown;
  operator: string;
}

/** 计费项 */
export interface MarketplacePricingItem {
  kind: string;
  label: string;
  unit_amount: string | null;
  source_fields: string[];
  free_quantity: number;
}

/** 模型广场计费规则 */
export interface MarketplacePricingRule {
  name: string;
  priority: number;
  conditions: MarketplacePricingCondition[];
  currency: string;
  items: MarketplacePricingItem[];
}

/** 模型广场价格信息 */
export interface MarketplacePricing {
  type: "rules" | "usage_based";
  message: string | null;
  rules?: MarketplacePricingRule[];
}

/** 模型广场公开分组 */
export interface MarketplaceGroup {
  group_id: number;
  name: string;
  pricing: MarketplacePricing;
}

/** 模型模板参数属性（JSON Schema 子集） */
export interface TemplateParameterProperty {
  type: string;
  minLength?: number;
  maxLength?: number;
  minimum?: number;
  maximum?: number;
  minItems?: number;
  maxItems?: number;
  items?: { type: string };
  enum?: Array<string | number>;
  default?: unknown;
}

/** 模型模板参数结构 */
export interface TemplateParameters {
  type: string;
  required: string[];
  properties: Record<string, TemplateParameterProperty>;
}

/** 素材字段声明：键为契约字段名，声明该字段接受素材上传 */
export interface TemplateMaterialField {
  /** 允许的素材类别：image / video / audio */
  categories: string[];
  /** 是否为多值字段（数组），false 时仅接受单个素材 */
  multiple: boolean;
}

/** 模型模板（仅详情接口返回） */
export interface ModelTemplate {
  template_id: string;
  label: string;
  summary: string;
  tags: string[];
  parameters: TemplateParameters;
  /** 素材上传字段声明；空对象表示该模板不接受文件上传 */
  material_fields?: Record<string, TemplateMaterialField>;
  example: Record<string, unknown>;
}

/** 模型广场模型；列表返回基础字段，详情额外返回 template 与 groups */
export interface MarketplaceModel {
  model_id: string;
  name: string;
  display_name: string;
  type: string;
  /** 模型介绍：模型未填写时回退模板简介；两者都没有时为 null */
  description: string | null;
  tags: string[];
  /** 供应商标识（如 minimax、openai），null 表示无明确供应商 */
  provider_id?: string | null;
  /** 供应商展示名（如 MiniMax、OpenAI），null 表示无明确供应商 */
  provider_name?: string | null;
  /** 供应商图标地址（相对路径，可直接作为 img src）；null 表示不渲染图标 */
  provider_logo_url?: string | null;
  template?: ModelTemplate | null;
  groups?: MarketplaceGroup[];
}

/** 模型广场列表响应 */
export interface MarketplaceListResponse {
  items: MarketplaceModel[];
  total: number;
  page: number;
  page_size: number;
}

/** 模型广场展示模型 */
export interface ModelInfo {
  id: string;
  name: string;
  provider: string;
  /** 供应商标识，用于筛选比较；null 表示无明确供应商 */
  providerId: string | null;
  /** 供应商展示名，用于标签文案；null 表示无明确供应商 */
  providerName: string | null;
  /** 供应商图标地址；null 表示不渲染图标 */
  providerLogoUrl: string | null;
  category: ModelCategory;
  description: string;
  inputPrice: number;
  outputPrice: number;
  unit?: string;
  cover?: string;
  tags: string[];
  /** 详情接口返回的完整数据 */
  _marketplace?: MarketplaceModel;
}
