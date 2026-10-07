"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Ban,
  Check,
  ChevronDown,
  CircleCheck,
  CircleHelp,
  Copy,
  KeyRound,
  Layers,
  Plus,
  RefreshCw,
  Search,
  Trash2,
  X,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Loading } from "@/components/ui/loading";
import { Pagination } from "@/components/ui/pagination";
import { toast } from "@/components/ui/toaster";
import { cn } from "@/lib/utils";
import { get, post } from "@/lib/request";

type ApiKeyItem = {
  id: string;
  label: string;
  /** 完整密钥明文（仅用于复制） */
  token: string;
  /** 中间打码后的展示串 */
  preview: string;
  created_at: string | null;
  last_used_at: string | null;
  revoked: boolean;
  enabled: boolean;
  /** 关联的分组列表 */
  groups: TokenGroup[];
};

type TokenGroup = {
  id: number;
  name: string;
  /** 分组介绍：仅用于展示，最长 512 字符；无介绍时为空字符串 */
  description?: string;
  /** 分组价格倍率（Decimal 字符串，实际计费金额按该倍率缩放） */
  price_multiplier?: string;
};

/** 展示倍率：保留两位小数（如 0.850000 → 0.85），缺失时按 1 处理 */
function formatMultiplier(m: string | undefined | null): string {
  const n = Number(m ?? "1");
  return Number.isFinite(n) ? n.toFixed(2) : "1.00";
}

/** 倍率标签配色：折扣（<1）绿色，加价（>1）琥珀色，原价（=1）灰色；与分组管理页一致 */
function multiplierBadgeClass(m: string | undefined | null): string {
  const n = Number(m ?? "1");
  if (!Number.isFinite(n) || n === 1) {
    return "border-border/60 bg-muted/50 text-muted-foreground";
  }
  if (n < 1) {
    return "border-emerald-500/40 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400";
  }
  return "border-amber-500/40 bg-amber-500/10 text-amber-600 dark:text-amber-400";
}

const PAGE_SIZE = 20;

/** 兼容多种响应字段：数组或 { items / list / tokens, total } */
function normalize(data: unknown): { items: ApiKeyItem[]; total: number } {
  const raw: unknown[] = Array.isArray(data)
    ? data
    : data && typeof data === "object"
      ? (((data as Record<string, unknown>).items ??
          (data as Record<string, unknown>).list ??
          (data as Record<string, unknown>).tokens ??
          (data as Record<string, unknown>).api_keys ??
          []) as unknown[])
      : [];
  const total =
    !Array.isArray(data) &&
    data &&
    typeof data === "object" &&
    typeof (data as Record<string, unknown>).total === "number"
      ? ((data as Record<string, unknown>).total as number)
      : raw.length;
  const items = raw.map((rawItem) => {
    const d = (rawItem ?? {}) as Record<string, unknown>;
    const token = (d.token ?? d.api_key ?? d.key ?? "") as string;
    return {
      id: String(d.id ?? d.token_id ?? ""),
      label: (d.label as string) || "",
      token,
      preview: maskKey(token, (d.key_prefix as string) || ""),
      created_at: (d.created_at as string) ?? null,
      last_used_at: (d.last_used_at as string) ?? null,
      revoked: Boolean(d.revoked ?? d.revoked_at ?? d.is_revoked),
      enabled: Boolean(
        d.enabled ?? d.is_active ?? (d.disabled_at ? false : true)
      ),
      groups: Array.isArray(d.groups) ? (d.groups as TokenGroup[]) : [],
    };
  });
  return { items, total };
}

/** 密钥脱敏：保留前缀（如 sk-U7kwHwY5）与末 4 位，中间用 … 代替 */
function maskKey(token: string, prefix: string): string {
  if (!token) return prefix ? `${prefix}…` : "";
  const head = prefix && token.startsWith(prefix) ? prefix : token.slice(0, 11);
  const tail = token.slice(-4);
  return `${head}…${tail}`;
}

/** 从创建/轮换响应中取出新密钥明文（仅本次返回） */
function pickNewKey(data: unknown): string {
  if (data && typeof data === "object") {
    const d = data as Record<string, unknown>;
    for (const k of ["token", "api_key", "key", "access_token"]) {
      if (typeof d[k] === "string" && d[k]) return d[k] as string;
    }
  }
  return "";
}

