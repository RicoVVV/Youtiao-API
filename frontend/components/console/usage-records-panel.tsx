"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Check,
  Copy,
  Eye,
  RefreshCw,
  ScrollText,
  Search,
  X,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Loading } from "@/components/ui/loading";
import { Pagination } from "@/components/ui/pagination";
import { Select } from "@/components/ui/select";
import { toast } from "@/components/ui/toaster";
import { cn } from "@/lib/utils";
import { get } from "@/lib/request";

/** 使用记录列表项：金额为小数字符串；管理员额外返回用户名/渠道 */
type UsageRecordItem = {
  id: string;
  request_type: string;
  token_display_name: string | null;
  model_name: string;
  status: string;
  amount: string;
  created_at: string | null;
  started_at: string | null;
  completed_at: string | null;
  duration_ms: number | null;
  first_token_duration_ms?: number | null;
  prompt_tokens?: number | null;
  completion_tokens?: number | null;
  cached_tokens?: number | null;
  username?: string;
  channel_name?: string;
};

/** 详情在列表字段基础上增加请求标识、请求体和响应载荷 */
type UsageRecordDetail = UsageRecordItem & {
  request_id: string;
  upstream_task_id: string | null;
  request_payload: Record<string, unknown>;
  public_response_payload: Record<string, unknown> | null;
  upstream_response_payload?: Record<string, unknown> | null;
};

const PAGE_SIZE = 20;

const STATUS_META: Record<
  string,
  {
    variant: "default" | "secondary" | "destructive" | "outline";
    className?: string;
  }
> = {
  reserved: {
    variant: "outline",
    className: "border-amber-500/40 bg-amber-500/10 text-amber-600 dark:text-amber-400",
  },
  succeeded: {
    variant: "outline",
    className: "border-emerald-500/40 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400",
  },
  failed: {
    variant: "outline",
    className: "border-red-500/40 bg-red-500/10 text-red-600 dark:text-red-400",
  },
  refunded: {
    variant: "outline",
    className: "border-sky-500/40 bg-sky-500/10 text-sky-600 dark:text-sky-400",
  },
};

const REQUEST_TYPE_META: Record<string, { className: string }> = {
  video: {
    className: "border-violet-500/40 bg-violet-500/10 text-violet-600 dark:text-violet-400",
  },
  image: {
    className: "border-pink-500/40 bg-pink-500/10 text-pink-600 dark:text-pink-400",
  },
  text: {
    className: "border-cyan-500/40 bg-cyan-500/10 text-cyan-600 dark:text-cyan-400",
  },
  channel_test: {
    className: "border-amber-500/40 bg-amber-500/10 text-amber-600 dark:text-amber-400",
  },
};

const STATUS_VALUES = ["", "reserved", "succeeded", "failed", "refunded"];
const REQUEST_TYPE_VALUES = ["", "video", "image", "text", "channel_test"];

const formatTime = (value: string | null, locale: string) =>
  value ? new Date(value).toLocaleString(locale, { hour12: false }) : "—";

/** 金额展示：纯字符串补齐六位小数（"12.5" → "¥12.500000"），不做数值运算 */
const formatYuan = (amount: string) => {
  const [intPart = "0", fracPart = ""] = String(amount).trim().split(".");
  return `$${intPart}.${`${fracPart}000000`.slice(0, 6)}`;
};

type Translate = (key: string, options?: Record<string, unknown>) => string;

/** 耗时展示：优先 duration_ms 格式化为秒/分秒；进行中兜底；其余显示 - */
const formatDuration = (
  t: Translate,
  durationMs: number | null,
  startedAt: string | null,
  completedAt: string | null
) => {
  if (durationMs != null) {
    return formatDurationValue(t, durationMs);
  }
  if (startedAt && !completedAt) return t("usageRecords.inProgress");
  return "-";
};

/** 耗时数值格式化：19.5 秒 / 12 分 10 秒 */
const formatDurationValue = (t: Translate, durationMs: number) => {
  if (durationMs < 1000) return t("usageRecords.durationMs", { value: durationMs });
  const totalSeconds = durationMs / 1000;
  if (totalSeconds < 60)
    return t("usageRecords.durationSeconds", { value: totalSeconds.toFixed(1) });
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = Math.round(totalSeconds % 60);
  return seconds
    ? t("usageRecords.durationMinutesSeconds", { minutes, seconds })
    : t("usageRecords.durationMinutes", { minutes });
};

