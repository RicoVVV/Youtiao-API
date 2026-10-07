"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Download, RefreshCw, ScrollText, Search } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DateTimePicker } from "@/components/ui/datetime-picker";
import { Input } from "@/components/ui/input";
import { Loading } from "@/components/ui/loading";
import { Pagination } from "@/components/ui/pagination";
import { Select } from "@/components/ui/select";
import { toast } from "@/components/ui/toaster";
import { cn } from "@/lib/utils";
import { clearToken, get, getToken, pickErrorMessage } from "@/lib/request";

/** 支付流水列表项：金额为十进制字符串，原样展示不做数值运算 */
type PaymentOrderItem = {
  order_no: string;
  user_id: string;
  username: string;
  topup_amount: string;
  pay_amount: string;
  payment_channel: string;
  payment_method: string;
  channel_transaction_id: string | null;
  status: string;
  created_at: string | null;
  paid_at: string | null;
};

/** 已生效的筛选条件：查询与导出共用，保证两个接口参数一致 */
type AppliedFilters = {
  start_at: string;
  end_at: string;
  username?: string;
  payment_channel?: string;
  order_no?: string;
};

const PAGE_SIZE = 20;
/** 与后端一致：查询时间跨度上限 366 天 */
const MAX_RANGE_MS = 366 * 24 * 60 * 60 * 1000;
const CHANNEL_VALUES = ["alipay_official", "epay", "stripe"];

const pad = (n: number) => String(n).padStart(2, "0");