function formatTime(value: string | null, locale: string): string {
  if (!value) return "-";
  return new Date(value).toLocaleString(locale, { hour12: false });
}

/**
 * 复制文本：优先 Clipboard API，非安全上下文（HTTP/IP 访问）时降级 execCommand
 * 返回是否复制成功
 */
async function copyText(value: string): Promise<boolean> {
  if (navigator.clipboard && window.isSecureContext) {
    try {
      await navigator.clipboard.writeText(value);
      return true;
    } catch {
      // 继续尝试降级方案
    }
  }
  try {
    const textarea = document.createElement("textarea");
    textarea.value = value;
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

type Translate = (key: string, options?: Record<string, unknown>) => string;

/** 获取完整密钥并复制到剪贴板 */
const copyToken = async (t: Translate, id: string) => {
  try {
    const data = await get<unknown>("/user/token/copy", {
      params: { token_id: id },
    });
    // 兼容返回字符串或 { token } 对象
    const key =
      typeof data === "string"
        ? data
        : data && typeof data === "object"
          ? ((data as Record<string, unknown>).token ??
            (data as Record<string, unknown>).api_key ??
            (data as Record<string, unknown>).key ??
            "")
          : "";
    if (!key || typeof key !== "string") {
      toast.error(t("apiKeys.noToken"));
      return;
    }
    if (await copyText(key)) {
      toast.success(t("apiKeys.tokenCopied"));
    } else {
      toast.error(t("apiKeys.copyFailed"));
    }
  } catch (err) {
    toast.error(err instanceof Error ? err.message : t("apiKeys.getTokenFailed"));
  }
};

/** 复制按钮：复制成功后短暂显示对勾 */
function CopyButton({
  value,
  className,
  onClick,
}: {
  value: string;
  className?: string;
  onClick?: () => void;
}) {
  const { t } = useTranslation("console");
  const [copied, setCopied] = useState(false);

  const copy = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (onClick) {
      onClick();
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
      return;
    }
    if (await copyText(value)) {
      setCopied(true);
      toast.success(t("apiKeys.copySuccess"));
      setTimeout(() => setCopied(false), 2000);
    } else {
      toast.error(t("apiKeys.copyFailed"));
    }
  };

  return (
    <Button
      variant="ghost"
      size="icon"
      className={cn("size-7", className)}
      onClick={copy}
      title={t("apiKeys.copyKeyTitle")}
    >
      {copied ? (
        <Check className="size-3.5 text-success" />
      ) : (
        <Copy className="size-3.5" />
      )}
    </Button>
  );
}

/** 新密钥展示弹窗：明文仅显示一次，支持一键复制 */
function KeyResultDialog({
  title,
  keyValue,
  onClose,
}: {
  title: string;
  keyValue: string;
  onClose: () => void;
}) {
  const { t } = useTranslation("console");
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    if (await copyText(keyValue)) {
      setCopied(true);
      toast.success(t("apiKeys.copySuccess"));
      setTimeout(() => setCopied(false), 2000);
    } else {
      toast.error(t("apiKeys.copyFailed"));
    }
  };

  return (
    <div
      className="fixed inset-0 z-[80] flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="w-full max-w-md rounded-xl border bg-background p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-base font-semibold">{title}</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          {t("apiKeys.saveKeyNotice")}
        </p>
        <div className="mt-4 flex items-center gap-2 rounded-lg border border-border/60 bg-muted/40 px-3 py-2.5">
          <code className="flex-1 break-all font-mono text-xs">{keyValue}</code>
          <Button variant="outline" size="icon" onClick={copy}>
            {copied ? (
              <Check className="size-4 text-success" />
            ) : (
              <Copy className="size-4" />
            )}
          </Button>
        </div>
        <div className="mt-5 flex justify-end">
          <Button onClick={onClose}>{t("apiKeys.saved")}</Button>
        </div>
      </div>
    </div>
  );
}