/** 复制文本：优先 Clipboard API，非安全上下文（HTTP/IP 访问）时降级 execCommand */
async function copyText(value: string): Promise<boolean> {
  if (navigator.clipboard && window.isSecureContext) {
    await navigator.clipboard.writeText(value);
    return true;
  }
  const textarea = document.createElement("textarea");
  textarea.value = value;
  textarea.style.position = "fixed";
  textarea.style.opacity = "0";
  document.body.appendChild(textarea);
  textarea.select();
  try {
    return document.execCommand("copy");
  } finally {
    document.body.removeChild(textarea);
  }
}

/** 复制按钮：复制成功后短暂显示对勾 */
function CopyButton({
  value,
  className,
  title,
}: {
  value: string;
  className?: string;
  title: string;
}) {
  const { t } = useTranslation("console");
  const [copied, setCopied] = useState(false);

  const onCopy = async () => {
    try {
      if (!(await copyText(value))) throw new Error();
      setCopied(true);
      toast.success(t("usageRecords.copySuccess"));
      setTimeout(() => setCopied(false), 1500);
    } catch {
      toast.error(t("usageRecords.copyFailed"));
    }
  };

  return (
    <Button
      type="button"
      variant="ghost"
      size="icon"
      className={className}
      onClick={onCopy}
      title={title}
      aria-label={title}
    >
      {copied ? (
        <Check className="size-4 text-success" />
      ) : (
        <Copy className="size-4" />
      )}
    </Button>
  );
}

/** 状态徽标：未知状态按原始字符串展示，避免限制后续新增状态 */
function StatusBadge({ status }: { status: string }) {
  const { t } = useTranslation("console");
  const meta = STATUS_META[status];
  if (!meta) return <Badge variant="outline">{status}</Badge>;
  return (
    <Badge variant={meta.variant} className={meta.className}>
      {t(`usageRecords.status.${status}`)}
    </Badge>
  );
}

/** 请求类型徽标：映射为本地化标签并着色，未映射类型显示原始值 */
function RequestTypeBadge({ type }: { type: string }) {
  const { t } = useTranslation("console");
  const meta = REQUEST_TYPE_META[type];
  if (!meta) return <Badge variant="outline">{type}</Badge>;
  return (
    <Badge variant="outline" className={meta.className}>
      {t(`usageRecords.requestTypeBadge.${type}`)}
    </Badge>
  );
}

/** 只读 JSON 查看块：仅展示，不提供编辑 */
function JsonBlock({
  title,
  value,
  hint,
}: {
  title: string;
  value: Record<string, unknown> | null;
  hint?: string;
}) {
  const { t } = useTranslation("console");
  const text = useMemo(
    () => (value ? JSON.stringify(value, null, 2) : ""),
    [value]
  );

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between">
        <p className="text-sm font-medium">{title}</p>
        {value && (
          <CopyButton
            value={text}
            className="size-6"
            title={t("usageRecords.copyBlock", { title })}
          />
        )}
      </div>
      {value ? (
        <pre className="max-h-64 overflow-auto rounded-lg border border-border/60 bg-muted/40 p-3 font-mono text-xs leading-relaxed break-all whitespace-pre-wrap">
          {text}
        </pre>
      ) : (
        <p className="text-sm text-muted-foreground">—</p>
      )}
      {hint && <p className="text-xs text-muted-foreground/80">{hint}</p>}
    </div>
  );
}