/** Date → datetime-local 值（本地时区） */
const toLocalValue = (d: Date) =>
  `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;

/** datetime-local 值 → 带时区 ISO 字符串 */
const toIso = (local: string) => new Date(local).toISOString();

const formatTime = (value: string | null, locale: string) =>
  value ? new Date(value).toLocaleString(locale, { hour12: false }) : "—";

/** 支付渠道标签：已知渠道本地化，未知渠道展示原始值 */
function ChannelBadge({ channel }: { channel: string }) {
  const { t } = useTranslation("payment-records");
  const known = (CHANNEL_VALUES as string[]).includes(channel);
  return <Badge variant="outline">{known ? t(`channel.${channel}`) : channel}</Badge>;
}

export function PaymentRecordsPanel() {
  const { t, i18n } = useTranslation("payment-records");
  const locale = i18n.language === "zh" ? "zh-CN" : "en-US";

  /* ── 筛选草稿：默认最近 30 天 ── */
  const [startLocal, setStartLocal] = useState(() =>
    toLocalValue(new Date(Date.now() - 30 * 24 * 60 * 60 * 1000))
  );
  const [endLocal, setEndLocal] = useState(() => toLocalValue(new Date()));
  const [username, setUsername] = useState("");
  const [channel, setChannel] = useState("");
  const [orderNo, setOrderNo] = useState("");

  /* ── 列表状态 ── */
  const [applied, setApplied] = useState<AppliedFilters>(() => ({
    start_at: toIso(toLocalValue(new Date(Date.now() - 30 * 24 * 60 * 60 * 1000))),
    end_at: toIso(toLocalValue(new Date())),
  }));
  const [records, setRecords] = useState<PaymentOrderItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [exporting, setExporting] = useState(false);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const channelOptions = useMemo(
    () => [
      { value: "", label: t("channel.all") },
      ...CHANNEL_VALUES.map((v) => ({ value: v, label: t(`channel.${v}`) })),
    ],
    [t]
  );

  /** 校验时间范围并组装筛选参数；不合法时返回错误文案 key */
  const validateFilters = useCallback((): {
    filters?: AppliedFilters;
    errorKey?: string;
  } => {
    if (!startLocal || !endLocal) return { errorKey: "rangeRequired" };
    const start = new Date(startLocal);
    const end = new Date(endLocal);
    if (start.getTime() > end.getTime()) return { errorKey: "rangeInvalid" };
    if (end.getTime() - start.getTime() > MAX_RANGE_MS)
      return { errorKey: "rangeTooLong" };
    return {
      filters: {
        start_at: toIso(startLocal),
        end_at: toIso(endLocal),
        username: username.trim() || undefined,
        payment_channel: channel || undefined,
        order_no: orderNo.trim() || undefined,
      },
    };
  }, [startLocal, endLocal, username, channel, orderNo]);

  const load = useCallback(
    async (p: number) => {
      setLoading(true);
      setError("");
      try {
        const data = await get<{ items: PaymentOrderItem[]; total: number }>(
          "/admin/payments/orders/list",
          { params: { ...applied, page: p, page_size: PAGE_SIZE } }
        );
        setRecords(data.items);
        setTotal(data.total);
      } catch (err) {
        setError(err instanceof Error ? err.message : t("loadFailed"));
      } finally {
        setLoading(false);
      }
    },
    [applied, t]
  );

  useEffect(() => {
    // 微任务中触发，避免在 effect 体内同步 setState（react-hooks/set-state-in-effect）
    void Promise.resolve().then(() => load(page));
  }, [load, page]);

  /** 查询：校验草稿后生效，回到第一页（applied 变更触发 reload） */
  const onSearch = (e: React.FormEvent) => {
    e.preventDefault();
    const { filters, errorKey } = validateFilters();
    if (errorKey || !filters) {
      toast.error(t(errorKey ?? "rangeRequired"));
      return;
    }
    setPage(1);
    setApplied(filters);
  };

  /** 导出：按当前已生效筛选条件请求 CSV，浏览器端触发下载（无统一响应信封） */
  const handleExport = async () => {
    setExporting(true);
    try {
      const query = Object.entries(applied)
        .filter(([, v]) => v !== undefined)
        .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`)
        .join("&");
      const res = await fetch(`/api/admin/payments/orders/export?${query}`, {
        headers: { Authorization: `Bearer ${getToken() ?? ""}` },
        credentials: "include",
      });
      // 401：清理登录态并跳转登录页（导出不经 request 封装，需自行处理）
      if (res.status === 401) {
        clearToken();
        window.location.href = `/login?redirect=${encodeURIComponent(window.location.pathname)}`;
        return;
      }
      if (!res.ok) {
        const data = await res.json().catch(() => null);
        throw new Error(pickErrorMessage(data, t("exportFailed")));
      }
      const blob = await res.blob();
      const disposition = res.headers.get("Content-Disposition") ?? "";
      const filename =
        /filename="?([^";]+)"?/.exec(disposition)?.[1] ?? "payment-orders.csv";
      const objectUrl = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = objectUrl;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(objectUrl);
      toast.success(t("exportSuccess"));
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t("exportFailed"));
    } finally {
      setExporting(false);
    }
  };

  return (
    <div className="flex min-h-[calc(100vh-7.5rem)] w-full flex-col gap-6">
      {/* 页头 */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold">{t("title")}</h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            {t("totalRecords", { total })}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => load(page)}
            disabled={loading || exporting}
          >
            <RefreshCw className={cn("size-4", loading && "animate-spin")} />
            {t("refresh")}
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={handleExport}
            disabled={loading || exporting}
          >
            <Download className="size-4" />
            {exporting ? t("exporting") : t("export")}
          </Button>
        </div>
      </div>

      {/* 筛选：时间范围必填，跨度上限 366 天 */}
      <form
        onSubmit={onSearch}
        className="flex flex-wrap items-center gap-3 rounded-xl border border-border/60 bg-card/40 p-4"
      >
        <DateTimePicker
          value={startLocal}
          onChange={setStartLocal}
          placeholder={t("startTime")}
          className="w-48"
        />
        <span className="text-xs text-muted-foreground">{t("rangeTo")}</span>
        <DateTimePicker
          value={endLocal}
          onChange={setEndLocal}
          placeholder={t("endTime")}
          className="w-48"
        />
        <Input
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          placeholder={t("filterByUsername")}
          className="w-40"
        />
        <Select
          value={channel}
          onValueChange={setChannel}
          options={channelOptions}
          className="w-auto"
          aria-label={t("filterByChannel")}
        />
        <Input
          value={orderNo}
          onChange={(e) => setOrderNo(e.target.value)}
          placeholder={t("filterByOrderNo")}
          className="w-48"
        />
        <Button type="submit" size="sm" variant="outline" disabled={loading}>
          <Search className="size-4" />
          {t("search")}
        </Button>
      </form>

      {/* 流水列表 */}
      <div className="relative overflow-hidden rounded-xl border border-border/60 bg-card/40">
        {error && records.length === 0 ? (
          <div className="flex flex-col items-center gap-2 py-16 text-sm text-muted-foreground">
            <p>{t("loadFailedWithReason", { error })}</p>
            <Button variant="outline" size="sm" onClick={() => load(page)}>
              {t("retry")}
            </Button>
          </div>
        ) : records.length === 0 ? (
          <div className="flex items-center justify-center py-16 text-muted-foreground">
            {loading ? (
              <Loading size="lg" />
            ) : (
              <div className="flex flex-col items-center gap-2">
                <ScrollText className="size-8 text-muted-foreground/50" />
                <p className="text-sm">{t("empty")}</p>
              </div>
            )}
          </div>
        ) : (
          <>
            {/* 加载中保留旧数据并降低透明度，避免表格整体闪烁 */}
            <div className="overflow-x-auto">
              <table
                className={cn(
                  "w-full min-w-max text-sm transition-opacity duration-300",
                  loading && "pointer-events-none opacity-40"
                )}
              >
                <thead>
                  <tr className="border-b border-border/60 bg-muted/40 text-center text-xs text-muted-foreground">
                    <th className="px-6 py-3 text-left font-medium">{t("colPaidAt")}</th>
                    <th className="px-6 py-3 text-left font-medium">{t("colOrderNo")}</th>
                    <th className="px-6 py-3 font-medium">{t("colUsername")}</th>
                    <th className="px-6 py-3 font-medium">{t("colTopupAmount")}</th>
                    <th className="px-6 py-3 font-medium">{t("colPayAmount")}</th>
                    <th className="px-6 py-3 font-medium">{t("colChannel")}</th>
                    <th className="px-6 py-3 font-medium">{t("colMethod")}</th>
                    <th className="px-6 py-3 text-left font-medium">{t("colTransactionId")}</th>
                    <th className="px-6 py-3 font-medium">{t("colStatus")}</th>
                    <th className="px-6 py-3 text-left font-medium">{t("colCreatedAt")}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/60">
                  {records.map((item) => (
                    <tr
                      key={item.order_no}
                      className="transition-colors hover:bg-accent/40"
                    >
                      <td className="px-6 py-3 whitespace-nowrap text-muted-foreground">
                        {formatTime(item.paid_at, locale)}
                      </td>
                      <td className="max-w-44 truncate px-6 py-3 font-mono text-xs" title={item.order_no}>
                        {item.order_no}
                      </td>
                      <td className="max-w-32 truncate px-6 py-3 text-center" title={item.username}>
                        {item.username}
                      </td>
                      <td className="px-6 py-3 text-center font-mono text-xs">
                        ¥{item.topup_amount}
                      </td>
                      <td className="px-6 py-3 text-center font-mono text-xs">
                        ¥{item.pay_amount}
                      </td>
                      <td className="px-6 py-3 text-center">
                        <ChannelBadge channel={item.payment_channel} />
                      </td>
                      <td className="px-6 py-3 text-center">
                        {item.payment_method || (
                          <span className="text-muted-foreground">—</span>
                        )}
                      </td>
                      <td
                        className="max-w-48 truncate px-6 py-3 font-mono text-xs"
                        title={item.channel_transaction_id ?? undefined}
                      >
                        {item.channel_transaction_id || (
                          <span className="text-muted-foreground">—</span>
                        )}
                      </td>
                      <td className="px-6 py-3 text-center">
                        <Badge
                          variant="outline"
                          className="border-emerald-500/40 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
                        >
                          {t(`status.${item.status}`)}
                        </Badge>
                      </td>
                      <td className="px-6 py-3 whitespace-nowrap text-muted-foreground">
                        {formatTime(item.created_at, locale)}
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
    </div>
  );
}