/** 分组下拉选择：单选/多选复用，支持按名称搜索，点击外部或 Esc 关闭 */
function GroupSelect({
  groups,
  value,
  onChange,
  multiple = false,
  placeholder,
  excludeIds = [],
}: {
  groups: TokenGroup[];
  value: number[];
  onChange: (v: number[]) => void;
  multiple?: boolean;
  placeholder?: string;
  excludeIds?: number[];
}) {
  const { t } = useTranslation("console");
  const [open, setOpen] = useState(false);
  const [keyword, setKeyword] = useState("");
  const [placement, setPlacement] = useState<"top" | "bottom">("bottom");
  const rootRef = useRef<HTMLDivElement | null>(null);

  const keywordLower = keyword.trim().toLowerCase();
  const options = groups.filter(
    (g) =>
      !excludeIds.includes(g.id) &&
      (g.name.toLowerCase().includes(keywordLower) ||
        formatMultiplier(g.price_multiplier).includes(keywordLower))
  );
  const selected = groups.filter((g) => value.includes(g.id));

  /** 打开时根据视口剩余空间决定面板向上还是向下展开 */
  const toggleOpen = () => {
    if (!open) {
      const rect = rootRef.current?.getBoundingClientRect();
      if (rect) {
        const panelH = Math.min(options.length * 36 + 56, 280);
        const spaceBelow = window.innerHeight - rect.bottom;
        const spaceAbove = rect.top;
        setPlacement(
          spaceBelow < panelH + 8 && spaceAbove > spaceBelow
            ? "top"
            : "bottom"
        );
      }
      setKeyword("");
    }
    setOpen((v) => !v);
  };

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (e: PointerEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  const toggle = (id: number) => {
    if (multiple) {
      onChange(
        value.includes(id) ? value.filter((v) => v !== id) : [...value, id]
      );
    } else {
      onChange([id]);
      setOpen(false);
    }
  };

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        role="combobox"
        aria-expanded={open}
        aria-haspopup="listbox"
        aria-multiselectable={multiple}
        onClick={toggleOpen}
        className={cn(
          "border-input dark:bg-input/30 flex min-h-9 w-full items-center justify-between gap-2 rounded-md border bg-transparent px-3 py-1.5 text-sm shadow-xs transition-[color,box-shadow,border-color] outline-none cursor-pointer",
          "hover:border-ring/60",
          "focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px]",
          open && "border-ring ring-ring/50 ring-[3px]"
        )}
      >
        <span
          className={cn(
            "min-w-0 flex-1 flex flex-wrap items-center gap-1 text-left",
            selected.length === 0 && "text-muted-foreground"
          )}
        >
          {selected.length > 0 ? (
            multiple ? (
              selected.map((g) => (
                <span
                  key={g.id}
                  title={g.description || undefined}
                  className="inline-flex max-w-56 flex-col rounded-md border border-border/60 bg-muted/50 px-1.5 py-0.5 text-xs font-medium"
                >
                  <span className="flex items-center gap-1">
                    <span className="truncate">{g.name}</span>
                    <span
                      className={cn(
                        "inline-flex shrink-0 items-center rounded border px-1 py-0 font-mono text-[10px] font-medium leading-3.5",
                        multiplierBadgeClass(g.price_multiplier)
                      )}
                    >
                      {formatMultiplier(g.price_multiplier)}
                    </span>
                    <span
                      role="button"
                      aria-label={t("apiKeys.removeGroup", { name: g.name })}
                      onClick={(e) => {
                        e.stopPropagation();
                        toggle(g.id);
                      }}
                      className="shrink-0 rounded-sm p-0.5 text-muted-foreground transition-colors hover:bg-accent hover:text-destructive cursor-pointer"
                    >
                      <X className="size-3" />
                    </span>
                  </span>
                  {g.description && (
                    <span className="truncate text-[11px] font-normal leading-4 text-muted-foreground">
                      {g.description}
                    </span>
                  )}
                </span>
              ))
            ) : (
              <span className="flex min-w-0 flex-col">
                  <span className="flex min-w-0 items-center gap-1.5">
                  <span className="truncate">{selected[0].name}</span>
                  <span
                    className={cn(
                      "inline-flex shrink-0 items-center rounded border px-1 py-0 font-mono text-[10px] font-medium leading-3.5",
                      multiplierBadgeClass(selected[0].price_multiplier)
                    )}
                  >
                    {formatMultiplier(selected[0].price_multiplier)}
                  </span>
                </span>
                {selected[0].description && (
                  <span className="truncate text-[11px] text-muted-foreground">
                    {selected[0].description}
                  </span>
                )}
              </span>
            )
          ) : (
            placeholder ?? t("apiKeys.selectGroupPlaceholder")
          )}
        </span>
        <ChevronDown
          aria-hidden
          className={cn(
            "size-4 shrink-0 text-muted-foreground transition-transform duration-200",
            open && "rotate-180"
          )}
        />
      </button>

      {open && (
        <div
          role="listbox"
          aria-multiselectable={multiple}
          className={cn(
            "border-border/60 bg-popover text-popover-foreground animate-in fade-in-0 zoom-in-95 absolute z-50 min-w-full overflow-y-auto overflow-x-hidden rounded-lg border p-1 shadow-lg",
            placement === "bottom" ? "top-full mt-1.5" : "bottom-full mb-1.5"
          )}
          style={{ maxHeight: "17.5rem" }}
        >
          <div className="sticky top-0 bg-popover pb-1">
            <div className="relative">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
              <input
                autoFocus
                value={keyword}
                onChange={(e) => setKeyword(e.target.value)}
                placeholder={t("apiKeys.searchGroupPlaceholder")}
                className="w-full rounded-md border border-border/60 bg-transparent py-1.5 pl-8 pr-2 text-sm outline-none placeholder:text-muted-foreground focus:border-ring"
              />
            </div>
          </div>
          {options.length === 0 ? (
            <p className="px-2.5 py-1.5 text-sm text-muted-foreground">
              {keyword ? t("apiKeys.noGroupFound") : t("apiKeys.noGroupAvailable")}
            </p>
          ) : (
            options.map((g) => {
              const checked = value.includes(g.id);
              return (
                <button
                  key={g.id}
                  type="button"
                  role="option"
                  aria-selected={checked}
                  onClick={() => toggle(g.id)}
                  className={cn(
                    "flex w-full items-center justify-between gap-2 rounded-md px-2.5 py-1.5 text-left text-sm transition-colors outline-none cursor-pointer",
                    "hover:bg-accent hover:text-accent-foreground focus-visible:bg-accent focus-visible:text-accent-foreground",
                    checked && "text-primary font-medium"
                  )}
                >
                  <span className="min-w-0 flex-1">
                    <span className="block truncate">{g.name}</span>
                    {g.description && (
                      <span className="block truncate text-xs font-normal text-muted-foreground">
                        {g.description}
                      </span>
                    )}
                  </span>
                  <span
                    className={cn(
                      "inline-flex shrink-0 items-center rounded-md border px-1.5 py-0.5 font-mono text-xs font-medium",
                      multiplierBadgeClass(g.price_multiplier)
                    )}
                  >
                    {formatMultiplier(g.price_multiplier)}
                  </span>
                  {checked && (
                    <Check className="size-4 shrink-0 text-primary" />
                  )}
                </button>
              );
            })
          )}
        </div>
      )}
    </div>
  );
}

