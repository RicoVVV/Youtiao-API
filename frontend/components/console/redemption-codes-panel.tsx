"use client";

import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Ban,
  Check,
  CircleCheck,
  Copy,
  Download,
  Eye,
  Pencil,
  Plus,
  RefreshCw,
  Search,
  Ticket as TicketIcon,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Loading } from "@/components/ui/loading";
import { Pagination } from "@/components/ui/pagination";
import { Select } from "@/components/ui/select";
import { DateTimePicker } from "@/components/ui/datetime-picker";
import { toast } from "@/components/ui/toaster";
import { cn } from "@/lib/utils";
import { ApiError, get, getToken, pickErrorMessage, post } from "@/lib/request";

type CodeStatus = "unused" | "disabled" | "expired" | "redeemed";

type RedemptionCodeItem = {
  id: string;
  name: string | null;
  remark: string | null;
  /** 完整明文（仅创建响应返回），列表项不含此字段 */
  code?: string;
  /** 面额，单位元，后端以字符串返回 */
  amount: string;
  status: CodeStatus;
  active: boolean;
  expires_at: string | null;
  redeemed_by_user_id: string | null;
  redeemed_at: string | null;
  created_at: string;
};

type CreatedCode = RedemptionCodeItem;

/** 兑换码脱敏展示：保留前缀，其余省略；无明文时返回占位符 */
const maskCode = (code?: string) =>
  code ? (code.length > 10 ? `${code.slice(0, 10)}…` : code) : "—";

const PAGE_SIZE = 100;

const STATUS_VARIANT: Record<
  CodeStatus,
  "default" | "secondary" | "destructive" | "outline"
> = {
  unused: "default",
  disabled: "secondary",
  expired: "outline",
  redeemed: "destructive",
};

const STATUS_OPTIONS: ("" | CodeStatus)[] = [
  "",
  "unused",
  "disabled",
  "expired",
  "redeemed",
];

type Translate = (key: string, options?: Record<string, unknown>) => string;

/** 金额展示：纯字符串截取两位小数（"0.500000" → "¥0.50"），不做数值运算 */
const formatYuan = (amount: string | number) => {
  const [intPart = "0", fracPart = ""] = String(amount).trim().split(".");
  return `$${intPart}.${`${fracPart}00`.slice(0, 2)}`;
};

/**
 * 输入金额规范化：0.5 / 0.50 / 1 均按"元"理解，统一输出 6 位小数字符串（"0.500000"）。
 * 纯字符串处理，禁止转分或用 JS number 做金额计算。
 */
const normalizeYuan = (raw: string): string | null => {
  const text = raw.trim();
  if (!/^\d+(\.\d{1,6})?$/.test(text)) return null;
  const [intPart, fracPart = ""] = text.split(".");
  // 排除 0 / 0.0 / 0.000000 等零值
  if (!/[1-9]/.test(intPart + fracPart)) return null;
  return `${intPart}.${fracPart.padEnd(6, "0")}`;
};

/** 兑换码状态展示文案 */
const statusLabel = (t: Translate, status: CodeStatus) =>
  t(`redemptionCodes.status.${status}`);

const formatTime = (locale: string, value: string | null) =>
  value
    ? new Date(value).toLocaleString(locale, { hour12: false })
    : "—";

/** datetime-local 值转 ISO 字符串；空值返回 null */
const localToIso = (value: string): string | null =>
  value ? new Date(value).toISOString() : null;

