"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Check,
  Clapperboard,
  Code2,
  Copy,
  ImageIcon,
  MessageSquare,
  Search,
  X,
  ZoomIn,
} from "lucide-react";

import { Reveal } from "@/components/reveal";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ProviderLogo } from "@/components/ui/provider-logo";
import { cn } from "@/lib/utils";
import { getModelDetail, getModels } from "@/lib/models";
import type {
  MarketplaceGroup,
  ModelCategory,
  ModelInfo,
  TemplateParameters,
} from "@/lib/types";

/** 本地封面池：public/images 下的随机封面图 */
const LOCAL_COVERS = Array.from(
  { length: 40 },
  (_, i) => `/images/random_image_${i + 1}.webp`
);

/**
 * 由系统按公开字段派生的内部计价字段（对应后端 derived_pricing_fields 的 type），
 * 仅用于计费匹配，不面向用户展示其原始取值。
 */
const DERIVED_PRICING_FIELDS = new Set(["image_pixel_count"]);

/** 文本 Token 计费项：unit_amount 单位为元 / 1M Token，直接展示接口数值 */
const TOKEN_ITEM_KINDS = new Set([
  "input_text_tokens",
  "cached_input_text_tokens",
  "output_text_tokens",
]);


function coverFor(model: ModelInfo, index: number): string {
  if (model.cover) return model.cover;
  return LOCAL_COVERS[index % LOCAL_COVERS.length];
}

const CATEGORIES: { key: "all" | ModelCategory; labelKey: string; icon?: typeof MessageSquare }[] = [
  { key: "all", labelKey: "category.all" },
  { key: "text", labelKey: "category.text", icon: MessageSquare },
  { key: "image", labelKey: "category.image", icon: ImageIcon },
  { key: "video", labelKey: "category.video", icon: Clapperboard },
];

/** 厂商筛选中"全部"选项的内部标识（非展示文案） */
const ALL_PROVIDER = "__all__";

function CategoryIcon({ category, className }: { category: ModelCategory; className?: string }) {
  if (category === "text") return <MessageSquare className={className} />;
  if (category === "image") return <ImageIcon className={className} />;
  return <Clapperboard className={className} />;
}

/** 从模型广场数据中提取价格文本 */
function formatPrice(model: ModelInfo, t: (key: string) => string): { input?: string; cached?: string; output?: string; value: string; unit: string } {
  const mp = model._marketplace;
  if (!mp) {
    if (model.category === "text") return { value: `¥${model.outputPrice}`, unit: t("price.perMillionTokens") };
    if (model.category === "image") return { value: `¥${model.outputPrice}`, unit: t("price.perImage") };
    return { value: `¥${model.outputPrice}`, unit: t("price.perSecond") };
  }
  const group = mp.groups?.[0];
  if (!group) return { value: t("price.usageBased"), unit: "" };
  if (group.pricing.type === "usage_based") {
    return { value: group.pricing.message || t("price.usageBased"), unit: "" };
  }
  const rule = group.pricing.rules?.[0];
  if (!rule) return { value: t("price.usageBased"), unit: "" };

  // 文本模型按 token 计费：展示输入/缓存命中/输出价格
  const inputItem = rule.items.find((e) => e.kind === "input_text_tokens" && e.unit_amount !== null);
  const cachedItem = rule.items.find((e) => e.kind === "cached_input_text_tokens" && e.unit_amount !== null);
  const outputItem = rule.items.find((e) => e.kind === "output_text_tokens" && e.unit_amount !== null);
  if (inputItem && outputItem) {
    return {
      input: `¥${inputItem.unit_amount}`,
      cached: cachedItem ? `¥${cachedItem.unit_amount}` : undefined,
      output: `¥${outputItem.unit_amount}`,
      value: "",
      unit: t("price.per1MTokens"),
    };
  }

  // 其他模型取第一个有价格的计费项
  const item = rule.items.find((entry) => entry.unit_amount !== null);
  const amount = item?.unit_amount ? Number(item.unit_amount) : NaN;
  if (!Number.isFinite(amount)) return { value: t("price.usageBased"), unit: "" };
  return {
    value: `¥${amount}`,
    unit: item?.kind === "output_video_duration" ? t("price.perSecond") : model.unit || t("price.perCall"),
  };
}

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