/** 分组选择区块：彩色描边卡片 + 徽标标签 + 问号提示 + 说明文字 */
function GroupFieldBox({
  tone,
  label,
  badge,
  hint,
  description,
  children,
}: {
  tone: "primary" | "warning";
  label: string;
  badge?: string;
  hint: string;
  description?: string;
  children: React.ReactNode;
}) {
  return (
    <div
      className={cn(
        "rounded-lg border p-3",
        tone === "primary"
          ? "border-primary/40 bg-primary/5"
          : "border-warning/40 bg-warning/5"
      )}
    >
      <div className="flex items-center gap-2">
        <span
          className={cn(
            "shrink-0 text-sm font-semibold",
            tone === "primary" ? "text-primary" : "text-warning"
          )}
        >
          {label}
        </span>
        {/* <Badge
          variant="outline"
          className={cn(
            "shrink-0 rounded px-1 py-0 text-[10px] leading-4",
            tone === "primary"
              ? "border-primary/40 bg-primary/10 text-primary"
              : "border-warning/40 bg-warning/10 text-warning"
          )}
        >
          {badge}
        </Badge> */}
        <span title={hint} className="shrink-0 cursor-help">
          <CircleHelp
            className="size-3.5 text-muted-foreground"
            aria-label={hint}
          />
        </span>
        <div className="min-w-0 flex-1">{children}</div>
      </div>
      {description && (
        <p className="mt-2 text-xs text-muted-foreground">{description}</p>
      )}
    </div>
  );
}