/** 使用记录详情弹窗：打开后才请求详情接口，请求体/响应载荷仅在弹窗内展示 */
function RecordDialog({
  id,
  isAdmin,
  onClose,
}: {
  id: string;
  isAdmin: boolean;
  onClose: () => void;
}) {
  const { t } = useTranslation("console");
  const [detail, setDetail] = useState<UsageRecordDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = await get<UsageRecordDetail>(
        `${isAdmin ? "/admin" : ""}/usage/records/detail`,
        { params: { usage_record_id: id } }
      );
      setDetail(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("usageRecords.loadFailed"));
    } finally {
      setLoading(false);
    }
  }, [id, isAdmin, t]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-[80] flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="flex max-h-[85vh] w-full max-w-xl flex-col rounded-xl border border-border/60 bg-background shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-border/60 px-6 py-4">
          <h2 className="text-base font-semibold">{t("usageRecords.detailTitle")}</h2>
          <Button
            variant="ghost"
            size="icon"
            onClick={onClose}
            aria-label={t("usageRecords.closeDetail")}
          >
            <X className="size-4" />
          </Button>
        </div>

        <div className="flex-1 space-y-5 overflow-y-auto px-6 py-5">
          {loading ? (
            <div className="flex justify-center py-16">
              <Loading size="lg" />
            </div>
          ) : error ? (
            <div className="flex flex-col items-center gap-2 py-16 text-sm text-muted-foreground">
              <p>{t("usageRecords.loadFailedWithReason", { error })}</p>
              <Button variant="outline" size="sm" onClick={load}>
                {t("usageRecords.retry")}
              </Button>
            </div>
          ) : detail ? (
            <>
              <div className="flex items-center justify-between gap-4 text-sm">
                <span className="shrink-0 text-muted-foreground">
                  {t("usageRecords.requestId")}
                </span>
                <span className="flex min-w-0 items-center gap-0.5">
                  <code
                    className="truncate font-mono text-xs"
                    title={detail.request_id}
                  >
                    {detail.request_id}
                  </code>
                  <CopyButton
                    value={detail.request_id}
                    className="size-6 shrink-0"
                    title={t("usageRecords.copyRequestId")}
                  />
                </span>
              </div>
              {isAdmin && detail.upstream_task_id && (
                <div className="flex items-center justify-between gap-4 text-sm">
                  <span className="shrink-0 text-muted-foreground">
                    {t("usageRecords.upstreamTaskId")}
                  </span>
                  <span className="flex min-w-0 items-center gap-0.5">
                    <code
                      className="truncate font-mono text-xs"
                      title={detail.upstream_task_id}
                    >
                      {detail.upstream_task_id}
                    </code>
                    <CopyButton
                      value={detail.upstream_task_id}
                      className="size-6 shrink-0"
                      title={t("usageRecords.copyUpstreamTaskId")}
                    />
                  </span>
                </div>
              )}

              <JsonBlock
                title={t("usageRecords.requestPayload")}
                value={detail.request_payload}
                hint={t("usageRecords.requestPayloadHint")}
              />
              <JsonBlock
                title={t("usageRecords.responsePayload")}
                value={detail.public_response_payload}
              />
              {isAdmin && (
                <JsonBlock
                  title={t("usageRecords.upstreamResponsePayload")}
                  value={detail.upstream_response_payload ?? null}
                />
              )}
            </>
          ) : null}
        </div>
      </div>
    </div>
  );
}