/** ISO 字符串转 datetime-local 输入值 */
const isoToLocal = (value: string | null): string => {
  if (!value) return "";
  const d = new Date(value);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
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

/** 导出兑换码 txt：响应为文件流不走统一信封，无法用 get/post 封装（内部固定 res.json()） */
async function exportRedemptionCodes(
  params: { name?: string; status?: string },
  errorFallback: string
) {
  const query = new URLSearchParams(
    Object.entries(params).filter(([, v]) => v !== undefined) as [string, string][]
  ).toString();
  const res = await fetch(
    `/api/admin/billing/redemption-codes/export${query ? `?${query}` : ""}`,
    {
      method: "GET",
      credentials: "include",
      headers: {
        Authorization: `Bearer ${getToken()}`,
        "X-Locale": window.location.pathname.split("/")[1] === "en" ? "en" : "zh",
      },
    }
  );
  if (!res.ok) {
    // 失败时后端仍返回统一信封 JSON，与 request.ts 的错误解析口径保持一致
    const data = await res.json().catch(() => null);
    throw new ApiError(
      pickErrorMessage(data, `${errorFallback}: ${res.status}`),
      res.status,
      data
    );
  }
  const blob = await res.blob();
  const filename =
    /filename="?([^"]+)"?/.exec(res.headers.get("Content-Disposition") ?? "")?.[1] ??
    "redemption-codes.txt";
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

/** 复制按钮：复制成功后短暂显示对勾 */
function CopyButton({
  value,
  className,
}: {
  value: string;
  className?: string;
}) {
  const [copied, setCopied] = useState(false);
  const { t } = useTranslation("console");

  const onCopy = async () => {
    try {
      if (!(await copyText(value))) throw new Error();
      setCopied(true);
      toast.success(t("redemptionCodes.copiedToast"));
      setTimeout(() => setCopied(false), 1500);
    } catch {
      toast.error(t("redemptionCodes.copyFailedToast"));
    }
  };

  return (
    <Button
      type="button"
      variant="ghost"
      size="icon"
      className={className}
      onClick={onCopy}
      title={t("redemptionCodes.copyCode")}
      aria-label={t("redemptionCodes.copyCode")}
    >
      {copied ? (
        <Check className="size-4 text-success" />
      ) : (
        <Copy className="size-4" />
      )}
    </Button>
  );
}