/** 主分组选择块（兜底分组逻辑已注释） */
function GroupBindingFields({
  groups,
  primaryId,
  // fallbackIds,
  onPrimaryChange,
  // onFallbackChange,
}: {
  groups: TokenGroup[];
  primaryId: number | null;
  // fallbackIds: number[];
  onPrimaryChange: (v: number | null) => void;
  // onFallbackChange: (v: number[]) => void;
}) {
  const { t } = useTranslation("console");
  return (
    <>
      <GroupFieldBox
        tone="primary"
        label={t("apiKeys.selectGroupLabel")}
        badge={t("apiKeys.selectGroupBadge")}
        hint={t("apiKeys.selectGroupHint")}
        description={t("apiKeys.selectGroupDescription")}
      >
        <GroupSelect
          groups={groups}
          value={primaryId === null ? [] : [primaryId]}
          onChange={(v) => onPrimaryChange(v[0] ?? null)}
          placeholder={t("apiKeys.selectGroupSearchPlaceholder")}
        />
      </GroupFieldBox>
      {/* 兜底分组逻辑已注释
      <GroupFieldBox
        tone="warning"
        label={t("apiKeys.fallbackGroupLabel")}
        badge=""
        hint={t("apiKeys.fallbackGroupHint")}
      >
        <GroupSelect
          multiple
          groups={groups}
          value={fallbackIds}
          onChange={onFallbackChange}
          placeholder={t("apiKeys.fallbackGroupPlaceholder")}
          excludeIds={primaryId === null ? [] : [primaryId]}
        />
      </GroupFieldBox>
      */}
    </>
  );
}

/** 创建 API 密钥弹窗 */
function CreateApiKeyDialog({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: (key: string) => void;
}) {
  const { t } = useTranslation("console");
  const [label, setLabel] = useState("");
  const [groups, setGroups] = useState<TokenGroup[]>([]);
  const [primaryId, setPrimaryId] = useState<number | null>(null);
  // 兜底分组逻辑已注释
  // const [fallbackIds, setFallbackIds] = useState<number[]>([]);
  const [submitting, setSubmitting] = useState(false);

  // 拉取分组列表供多选关联
  useEffect(() => {
    get<unknown>("/user/token/group/list", {
      params: { page: 1, page_size: 100 },
    })
      .then((data) => {
        if (Array.isArray(data)) {
          setGroups(data);
        } else if (data && typeof data === "object") {
          const d = data as Record<string, unknown>;
          setGroups((d.items ?? d.groups ?? d.list ?? []) as TokenGroup[]);
        }
      })
      .catch(() => {});
  }, []);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (primaryId === null) {
      toast.warning(t("apiKeys.pleaseSelectGroup"));
      return;
    }
    setSubmitting(true);
    try {
      const data = await post<unknown>("/user/token/create", {
        label: label.trim(),
        group_ids: [primaryId /*, ...fallbackIds*/],
      });
      const key = pickNewKey(data);
      toast.success(t("apiKeys.createSuccess"));
      onCreated(key);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t("apiKeys.createFailed"));
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
        className="w-full max-w-lg rounded-xl border bg-background p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-base font-semibold">{t("apiKeys.createTitle")}</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          {t("apiKeys.createDesc")}
        </p>
        <form onSubmit={onSubmit} className="mt-5 space-y-3">
          <div className="space-y-1.5">
            <label htmlFor="create-label" className="text-sm font-medium">
              {t("apiKeys.labelField")}
            </label>
            <Input
              id="create-label"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              placeholder={t("apiKeys.labelPlaceholder")}
              autoComplete="off"
            />
          </div>
          <GroupBindingFields
            groups={groups}
            primaryId={primaryId}
            // fallbackIds={fallbackIds}
            onPrimaryChange={setPrimaryId}
            // onFallbackChange={setFallbackIds}
          />
          <div className="flex justify-end gap-2 pt-1">
            <Button type="button" variant="outline" onClick={onClose}>
              {t("apiKeys.cancel")}
            </Button>
            <Button type="submit" disabled={submitting}>
              {submitting && <Loading size="sm" />}
              {t("apiKeys.create")}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}