export function UsageRecordsPanel() {
  const { t, i18n } = useTranslation("console");
  const locale = i18n.language === "zh" ? "zh-CN" : "en-US";
  /** 角色未知时不发列表请求，避免管理员看到用户视角数据 */
  const [isAdmin, setIsAdmin] = useState<boolean | null>(null);
  const [records, setRecords] = useState<UsageRecordItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [requestTypeFilter, setRequestTypeFilter] = useState("");
  const [modelFilter, setModelFilter] = useState("");
  const [tokenFilter, setTokenFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [usernameFilter, setUsernameFilter] = useState("");
  const [detailId, setDetailId] = useState<string | null>(null);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const statusOptions = useMemo(
    () =>
      STATUS_VALUES.map((value) => ({
        value,
        label: t(`usageRecords.status.${value || "all"}`),
      })),
    [t]
  );
  const requestTypeOptions = useMemo(
    () =>
      REQUEST_TYPE_VALUES.map((value) => ({
        value,
        label: t(`usageRecords.requestType.${value || "all"}`),
      })),
    [t]
  );

  useEffect(() => {
    get<{ is_admin: boolean }>("/user/info")
      .then((p) => setIsAdmin(p.is_admin))
      .catch(() => setIsAdmin(false));
  }, []);

  const load = useCallback(
    async (p: number) => {
      if (isAdmin === null) return;
      setLoading(true);
      setError("");
      try {
        const data = await get<{ items: UsageRecordItem[]; total: number }>(
          `${isAdmin ? "/admin" : ""}/usage/records/list`,
          {
            params: {
              page: p,
              page_size: PAGE_SIZE,
              request_type: requestTypeFilter.trim() || undefined,
              model_name: modelFilter.trim() || undefined,
              token_display_name: tokenFilter.trim() || undefined,
              status: statusFilter || undefined,
              ...(isAdmin
                ? {
                    username: usernameFilter.trim() || undefined,
                  }
                : {}),
            },
          }
        );
        setRecords(data.items);
        setTotal(data.total);
      } catch (err) {
        setError(err instanceof Error ? err.message : t("usageRecords.loadFailed"));
      } finally {
        setLoading(false);
      }
    },
    [
      isAdmin,
      requestTypeFilter,
      modelFilter,
      tokenFilter,
      statusFilter,
      usernameFilter,
      t,
    ]
  );

  useEffect(() => {
    load(page);
  }, [load, page]);

  const onSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setPage(1);
    load(1);
  };

  return (
    <div className="flex min-h-[calc(100vh-7.5rem)] w-full flex-col gap-6">
      {/* 页头 */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold">{t("usageRecords.title")}</h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            {t("usageRecords.totalRecords", { total })}
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => load(page)}
          disabled={loading}
        >
          <RefreshCw className={cn("size-4", loading && "animate-spin")} />
          {t("usageRecords.refresh")}
        </Button>
      </div>

      {/* 筛选：管理员额外支持按用户名筛选 */}
      <form
        onSubmit={onSearch}
        className="flex flex-wrap items-center gap-3 rounded-xl border border-border/60 bg-card/40 p-4"
      >
        <Select
          value={requestTypeFilter}
          onValueChange={(v) => {
            setRequestTypeFilter(v);
            setPage(1);
          }}
          options={requestTypeOptions}
          className="w-auto"
          aria-label={t("usageRecords.filterByType")}
        />
        <Input
          value={modelFilter}
          onChange={(e) => setModelFilter(e.target.value)}
          placeholder={t("usageRecords.filterByModel")}
          className="w-44"
        />
        <Input
          value={tokenFilter}
          onChange={(e) => setTokenFilter(e.target.value)}
          placeholder={t("usageRecords.filterByToken")}
          className="w-44"
        />
        <Select
          value={statusFilter}
          onValueChange={(v) => {
            setStatusFilter(v);
            setPage(1);
          }}
          options={statusOptions}
          className="w-auto"
          aria-label={t("usageRecords.filterByStatus")}
        />
        {isAdmin && (
          <Input
            value={usernameFilter}
            onChange={(e) => setUsernameFilter(e.target.value)}
            placeholder={t("usageRecords.filterByUsername")}
            className="w-44"
          />
        )}
        <Button type="submit" size="sm" variant="outline" disabled={loading}>
          <Search className="size-4" />
          {t("usageRecords.search")}
        </Button>
      </form>

      {/* 使用记录列表 */}
      <div className="relative overflow-hidden rounded-xl border border-border/60 bg-card/40">
        {error && records.length === 0 ? (
          <div className="flex flex-col items-center gap-2 py-16 text-sm text-muted-foreground">
            <p>{t("usageRecords.loadFailedWithReason", { error })}</p>
            <Button variant="outline" size="sm" onClick={() => load(page)}>
              {t("usageRecords.retry")}
            </Button>
          </div>
        ) : records.length === 0 ? (
          <div className="flex items-center justify-center py-16 text-muted-foreground">
            {loading ? (
              <Loading size="lg" />
            ) : (
              <div className="flex flex-col items-center gap-2">
                <ScrollText className="size-8 text-muted-foreground/50" />
                <p className="text-sm">{t("usageRecords.empty")}</p>
              </div>
            )}
          </div>
        ) : (
          <>
            {/* 加载中保留旧数据并降低透明度，避免表格整体闪烁 */}
            {/* 列过多时允许横向滚动，避免操作列被挤压消失 */}
            <div className="overflow-x-auto">
            <table
              className={cn(
                "w-full min-w-max text-sm transition-opacity duration-300",
                loading && "pointer-events-none opacity-40"
              )}
            >
              <thead>
                <tr className="border-b border-border/60 bg-muted/40 text-center text-xs text-muted-foreground">
                  <th className="px-6 py-3 text-left font-medium">{t("usageRecords.colCreatedAt")}</th>
                  {isAdmin && (
                    <th className="px-6 py-3 font-medium">{t("usageRecords.colUsername")}</th>
                  )}
                  <th className="px-6 py-3 font-medium">{t("usageRecords.colType")}</th>
                  <th className="px-6 py-3 text-left font-medium">{t("usageRecords.colModel")}</th>
                  <th className="px-6 py-3 font-medium">{t("usageRecords.colToken")}</th>
                  {isAdmin && <th className="px-6 py-3 font-medium">{t("usageRecords.colChannel")}</th>}
                  <th className="px-6 py-3 font-medium">{t("usageRecords.colStatus")}</th>
                  <th className="px-6 py-3 font-medium">Tokens</th>
                  <th className="px-6 py-3 font-medium">{t("usageRecords.colAmount")}</th>
                  <th className="px-6 py-3 font-medium">{t("usageRecords.colDuration")}</th>
                  <th className="sticky right-0 z-20 bg-muted shadow-[-10px_0_12px_-10px_rgba(0,0,0,0.12)] px-6 py-3 font-medium">
                    {t("usageRecords.colActions")}
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/60">
                {records.map((item) => (
                  <tr
                    key={item.id}
                    className="transition-colors hover:bg-accent/40"
                  >
                    <td className="px-6 py-3 whitespace-nowrap text-muted-foreground">
                      {formatTime(item.created_at, locale)}
                    </td>
                    {isAdmin && (
                      <td className="max-w-32 truncate px-6 py-3 text-center" title={item.username || undefined}>
                        {item.username || (
                          <span className="text-muted-foreground">—</span>
                        )}
                      </td>
                    )}
                    <td className="px-6 py-3 text-center">
                      <RequestTypeBadge type={item.request_type} />
                    </td>
                    <td className="max-w-40 truncate px-6 py-3" title={item.model_name}>
                      {item.model_name}
                    </td>
                    <td className="max-w-40 truncate px-6 py-3 text-center" title={item.token_display_name || undefined}>
                      {item.token_display_name || (
                        <span className="text-muted-foreground">—</span>
                      )}
                    </td>
                    {isAdmin && (
                      <td className="max-w-32 truncate px-6 py-3 text-center" title={item.channel_name || undefined}>
                        {item.channel_name || (
                          <span className="text-muted-foreground">—</span>
                        )}
                      </td>
                    )}
                    <td className="px-6 py-3 text-center">
                      <StatusBadge status={item.status} />
                    </td>
                    <td className="px-6 py-3 text-center font-mono text-xs">
                      <div>
                        {(item.prompt_tokens ?? 0).toLocaleString()} /{" "}
                        {(item.completion_tokens ?? 0).toLocaleString()}
                      </div>
                      {item.cached_tokens != null && item.cached_tokens > 0 && (
                        <div className="text-muted-foreground/70">
                          {t("usageRecords.cachedTokens", { count: item.cached_tokens.toLocaleString() })}
                        </div>
                      )}
                    </td>
                    <td className="px-6 py-3 text-center font-mono text-xs">
                      {formatYuan(item.amount)}
                    </td>
                    <td className="px-6 py-3 text-center whitespace-nowrap text-muted-foreground">
                      {item.request_type === "text" ? (
                        <div className="flex flex-col items-center gap-0.5 text-xs">
                          <span className="flex items-center gap-1">
                            <span className="inline-block h-3 w-0.5 rounded-full bg-emerald-500" />
                            {t("usageRecords.firstToken")} {item.first_token_duration_ms != null ? formatDurationValue(t, item.first_token_duration_ms) : "-"}
                          </span>
                          <span className="flex items-center gap-1">
                            <span className="inline-block h-3 w-0.5 rounded-full bg-red-500" />
                            {t("usageRecords.durationLabel")} {formatDuration(
                              t,
                              item.duration_ms,
                              item.started_at,
                              item.completed_at
                            )}
                          </span>
                        </div>
                      ) : (
                        formatDuration(
                          t,
                          item.duration_ms,
                          item.started_at,
                          item.completed_at
                        )
                      )}
                    </td>
                    <td className="sticky right-0 bg-card shadow-[-10px_0_12px_-10px_rgba(0,0,0,0.12)] px-6 py-3 text-center">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setDetailId(item.id)}
                      >
                        <Eye className="size-4" />
                        {t("usageRecords.detail")}
                      </Button>
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
      {!error && records.length > 0 && (
        <Pagination
          page={page}
          totalPages={totalPages}
          loading={loading}
          onChange={setPage}
          className="mt-auto"
        />
      )}

      {detailId && isAdmin !== null && (
        <RecordDialog
          id={detailId}
          isAdmin={isAdmin}
          onClose={() => setDetailId(null)}
        />
      )}
    </div>
  );
}
