"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Check,
  CircleCheck,
  CircleX,
  CircleDollarSign,
  History,
  ScrollText,
  Wallet,
  X,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Loading } from "@/components/ui/loading";
import { Pagination } from "@/components/ui/pagination";
import { toast } from "@/components/ui/toaster";
import { get, post } from "@/lib/request";
import { cn } from "@/lib/utils";

type TopupInfo = {
  payments: {
    payment_channel: string;
    payment_method: string;
    payment_name: string;
    payment_icon: string;
    min_topup: string | null;
    max_topup: string | null;
  }[];
  pricing: {
    min_topup: string;
    max_topup: string;
    amount_options: string[];
    amount_discount: Record<string, string>;
    group_ratios: Record<string, string>;
  };
};

type AmountQuote = {
  payment_channel: string;
  payment_method: string;
  topup_amount: string;
  pay_amount: string;
  topup_currency: string;
  pay_currency: string;
  group_ratio: string;
  discount: string;
};

type EpayOrder = {
  order_no: string;
  status: string;
  topup_amount: string;
  pay_amount: string;
  currency: string;
  provider: string;
  payment_method: string;
  payment_action: {
    action_type?: string;
    gateway_url?: string;
    method?: string;
    params?: Record<string, string>;
  };
};

type PayingOrder = {
  order_no: string;
  topup_amount: string;
  status: "pending" | "paid" | "failed";
};

type PaidOrder = {
  order_no: string;
  topup_amount: string;
  pay_amount: string;
  payment_channel: string;
  payment_method: string;
  paid_at: string;
};

type BalanceRecord = {
  id: string;
  record_type: string;
  change_amount: string;
  balance_before: string;
  balance_after: string;
  reason: string;
  created_at: string;
};

const HISTORY_PAGE_SIZE = 10;
const RECORDS_PAGE_SIZE = 10;

type Translate = (key: string, options?: Record<string, unknown>) => string;

/** 支付渠道标签：Stripe 为品牌名，其余本地化 */
const channelLabel = (t: Translate, ch: string) =>
  ch === "stripe"
    ? "Stripe"
    : ch === "alipay_official"
      ? t("topup.channelAlipayOfficial")
      : t("topup.channelEpay");
const methodLabel = (t: Translate, ch: string, m: string) => {
  if (ch === "stripe") return t("topup.methodBankCard");
  if (m === "page_pay") return t("topup.methodPagePay");
  return m === "wxpay" ? t("topup.methodWxpay") : t("topup.methodAlipay");
};
const payCurrency = (ch: string) => (ch === "stripe" ? "$" : "¥");

/** 余额变动类型标签，未识别类型显示原始值 */
const recordTypeLabel = (t: Translate, type: string) =>
  type === "recharge"
    ? t("topup.recordRecharge")
    : type === "admin_grant"
      ? t("topup.recordAdminGrant")
      : type === "redemption"
        ? t("topup.recordRedemption")
        : type === "usage"
          ? t("topup.recordUsage")
          : type === "refund"
            ? t("topup.recordRefund")
            : type;
const recordTypeColor = (t: string) =>
  t === "usage"
    ? "bg-destructive/10 text-destructive"
    : t === "refund"
      ? "bg-sky-500/10 text-sky-600 dark:text-sky-400"
      : "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400";

/** 金额格式化：纯字符串截取两位小数，千分位展示 */
const formatAmount = (raw: string) => {
  const [intPart = "0", fracPart = ""] = raw.trim().split(".");
  const withSep = intPart.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  return `${withSep}.${`${fracPart}00`.slice(0, 2)}`;
};

/** 输入规范化：仅允许正十进制、最多两位小数；非法返回 null */
const normalizeAmount = (raw: string): string | null => {
  const text = raw.trim();
  if (!/^\d+(\.\d{1,2})?$/.test(text)) return null;
  const [intPart, fracPart = ""] = text.split(".");
  if (!/[1-9]/.test(intPart + fracPart)) return null;
  return `${intPart}.${fracPart.padEnd(2, "0")}`;
};