/** 编辑分组绑定弹窗：整体替换密钥的有序分组绑定 */
function EditGroupsDialog({
  item,
  onClose,
  onSaved,
}: {
  item: ApiKeyItem;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { t } = useTranslation("console");
  const [groups, setGroups] = useState<TokenGroup[]>([]);
  // 有序分组绑定：首个为主分组（兜底分组逻辑已注释）
  const [primaryId, setPrimaryId] = useState<number | null>(
    () => item.groups[0]?.id ?? null
  );
  // const [fallbackIds, setFallbackIds] = useState<number[]>(() =>
  //   item.groups.slice(1).map((g) => g.id)
  // );
  const [submitting, setSubmitting] = useState(false);

  // 拉取当前用户可绑定的全部启用分组
  useEffect(() => {
    get<unknown>("/user/token/group/list")
      .then((data) => {
        if (Array.isArray(data)) {
          setGroups(data);
        } else if (data && typeof data === "object") {
          const d = data as Record<string, unknown>;
          setGroups((d.items ?? d.groups ?? d.list ?? []) as TokenGroup[]);
        }
      })
      .catch(() => {});
  }, []);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (primaryId === null) {
      toast.warning(t("apiKeys.pleaseSelectGroup"));
      return;
    }
    setSubmitting(true);
    try {
      await post("/user/token/groups/update", {
        token_id: item.id,
        group_ids: [primaryId /*, ...fallbackIds*/],
      });
      toast.success(t("apiKeys.groupsUpdated"));
      onSaved();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t("apiKeys.updateFailed"));
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
        className="w-full max-w-lg rounded-xl border bg-background p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-base font-semibold">{t("apiKeys.editGroupsTitle")}</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          {t("apiKeys.editGroupsDesc", { name: item.label || t("apiKeys.unnamed") })}
        </p>
        <form onSubmit={onSubmit} className="mt-5 space-y-3">
          <GroupBindingFields
            groups={groups}
            primaryId={primaryId}
            // fallbackIds={fallbackIds}
            onPrimaryChange={setPrimaryId}
            // onFallbackChange={setFallbackIds}
          />
          <div className="flex justify-end gap-2 pt-1">
            <Button type="button" variant="outline" onClick={onClose}>
              {t("apiKeys.cancel")}
            </Button>
            <Button type="submit" disabled={submitting}>
              {submitting && <Loading size="sm" />}
              {t("apiKeys.save")}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}

/** 删除 API 密钥确认弹窗 */
function DeleteApiKeyDialog({
  item,
  onClose,
  onDeleted,
}: {
  item: ApiKeyItem;
  onClose: () => void;
  onDeleted: () => void;
}) {
  const { t } = useTranslation("console");
  const [submitting, setSubmitting] = useState(false);

  const onConfirm = async () => {
    setSubmitting(true);
    try {
      await post<unknown>("/user/token/delete", { token_id: item.id });
      toast.success(t("apiKeys.deleteSuccess"));
      onDeleted();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t("apiKeys.deleteFailed"));
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
        <h2 className="text-base font-semibold">{t("apiKeys.deleteTitle")}</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          {t("apiKeys.deleteConfirmPrefix")}
          <span className="text-destructive"> {t("apiKeys.deleteConfirmHighlight")}</span>
          {t("apiKeys.deleteConfirmSuffix", { name: item.label || t("apiKeys.unnamed") })}
        </p>
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="outline" onClick={onClose}>
            {t("apiKeys.cancel")}
          </Button>
          <Button variant="destructive" disabled={submitting} onClick={onConfirm}>
            {submitting && <Loading size="sm" />}
            {t("apiKeys.confirmDelete")}
          </Button>
        </div>
      </div>
    </div>
  );
}

export function ApiKeysPanel() {
  const { t, i18n } = useTranslation("console");
  const locale = i18n.language === "zh" ? "zh-CN" : "en-US";
  const [apiKeys, setApiKeys] = useState<ApiKeyItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [createOpen, setCreateOpen] = useState(false);
  const [editingGroups, setEditingGroups] = useState<ApiKeyItem | null>(null);
  const [deleting, setDeleting] = useState<ApiKeyItem | null>(null);
  const [togglingId, setTogglingId] = useState<string | null>(null);
  const [result, setResult] = useState<{ title: string; keyValue: string } | null>(
    null
  );

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const load = useCallback(async (p: number) => {
    setLoading(true);
    setError("");
    try {
      const data = await get<unknown>("/user/token/list", {
        params: { page: p, page_size: PAGE_SIZE },
      });
      const { items, total } = normalize(data);
      // 删除后当前页可能已无数据，回退一页
      if (items.length === 0 && p > 1) {
        setPage(p - 1);
        return;
      }
      setApiKeys(items);
      setTotal(total);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("apiKeys.loadFailed"));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    load(page);
  }, [load, page]);

  const showResult = (title: string, keyValue: string) => {
    if (keyValue) setResult({ title, keyValue });
    load(page);
  };

  /** 启用/禁用切换 */
  const toggleEnabled = async (item: ApiKeyItem) => {
    setTogglingId(item.id);
    try {
      await post(
        item.enabled ? "/user/token/disable" : "/user/token/enable",
        { token_id: item.id }
      );
      toast.success(item.enabled ? t("apiKeys.disabledToast") : t("apiKeys.enabledToast"));
      load(page);
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : item.enabled ? t("apiKeys.disableFailed") : t("apiKeys.enableFailed")
      );
    } finally {
      setTogglingId(null);
    }
  };

  return (
    <div className="flex min-h-[calc(100vh-7.5rem)] w-full flex-col gap-6">
      {/* 页头（shrink-0 防止列表高度不足时按钮被压缩裁剪） */}
      <div className="flex shrink-0 items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold">{t("apiKeys.title")}</h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            {t("apiKeys.totalKeys", { total })}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            className="whitespace-nowrap"
            onClick={() => load(page)}
            disabled={loading}
          >
            <RefreshCw className={cn("size-4", loading && "animate-spin")} />
            {t("apiKeys.refresh")}
          </Button>
          <Button
            size="sm"
            className="whitespace-nowrap"
            onClick={() => setCreateOpen(true)}
          >
            <Plus className="size-4" />
            {t("apiKeys.createKey")}
          </Button>
        </div>
      </div>

      {/* 密钥列表 */}
      <div className="relative overflow-hidden rounded-xl border border-border/60 bg-card/40">
        {error && apiKeys.length === 0 ? (
          <div className="flex flex-col items-center gap-2 py-16 text-sm text-muted-foreground">
            <p>{t("apiKeys.loadFailedWithReason", { error })}</p>
            <Button variant="outline" size="sm" onClick={() => load(page)}>
              {t("apiKeys.retry")}
            </Button>
          </div>
        ) : apiKeys.length === 0 ? (
          <div className="flex items-center justify-center py-16 text-muted-foreground">
            {loading ? (
              <Loading size="lg" />
            ) : (
              <div className="flex flex-col items-center gap-2">
                <KeyRound className="size-8 text-muted-foreground/50" />
                <p className="text-sm">{t("apiKeys.empty")}</p>
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
                  <th className="px-6 py-3 text-left font-medium">{t("apiKeys.colLabel")}</th>
                  <th className="px-6 py-3 text-left font-medium">{t("apiKeys.colKey")}</th>
                  <th className="px-6 py-3 text-left font-medium">{t("apiKeys.colGroups")}</th>
                  <th className="px-6 py-3 font-medium">{t("apiKeys.colStatus")}</th>
                  <th className="px-6 py-3 font-medium">{t("apiKeys.colCreatedAt")}</th>
                  <th className="px-6 py-3 font-medium">{t("apiKeys.colLastUsed")}</th>
                  <th className="sticky right-0 z-20 bg-muted shadow-[-10px_0_12px_-10px_rgba(0,0,0,0.12)] px-6 py-3 font-medium">
                    {t("apiKeys.colActions")}
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/60">
                {apiKeys.map((item) => (
                  <tr key={item.id} className="transition-colors hover:bg-accent/40">
                    <td className="px-6 py-3 font-medium">
                      {item.label || <span className="text-muted-foreground">{t("apiKeys.unnamed")}</span>}
                    </td>
                    <td className="px-6 py-3">
                      <div className="flex items-center gap-1.5">
                        <span
                          className="cursor-pointer select-all font-mono text-xs text-muted-foreground hover:text-foreground"
                          title={t("apiKeys.clickToSelect")}
                        >
                          {item.preview || "-"}
                        </span>
                        <CopyButton
                          value={item.preview}
                          onClick={() => copyToken(t, item.id)}
                        />
                      </div>
                    </td>
                    <td className="px-6 py-3">
                      {item.groups.length > 0 ? (
                        <div className="flex flex-wrap gap-1.5">
                          {item.groups.map((g) => (
                            <div
                              key={g.id}
                              className="flex max-w-64 flex-col gap-0.5 rounded-lg border border-border/60 bg-muted/30 px-2 py-1.5"
                            >
                              <div className="flex items-center gap-1.5">
                                <span
                                  className="truncate text-xs font-medium"
                                  title={g.name}
                                >
                                  {g.name}
                                </span>
                                <span
                                  className={cn(
                                    "inline-flex shrink-0 items-center rounded-md border px-1.5 py-0 font-mono text-[11px] font-medium leading-4",
                                    multiplierBadgeClass(g.price_multiplier)
                                  )}
                                >
                                  {formatMultiplier(g.price_multiplier)}
                                </span>
                              </div>
                              {g.description && (
                                <p
                                  className="line-clamp-2 text-[11px] leading-4 text-muted-foreground"
                                  title={g.description}
                                >
                                  {g.description}
                                </p>
                              )}
                            </div>
                          ))}
                        </div>
                      ) : (
                        <span className="text-muted-foreground">-</span>
                      )}
                    </td>
                    <td className="px-6 py-3 text-center">
                      <Badge
                        variant={
                          item.revoked
                            ? "destructive"
                            : item.enabled
                              ? "default"
                              : "secondary"
                        }
                      >
                        {item.revoked ? t("apiKeys.statusRevoked") : item.enabled ? t("apiKeys.statusEnabled") : t("apiKeys.statusDisabled")}
                      </Badge>
                    </td>
                    <td className="px-6 py-3 text-center text-muted-foreground">
                      {formatTime(item.created_at, locale)}
                    </td>
                    <td className="px-6 py-3 text-center text-muted-foreground">
                      {formatTime(item.last_used_at, locale)}
                    </td>
                    <td className="sticky right-0 bg-card shadow-[-10px_0_12px_-10px_rgba(0,0,0,0.12)] px-6 py-3 text-center">
                      <div className="flex items-center justify-center gap-1.5">
                        <Button
                          variant="outline"
                          size="sm"
                          disabled={item.revoked}
                          onClick={() => setEditingGroups(item)}
                        >
                          <Layers className="size-4" />
                          {t("apiKeys.groupsAction")}
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          className={
                            item.enabled
                              ? "text-warning hover:bg-warning/10 hover:text-warning"
                              : "text-success hover:bg-success/10 hover:text-success"
                          }
                          disabled={item.revoked || togglingId === item.id}
                          onClick={() => toggleEnabled(item)}
                        >
                          {togglingId === item.id ? (
                            <Loading size="sm" />
                          ) : item.enabled ? (
                            <Ban className="size-4" />
                          ) : (
                            <CircleCheck className="size-4" />
                          )}
                          {item.enabled ? t("apiKeys.disable") : t("apiKeys.enable")}
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          className="text-destructive hover:bg-destructive/10 hover:text-destructive"
                          onClick={() => setDeleting(item)}
                        >
                          <Trash2 className="size-4" />
                          {t("apiKeys.delete")}
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            </div>
            {loading && (
              <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
                <Loading size="md" />
              </div>
            )}
          </>
        )}
      </div>

      {/* 分页：mt-auto 固定吸底，不随列表高度跳动 */}
      {!error && apiKeys.length > 0 && (
        <Pagination
          page={page}
          totalPages={totalPages}
          loading={loading}
          onChange={setPage}
          className="mt-auto"
        />
      )}

      {createOpen && (
        <CreateApiKeyDialog
          onClose={() => setCreateOpen(false)}
          onCreated={(key) => {
            setCreateOpen(false);
            showResult(t("apiKeys.createSuccess"), key);
          }}
        />
      )}
      {editingGroups && (
        <EditGroupsDialog
          item={editingGroups}
          onClose={() => setEditingGroups(null)}
          onSaved={() => {
            setEditingGroups(null);
            load(page);
          }}
        />
      )}
      {deleting && (
        <DeleteApiKeyDialog
          item={deleting}
          onClose={() => setDeleting(null)}
          onDeleted={() => {
            setDeleting(null);
            load(page);
          }}
        />
      )}
      {result && (
        <KeyResultDialog
          title={result.title}
          keyValue={result.keyValue}
          onClose={() => setResult(null)}
        />
      )}
    </div>
  );
}
