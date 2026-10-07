import { get } from "@/lib/request";
import type {
  TemplateMaterialField,
  TemplateParameters,
} from "@/lib/types";

/* ---------------- 目录 ---------------- */

export interface ApiDocsAuth {
  type: string;
  header: string;
  format: string;
}

/** 目录接口的接口节点（叶子）：多形态接口按形态平铺 */
export interface ApiDocsEndpointNode {
  /** 接口稳定标识；null 表示该端点尚未登记说明 */
  operation_id: string | null;
  name: string;
  method: string;
  path: string;
  /** 非空表示该节点是"接口 × 调用形态"的形态叶子 */
  template_id: string | null;
}

export interface ApiDocsItem {
  slug: string;
  name: string;
  summary: string;
  tags: string[];
  endpoints: ApiDocsEndpointNode[];
}

export interface ApiDocsFamily {
  family_id: string | null;
  family_name: string | null;
  provider_logo_url: string | null;
  items: ApiDocsItem[];
}

export interface ApiDocsCapability {
  model_type: string;
  name: string;
  families: ApiDocsFamily[];
}

export interface ApiDocsListResponse {
  auth: ApiDocsAuth;
  capabilities: ApiDocsCapability[];
}

/* ---------------- 详情 ---------------- */

export interface ApiDocsParam {
  name: string;
  description: string;
}

export interface ApiDocsResponseItem {
  status: number;
  content_type: string;
  description: string;
}

/** 请求体契约（逐调用形态） */
export interface ApiDocsForm {
  template_id: string;
  title: string;
  summary: string;
  parameters: TemplateParameters;
  material_fields: Record<string, TemplateMaterialField>;
  example: Record<string, unknown>;
  notes: string[];
}

export interface ApiDocsEndpoint {
  operation_id: string | null;
  name: string;
  summary?: string;
  protocol_id?: string | null;
  method: string;
  path: string;
  content_type: string;
  /** request：由请求体 stream 决定；always：接口自身始终流式；null：不涉及 */
  stream: "request" | "always" | null;
  path_params: ApiDocsParam[];
  query_params: ApiDocsParam[];
  responses: ApiDocsResponseItem[];
  notes: string[];
  forms: ApiDocsForm[];
}

export interface ApiDocsErrorEntry {
  status: number;
  code: string | null;
  message: string;
  scene: string;
}

export interface ApiDocsErrorShape {
  shape: string;
  protocol_ids: string[];
  body: unknown;
  entries: ApiDocsErrorEntry[];
}

export interface ApiDocsStatusRef {
  statuses: { status: string; description: string }[];
  note: string;
}

export interface ApiDocsDetail {
  slug: string;
  name: string;
  model_type: string;
  capability_name: string;
  summary: string;
  tags: string[];
  family: {
    family_id: string | null;
    family_name: string | null;
    provider_logo_url: string | null;
  };
  auth: ApiDocsAuth;
  endpoints: ApiDocsEndpoint[];
  error_reference: ApiDocsErrorShape[];
  status_reference: ApiDocsStatusRef | null;
}

/* ---------------- 请求 ---------------- */

export async function getApiDocsList(
  modelType?: string
): Promise<ApiDocsListResponse> {
  return get<ApiDocsListResponse>("/api-docs/list", {
    params: { model_type: modelType },
  });
}

export async function getApiDocsDetail(slug: string): Promise<ApiDocsDetail> {
  return get<ApiDocsDetail>("/api-docs/detail", { params: { slug } });
}