/** 生成兑换码弹窗：明文仅在本次响应返回，成功后展示并允许复制 */
function CreateCodeDialog({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: () => void;
}) {
  const [name, setName] = useState("");
  const [amount, setAmount] = useState("");
  const [remark, setRemark] = useState("");
  const [expiresAt, setExpiresAt] = useState("");
  const [quantity, setQuantity] = useState("1");
  const [submitting, setSubmitting] = useState(false);
  const [created, setCreated] = useState<CreatedCode[] | null>(null);
  const { t, i18n } = useTranslation("console");
  const locale = i18n.language === "zh" ? "zh-CN" : "en-US";

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmedName = name.trim();
    // 后端 name 为必填，空值会被 422 拒绝，前端先拦截
    if (!trimmedName) {
      toast.warning(t("redemptionCodes.nameRequired"));
      return;
    }
    // 金额全程按元字符串处理：不转分、不用 JS number 计算
    const amountYuan = normalizeYuan(amount);
    if (!amountYuan) {
      toast.warning(t("redemptionCodes.amountInvalid"));
      return;
    }
    const qty = Number(quantity);
    if (!Number.isInteger(qty) || qty < 1 || qty > 1000) {
      toast.warning(t("redemptionCodes.quantityInvalid"));
      return;
    }
    setSubmitting(true);
    try {
      const data = await post<{ items: CreatedCode[]; total: number }>(
        "/admin/billing/redemption-codes/create",
        {
          name: trimmedName,
          amount: amountYuan,
          remark: remark.trim() || undefined,
          expires_at: localToIso(expiresAt),
          quantity: qty,
        }
      );
      // 后端未回显面额时用本次提交值兜底
      setCreated(
        data.items.map((item) => ({ ...item, amount: item.amount || amountYuan }))
      );
      onCreated();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t("redemptionCodes.createFailed"));
    } finally {
      setSubmitting(false);
    }
  };

  /** 复制批量生成的全部明文，一行一个 */
  const onCopyAll = async () => {
    if (!created) return;
    try {
      const text = created.map((item) => item.code).filter(Boolean).join("\n");
      if (!text || !(await copyText(text))) throw new Error();
      toast.success(t("redemptionCodes.copiedToast"));
    } catch {
      toast.error(t("redemptionCodes.copyFailedToast"));
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
        {created ? (
          <>
            <h2 className="text-base font-semibold">{t("redemptionCodes.createSuccessTitle")}</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              {created.length > 1
                ? t("redemptionCodes.batchCreateSuccessDesc", { total: created.length })
                : t("redemptionCodes.createSuccessDesc")}
            </p>
            {created.length === 1 ? (
              <div className="mt-5 flex items-center gap-1 rounded-lg border border-border/60 bg-muted/40 px-3 py-2.5">
                <code className="flex-1 truncate font-mono text-sm">
                  {created[0].code ?? "—"}
                </code>
                {created[0].code && <CopyButton value={created[0].code} />}
              </div>
            ) : (
              <div className="mt-5 rounded-lg border border-border/60 bg-muted/40">
                <div className="flex items-center justify-between gap-2 border-b border-border/60 px-3 py-2">
                  <span className="text-xs text-muted-foreground">
                    {t("redemptionCodes.totalCodes", { total: created.length })}
                  </span>
                  <Button type="button" variant="outline" size="sm" onClick={onCopyAll}>
                    <Copy className="size-4" />
                    {t("redemptionCodes.copyAll")}
                  </Button>
                </div>
                <div className="max-h-48 space-y-1 overflow-y-auto px-3 py-2">
                  {created.map((item) => (
                    <code key={item.id} className="block truncate font-mono text-xs">
                      {item.code}
                    </code>
                  ))}
                </div>
              </div>
            )}
            <dl className="mt-4 space-y-2 text-sm">
              <div className="flex justify-between">
                <dt className="text-muted-foreground">{t("redemptionCodes.amountLabel")}</dt>
                <dd className="font-mono">{formatYuan(created[0].amount)}</dd>
              </div>
              {created[0].name && (
                <div className="flex justify-between">
                  <dt className="text-muted-foreground">{t("redemptionCodes.nameLabel")}</dt>
                  <dd>{created[0].name}</dd>
                </div>
              )}
              <div className="flex justify-between">
                <dt className="text-muted-foreground">{t("redemptionCodes.expiresAtLabel")}</dt>
                <dd>{formatTime(locale, created[0].expires_at)}</dd>
              </div>
            </dl>
            <div className="mt-6 flex justify-end">
              <Button onClick={onClose}>{t("redemptionCodes.done")}</Button>
            </div>
          </>
        ) : (
          <>
            <h2 className="text-base font-semibold">{t("redemptionCodes.createTitle")}</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              {t("redemptionCodes.createDesc")}
            </p>
            <form onSubmit={onSubmit} className="mt-5 space-y-4">
              <div className="space-y-1.5">
                <label htmlFor="code-amount" className="text-sm font-medium">
                  {t("redemptionCodes.amountLabelYuan")}<span className="text-destructive">*</span>
                </label>
                <Input
                  id="code-amount"
                  type="number"
                  min="0.000001"
                  step="0.000001"
                  value={amount}
                  onChange={(e) => setAmount(e.target.value)}
                  placeholder={t("redemptionCodes.amountPlaceholder")}
                />
                <p className="text-xs text-muted-foreground">
                  {t("redemptionCodes.amountHint")}
                </p>
              </div>
              <div className="space-y-1.5">
                <label htmlFor="code-name" className="text-sm font-medium">
                  {t("redemptionCodes.nameLabel")}<span className="text-destructive">*</span>
                </label>
                <Input
                  id="code-name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder={t("redemptionCodes.namePlaceholder")}
                  maxLength={128}
                />
              </div>
              <div className="space-y-1.5">
                <label htmlFor="code-quantity" className="text-sm font-medium">
                  {t("redemptionCodes.quantityLabel")}
                </label>
                <Input
                  id="code-quantity"
                  type="number"
                  min="1"
                  max="1000"
                  step="1"
                  value={quantity}
                  onChange={(e) => setQuantity(e.target.value)}
                />
                <p className="text-xs text-muted-foreground">
                  {t("redemptionCodes.quantityHint")}
                </p>
              </div>
              <div className="space-y-1.5">
                <label htmlFor="code-remark" className="text-sm font-medium">
                  {t("redemptionCodes.remarkLabel")}
                </label>
                <Input
                  id="code-remark"
                  value={remark}
                  onChange={(e) => setRemark(e.target.value)}
                  placeholder={t("redemptionCodes.remarkPlaceholder")}
                  maxLength={512}
                />
              </div>
              <div className="space-y-1.5">
                <label htmlFor="code-expires" className="text-sm font-medium">
                  {t("redemptionCodes.expiresAtLabel")}
                </label>
                <DateTimePicker
                  id="code-expires"
                  value={expiresAt}
                  onChange={setExpiresAt}
                  placeholder={t("redemptionCodes.expiresAtPlaceholder")}
                />
                <p className="text-xs text-muted-foreground">
                  {t("redemptionCodes.expiresAtHint")}
                </p>
              </div>
              <div className="flex justify-end gap-2 pt-1">
                <Button type="button" variant="outline" onClick={onClose}>
                  {t("redemptionCodes.cancel")}
                </Button>
                <Button type="submit" disabled={submitting}>
                  {submitting ? <Loading size="sm" /> : <Plus className="size-4" />}
                  {t("redemptionCodes.generate")}
                </Button>
              </div>
            </form>
          </>
        )}
      </div>
    </div>
  );
}

