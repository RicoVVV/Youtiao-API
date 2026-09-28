"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { BookOpen, Check, ChevronDown, Copy, FileText, Loader2, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { ProviderLogo } from "@/components/ui/provider-logo";
import {
  getApiDocsDetail,
  getApiDocsList,
  type ApiDocsAuth,
  type ApiDocsDetail,
  type ApiDocsEndpoint,
  type ApiDocsErrorEntry,
  type ApiDocsErrorShape,
  type ApiDocsForm,
  type ApiDocsListResponse,
  type ApiDocsParam,
  type ApiDocsResponseItem,
} from "@/lib/api-docs";
import { cn } from "@/lib/utils";

/** 导航叶子的选中态：定位到 模型 × 接口（× 形态） */
interface Selection {
  slug: string;
  operationId: string | null;
  templateId: string | null;
}

/* ---------------- 工具 ---------------- */

/** 复制文本到剪贴板 */
async function copyToClipboard(text: string): Promise<boolean> {
  if (navigator.clipboard && window.isSecureContext) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      // 继续尝试降级方案
    }
  }
  try {
    const textarea = document.createElement("textarea");
    textarea.value = text;
    textarea.style.position = "fixed";
    textarea.style.opacity = "0";
    document.body.appendChild(textarea);
    textarea.focus();
    textarea.select();
    const ok = document.execCommand("copy");
    document.body.removeChild(textarea);
    return ok;
  } catch {
    return false;
  }
}

const METHOD_STYLES: Record<string, string> = {
  POST: "border-emerald-500/40 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400",
  GET: "border-sky-500/40 bg-sky-500/10 text-sky-600 dark:text-sky-400",
  HEAD: "border-amber-500/40 bg-amber-500/10 text-amber-600 dark:text-amber-400",
  DELETE: "border-red-500/40 bg-red-500/10 text-red-600 dark:text-red-400",
};

function MethodBadge({ method, className }: { method: string; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex w-14 shrink-0 items-center justify-center rounded border px-1 py-0.5 font-mono text-[10px] font-bold tracking-wide",
        METHOD_STYLES[method.toUpperCase()] ??
          "border-muted-foreground/40 bg-muted text-muted-foreground",
        className
      )}
    >
      {method.toUpperCase()}
    </span>
  );
}

/** 路径文本：高亮 {video_id}、{model} 等占位符，不做替换或改写 */
function PathText({ path }: { path: string }) {
  const parts = path.split(/(\{[^}]+\})/g);
  return (
    <code className="break-all font-mono text-sm">
      {parts.map((part, i) =>
        part.startsWith("{") ? (
          <span key={i} className="font-semibold text-amber-600 dark:text-amber-400">
            {part}
          </span>
        ) : (
          part
        )
      )}
    </code>
  );
}

/** 目录中定位第一个接口叶子，作为默认选中 */
function firstSelection(list: ApiDocsListResponse): Selection | null {
  for (const cap of list.capabilities) {
    for (const family of cap.families) {
      for (const item of family.items) {
        const ep = item.endpoints[0];
        if (ep) {
          return { slug: item.slug, operationId: ep.operation_id, templateId: ep.template_id };
        }
      }
    }
  }
  return null;
}

/* ---------------- 左侧目录 ---------------- */