/* ---------------- 参数结构展示（只读） ---------------- */

function ParametersView({ parameters }: { parameters: TemplateParameters }) {
  const { t } = useTranslation("models");
  const entries = Object.entries(parameters.properties);
  return (
    <div className="space-y-2">
      {entries.map(([key, prop]) => {
        const required = parameters.required.includes(key);
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
                {prop.type === "string" && prop.minLength && prop.maxLength && (
                  <span>{prop.minLength}–{prop.maxLength} {t("detail.characters")}</span>
                )}
                {(prop.type === "integer" || prop.type === "number") &&
                  prop.minimum !== undefined &&
                  prop.maximum !== undefined && <span>{prop.minimum}–{prop.maximum}</span>}
                {prop.type === "array" && prop.maxItems && <span>{t("detail.maxItems", { count: prop.maxItems })}</span>}
              </div>
              {prop.enum && (
                <div className="flex flex-wrap items-center gap-1.5 rounded-md bg-background/60 px-2 py-1.5">
                  <span className="mr-1 text-xs font-medium text-muted-foreground">{t("detail.optionalValues")}</span>
                  {prop.enum.map((value) => (
                    <Badge key={String(value)} className="border border-primary/30 bg-primary/15 px-1.5 py-0 font-mono text-[11px] font-medium text-foreground">
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

/* ---------------- 计费规则展示 ---------------- */

function PricingGroupsView({ groups }: { groups: MarketplaceGroup[] }) {
  const { t } = useTranslation("models");
  const [expandedRules, setExpandedRules] = useState<Set<string>>(new Set());
  const toggleRule = (ruleKey: string) => {
    setExpandedRules((current) => {
      const next = new Set(current);
      if (next.has(ruleKey)) {
        next.delete(ruleKey);
      } else {
        next.add(ruleKey);
      }
      return next;
    });
  };

  return (
    <div className="space-y-4">
      {groups.map((group) => (
        <section key={group.group_id} className="overflow-hidden rounded-xl border bg-card">
          <div className="flex flex-wrap items-center gap-2 border-b px-4 py-3">
            <h3 className="font-semibold">{group.name}</h3>
            <Badge variant="outline">{group.pricing.type === "usage_based" ? t("detail.usageBased") : t("detail.standard")}</Badge>
            <span className="text-xs text-muted-foreground">{t("detail.defaultTier")}</span>
          </div>
          {group.pricing.type === "usage_based" ? (
            <p className="p-4 text-sm text-muted-foreground">{group.pricing.message || t("detail.usageBasedDesc")}</p>
          ) : (
            <div className="flex flex-wrap gap-2 p-3">
              {group.pricing.rules?.map((rule) => {
                const ruleKey = `${group.group_id}-${rule.name}-${rule.priority}`;
                const expanded = expandedRules.has(ruleKey);
                const primaryItem = rule.items.find((item) => item.kind === "output_video_duration" && item.unit_amount !== null)
                  ?? rule.items.find((item) => item.unit_amount !== null);
                const visibleConditions = rule.conditions.filter(
                  (condition) => !DERIVED_PRICING_FIELDS.has(condition.field)
                );
                const conditions = visibleConditions
                  .map(
                    (condition) =>
                      `${condition.field}：${Array.isArray(condition.value) ? condition.value.join("、") : String(condition.value)}`
                  )
                  .join("；");
                return (
                  <div key={ruleKey} className="w-fit rounded-xl border bg-background p-3.5">
                    <div className="flex items-start justify-between gap-2">
                      <span className="font-semibold">{rule.name}</span>
                      <span className="text-xs text-muted-foreground">{rule.currency}</span>
                    </div>
                    <p className="mt-2 font-mono text-base font-bold text-primary">
                      {primaryItem?.unit_amount ? `¥${primaryItem.unit_amount}` : t("detail.notConfigured")}
                      {primaryItem?.kind === "output_video_duration" && <span className="ml-1 text-xs font-normal text-muted-foreground">{t("detail.perSec")}</span>}
                    </p>
                    {visibleConditions.length > 0 && (
                      <div className="mt-2">
                        <p className={cn("text-xs text-muted-foreground", !expanded && "truncate")}>
                          {conditions}
                        </p>
                        {conditions.length > 36 && (
                          <button
                            type="button"
                            onClick={() => toggleRule(ruleKey)}
                            className="mt-1 cursor-pointer text-xs font-medium text-primary hover:underline"
                          >
                            {expanded ? t("detail.collapse") : t("detail.expand")}
                          </button>
                        )}
                      </div>
                    )}
                    <div className="mt-3 space-y-1.5 border-t pt-2.5 text-xs">
                      {rule.items.map((item) => (
                        <div key={item.kind}>
                          <div className="flex items-center justify-between gap-2">
                            <span className="shrink-0 text-muted-foreground">{item.label}</span>
                            <span className="shrink-0 font-mono">{item.unit_amount === null ? t("detail.perUsage") : `¥${item.unit_amount}${TOKEN_ITEM_KINDS.has(item.kind) ? t("detail.perMToken") : ""}`}</span>
                          </div>
                          {item.free_quantity > 0 && (
                            <p className="text-muted-foreground/80">{t("detail.freeQuota", { count: item.free_quantity })}</p>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </section>
      ))}
    </div>
  );
}

/* ---------------- 模型详情抽屉 ---------------- */

const DETAIL_SECTIONS = [
  { id: "pricing", labelKey: "detail.pricing" },
  { id: "example", labelKey: "detail.example" },
  { id: "parameters", labelKey: "detail.parameters" },
] as const;

function ModelDetailModal({
  model,
  onClose,
}: {
  model: ModelInfo;
  onClose: () => void;
}) {
  const { t } = useTranslation("models");
  const mp = model._marketplace;
  const template = mp?.template ?? null;
  const [copied, setCopied] = useState<"example" | "parameters" | "name" | null>(null);
  const [activeSection, setActiveSection] = useState<(typeof DETAIL_SECTIONS)[number]["id"]>("pricing");
  /** 记录 mousedown 是否发生在遮罩上：避免从面板内拖选文本、在遮罩上松手时误关闭抽屉 */
  const overlayMouseDown = useRef(false);

  // 弹窗打开时锁定背景滚动
  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, []);

  // ESC 关闭
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const exampleJson = template ? JSON.stringify(template.example, null, 2) : "";
  const parametersJson = template ? JSON.stringify(template.parameters, null, 2) : "";

  const handleCopy = async (type: "example" | "parameters") => {
    const text = type === "example" ? exampleJson : parametersJson;
    const ok = await copyToClipboard(text);
    if (ok) {
      setCopied(type);
      setTimeout(() => setCopied(null), 2000);
    }
  };

  const handleCopyName = async () => {
    const ok = await copyToClipboard(model.name);
    if (ok) {
      setCopied("name");
      setTimeout(() => setCopied(null), 2000);
    }
  };

  const sections = DETAIL_SECTIONS.filter((section) =>
    (section.id === "pricing" && Boolean(mp?.groups?.length))
    || (section.id === "example" && Boolean(template))
    || (section.id === "parameters" && Boolean(template))
  );
  const scrollTo = (id: (typeof DETAIL_SECTIONS)[number]["id"]) => {
    setActiveSection(id);
    document.querySelector(`[data-model-section="${id}"]`)?.scrollIntoView({
      behavior: "smooth",
      block: "start",
    });
  };

  return (
    <div
      className="fixed inset-0 z-[60] flex justify-end bg-black/50 backdrop-blur-sm animate-in fade-in-0 duration-200"
      onMouseDown={(e) => {
        overlayMouseDown.current = e.target === e.currentTarget;
      }}
      onClick={(e) => {
        // 只有按下和抬起都在遮罩自身上才关闭；从面板内拖选文本到遮罩松手不关闭
        if (overlayMouseDown.current && e.target === e.currentTarget) onClose();
      }}
    >
      <div
        className="flex h-full w-full max-w-4xl flex-col border-l border-border/80 bg-background shadow-2xl animate-in slide-in-from-right duration-300"
        onClick={(e) => e.stopPropagation()}
      >
        {/* 头部 */}
        <div className="flex shrink-0 items-start justify-between gap-4 border-b px-6 py-5">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h2 className="font-mono text-xl font-bold">{model.name}</h2>
              <button
                type="button"
                onClick={handleCopyName}
                aria-label={t("detail.copyName")}
                className="flex size-7 shrink-0 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
              >
                {copied === "name" ? (
                  <Check className="size-4 text-green-500" />
                ) : (
                  <Copy className="size-4" />
                )}
              </button>
            </div>
            <p className="mt-1 text-sm text-muted-foreground">
              {model.description || template?.summary}
            </p>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {model.providerName && (
                <Badge variant="outline">
                  <ProviderLogo
                    src={model.providerLogoUrl}
                    providerId={model.providerId}
                    className="mr-1 size-3.5"
                  />
                  {model.providerName}
                </Badge>
              )}
              {model.tags.map((tag) => (
                <Badge key={tag} variant="outline">
                  {tag}
                </Badge>
              ))}
            </div>
          </div>
          <button
            onClick={onClose}
            aria-label={t("detail.close")}
            className="flex size-8 shrink-0 items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          >
            <X className="size-4" />
          </button>
        </div>

        <nav className="flex shrink-0 gap-1 border-b border-border/60 px-6 py-2">
          {sections.map((section) => (
            <button
              key={section.id}
              type="button"
              onClick={() => scrollTo(section.id)}
              className={cn(
                "cursor-pointer rounded-full px-3 py-1.5 text-xs transition-all duration-200",
                activeSection === section.id
                  ? "bg-primary/10 font-medium text-primary shadow-[inset_0_0_0_1px_rgb(76_111_255/30%)]"
                  : "text-muted-foreground hover:bg-accent/70 hover:text-foreground"
              )}
            >
              {t(section.labelKey)}
            </button>
          ))}
        </nav>

        {/* 内容 */}
        <div className="min-h-0 flex-1 space-y-6 overflow-y-auto px-6 py-5">
          {/* 计费规则 */}
          {mp?.groups && mp.groups.length > 0 && (
            <section data-model-section="pricing" className="scroll-mt-4 space-y-2">
              <div className="flex items-center gap-2">
                <Search className="size-4 text-primary" />
                <h3 className="font-semibold">{t("detail.pricing")}</h3>
              </div>
              <PricingGroupsView groups={mp.groups} />
            </section>
          )}

          {/* 调用示例 */}
          {template && (
            <section data-model-section="example" className="scroll-mt-4 space-y-2">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Code2 className="size-4 text-primary" />
                  <h3 className="font-semibold">{t("detail.example")}</h3>
                </div>
                <button
                  onClick={() => handleCopy("example")}
                  className="flex items-center gap-1.5 rounded-md px-2 py-1 text-xs text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                >
                  {copied === "example" ? (
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
              </div>
              <pre className="max-h-64 overflow-auto rounded-lg bg-muted p-4 text-xs leading-relaxed">
                <code>{exampleJson}</code>
              </pre>
            </section>
          )}

          {/* 参数结构（只读） */}
          {template && (
            <section data-model-section="parameters" className="scroll-mt-4 space-y-4 rounded-lg border p-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Search className="size-4 text-primary" />
                  <h3 className="font-semibold">{t("detail.parameters")}</h3>
                  <Badge variant="secondary" className="text-xs">
                    {t("detail.fieldCount", { count: Object.keys(template.parameters.properties).length })}
                  </Badge>
                </div>
                <button
                  onClick={() => handleCopy("parameters")}
                  className="flex items-center gap-1.5 rounded-md px-2 py-1 text-xs text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                >
                  {copied === "parameters" ? (
                    <>
                      <Check className="size-3.5 text-green-500" />
                      {t("detail.copied")}
                    </>
                  ) : (
                    <>
                      <Copy className="size-3.5" />
                      {t("detail.copyJson")}
                    </>
                  )}
                </button>
              </div>
              <ParametersView parameters={template.parameters} />
            </section>
          )}
        </div>
      </div>
    </div>
  );
}

/* ---------------- 主组件 ---------------- */

export function ModelExplorer() {
  const { t } = useTranslation("models");
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [loading, setLoading] = useState(true);

  // 模型广场页面隐藏页面级滚动条（保留滚动能力）
  useEffect(() => {
    document.documentElement.classList.add("no-page-scrollbar");
    return () => document.documentElement.classList.remove("no-page-scrollbar");
  }, []);
  const [keyword, setKeyword] = useState("");
  const [provider, setProvider] = useState<string>(ALL_PROVIDER);
  const [preview, setPreview] = useState<ModelInfo | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const providerRowRef = useRef<HTMLDivElement>(null);

  // 客户端拉取模型列表（浏览器可见请求）
  useEffect(() => {
    getModels()
      .then(setModels)
      .finally(() => setLoading(false));
  }, []);

  const openDetail = async (model: ModelInfo) => {
    setDetailLoading(true);
    try {
      setPreview(await getModelDetail(model.id));
    } catch {
      setPreview(model);
    } finally {
      setDetailLoading(false);
    }
  };

  // 厂商行：鼠标滚轮纵向滚动转为横向滚动
  useEffect(() => {
    const el = providerRowRef.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      if (el.scrollWidth <= el.clientWidth) return;
      e.preventDefault();
      el.scrollLeft += e.deltaY;
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, []);

  const providers = useMemo(
    () => [
      { id: ALL_PROVIDER, name: t("provider.all"), logoUrl: null as string | null },
      ...Array.from(
        new Map(
          models
            .filter(
              (m): m is ModelInfo & { providerId: string; providerName: string } =>
                Boolean(m.providerId && m.providerName)
            )
            .map((m) => [
              m.providerId,
              { id: m.providerId, name: m.providerName, logoUrl: m.providerLogoUrl },
            ])
        ).values()
      ),
    ],
    [models, t]
  );

  const filtered = useMemo(() => {
    const kw = keyword.trim().toLowerCase();
    return models.filter((m) => {
      const matchProvider = provider === ALL_PROVIDER || m.providerId === provider;
      const matchKeyword =
        !kw ||
        m.name.toLowerCase().includes(kw) ||
        m.id.toLowerCase().includes(kw) ||
        m.description.toLowerCase().includes(kw);
      return matchProvider && matchKeyword;
    });
  }, [models, keyword, provider]);

  /** 为无自带封面的模型顺序分配封面序号，仅在需要封面的数量超过封面总数时才重复 */
  const coverIndexes = useMemo(() => {
    const map = new Map<string, number>();
    let n = 0;
    for (const m of filtered) {
      if (!m.cover) map.set(m.id, n++);
    }
    return map;
  }, [filtered]);

  return (
    <div className="space-y-6">
      {/* 搜索 + 厂商筛选 */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="relative w-full shrink-0 sm:max-w-64">
          <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            placeholder={t("search.placeholder")}
            className="h-10 rounded-full pl-9"
          />
        </div>
        <div
          ref={providerRowRef}
          className="flex min-w-0 flex-1 flex-nowrap justify-start gap-2 overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
        >
          {providers.map((p) => (
            <button
              key={p.id}
              onClick={() => setProvider(p.id)}
              className={cn(
                "flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full border px-3 py-1 text-sm transition-colors",
                provider === p.id
                  ? "border-primary bg-primary text-primary-foreground"
                  : "bg-background text-muted-foreground hover:border-primary/40 hover:text-foreground"
              )}
            >
              <ProviderLogo
                src={p.logoUrl}
                providerId={p.id === ALL_PROVIDER ? null : p.id}
                pad
                className="size-4"
              />
              {p.name}
            </button>
          ))}
        </div>
      </div>

      {/* 模型卡片墙 */}
      {loading ? (
        <div className="mt-8 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="overflow-hidden rounded-xl border">
              <div className="aspect-video animate-pulse bg-muted" />
              <div className="space-y-2 p-4">
                <div className="h-4 w-1/2 animate-pulse rounded bg-muted" />
                <div className="h-3 w-full animate-pulse rounded bg-muted" />
                <div className="h-3 w-2/3 animate-pulse rounded bg-muted" />
              </div>
            </div>
          ))}
        </div>
      ) : filtered.length > 0 ? (
        <div className="mt-8 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {filtered.map((model, index) => {
            const price = formatPrice(model, t);
            const featured = model.tags.includes("主推");
            const categoryLabelKey = CATEGORIES.find((c) => c.key === model.category)?.labelKey;
            const card = (
              <Card
                className={cn(
                  "card-hover group h-full gap-0 overflow-hidden p-0 cursor-pointer transition-all duration-300 hover:-translate-y-1 hover:border-primary/50 hover:shadow-xl hover:shadow-primary/15",
                  detailLoading && "pointer-events-none opacity-70",
                  featured && "border-transparent"
                )}
                onClick={() => void openDetail(model)}
              >
                {/* 封面区 */}
                <div className="relative aspect-video overflow-hidden">
                  <img
                    src={coverFor(model, coverIndexes.get(model.id) ?? 0)}
                    alt={t("price.coverAlt", { name: model.name })}
                    loading="lazy"
                    className="size-full object-cover transition-transform duration-500 group-hover:scale-105"
                  />
                  <div className="absolute inset-0 bg-gradient-to-t from-black/75 via-black/15 to-transparent" />
                  <div className="pointer-events-none absolute inset-0 -translate-x-full bg-gradient-to-r from-transparent via-white/20 to-transparent transition-transform duration-700 group-hover:translate-x-full" />
                  <div className="absolute left-3 top-3 flex items-center gap-1.5">
                    {featured && (
                      <Badge className="border-0 bg-gradient-to-r from-[#4c6fff] to-[#7c5cff] text-white shadow-lg shadow-[#4c6fff]/30">
                        {t("price.featured")}
                      </Badge>
                    )}
                    <Badge className="border-white/20 bg-black/40 text-white backdrop-blur-sm">
                      <CategoryIcon category={model.category} className="mr-1 size-3" />
                      {categoryLabelKey ? t(categoryLabelKey) : null}
                    </Badge>
                  </div>
                  {model.providerName && (
                    <Badge className="absolute right-3 top-3 border-white/20 bg-black/40 text-white backdrop-blur-sm">
                      <ProviderLogo
                        src={model.providerLogoUrl}
                        providerId={model.providerId}
                        pad
                        className="mr-1 size-3.5"
                      />
                      {model.providerName}
                    </Badge>
                  )}
                  <span className="absolute bottom-3 left-3 font-mono text-xs text-white/85">
                    {model.name}
                  </span>
                  <span className="absolute left-1/2 top-1/2 flex -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full bg-black/55 p-2.5 text-white opacity-0 shadow-lg backdrop-blur-sm transition-all duration-300 group-hover:opacity-100">
                    <ZoomIn className="size-5" aria-label={t("price.zoomAlt")} />
                  </span>
                  <span className="absolute bottom-3 right-3 flex flex-col items-end gap-0.5 font-mono text-xs text-white/85">
                    {price.input && price.output ? (
                      <>
                        <span>{t("price.input")} {price.input}</span>
                        {price.cached && <span>{t("price.cached")} {price.cached}</span>}
                        <span>{t("price.output")} {price.output}</span>
                        <span className="text-[10px] text-white/70">{price.unit}</span>
                      </>
                    ) : (
                      <span className="flex items-center gap-1">
                        {price.value}
                        <span className="text-[10px] text-white/70">{price.unit}</span>
                      </span>
                    )}
                  </span>
                </div>

                {/* 信息区 */}
                <CardHeader className="pb-2 pt-4">
                  <CardTitle className="text-base">{model.name}</CardTitle>
                  <CardDescription className="line-clamp-2 min-h-10">
                    {model.description}
                  </CardDescription>
                </CardHeader>
                <CardContent className="flex flex-1 flex-col justify-end pb-5">
                  <div className="flex flex-wrap gap-1.5">
                    {model.tags
                      .filter((tag) => tag !== "主推")
                      .slice(0, 3)
                      .map((tag) => (
                        <Badge key={tag} variant="secondary">
                          {tag}
                        </Badge>
                      ))}
                  </div>
                </CardContent>
              </Card>
            );

            return (
              <Reveal key={model.id} delay={(index % 3) * 90} className="h-full">
                {featured ? (
                  <div className="relative h-full overflow-hidden rounded-[15px] p-[1.5px]">
                    <div className="animate-spin-slow absolute inset-[-120%] bg-[conic-gradient(from_0deg,transparent_0deg,transparent_290deg,#4c6fff_330deg,#7c5cff_360deg)] [animation-duration:3.5s]" />
                    <div className="relative h-full">{card}</div>
                  </div>
                ) : (
                  card
                )}
              </Reveal>
            );
          })}
        </div>
      ) : (
        <div className="mt-16 text-center text-sm text-muted-foreground">
          {models.length === 0
            ? t("empty.noModels")
            : t("empty.noMatch")}
        </div>
      )}

      {/* 详情弹窗 */}
      {preview && <ModelDetailModal model={preview} onClose={() => setPreview(null)} />}
    </div>
  );
}