/** 编辑兑换码运营信息弹窗（仅未兑换的记录可编辑） */
function EditCodeDialog({
  code,
  onClose,
  onSaved,
}: {
  code: RedemptionCodeItem;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [name, setName] = useState(code.name ?? "");
  const [remark, setRemark] = useState(code.remark ?? "");
  const [expiresAt, setExpiresAt] = useState(isoToLocal(code.expires_at));
  const [submitting, setSubmitting] = useState(false);
  const { t } = useTranslation("console");

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      await post("/admin/billing/redemption-codes/update", {
        id: code.id,
        name: name.trim() || null,
        remark: remark.trim() || null,
        expires_at: localToIso(expiresAt),
      });
      toast.success(t("redemptionCodes.updateSuccess"));
      onSaved();
      onClose();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t("redemptionCodes.updateFailed"));
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
        className="w-full max-w-md rounded-xl border bg-background p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-base font-semibold">{t("redemptionCodes.editTitle")}</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          {t("redemptionCodes.editDesc")}
        </p>
        <form onSubmit={onSubmit} className="mt-5 space-y-4">
          <div className="space-y-1.5">
            <label htmlFor="edit-name" className="text-sm font-medium">
              {t("redemptionCodes.nameLabel")}
            </label>
            <Input
              id="edit-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={t("redemptionCodes.nameEditPlaceholder")}
              maxLength={128}
            />
          </div>
          <div className="space-y-1.5">
            <label htmlFor="edit-remark" className="text-sm font-medium">
              {t("redemptionCodes.remarkLabel")}
            </label>
            <Input
              id="edit-remark"
              value={remark}
              onChange={(e) => setRemark(e.target.value)}
              placeholder={t("redemptionCodes.remarkEditPlaceholder")}
              maxLength={512}
            />
          </div>
          <div className="space-y-1.5">
            <label htmlFor="edit-expires" className="text-sm font-medium">
              {t("redemptionCodes.expiresAtLabel")}
            </label>
            <Input
              id="edit-expires"
              type="datetime-local"
              value={expiresAt}
              onChange={(e) => setExpiresAt(e.target.value)}
            />
            <p className="text-xs text-muted-foreground">{t("redemptionCodes.expiresAtHint")}</p>
          </div>
          <div className="flex justify-end gap-2 pt-1">
            <Button type="button" variant="outline" onClick={onClose}>
              {t("redemptionCodes.cancel")}
            </Button>
            <Button type="submit" disabled={submitting}>
              {submitting && <Loading size="sm" />}
              {t("redemptionCodes.save")}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}