/** 支付回跳地址：开发环境用固定域名，生产环境用当前页面地址 */
const getReturnUrl = (orderNo?: string) =>
  process.env.NODE_ENV === "development"
    ? orderNo ? `https://www.hkshot.com?order_no=${orderNo}` : "https://www.hkshot.com"
    : orderNo ? `${window.location.origin}?order_no=${orderNo}` : window.location.origin;

/** 原样提交服务端返回的支付表单 */
const submitPaymentForm = (t: Translate, order: any) => {
    if (order?.payment_action?.url) {
        window.open(order.payment_action.url, "_blank");
        return;
    }

  const { gateway_url, method = "POST", params } = order.payment_action;
  if (!gateway_url || !params) {
    toast.error(t("topup.formIncomplete"));
    return;
  }
  const form = document.createElement("form");
  form.method = method;
  form.action = gateway_url;
  form.target = "_blank";
  form.style.display = "none";
  for (const [key, value] of Object.entries(params)) {
    const input = document.createElement("input");
    input.type = "hidden";
    input.name = key;
    if (key === "return_url") {
      input.value = getReturnUrl(order.order_no);
    } else {
        input.value = value as any;
    }
    form.appendChild(input);
  }
  document.body.appendChild(form);
  form.submit();
};

export function WalletTopup() {
  const { t, i18n } = useTranslation("console");
  const locale = i18n.language === "zh" ? "zh-CN" : "en-US";
  const [topupInfo, setTopupInfo] = useState<TopupInfo | null>(null);
  const [loadingInfo, setLoadingInfo] = useState(true);

  // 额度包选中档位（到账金额字符串），null 表示未选中
  const [selectedOption, setSelectedOption] = useState<string | null>(null);
  // 自定义输入（额度/到账金额）
  const [customAmount, setCustomAmount] = useState("");
  // 当前试算结果
  const [quote, setQuote] = useState<AmountQuote | null>(null);
  const [quoting, setQuoting] = useState(false);

  // 选中的支付方式（channel:method 作为 key），null 表示默认第一个
  const [selectedPaymentKey, setSelectedPaymentKey] = useState<string | null>(null);

  const [confirmOpen, setConfirmOpen] = useState(false);
  const [paying, setPaying] = useState(false);

  // 支付中订单数组
  const [payingOrders, setPayingOrders] = useState<PayingOrder[]>([]);

  // 历史订单弹窗
  const [historyOpen, setHistoryOpen] = useState(false);
  const [historyPage, setHistoryPage] = useState(1);
  const [historyOrders, setHistoryOrders] = useState<PaidOrder[]>([]);
  const [historyTotal, setHistoryTotal] = useState(0);
  const [historyLoading, setHistoryLoading] = useState(false);

  // 余额变动明细弹窗
  const [recordsOpen, setRecordsOpen] = useState(false);
  const [recordsPage, setRecordsPage] = useState(1);
  const [balanceRecords, setBalanceRecords] = useState<BalanceRecord[]>([]);
  const [recordsLoading, setRecordsLoading] = useState(false);

  const quoteSeqRef = useRef(0);

  const epayPayments = topupInfo?.payments || [];
  // 以 channel:method 作为支付方式唯一 key
  const paymentKey = (p: TopupInfo["payments"][number]) =>
    `${p.payment_channel}:${p.payment_method}`;
  // 当前选中的支付方式，默认取第一个
  const activePayment =
    epayPayments.find((p) => paymentKey(p) === selectedPaymentKey) ??
    epayPayments[0];
  const activeMethod = activePayment?.payment_method;

  const pricing = topupInfo?.pricing;

  // 充值限额：优先取支付方式自身配置，未设置则回退到 pricing
  const minTopup = activePayment?.min_topup ?? pricing?.min_topup ?? "1.00";
  const maxTopup = activePayment?.max_topup ?? pricing?.max_topup ?? "5000.00";

  // 生效的到账金额：优先自定义输入，其次选中档位
  const effectiveAmount = normalizeAmount(customAmount) ?? selectedOption;

  const loadTopupInfo = useCallback(async () => {
    setLoadingInfo(true);
    try {
      const info = await get<TopupInfo>("/payments/topups/detail");
      setTopupInfo(info);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t("topup.getInfoFailed"));
    } finally {
      setLoadingInfo(false);
    }
  }, [t]);

  useEffect(() => {
    loadTopupInfo();
  }, [loadTopupInfo]);

  // 金额或支付方式变化时试算实际支付金额
  useEffect(() => {
    if (!effectiveAmount || !activePayment) {
      setQuote(null);
      return;
    }
    const seq = ++quoteSeqRef.current;
    setQuoting(true);
    post<AmountQuote>("/payments/quote", {
      amount: effectiveAmount,
      payment_channel: activePayment.payment_channel,
      payment_method: activePayment.payment_method,
    })
      .then((res) => {
        if (seq !== quoteSeqRef.current) return;
        setQuote(res);
      })
      .catch((err) => {
        if (seq !== quoteSeqRef.current) return;
        setQuote(null);
        toast.warning(err instanceof Error ? err.message : t("topup.quoteFailed"));
      })
      .finally(() => {
        if (seq === quoteSeqRef.current) setQuoting(false);
      });
  }, [effectiveAmount, activePayment, t]);

  // 轮询支付中订单的状态
  useEffect(() => {
    const hasPending = payingOrders.some((o) => o.status === "pending");
    if (!hasPending) return;
    const timer = setInterval(async () => {
      const pending = payingOrders.filter((o) => o.status === "pending");
      if (pending.length === 0) return;
      const results = await Promise.all(
        pending.map((o) =>
          get<{ order_no: string; status: string }>(
            `/payments/orders/detail?order_no=${encodeURIComponent(o.order_no)}`
          )
            .then((res) => ({ order_no: o.order_no, status: res.status }))
            .catch(() => null)
        )
      );
      const paidAny = results.some((r) => r?.status === "paid");
      setPayingOrders((prev) =>
        prev.map((o) => {
          if (o.status !== "pending") return o;
          const r = results.find((x) => x?.order_no === o.order_no);
          if (!r) return o;
          if (r.status === "paid") return { ...o, status: "paid" as const };
          if (r.status === "closed" || r.status === "refunded")
            return { ...o, status: "failed" as const };
          return o;
        })
      );
      if (paidAny) window.dispatchEvent(new Event("wallet:refresh"));
    }, 3000);
    return () => clearInterval(timer);
  }, [payingOrders]);

  const dismissOrder = (orderNo: string) => {
    setPayingOrders((prev) => prev.filter((o) => o.order_no !== orderNo));
  };

  const loadHistory = useCallback(async (page: number) => {
    setHistoryLoading(true);
    try {
      const res = await get<{
        items: PaidOrder[];
        total: number;
      }>(
        `/payments/orders/paid?page=${page}&page_size=${HISTORY_PAGE_SIZE}`
      );
      setHistoryOrders(res.items);
      setHistoryTotal(res.total);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t("topup.historyFailed"));
    } finally {
      setHistoryLoading(false);
    }
  }, [t]);

  const openHistory = () => {
    setHistoryPage(1);
    setHistoryOpen(true);
    loadHistory(1);
  };

  // 分页变化时重新拉取
  const onHistoryPageChange = (page: number) => {
    setHistoryPage(page);
    loadHistory(page);
  };

  // 加载余额变动明细（接口返回全量，前端分页）
  const loadBalanceRecords = useCallback(async () => {
    setRecordsLoading(true);
    try {
      const res = await get<BalanceRecord[]>("/wallet/balance-records/list");
      setBalanceRecords(res);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t("topup.recordsFailed"));
    } finally {
      setRecordsLoading(false);
    }
  }, [t]);

  const openRecords = () => {
    setRecordsPage(1);
    setRecordsOpen(true);
    loadBalanceRecords();
  };

  const onRecordsPageChange = (page: number) => {
    setRecordsPage(page);
  };

  const onSelectOption = (option: string) => {
    setSelectedOption(option);
    // 点击额度包，实际到账金额在自定义金额里展示
    const [intPart = "0", fracPart = ""] = option.split(".");
    setCustomAmount(`${intPart}.${fracPart.padEnd(2, "0").slice(0, 2)}`);
  };

  const onCustomAmountChange = (value: string) => {
    setCustomAmount(value);
    // 手动输入时取消档位选中态（除非与档位一致）
    if (selectedOption) {
      const normalized = normalizeAmount(value);
      if (normalized !== selectedOption) setSelectedOption(null);
    }
  };

  const onClickPay = () => {
    if (!effectiveAmount) {
      toast.warning(t("topup.enterAmount"));
      return;
    }
    if (!quote) {
      toast.warning(t("topup.noQuote"));
      return;
    }
    if (!activeMethod) {
      toast.error(t("topup.paymentNotEnabled"));
      return;
    }
    setConfirmOpen(true);
  };

  const onConfirmPay = async () => {
    if (!effectiveAmount || !activeMethod) return;
    setPaying(true);
    try {
        const channelObj: Record<string, string> = {
            'epay': '/payments/epay-orders/create',
            'stripe': '/payments/stripe-orders/create',
        }
      const order = await post<EpayOrder>(channelObj[activePayment.payment_channel], {
        amount: effectiveAmount,
        payment_method: activeMethod,
        return_url: getReturnUrl(),
      });
      if (order.status === "paid") {
        toast.success(t("topup.orderPaid"));
        setConfirmOpen(false);
        return;
      }
      // 提交易支付表单，跳转收银台
      submitPaymentForm(t, order);
      setPayingOrders((prev) => [
        ...prev,
        {
          order_no: order.order_no,
          topup_amount: order.topup_amount,
          status: "pending",
        },
      ]);
      setCustomAmount("");
      setConfirmOpen(false);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t("topup.createOrderFailed"));
    } finally {
      setPaying(false);
    }
  };

  return (
    <>
      <Card className="shadow-card">
        <CardContent className="p-6">
          {/* 标题区 */}
          <div className="flex items-center gap-3 border-b pb-5">
            <span className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-[#f59e0b] to-[#f97316] text-white shadow-md">
              <CircleDollarSign className="size-5" />
            </span>
            <div>
              <h2 className="text-lg font-semibold">{t("topup.title")}</h2>
              <p className="text-sm text-muted-foreground">
                {t("topup.subtitle")}
              </p>
            </div>
            <div className="ml-auto flex items-center gap-2">
              <button
                type="button"
                onClick={openRecords}
                className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-border bg-background px-3 text-sm font-medium text-muted-foreground shadow-xs transition-all hover:-translate-y-px hover:border-primary/30 hover:bg-primary/5 hover:text-primary hover:shadow-sm"
              >
                <ScrollText className="size-4" />
                {t("topup.recordsButton")}
              </button>
              <button
                type="button"
                onClick={openHistory}
                className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-border bg-background px-3 text-sm font-medium text-muted-foreground shadow-xs transition-all hover:-translate-y-px hover:border-primary/30 hover:bg-primary/5 hover:text-primary hover:shadow-sm"
              >
                <History className="size-4" />
                {t("topup.historyButton")}
              </button>
            </div>
          </div>

          {loadingInfo ? (
            <div className="flex justify-center py-16">
              <Loading />
            </div>
          ) : (
            <div className="space-y-6 pt-6">
              {/* 额度包列表 */}
              <section className="space-y-3">
                <h3 className="text-sm font-medium text-muted-foreground">
                  {t("topup.amountSection")}
                </h3>
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                  {(pricing?.amount_options ?? []).map((option) => {
                    const discount = pricing?.amount_discount?.[option];
                    const selected =
                      selectedOption === option ||
                      normalizeAmount(customAmount) === option;
                    return (
                      <button
                        key={option}
                        type="button"
                        onClick={() => onSelectOption(option)}
                        className={cn(
                          "group relative overflow-hidden rounded-xl border p-4 text-left transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md",
                          selected
                            ? "border-primary bg-primary/5 shadow-sm ring-1 ring-primary/20"
                            : "border-border bg-background hover:border-primary/40"
                        )}
                      >
                        <span
                          className={cn(
                            "absolute right-3 top-3 flex size-5 items-center justify-center rounded-full border transition-all",
                            selected
                              ? "border-primary bg-primary text-primary-foreground"
                              : "border-border bg-muted/50 text-transparent group-hover:border-primary/40"
                          )}
                        >
                          <Check className="size-3" />
                        </span>
                        {/* 角标光斑装饰 */}
                        <div
                          aria-hidden
                          className={cn(
                            "absolute -bottom-6 -left-6 size-16 rounded-full blur-xl transition-colors",
                            selected ? "bg-primary/15" : "bg-muted/60 group-hover:bg-primary/10"
                          )}
                        />
                        <p className="text-xs text-muted-foreground">{t("topup.amountLabel")}</p>
                        <p className="mt-1 text-xl font-semibold tracking-tight tabular-nums">
                          {formatAmount(option)}
                        </p>
                      </button>
                    );
                  })}
                </div>
              </section>

              {/* 付款方式：默认选中第一个易支付 */}
              <section className="space-y-3">
                <h3 className="text-sm font-medium text-muted-foreground">
                  {t("topup.paymentSection")}
                </h3>
                {epayPayments.length > 0 ? (
                  <div className="flex flex-wrap gap-3">
                    {epayPayments.map((payment) => {
                      const key = paymentKey(payment);
                      const selected = activePayment && paymentKey(activePayment) === key;
                      return (
                        <button
                          key={key}
                          type="button"
                          onClick={() => setSelectedPaymentKey(key)}
                          className={cn(
                            "flex items-center gap-3 rounded-xl border p-4 text-left transition-all hover:border-foreground/40 hover:shadow-sm sm:min-w-50 sm:flex-1 sm:max-w-70",
                            selected
                              ? "border-foreground bg-muted/60 shadow-sm"
                              : "border-border bg-background"
                          )}
                        >
                          <span className="font-medium">
                            {payment.payment_name}
                          </span>
                          {selected && <Check className="ml-auto size-4 text-primary" />}
                        </button>
                      );
                    })}
                  </div>
                ) : (
                  <p className="text-sm text-muted-foreground">
                    {t("topup.paymentNotConfigured")}
                  </p>
                )}
              </section>

              {/* 自定义额度 */}
              <section className="space-y-3">
                <h3 className="text-sm font-medium text-muted-foreground">
                  {t("topup.customSection")}
                </h3>
                <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
                  <Input
                    value={customAmount}
                    onChange={(e) => onCustomAmountChange(e.target.value)}
                    placeholder={t("topup.customPlaceholder", {
                      min: minTopup,
                      max: maxTopup,
                    })}
                    inputMode="decimal"
                    className="h-11 sm:max-w-md"
                  />
                  <div className="flex h-11 items-center justify-between rounded-md border bg-muted/40 px-4 sm:min-w-56">
                    <span className="text-sm text-muted-foreground">
                      {t("topup.actualPay")}
                    </span>
                    <span className="text-base font-semibold">
                      {quoting ? (
                        <Loading size="sm" />
                      ) : quote ? (
                        `$ ${formatAmount(quote.pay_amount)}`
                      ) : (
                        "—"
                      )}
                    </span>
                  </div>
                  <Button
                    onClick={onClickPay}
                    disabled={quoting || !effectiveAmount}
                    className="h-11 min-w-20 px-8"
                  >
                    {t("topup.topupButton")}
                  </Button>
                </div>
              </section>
            </div>
          )}
        </CardContent>
      </Card>

      {/* 支付中订单状态条 */}
      {payingOrders.length > 0 && (
        <div className="space-y-2">
          {payingOrders.map((o) => (
            <div
              key={o.order_no}
              className="flex items-center gap-3 rounded-xl border bg-background px-4 py-3 shadow-card"
            >
              {o.status === "pending" && (
                <>
                  <Loading size="sm" />
                  <p className="text-sm">
                    {t("topup.orderPaying")}
                    <span className="ml-2 text-muted-foreground">
                      ¥{formatAmount(o.topup_amount)}
                    </span>
                  </p>
                </>
              )}
              {o.status === "paid" && (
                <>
                  <CircleCheck className="size-4 text-emerald-500" />
                  <p className="text-sm">
                    {t("topup.orderPaidSuccess")}
                    <span className="ml-2 text-muted-foreground">
                      ¥{formatAmount(o.topup_amount)}
                    </span>
                  </p>
                  <button
                    type="button"
                    onClick={() => dismissOrder(o.order_no)}
                    className="ml-auto text-muted-foreground hover:text-foreground"
                  >
                    <X className="size-4" />
                  </button>
                </>
              )}
              {o.status === "failed" && (
                <>
                  <CircleX className="size-4 text-destructive" />
                  <p className="text-sm">
                    {t("topup.orderFailed")}
                    <span className="ml-2 text-muted-foreground">
                      ¥{formatAmount(o.topup_amount)}
                    </span>
                  </p>
                  <button
                    type="button"
                    onClick={() => dismissOrder(o.order_no)}
                    className="ml-auto text-muted-foreground hover:text-foreground"
                  >
                    <X className="size-4" />
                  </button>
                </>
              )}
            </div>
          ))}
        </div>
      )}

      {/* 确认付款弹窗 */}
      {confirmOpen && quote && effectiveAmount && activeMethod && (
        <div
          className="fixed inset-0 z-80 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm"
          onClick={() => !paying && setConfirmOpen(false)}
        >
          <div
            className="w-full max-w-sm rounded-xl border bg-background p-6 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="text-base font-semibold">{t("topup.confirmTitle")}</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              {t("topup.confirmDesc")}
            </p>
            <div className="mt-5 space-y-4">
              <div className="flex items-center justify-between">
                <span className="text-sm text-muted-foreground">{t("topup.confirmAmount")}</span>
                <span className="text-base font-medium">
                  {formatAmount(effectiveAmount)}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm text-muted-foreground">{t("topup.confirmPay")}</span>
                <span className="text-2xl font-semibold">
                  ${formatAmount(quote.pay_amount)}
                </span>
              </div>
              <div className="flex items-center justify-between border-t pt-4">
                <span className="text-sm text-muted-foreground">{t("topup.confirmPaymentMethod")}</span>
                <span className="flex items-center gap-2 font-medium">
                  {activePayment.payment_name}
                </span>
              </div>
            </div>
            <div className="mt-6 flex justify-end gap-2">
              <Button
                variant="outline"
                onClick={() => setConfirmOpen(false)}
                disabled={paying}
              >
                {t("topup.cancel")}
              </Button>
              <Button onClick={onConfirmPay} disabled={paying}>
                {paying && <Loading size="sm" />}
                {t("topup.confirmButton")}
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* 历史已支付订单弹窗 */}
      {historyOpen && (
        <div
          className="fixed inset-0 z-80 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm"
          onClick={() => setHistoryOpen(false)}
        >
          <div
            className="flex max-h-[80vh] w-full max-w-3xl flex-col rounded-xl border bg-background shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            {/* 弹窗标题 */}
            <div className="flex items-center justify-between border-b px-6 py-4">
              <h2 className="text-base font-semibold">{t("topup.historyTitle")}</h2>
              <button
                type="button"
                onClick={() => setHistoryOpen(false)}
                className="text-muted-foreground hover:text-foreground"
              >
                <X className="size-5" />
              </button>
            </div>

            {/* 表格 */}
            <div className="flex-1 overflow-auto px-6 py-4">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
                    <th className="pb-2 font-medium">{t("topup.colOrderNo")}</th>
                    <th className="pb-2 font-medium">{t("topup.colTopupAmount")}</th>
                    <th className="pb-2 font-medium">{t("topup.colPayAmount")}</th>
                    <th className="pb-2 font-medium">{t("topup.colPaymentMethod")}</th>
                    <th className="pb-2 font-medium">{t("topup.colPaidAt")}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/60">
                  {historyLoading && historyOrders.length === 0 ? (
                    <tr>
                      <td colSpan={5} className="py-16 text-center text-muted-foreground">
                        <Loading />
                      </td>
                    </tr>
                  ) : historyOrders.length === 0 ? (
                    <tr>
                      <td
                        colSpan={5}
                        className="py-16 text-center text-muted-foreground"
                      >
                        {t("topup.historyEmpty")}
                      </td>
                    </tr>
                  ) : (
                    historyOrders.map((o) => (
                      <tr key={o.order_no} className="text-sm">
                        <td className="whitespace-nowrap py-3 font-mono text-xs text-muted-foreground">
                          {o.order_no}
                        </td>
                        <td className="whitespace-nowrap py-3 font-medium">
                          {formatAmount(o.topup_amount)}
                        </td>
                        <td className="whitespace-nowrap py-3">
                          {payCurrency(o.payment_channel)}{formatAmount(o.pay_amount)}
                        </td>
                        <td className="whitespace-nowrap py-3">
                          {channelLabel(t, o.payment_channel)} / {methodLabel(t, o.payment_channel, o.payment_method)}
                        </td>
                        <td className="whitespace-nowrap py-3 text-muted-foreground">
                          {new Date(o.paid_at).toLocaleString(locale, {
                            year: "numeric",
                            month: "2-digit",
                            day: "2-digit",
                            hour: "2-digit",
                            minute: "2-digit",
                            second: "2-digit",
                            hour12: false,
                          })}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>

            {/* 分页 */}
            {historyTotal > HISTORY_PAGE_SIZE && (
              <div className="border-t px-6 py-3">
                <Pagination
                  page={historyPage}
                  totalPages={Math.ceil(historyTotal / HISTORY_PAGE_SIZE)}
                  loading={historyLoading}
                  onChange={onHistoryPageChange}
                />
              </div>
            )}
          </div>
        </div>
      )}

      {/* 余额变动明细弹窗 */}
      {recordsOpen && (
        <div
          className="fixed inset-0 z-80 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm"
          onClick={() => setRecordsOpen(false)}
        >
          <div
            className="w-full max-w-5xl overflow-hidden rounded-2xl border bg-background shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            {/* 弹窗标题 */}
            <div className="flex items-center justify-between border-b bg-muted/30 px-6 py-4">
              <div className="flex items-baseline gap-3">
                <h2 className="text-lg font-semibold">{t("topup.recordsTitle")}</h2>
                <p className="text-sm text-muted-foreground">
                  {t("topup.recordsTotal", { total: balanceRecords.length })}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setRecordsOpen(false)}
                className="rounded-lg p-1.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
              >
                <X className="size-5" />
              </button>
            </div>

            {/* 表格 */}
            <div className="h-[580px] px-6 py-4">
              <div className="h-[548px] overflow-hidden rounded-xl border bg-card">
                <table className="w-full table-fixed text-sm">
                  <colgroup>
                    <col className="w-37" />
                    <col className="w-26" />
                    <col className="w-29" />
                    <col className="w-29" />
                    <col className="w-29" />
                    <col />
                  </colgroup>
                  <thead className="bg-muted/50">
                    <tr className="text-center text-xs font-medium text-muted-foreground">
                      <th className="px-4 py-2.5 font-medium">{t("topup.colTime")}</th>
                      <th className="px-3 py-2.5 font-medium">{t("topup.colType")}</th>
                      <th className="px-3 py-2.5 font-medium">{t("topup.colChange")}</th>
                      <th className="px-3 py-2.5 font-medium">{t("topup.colBalanceBefore")}</th>
                      <th className="px-3 py-2.5 font-medium">{t("topup.colBalanceAfter")}</th>
                      <th className="px-4 py-2.5 font-medium">{t("topup.colReason")}</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/60">
                  {recordsLoading && balanceRecords.length === 0 ? (
                    <tr>
                      <td colSpan={6} className="py-16 text-center text-muted-foreground">
                        <Loading />
                      </td>
                    </tr>
                  ) : balanceRecords.length === 0 ? (
                    <tr>
                      <td
                        colSpan={6}
                        className="py-16 text-center text-muted-foreground"
                      >
                        {t("topup.recordsEmpty")}
                      </td>
                    </tr>
                  ) : (
                    balanceRecords
                      .slice(
                        (recordsPage - 1) * RECORDS_PAGE_SIZE,
                        recordsPage * RECORDS_PAGE_SIZE
                      )
                      .map((r) => {
                        const isNegative = r.change_amount.startsWith("-");
                        return (
                          <tr
                            key={r.id}
                            className="text-sm transition-colors hover:bg-muted/40"
                          >
                            <td className="whitespace-nowrap px-4 py-3 text-center text-xs text-muted-foreground">
                              {new Date(r.created_at).toLocaleString(locale, {
                                month: "2-digit",
                                day: "2-digit",
                                hour: "2-digit",
                                minute: "2-digit",
                                second: "2-digit",
                                hour12: false,
                              })}
                            </td>
                            <td className="whitespace-nowrap px-3 py-3 text-center">
                              <span
                                className={cn(
                                  "inline-flex items-center rounded-md px-2 py-1 text-xs font-medium",
                                  recordTypeColor(r.record_type)
                                )}
                              >
                                {recordTypeLabel(t, r.record_type)}
                              </span>
                            </td>
                            <td
                              className={cn(
                                "whitespace-nowrap px-3 py-3 text-center font-semibold tabular-nums",
                                isNegative
                                  ? "text-destructive"
                                  : "text-emerald-600 dark:text-emerald-400"
                              )}
                            >
                              {isNegative ? "" : "+"}$
                              {formatAmount(r.change_amount)}
                            </td>
                            <td className="whitespace-nowrap px-3 py-3 text-center text-muted-foreground tabular-nums">
                              ${formatAmount(r.balance_before)}
                            </td>
                            <td className="whitespace-nowrap px-3 py-3 text-center font-medium tabular-nums">
                              ${formatAmount(r.balance_after)}
                            </td>
                            <td
                              className="truncate px-4 py-3 text-center text-muted-foreground"
                              title={r.reason}
                            >
                              {r.reason}
                            </td>
                          </tr>
                        );
                      })
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            {/* 分页 */}
            <div className="h-18 border-t bg-muted/20 px-6 py-5">
              {balanceRecords.length > 0 && (
                <Pagination
                  page={recordsPage}
                  totalPages={Math.ceil(
                    balanceRecords.length / RECORDS_PAGE_SIZE
                  )}
                  loading={recordsLoading}
                  onChange={onRecordsPageChange}
                />
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