function DocsSidebar({
  list,
  selection,
  onSelect,
}: {
  list: ApiDocsListResponse;
  selection: Selection | null;
  onSelect: (sel: Selection) => void;
}) {
  const { t } = useTranslation("api-docs");
  // 各级折叠状态：默认全部折叠，仅「视频生成」能力与其第一个模型族（含族下模型）默认展开
  const [open, setOpen] = useState<Record<string, boolean>>(() => {
    const initial: Record<string, boolean> = {};
    const video = list.capabilities.find((c) => c.model_type === "video");
    const firstFamily = video?.families[0];
    if (video && firstFamily) {
      initial[`cap:${video.model_type}`] = true;
      initial[`fam:video:${firstFamily.family_id ?? 0}`] = true;
      firstFamily.items.forEach((item) => {
        initial[`mod:${item.slug}`] = true;
      });
    }
    return initial;
  });
  const toggle = (key: string) => setOpen((prev) => ({ ...prev, [key]: !prev[key] }));

  const chevron = (expanded: boolean) => (
    <ChevronDown
      className={cn(
        "size-3.5 shrink-0 text-muted-foreground transition-transform",
        !expanded && "-rotate-90"
      )}
    />
  );

  /** 选中某能力/模型下第一个接口叶子 */
  const selectFirstLeaf = (families: ApiDocsListResponse["capabilities"][number]["families"]) => {
    for (const family of families) {
      for (const item of family.items) {
        const ep = item.endpoints[0];
        if (ep) {
          onSelect({ slug: item.slug, operationId: ep.operation_id, templateId: ep.template_id });
          return;
        }
      }
    }
  };

  return (
    <nav className="space-y-5">
      {list.capabilities.map((cap) => {
        const capKey = `cap:${cap.model_type}`;
        const capOpen = !!open[capKey];
        return (
          <section key={cap.model_type}>
            <button
              type="button"
              onClick={() => {
                toggle(capKey);
                selectFirstLeaf(cap.families);
              }}
              className="mb-2 flex w-full items-center gap-1 px-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground transition-colors hover:text-foreground"
            >
              {chevron(capOpen)}
              {cap.name}
            </button>
            {capOpen && (
              <div className="space-y-3">
                {cap.families.map((family, fi) => {
                  const famKey = `fam:${cap.model_type}:${family.family_id ?? fi}`;
                  const famOpen = !!open[famKey];
                  return (
                    <div key={family.family_id ?? `family-${fi}`}>
                      <button
                        type="button"
                        onClick={() => toggle(famKey)}
                        className="mb-1 flex w-full items-center gap-1.5 px-2 text-left text-sm font-medium transition-colors hover:text-foreground/80"
                      >
                        {chevron(famOpen)}
                        {family.provider_logo_url && (
                          <ProviderLogo
                            src={family.provider_logo_url}
                            providerId={family.family_id}
                            className="size-4"
                          />
                        )}
                        <span className="truncate">
                          {family.family_name ?? family.family_id ?? t("sidebar.unknownFamily")}
                        </span>
                      </button>
                      {famOpen && (
                        <div className="space-y-1 pl-3">
                          {family.items.map((item) => {
                            const modKey = `mod:${item.slug}`;
                            const modOpen = !!open[modKey];
                            return (
                              <div key={item.slug}>
                                <button
                                  type="button"
                                  onClick={() => {
                                    toggle(modKey);
                                    const ep = item.endpoints[0];
                                    if (ep) {
                                      onSelect({
                                        slug: item.slug,
                                        operationId: ep.operation_id,
                                        templateId: ep.template_id,
                                      });
                                    }
                                  }}
                                  className="flex w-full items-center gap-1 px-2 py-1 text-left text-sm font-medium text-foreground/90 transition-colors hover:text-foreground"
                                >
                                  {chevron(modOpen)}
                                  <span className="truncate">{item.name}</span>
                                </button>
                                {modOpen && (
                                  <ul className="space-y-0.5">
                                    {item.endpoints.map((ep, ei) => {
                                      const active =
                                        selection?.slug === item.slug &&
                                        selection.operationId === ep.operation_id &&
                                        selection.templateId === ep.template_id;
                                      return (
                                        <li
                                          key={`${ep.operation_id ?? "unregistered"}-${ep.template_id ?? "self"}-${ei}`}
                                        >
                                          <button
                                            type="button"
                                            onClick={() =>
                                              onSelect({
                                                slug: item.slug,
                                                operationId: ep.operation_id,
                                                templateId: ep.template_id,
                                              })
                                            }
                                            className={cn(
                                              "flex w-full items-center gap-2 rounded-md py-1.5 pl-6 pr-2 text-left text-[13px] transition-colors",
                                              active
                                                ? "bg-primary/10 font-bold text-primary"
                                                : "text-muted-foreground hover:bg-accent hover:text-foreground"
                                            )}
                                          >
                                            <MethodBadge method={ep.method} className="w-12 text-[9px]" />
                                            <span className="min-w-0 flex-1 truncate">{ep.name}</span>
                                          </button>
                                        </li>
                                      );
                                    })}
                                  </ul>
                                )}
                              </div>
                            );
                          })}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </section>
        );
      })}
    </nav>
  );
}

/* ---------------- 详情小块 ---------------- */

function CopyButton({ text }: { text: string }) {
  const { t } = useTranslation("api-docs");
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      onClick={async () => {
        if (await copyToClipboard(text)) {
          setCopied(true);
          setTimeout(() => setCopied(false), 2000);
        }
      }}
      className="flex items-center gap-1.5 rounded-md px-2 py-1 text-xs text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
    >
      {copied ? (
        <>
          <Check className="size-3.5 text-green-500" />
          {t("detail.copied")}
        </>
      ) : (
        <>
          <Copy className="size-3.5" />
          {t("detail.copy")}
        </>
      )}
    </button>
  );
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return <h4 className="text-sm font-semibold">{children}</h4>;
}

/** 路径/查询参数表 */
function ParamsTable({ params }: { params: ApiDocsParam[] }) {
  const { t } = useTranslation("api-docs");
  return (
    <div className="overflow-hidden rounded-lg border">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b bg-muted/50 text-left text-xs text-muted-foreground">
            <th className="px-3 py-2 font-medium">{t("detail.paramName")}</th>
            <th className="px-3 py-2 font-medium">{t("detail.paramDesc")}</th>
          </tr>
        </thead>
        <tbody>
          {params.map((p) => (
            <tr key={p.name} className="border-b last:border-0">
              <td className="px-3 py-2 align-top">
                <code className="font-mono text-xs font-semibold">{p.name}</code>
              </td>
              <td className="px-3 py-2 align-top text-xs text-muted-foreground">
                {p.description}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** 请求体参数结构（JSON Schema 子集，只读） */
function FormParametersView({ form }: { form: ApiDocsForm }) {
  const { t } = useTranslation("api-docs");
  const entries = Object.entries(form.parameters.properties);
  return (
    <div className="space-y-2">
      {entries.map(([key, prop]) => {
        const required = form.parameters.required.includes(key);
        const material = form.material_fields[key];
        return (
          <div
            key={key}
            className="flex flex-col gap-2 rounded-lg border bg-muted/30 px-3 py-2.5 sm:flex-row sm:items-start sm:gap-3"
          >
            <div className="flex shrink-0 items-center gap-2 sm:w-55">
              <code className="break-all text-sm font-semibold text-foreground">{key}</code>
              {required && <span className="text-xs text-red-500">*</span>}
            </div>
            <div className="min-w-0 flex-1 space-y-2 text-xs text-muted-foreground">
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant="outline" className="font-mono">
                  {prop.type}
                </Badge>
                {material && (
                  <Badge variant="secondary" className="text-[11px]">
                    {t("detail.material", {
                      categories: material.categories.join("/"),
                      multiple: material.multiple ? t("detail.materialMultiple") : "",
                    })}
                  </Badge>
                )}
                {prop.type === "string" && prop.minLength && prop.maxLength && (
                  <span>
                    {prop.minLength}–{prop.maxLength} {t("detail.characters")}
                  </span>
                )}
                {prop.type === "string" && prop.minLength && !prop.maxLength && (
                  <span>{t("detail.minLength", { count: prop.minLength })}</span>
                )}
                {(prop.type === "integer" || prop.type === "number") &&
                  prop.minimum !== undefined &&
                  prop.maximum !== undefined && (
                    <span>
                      {prop.minimum}–{prop.maximum}
                    </span>
                  )}
                {prop.type === "array" && prop.maxItems && (
                  <span>{t("detail.maxItems", { count: prop.maxItems })}</span>
                )}
              </div>
              {prop.enum && (
                <div className="flex flex-wrap items-center gap-1.5 rounded-md bg-background/60 px-2 py-1.5">
                  <span className="mr-1 text-xs font-medium text-muted-foreground">
                    {t("detail.optionalValues")}
                  </span>
                  {prop.enum.map((value) => (
                    <Badge
                      key={String(value)}
                      className="border border-primary/30 bg-primary/15 px-1.5 py-0 font-mono text-[11px] font-medium text-foreground"
                    >
                      {String(value)}
                    </Badge>
                  ))}
                </div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

/** 生成 cURL 请求示例：路径为公开协议面业务路径，拼当前站点源 */
function buildCurl(
  endpoint: ApiDocsEndpoint,
  auth: ApiDocsAuth,
  body: Record<string, unknown>
): string {
  const origin = typeof window !== "undefined" ? window.location.origin : "";
  return [
    `curl --request ${endpoint.method} \\`,
    `  --url '${origin}${endpoint.path}' \\`,
    `  --header '${auth.header}: ${auth.format}' \\`,
    `  --header 'Content-Type: ${endpoint.content_type}' \\`,
    `  --data '${JSON.stringify(body, null, 2)}'`,
  ].join("\n");
}

/** 模型头 */
function ModelHeader({ detail }: { detail: ApiDocsDetail }) {
  const { t } = useTranslation("api-docs");
  return (
    <header className="space-y-3 border-b pb-5">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-2xl font-bold tracking-tight">{detail.name}</h2>
        <Badge variant="secondary">{detail.capability_name}</Badge>
        {detail.family.family_name && (
          <Badge variant="outline">
            <ProviderLogo
              src={detail.family.provider_logo_url}
              providerId={detail.family.family_id}
              className="mr-1 size-3.5"
            />
            {detail.family.family_name}
          </Badge>
        )}
      </div>
      {detail.summary && (
        <p className="text-sm text-muted-foreground">{detail.summary}</p>
      )}
      {detail.tags.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {detail.tags.map((tag) => (
            <Badge key={tag} variant="outline">
              {tag}
            </Badge>
          ))}
        </div>
      )}
      {/* 鉴权方式（全站统一，展示一次） */}
      <div className="flex flex-wrap items-center gap-2 rounded-lg border bg-muted/40 px-3 py-2 text-xs">
        <span className="font-medium">{t("detail.auth")}</span>
        <code className="break-all font-mono text-muted-foreground">
          {detail.auth.header}: {detail.auth.format}
        </code>
      </div>
    </header>
  );
}

/** 视频任务状态说明 */
function StatusReferenceSection({ detail }: { detail: ApiDocsDetail }) {
  const { t } = useTranslation("api-docs");
  const statusRef = detail.status_reference;
  if (!statusRef) return null;
  return (
    <section className="space-y-2 border-t pt-6">
      <h3 className="text-base font-semibold">{t("detail.taskStatus")}</h3>
      <div className="overflow-hidden rounded-lg border">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b bg-muted/50 text-left text-xs text-muted-foreground">
              <th className="px-3 py-2 font-medium">{t("detail.statusName")}</th>
              <th className="px-3 py-2 font-medium">{t("detail.statusDesc")}</th>
            </tr>
          </thead>
          <tbody>
            {statusRef.statuses.map((s) => (
              <tr key={s.status} className="border-b last:border-0">
                <td className="px-3 py-2 align-top">
                  <code className="font-mono text-xs font-semibold">{s.status}</code>
                </td>
                <td className="px-3 py-2 align-top text-xs text-muted-foreground">
                  {s.description}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-muted-foreground">{statusRef.note}</p>
    </section>
  );
}

/** 接口详情：中栏文字契约独立滚动，右栏示例与状态码固定不动 */
function EndpointDetailView({
  detail,
  endpoint,
  selectedTemplateId,
}: {
  detail: ApiDocsDetail;
  endpoint: ApiDocsEndpoint;
  selectedTemplateId: string | null;
}) {
  const { t } = useTranslation("api-docs");
  const errors = detail.error_reference;
  const forms = endpoint.forms ?? [];
  const [activeFormId, setActiveFormId] = useState<string | null>(
    selectedTemplateId ?? forms[0]?.template_id ?? null
  );
  const activeForm = forms.find((f) => f.template_id === activeFormId) ?? forms[0] ?? null;
  const curlExample = activeForm
    ? buildCurl(endpoint, detail.auth, activeForm.example)
    : "";
  const hasAside = Boolean(activeForm) || endpoint.responses.length > 0 || errors.length > 0;

  return (
    <div
      className={cn(
        "space-y-8",
        hasAside &&
          "lg:grid lg:grid-cols-[minmax(0,1fr)_520px] lg:items-start lg:gap-8 lg:space-y-0 2xl:grid-cols-[minmax(0,1fr)_640px]"
      )}
    >
      {/* 中栏：模型头 + 文档契约，随整页滚动 */}
      <div className="min-w-0 space-y-8">
        <ModelHeader detail={detail} />

        <div className="space-y-5">
          {/* 方法与路径 */}
          <div className="flex flex-wrap items-center gap-2 rounded-lg border bg-muted/40 px-3 py-2.5">
            <MethodBadge method={endpoint.method} />
            <PathText path={endpoint.path} />
            {endpoint.stream && (
              <Badge variant="secondary" className="ml-auto font-mono text-[11px]">
                {endpoint.stream === "always" ? t("detail.streamAlways") : t("detail.streamRequest")}
              </Badge>
            )}
          </div>
          {endpoint.summary && (
            <p className="text-sm text-muted-foreground">{endpoint.summary}</p>
          )}

          {/* 路径参数 */}
          {endpoint.path_params.length > 0 && (
            <section className="space-y-2">
              <SectionTitle>{t("detail.pathParams")}</SectionTitle>
              <ParamsTable params={endpoint.path_params} />
            </section>
          )}

          {/* 查询参数 */}
          {endpoint.query_params.length > 0 && (
            <section className="space-y-2">
              <SectionTitle>{t("detail.queryParams")}</SectionTitle>
              <ParamsTable params={endpoint.query_params} />
            </section>
          )}

          {/* 请求体（按调用形态） */}
          {forms.length > 0 && (
            <section className="space-y-3">
              <SectionTitle>{t("detail.requestBody")}</SectionTitle>
              {forms.length > 1 && (
                <div className="flex flex-wrap gap-1 border-b border-border/60">
                  {forms.map((form) => (
                    <button
                      key={form.template_id}
                      type="button"
                      onClick={() => setActiveFormId(form.template_id)}
                      className={cn(
                        "cursor-pointer rounded-t-md border-b-2 px-3 py-1.5 text-xs transition-colors",
                        form.template_id === activeForm?.template_id
                          ? "border-primary font-medium text-primary"
                          : "border-transparent text-muted-foreground hover:text-foreground"
                      )}
                    >
                      {form.title}
                    </button>
                  ))}
                </div>
              )}
              {activeForm && (
                <div className="space-y-3">
                  {activeForm.summary && (
                    <p className="text-xs text-muted-foreground">{activeForm.summary}</p>
                  )}
                  <FormParametersView form={activeForm} />
                  {activeForm.notes.length > 0 && (
                    <ul className="list-inside list-disc space-y-1 text-xs text-muted-foreground">
                      {activeForm.notes.map((note, i) => (
                        <li key={i}>{note}</li>
                      ))}
                    </ul>
                  )}
                </div>
              )}
            </section>
          )}

          {/* 接口级说明 */}
          {endpoint.notes.length > 0 && (
            <section className="space-y-2">
              <SectionTitle>{t("detail.notes")}</SectionTitle>
              <ul className="list-inside list-disc space-y-1 text-sm text-muted-foreground">
                {endpoint.notes.map((note, i) => (
                  <li key={i}>{note}</li>
                ))}
              </ul>
            </section>
          )}
        </div>

        <StatusReferenceSection detail={detail} />
      </div>

      {/* 右栏：请求示例 + 状态码，sticky 固定吸附头部下方，内部卡片垂直居中 */}
      {hasAside && (
        <div className="lg:sticky lg:top-[5.5rem] lg:flex lg:h-[calc(100vh-7.5rem)] lg:flex-col lg:overflow-y-auto">
          {/* my-auto 使内容在有余量时垂直居中，超高时回退顶端对齐并可滚动，不会裁掉顶部 */}
          <div className="space-y-4 lg:my-auto">
          {activeForm && (
            <div className="overflow-hidden rounded-lg border bg-card">
              <div className="flex items-center justify-between border-b bg-muted/40 px-3 py-2">
                <span className="flex items-center gap-1.5 text-xs font-semibold">
                  <span className="font-mono text-muted-foreground">cURL</span>
                  {activeForm.title}
                </span>
                <CopyButton text={curlExample} />
              </div>
              <pre className="max-h-[32rem] overflow-auto p-4 text-xs leading-relaxed">
                <code>{curlExample}</code>
              </pre>
              <p className="border-t px-3 py-2 text-xs text-muted-foreground/80">
                {t("detail.exampleModelHint")}
              </p>
            </div>
          )}
          <StatusCodesCard responses={endpoint.responses} errors={errors} />
          </div>
        </div>
      )}
    </div>
  );
}

/** 把错误条目的 code/message 回填到错误体骨架的 "..." 占位处 */
function fillErrorBody(body: unknown, entry: ApiDocsErrorEntry): unknown {
  const walk = (value: unknown, key?: string): unknown => {
    if (Array.isArray(value)) return value.map((item) => walk(item));
    if (value && typeof value === "object") {
      return Object.fromEntries(
        Object.entries(value as Record<string, unknown>).map(([k, v]) => [k, walk(v, k)])
      );
    }
    if (value === "..." && key) {
      const k = key.toLowerCase();
      if ((k === "code" || k === "type") && entry.code) return entry.code;
      if (k === "message") return entry.message;
    }
    return value;
  };
  return walk(body);
}

/** 状态码卡片：成功响应与错误码合并，状态码横向切换 */
function StatusCodesCard({
  responses,
  errors,
}: {
  responses: ApiDocsResponseItem[];
  errors: ApiDocsErrorShape[];
}) {
  const errorEntries = errors.flatMap((shape) =>
    shape.entries.map((entry) => ({ ...entry, shape }))
  );
  const statuses = [
    ...new Set([...responses.map((r) => r.status), ...errorEntries.map((e) => e.status)]),
  ];
  const [activeStatus, setActiveStatus] = useState<number | null>(statuses[0] ?? null);

  const activeResponse = responses.find((r) => r.status === activeStatus);
  const activeErrors = errorEntries.filter((e) => e.status === activeStatus);

  if (statuses.length === 0) return null;

  return (
    <div className="overflow-hidden rounded-lg border bg-card">
      <div className="flex flex-wrap items-center gap-1 border-b bg-muted/40 px-3 py-2">
        {statuses.map((status) => (
          <button
            key={status}
            type="button"
            onClick={() => setActiveStatus(status)}
            className={cn(
              "cursor-pointer rounded px-2 py-0.5 font-mono text-xs transition-colors",
              status === activeStatus
                ? "bg-background font-semibold text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground"
            )}
          >
            {status}
          </button>
        ))}
      </div>

      {/* 成功/普通响应说明 */}
      {activeResponse && (
        <div className="space-y-2 p-3">
          <div className="flex items-center gap-2">
            <Badge
              variant="outline"
              className={cn(
                "font-mono",
                activeResponse.status < 300
                  ? "border-emerald-500/40 text-emerald-600 dark:text-emerald-400"
                  : "border-amber-500/40 text-amber-600 dark:text-amber-400"
              )}
            >
              {activeResponse.status}
            </Badge>
            <code className="text-xs text-muted-foreground">{activeResponse.content_type}</code>
          </div>
          <p className="text-xs text-muted-foreground">{activeResponse.description}</p>
        </div>
      )}

      {/* 错误响应：错误体已回填当前状态码的 code/message，下方仅保留形状与场景 */}
      {activeErrors.length > 0 && (
        <div className="space-y-3 px-3 py-2.5">
          {activeErrors.map((entry, i) => {
            const filledJson = JSON.stringify(fillErrorBody(entry.shape.body, entry), null, 2);
            return (
              <div key={`${entry.shape.shape}-${entry.code ?? "none"}-${i}`} className="space-y-1.5">
                <div className="relative">
                  <pre className="max-h-72 overflow-auto rounded-md border bg-muted/40 p-3 text-xs leading-relaxed">
                    <code>{filledJson}</code>
                  </pre>
                  <span className="absolute right-2 top-2">
                    <CopyButton text={filledJson} />
                  </span>
                </div>
                <div className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
                  <Badge variant="secondary" className="font-mono text-[11px]">
                    {entry.shape.shape}
                  </Badge>
                  <span>{entry.scene}</span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

/* ---------------- 主组件 ---------------- */

export function DocsExplorer() {
  const { t } = useTranslation("api-docs");
  const [list, setList] = useState<ApiDocsListResponse | null>(null);
  const [listError, setListError] = useState(false);
  const [selection, setSelection] = useState<Selection | null>(null);
  const [detail, setDetail] = useState<ApiDocsDetail | null>(null);
  const [detailError, setDetailError] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const detailCache = useRef(new Map<string, ApiDocsDetail>());

  // 加载目录，默认选中第一个接口叶子
  useEffect(() => {
    getApiDocsList()
      .then((data) => {
        setList(data);
        setSelection(firstSelection(data));
      })
      .catch(() => setListError(true));
  }, []);

  // 选中模型变化时拉取详情（按 slug 缓存，同一页面生命周期内有效）
  useEffect(() => {
    if (!selection) return;
    const cached = detailCache.current.get(selection.slug);
    if (cached) {
      setDetail(cached);
      setDetailError(false);
      return;
    }
    setDetailLoading(true);
    setDetailError(false);
    getApiDocsDetail(selection.slug)
      .then((data) => {
        detailCache.current.set(selection.slug, data);
        setDetail(data);
      })
      .catch(() => {
        setDetail(null);
        setDetailError(true);
      })
      .finally(() => setDetailLoading(false));
  }, [selection]);

  // 当前选中的接口；operation_id 为 null 表示该端点尚未登记说明
  const activeEndpoint = useMemo(() => {
    if (!detail || !selection) return null;
    if (selection.operationId === null) return undefined;
    return detail.endpoints.find((ep) => ep.operation_id === selection.operationId) ?? undefined;
  }, [detail, selection]);

  // 目录中当前选中节点（用于 operation_id 为 null 时的降级展示）
  const activeNode = useMemo(() => {
    if (!list || !selection) return null;
    for (const cap of list.capabilities) {
      for (const family of cap.families) {
        for (const item of family.items) {
          if (item.slug !== selection.slug) continue;
          return (
            item.endpoints.find(
              (ep) =>
                ep.operation_id === selection.operationId &&
                ep.template_id === selection.templateId
            ) ?? null
          );
        }
      }
    }
    return null;
  }, [list, selection]);

  if (listError) {
    return (
      <div className="flex flex-col items-center gap-2 py-24 text-sm text-muted-foreground">
        <X className="size-5" />
        {t("empty.loadFailed")}
      </div>
    );
  }

  if (!list) {
    return (
      <div className="flex items-center justify-center gap-2 py-24 text-sm text-muted-foreground">
        <Loader2 className="size-4 animate-spin" />
        {t("loading")}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6 lg:flex-row lg:gap-8">
      {/* 左侧目录：能力 → 模型族 → 模型 → 接口（外层撑满高度，内层 sticky 固定不动） */}
      <aside className="shrink-0 lg:w-72 lg:self-stretch lg:border-r">
        <div className="lg:sticky lg:top-[5.5rem] lg:h-[calc(100vh-7.5rem)] lg:overflow-y-auto lg:pr-4">
          <div className="mb-3 flex items-center gap-2 px-2 text-sm font-semibold">
            <BookOpen className="size-4 text-primary" />
            {t("sidebar.title")}
          </div>
          <DocsSidebar list={list} selection={selection} onSelect={setSelection} />
        </div>
      </aside>

      {/* 右侧正文区：随整页滚动（滚动条在页面最右侧），右示例栏 sticky 固定 */}
      <div className="min-w-0 flex-1">
        {detailLoading && !detail ? (
          <div className="flex items-center justify-center gap-2 py-24 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" />
            {t("loading")}
          </div>
        ) : detailError ? (
          <div className="flex flex-col items-center gap-2 py-24 text-sm text-muted-foreground">
            <X className="size-5" />
            {t("empty.detailFailed")}
          </div>
        ) : detail ? (
          activeEndpoint ? (
            <EndpointDetailView
              key={`${activeEndpoint.operation_id ?? "unregistered"}-${selection?.templateId ?? "self"}`}
              detail={detail}
              endpoint={activeEndpoint}
              selectedTemplateId={selection?.templateId ?? null}
            />
          ) : (
            // 端点尚未在文档侧登记说明：降级渲染路径文本，不中断展示
            <div className="space-y-8">
              <ModelHeader detail={detail} />
              {activeNode && (
                <div className="space-y-3">
                  <div className="flex flex-wrap items-center gap-2 rounded-lg border bg-muted/40 px-3 py-2.5">
                    <MethodBadge method={activeNode.method} />
                    <PathText path={activeNode.path} />
                  </div>
                  <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
                    <FileText className="size-3.5" />
                    {t("detail.unregistered")}
                  </p>
                </div>
              )}
            </div>
          )
        ) : (
          <div className="py-24 text-center text-sm text-muted-foreground">
            {t("empty.noSelection")}
          </div>
        )}
      </div>
    </div>
  );
}