/** 兑换码详情弹窗：仅展示脱敏运营信息 */
function DetailDialog({
  code,
  onClose,
}: {
  code: RedemptionCodeItem;
  onClose: () => void;
}) {
  const { t, i18n } = useTranslation("console");
  const locale = i18n.language === "zh" ? "zh-CN" : "en-US";

  const rows: Array<[string, React.ReactNode]> = [
    [t("redemptionCodes.nameLabel"), code.name || "—"],
    [
      t("redemptionCodes.codeLabel"),
      <span key="prefix" className="flex items-center gap-0.5">
        <code className="font-mono text-xs">{maskCode(code.code)}</code>
        {code.code && <CopyButton value={code.code} className="size-6" />}
      </span>,
    ],
    [t("redemptionCodes.amountLabel"), <span key="amount" className="font-mono">{formatYuan(code.amount)}</span>],
    [
      t("redemptionCodes.statusLabel"),
      <Badge key="status" variant={STATUS_VARIANT[code.status]}>
        {statusLabel(t, code.status)}
      </Badge>,
    ],
    [t("redemptionCodes.remarkLabel"), code.remark || "—"],
    [t("redemptionCodes.expiresAtLabel"), formatTime(locale, code.expires_at)],
    [t("redemptionCodes.redeemedByLabel"), code.redeemed_by_user_id || "—"],
    [t("redemptionCodes.redeemedAtLabel"), formatTime(locale, code.redeemed_at)],
    [t("redemptionCodes.createdAtLabel"), formatTime(locale, code.created_at)],
  ];

  return (
    <div
      className="fixed inset-0 z-[80] flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="w-full max-w-md rounded-xl border bg-background p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-base font-semibold">{t("redemptionCodes.detailTitle")}</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          {t("redemptionCodes.detailDesc")}
        </p>
        <dl className="mt-5 space-y-3 text-sm">
          {rows.map(([label, value]) => (
            <div key={label} className="flex items-center justify-between gap-4">
              <dt className="shrink-0 text-muted-foreground">{label}</dt>
              <dd className="truncate text-right">{value}</dd>
            </div>
          ))}
        </dl>
        <div className="mt-6 flex justify-end">
          <Button variant="outline" onClick={onClose}>
            {t("redemptionCodes.close")}
          </Button>
        </div>
      </div>
    </div>
  );
}

export function RedemptionCodesPanel() {
  const { t, i18n } = useTranslation("console");
  const locale = i18n.language === "zh" ? "zh-CN" : "en-US";
  const [codes, setCodes] = useState<RedemptionCodeItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [nameFilter, setNameFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState<"" | CodeStatus>("");
  const [createOpen, setCreateOpen] = useState(false);
  const [editing, setEditing] = useState<RedemptionCodeItem | null>(null);
  const [detail, setDetail] = useState<RedemptionCodeItem | null>(null);
  const [togglingId, setTogglingId] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const load = useCallback(
    async (p: number) => {
      setLoading(true);
      setError("");
      try {
        const data = await get<{
          items: RedemptionCodeItem[];
          total: number;
        }>("/admin/billing/redemption-codes/list", {
          params: {
            page: p,
            page_size: PAGE_SIZE,
            name: nameFilter.trim() || undefined,
            status: statusFilter || undefined,
          },
        });
        setCodes(data.items);
        setTotal(data.total);
      } catch (err) {
        setError(err instanceof Error ? err.message : t("redemptionCodes.loadFailed"));
      } finally {
        setLoading(false);
      }
    },
    [nameFilter, statusFilter, t]
  );

  useEffect(() => {
    load(page);
  }, [load, page]);

  const onSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setPage(1);
    load(1);
  };

  /** 按当前名称/状态筛选导出全部兑换码明文（不分页），浏览器直接下载 txt */
  const onExport = async () => {
    setExporting(true);
    try {
      await exportRedemptionCodes(
        {
          name: nameFilter.trim() || undefined,
          status: statusFilter || undefined,
        },
        t("redemptionCodes.exportFailed")
      );
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t("redemptionCodes.exportFailed"));
    } finally {
      setExporting(false);
    }
  };

  const onToggleActive = async (item: RedemptionCodeItem) => {
    setTogglingId(item.id);
    try {
      await post("/admin/billing/redemption-codes/update-status", {
        id: item.id,
        active: !item.active,
      });
      toast.success(item.active ? t("redemptionCodes.disabledToast") : t("redemptionCodes.enabledToast"));
      load(page);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t("redemptionCodes.toggleFailed"));
    } finally {
      setTogglingId(null);
    }
  };

  return (
    <div className="flex min-h-[calc(100vh-7.5rem)] w-full flex-col gap-6">
      {/* 页头 */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold">{t("redemptionCodes.title")}</h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            {t("redemptionCodes.totalCodes", { total })}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => load(page)}
            disabled={loading}
          >
            <RefreshCw className={cn("size-4", loading && "animate-spin")} />
            {t("redemptionCodes.refresh")}
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={onExport}
            disabled={exporting}
          >
            {exporting ? <Loading size="sm" /> : <Download className="size-4" />}
            {t("redemptionCodes.exportButton")}
          </Button>
          <Button size="sm" onClick={() => setCreateOpen(true)}>
            <Plus className="size-4" />
            {t("redemptionCodes.createButton")}
          </Button>
        </div>
      </div>

      {/* 筛选 */}
      <form
        onSubmit={onSearch}
        className="flex items-center gap-3 rounded-xl border border-border/60 bg-card/40 p-4"
      >
        <Input
          value={nameFilter}
          onChange={(e) => setNameFilter(e.target.value)}
          placeholder={t("redemptionCodes.searchPlaceholder")}
          className="w-56"
        />
        <Select
          value={statusFilter}
          onValueChange={(v) => {
            setStatusFilter(v as "" | CodeStatus);
            setPage(1);
          }}
          options={STATUS_OPTIONS.map((s) => ({
            value: s,
            label: s === "" ? t("redemptionCodes.statusAll") : statusLabel(t, s),
          }))}
          className="w-auto"
          aria-label={t("redemptionCodes.statusFilterAria")}
        />
        <Button type="submit" size="sm" variant="outline" disabled={loading}>
          <Search className="size-4" />
          {t("redemptionCodes.search")}
        </Button>
      </form>

      {/* 兑换码列表：始终只展示脱敏前缀 */}
      <div className="relative overflow-hidden rounded-xl border border-border/60 bg-card/40">
        {error && codes.length === 0 ? (
          <div className="flex flex-col items-center gap-2 py-16 text-sm text-muted-foreground">
            <p>{t("redemptionCodes.loadFailedWithReason", { error })}</p>
            <Button variant="outline" size="sm" onClick={() => load(page)}>
              {t("redemptionCodes.retry")}
            </Button>
          </div>
        ) : codes.length === 0 ? (
          <div className="flex items-center justify-center py-16 text-muted-foreground">
            {loading ? (
              <Loading size="lg" />
            ) : (
              <div className="flex flex-col items-center gap-2">
                <TicketIcon className="size-8 text-muted-foreground/50" />
                <p className="text-sm">{t("redemptionCodes.empty")}</p>
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
                  <th className="px-6 py-3 text-left font-medium">{t("redemptionCodes.colName")}</th>
                  <th className="px-6 py-3 text-left font-medium">{t("redemptionCodes.colCode")}</th>
                  <th className="px-6 py-3 text-left font-medium">{t("redemptionCodes.colRemark")}</th>
                  <th className="px-6 py-3 font-medium">{t("redemptionCodes.colAmount")}</th>
                  <th className="px-6 py-3 font-medium">{t("redemptionCodes.colStatus")}</th>
                  <th className="px-6 py-3 font-medium">{t("redemptionCodes.colExpiresAt")}</th>
                  <th className="px-6 py-3 font-medium">{t("redemptionCodes.colCreatedAt")}</th>
                  <th className="sticky right-0 z-20 bg-muted shadow-[-10px_0_12px_-10px_rgba(0,0,0,0.12)] px-6 py-3 font-medium">
                    {t("redemptionCodes.colActions")}
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/60">
                {codes.map((item) => {
                  const editable = item.status !== "redeemed";
                  return (
                    <tr
                      key={item.id}
                      className="transition-colors hover:bg-accent/40"
                    >
                      <td className="max-w-40 truncate px-6 py-3">
                        {item.name || (
                          <span className="text-muted-foreground">—</span>
                        )}
                      </td>
                      <td className="px-6 py-3">
                        <div className="flex items-center gap-0.5">
                          <code className="font-mono text-xs text-muted-foreground">
                            {maskCode(item.code)}
                          </code>
                          {item.code && (
                            <CopyButton value={item.code} className="size-6" />
                          )}
                        </div>
                      </td>
                      <td
                        className="max-w-40 truncate px-6 py-3 text-muted-foreground"
                        title={item.remark ?? undefined}
                      >
                        {item.remark || (
                          <span className="text-muted-foreground">—</span>
                        )}
                      </td>
                      <td className="px-6 py-3 text-center font-mono text-xs">
                        {formatYuan(item.amount)}
                      </td>
                      <td className="px-6 py-3 text-center">
                        <Badge variant={STATUS_VARIANT[item.status]}>
                          {statusLabel(t, item.status)}
                        </Badge>
                      </td>
                      <td className="px-6 py-3 text-center text-muted-foreground">
                        {formatTime(locale, item.expires_at)}
                      </td>
                      <td className="px-6 py-3 text-center text-muted-foreground">
                        {formatTime(locale, item.created_at)}
                      </td>
                      <td className="sticky right-0 bg-card shadow-[-10px_0_12px_-10px_rgba(0,0,0,0.12)] px-6 py-3 text-center">
                        <div className="flex items-center justify-center gap-1.5">
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => setDetail(item)}
                          >
                            <Eye className="size-4" />
                            {t("redemptionCodes.detail")}
                          </Button>
                          {editable && (
                            <>
                              <Button
                                variant="outline"
                                size="sm"
                                onClick={() => setEditing(item)}
                              >
                                <Pencil className="size-4" />
                                {t("redemptionCodes.edit")}
                              </Button>
                              {/* 启用/停用按钮与 API 密钥页保持一致 */}
                              <Button
                                variant="outline"
                                size="sm"
                                className={
                                  item.active
                                    ? "text-warning hover:bg-warning/10 hover:text-warning"
                                    : "text-success hover:bg-success/10 hover:text-success"
                                }
                                disabled={togglingId === item.id}
                                onClick={() => onToggleActive(item)}
                              >
                                {togglingId === item.id ? (
                                  <Loading size="sm" />
                                ) : item.active ? (
                                  <Ban className="size-4" />
                                ) : (
                                  <CircleCheck className="size-4" />
                                )}
                                {item.active ? t("redemptionCodes.disable") : t("redemptionCodes.enable")}
                              </Button>
                            </>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
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
      {!error && codes.length > 0 && (
        <Pagination
          page={page}
          totalPages={totalPages}
          loading={loading}
          onChange={setPage}
          className="mt-auto"
        />
      )}

      <p className="text-xs text-muted-foreground/80">
        {t("redemptionCodes.listHint")}
      </p>

      {createOpen && (
        <CreateCodeDialog
          onClose={() => setCreateOpen(false)}
          onCreated={() => load(1)}
        />
      )}
      {editing && (
        <EditCodeDialog
          code={editing}
          onClose={() => setEditing(null)}
          onSaved={() => load(page)}
        />
      )}
      {detail && (
        <DetailDialog code={detail} onClose={() => setDetail(null)} />
      )}
    </div>
  );
}
