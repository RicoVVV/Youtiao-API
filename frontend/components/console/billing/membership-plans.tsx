"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Check,
  CircleCheck,
  CircleX,
  Crown,
  Loader2,
  Sparkles,
  X,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Loading } from "@/components/ui/loading";
import { toast } from "@/components/ui/toaster";
import { get, post } from "@/lib/request";
import {
  listMembershipPlans,
  type MembershipLevel,
  type MembershipPlan,
  type UserMembership,
} from "@/lib/membership";
import { cn } from "@/lib/utils";

/** 支付方式（复用充值信息接口的 payments 列表） */
type PaymentOption = {
  payment_channel: string;
  payment_method: string;
  payment_name: string;
  payment_icon: string;
};

type TopupInfo = {
  payments: PaymentOption[];
};

/** 试算结果 */
type Quote = {
  payment_channel: string;
  payment_method: string;
  topup_amount: string;
  topup_currency: string;
  pay_amount: string;
  pay_currency: string;
};

/** 下单响应（易支付 / Stripe / 支付宝官方 / 通联收银宝共用结构） */
type CreatedOrder = {
  order_no: string;
  status: string;
  topup_amount: string;
  pay_amount: string;
  currency: string;
  payment_action?: {
    action_type?: string;
    url?: string;
    qr_code?: string;
    gateway_url?: string;
    method?: string;
    params?: Record<string, string>;
  };
};

/** 支付中订单 */
type PayingOrder = {
  order_no: string;
  topup_amount: string;
  status: "pending" | "paid" | "failed";
};

type Translate = (key: string, options?: Record<string, unknown>) => string;

/** 金额格式化：纯字符串截取两位小数 */
const formatAmount = (raw: string) => {
  const [intPart = "0", fracPart = ""] = raw.trim().split(".");
  const withSep = intPart.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  return `${withSep}.${`${fracPart}00`.slice(0, 2)}`;
};

/** 支付回跳地址：与钱包充值保持一致 */
const getReturnUrl = (orderNo?: string) =>
  process.env.NODE_ENV === "development"
    ? orderNo
      ? `https://www.hkshot.com?order_no=${orderNo}`
      : "https://www.hkshot.com"
    : orderNo
      ? `${window.location.origin}?order_no=${orderNo}`
      : window.location.origin;

/** 原样提交服务端返回的支付表单 */
const submitPaymentForm = (t: Translate, order: CreatedOrder) => {
  if (order?.payment_action?.url) {
    window.open(order.payment_action.url, "_blank");
    return;
  }
  const action = order.payment_action;
  if (!action?.gateway_url || !action.params) {
    toast.error(t("membership.formIncomplete"));
    return;
  }
  const form = document.createElement("form");
  form.method = action.method ?? "POST";
  form.action = action.gateway_url;
  form.target = "_blank";
  form.style.display = "none";
  for (const [key, value] of Object.entries(action.params)) {
    const input = document.createElement("input");
    input.type = "hidden";
    input.name = key;
    input.value = key === "return_url" ? getReturnUrl(order.order_no) : value;
    form.appendChild(input);
  }
  document.body.appendChild(form);
  form.submit();
};

/** 购买动作：开通 / 续费 / 升级 / 不可购买 */
type PurchaseAction = "subscribe" | "renew" | "upgrade" | "disabled";

/** 以当前有效会员为准判定购买动作 */
const resolveAction = (
  level: MembershipLevel,
  membership: UserMembership | null
): PurchaseAction => {
  if (!membership?.is_active || !membership.level) return "subscribe";
  if (membership.level.id === level.id) return "renew";
  if (level.rank > membership.level.rank) return "upgrade";
  return "disabled";
};

/** 会员套餐展示与购买 */
export function MembershipPlans() {
  const { t, i18n } = useTranslation("console");
  const locale = i18n.language === "zh" ? "zh-CN" : "en-US";

  const [levels, setLevels] = useState<MembershipLevel[] | null>(null);
  const [membership, setMembership] = useState<UserMembership | null>(null);
  const [payments, setPayments] = useState<PaymentOption[]>([]);
  const [loadFailed, setLoadFailed] = useState(false);

  // 选中的套餐（等级卡片内的周/月套餐切换）
  const [selectedPlanId, setSelectedPlanId] = useState<Record<string, string>>({});
  // 选中的支付方式（channel:method）
  const [paymentKey, setPaymentKey] = useState<string | null>(null);

  // 确认弹窗
  const [confirmPlan, setConfirmPlan] = useState<{
    level: MembershipLevel;
    plan: MembershipPlan;
  } | null>(null);
  const [quote, setQuote] = useState<Quote | null>(null);
  const [quoting, setQuoting] = useState(false);
  const [paying, setPaying] = useState(false);

  // 支付中订单
  const [payingOrders, setPayingOrders] = useState<PayingOrder[]>([]);
  // 支付完成后提示「金额已转入钱包余额」的订单号集合
  const [convertedOrders, setConvertedOrders] = useState<Set<string>>(new Set());

  const quoteSeqRef = useRef(0);

  const keyOf = (p: PaymentOption) => `${p.payment_channel}:${p.payment_method}`;
  const activePayment =
    payments.find((p) => keyOf(p) === paymentKey) ?? payments[0];

  /** 加载当前会员状态 */
  const loadMembership = useCallback(() => {
    return get<{ membership: UserMembership }>("/user/info")
      .then((res) => setMembership(res.membership))
      .catch(() => {});
  }, []);

  /** 初始加载：套餐列表 + 支付方式 + 当前会员 */
  useEffect(() => {
    let cancelled = false;
    Promise.all([
      listMembershipPlans(),
      get<TopupInfo>("/payments/topups/detail").catch(() => ({ payments: [] })),
      loadMembership(),
    ])
      .then(([plansRes, topupInfo]) => {
        if (cancelled) return;
        setLevels(plansRes.items);
        setPayments(topupInfo.payments ?? []);
        // 默认选中每个等级的第一个套餐
        const defaults: Record<string, string> = {};
        for (const lv of plansRes.items) {
          if (lv.plans[0]) defaults[lv.id] = lv.plans[0].id;
        }
        setSelectedPlanId(defaults);
      })
      .catch(() => !cancelled && setLoadFailed(true));
    return () => {
      cancelled = true;
    };
  }, [loadMembership]);

  /** 打开确认弹窗并试算 */
  const openConfirm = (level: MembershipLevel, plan: MembershipPlan) => {
    if (!activePayment) {
      toast.error(t("membership.paymentNotConfigured"));
      return;
    }
    setConfirmPlan({ level, plan });
    setQuote(null);
    const seq = ++quoteSeqRef.current;
    setQuoting(true);
    post<Quote>("/payments/quote", {
      membership_plan_id: plan.id,
      payment_channel: activePayment.payment_channel,
      payment_method: activePayment.payment_method,
    })
      .then((res) => {
        if (seq === quoteSeqRef.current) setQuote(res);
      })
      .catch((err) => {
        if (seq === quoteSeqRef.current) {
          toast.warning(err instanceof Error ? err.message : t("membership.quoteFailed"));
        }
      })
      .finally(() => {
        if (seq === quoteSeqRef.current) setQuoting(false);
      });
  };

  /** 会员订单支付完成后：刷新会员状态，识别 purchase_converted（降级转余额） */
  const handleMembershipPaid = useCallback(
    async (orderNo: string) => {
      try {
        const res = await get<{
          items: { order_no: string; membership: { source: string } | null }[];
        }>("/payments/orders/paid", { params: { page: 1, page_size: 20 } });
        const item = res.items.find((o) => o.order_no === orderNo);
        if (item?.membership?.source === "purchase_converted") {
          setConvertedOrders((prev) => new Set(prev).add(orderNo));
        }
      } catch {
        // 查询失败不影响主流程
      }
      loadMembership();
      window.dispatchEvent(new Event("wallet:refresh"));
    },
    [loadMembership]
  );

  /** 轮询支付中订单的状态 */
  useEffect(() => {
    const hasPending = payingOrders.some((o) => o.status === "pending");
    if (!hasPending) return;
    const timer = setInterval(async () => {
      const pending = payingOrders.filter((o) => o.status === "pending");
      if (pending.length === 0) return;
      const results = await Promise.all(
        pending.map((o) =>
          get<{ order_no: string; status: string; order_type?: string }>(
            `/payments/orders/detail?order_no=${encodeURIComponent(o.order_no)}`
          )
            .then((res) => ({ order_no: o.order_no, status: res.status }))
            .catch(() => null)
        )
      );
      const newlyPaid: string[] = [];
      setPayingOrders((prev) =>
        prev.map((o) => {
          if (o.status !== "pending") return o;
          const r = results.find((x) => x?.order_no === o.order_no);
          if (!r) return o;
          if (r.status === "paid") {
            newlyPaid.push(o.order_no);
            return { ...o, status: "paid" as const };
          }
          if (r.status === "closed" || r.status === "refunded")
            return { ...o, status: "failed" as const };
          return o;
        })
      );
      for (const orderNo of newlyPaid) void handleMembershipPaid(orderNo);
    }, 3000);
    return () => clearInterval(timer);
  }, [payingOrders, handleMembershipPaid]);

  /** 确认付款并创建会员订单 */
  const onConfirmPay = async () => {
    if (!confirmPlan || !activePayment) return;
    setPaying(true);
    try {
      const endpointMap: Record<string, string> = {
        epay: "/payments/epay-orders/create",
        stripe: "/payments/stripe-orders/create",
        alipay_official: "/payments/alipay-orders/create",
      };
      const endpoint = endpointMap[activePayment.payment_channel];
      if (!endpoint) throw new Error(t("membership.paymentNotConfigured"));
      const order = await post<CreatedOrder>(endpoint, {
        membership_plan_id: confirmPlan.plan.id,
        payment_method: activePayment.payment_method,
        return_url: getReturnUrl(),
      });
      if (order.status === "paid") {
        toast.success(t("membership.orderPaid"));
        setConfirmPlan(null);
        void handleMembershipPaid(order.order_no);
        return;
      }
      submitPaymentForm(t, order);
      setPayingOrders((prev) => [
        ...prev,
        {
          order_no: order.order_no,
          topup_amount: order.topup_amount,
          status: "pending",
        },
      ]);
      setConfirmPlan(null);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t("membership.createOrderFailed"));
    } finally {
      setPaying(false);
    }
  };

  if (loadFailed) {
    return (
      <Card className="shadow-card">
        <CardContent className="p-6">
          <p className="text-sm text-muted-foreground">{t("membership.loadFailed")}</p>
        </CardContent>
      </Card>
    );
  }

  if (!levels) {
    return (
      <Card className="shadow-card">
        <CardContent className="flex justify-center p-16">
          <Loading />
        </CardContent>
      </Card>
    );
  }

  // 无对外售卖等级时不展示整个模块
  if (levels.length === 0) return null;

  const periodLabel = (p: "week" | "month") =>
    p === "week" ? t("membership.periodWeek") : t("membership.periodMonth");

  return (
    <>
      <Card className="shadow-card">
        <CardContent className="p-6">
          {/* 标题区 */}
          <div className="flex items-center gap-3 border-b pb-5">
            <span className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-[#f59e0b] to-[#ec4899] text-white shadow-md">
              <Crown className="size-5" />
            </span>
            <div>
              <h2 className="text-lg font-semibold">{t("membership.title")}</h2>
              <p className="text-sm text-muted-foreground">
                {t("membership.subtitle")}
              </p>
            </div>
            {membership?.is_active && membership.level && (
              <Badge variant="secondary" className="ml-auto">
                {t("membership.currentBadge", {
                  name: membership.level.name,
                  date: membership.expires_at
                    ? new Date(membership.expires_at).toLocaleDateString(locale)
                    : "—",
                })}
              </Badge>
            )}
          </div>

          {/* 支付方式 */}
          {payments.length > 0 && (
            <div className="flex flex-wrap items-center gap-2 pt-5">
              <span className="text-sm text-muted-foreground">
                {t("membership.paymentSection")}：
              </span>
              {payments.map((p) => {
                const key = keyOf(p);
                const selected = activePayment && keyOf(activePayment) === key;
                return (
                  <button
                    key={key}
                    type="button"
                    onClick={() => setPaymentKey(key)}
                    className={cn(
                      "flex items-center gap-2 rounded-lg border px-3 py-1.5 text-sm transition-all",
                      selected
                        ? "border-foreground bg-muted/60 font-medium shadow-sm"
                        : "border-border bg-background text-muted-foreground hover:border-foreground/40"
                    )}
                  >
                    {p.payment_icon && (
                      <img
                        src={p.payment_icon}
                        alt=""
                        className="size-4 shrink-0 rounded object-contain"
                        loading="lazy"
                      />
                    )}
                    {p.payment_name}
                    {selected && <Check className="size-3.5 text-primary" />}
                  </button>
                );
              })}
            </div>
          )}

          {/* 等级卡片 */}
          <div className="grid gap-4 pt-5 sm:grid-cols-2 xl:grid-cols-3">
            {levels.map((level) => {
              const action = resolveAction(level, membership);
              const planId = selectedPlanId[level.id];
              const plan = level.plans.find((p) => p.id === planId) ?? level.plans[0];
              const isCurrent = membership?.is_active && membership.level?.id === level.id;
              return (
                <div
                  key={level.id}
                  className={cn(
                    "relative overflow-hidden rounded-xl border p-5 transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md",
                    isCurrent
                      ? "border-primary bg-primary/5 ring-1 ring-primary/20"
                      : "border-border bg-background"
                  )}
                >
                  <div
                    aria-hidden
                    className="absolute -right-8 -top-8 size-24 rounded-full bg-primary/10 blur-2xl"
                  />
                  <div className="relative space-y-4">
                    <div className="flex items-center gap-2">
                      <p className="text-base font-semibold">{level.name}</p>
                      {isCurrent && (
                        <Badge variant="default">{t("membership.currentLevel")}</Badge>
                      )}
                    </div>
                    {level.description && (
                      <p className="line-clamp-2 text-sm text-muted-foreground">
                        {level.description}
                      </p>
                    )}

                    {/* 特权摘要 */}
                    <ul className="space-y-1.5 text-xs text-muted-foreground">
                      {level.groups.length > 0 && (
                        <li className="flex items-center gap-1.5">
                          <Sparkles className="size-3.5 text-amber-500" />
                          {t("membership.exclusiveGroups", {
                            names: level.groups.map((g) => g.name).join("、"),
                          })}
                        </li>
                      )}
                    </ul>

                    {/* 周期切换 */}
                    {level.plans.length > 1 && (
                      <div className="flex gap-1 rounded-lg bg-muted/60 p-1">
                        {level.plans.map((p) => (
                          <button
                            key={p.id}
                            type="button"
                            onClick={() =>
                              setSelectedPlanId((prev) => ({ ...prev, [level.id]: p.id }))
                            }
                            className={cn(
                              "flex-1 rounded-md px-2 py-1 text-xs font-medium transition-all",
                              plan?.id === p.id
                                ? "bg-background shadow-sm"
                                : "text-muted-foreground hover:text-foreground"
                            )}
                          >
                            {periodLabel(p.period)}
                          </button>
                        ))}
                      </div>
                    )}

                    {/* 价格与赠送 */}
                    {plan && (
                      <div className="flex items-baseline gap-2">
                        <span className="text-2xl font-semibold tracking-tight">
                          ¥{formatAmount(plan.price)}
                        </span>
                        <span className="text-xs text-muted-foreground">
                          / {periodLabel(plan.period)}
                        </span>
                        {Number(plan.bonus_amount) > 0 && (
                          <span className="text-xs text-emerald-600 dark:text-emerald-400">
                            {t("membership.bonusHint", {
                              amount: formatAmount(plan.bonus_amount),
                            })}
                          </span>
                        )}
                      </div>
                    )}

                    {/* 购买按钮 */}
                    <Button
                      className="w-full"
                      disabled={action === "disabled" || !plan || payments.length === 0}
                      variant={action === "disabled" ? "outline" : "default"}
                      onClick={() => plan && openConfirm(level, plan)}
                    >
                      {action === "subscribe" && t("membership.actionSubscribe")}
                      {action === "renew" && t("membership.actionRenew")}
                      {action === "upgrade" && t("membership.actionUpgrade")}
                      {action === "disabled" && t("membership.actionDisabled")}
                    </Button>
                    {action === "upgrade" && (
                      <p className="text-center text-xs text-amber-600 dark:text-amber-400">
                        {t("membership.upgradeHint")}
                      </p>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
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
                    {t("membership.orderPaying")}
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
                    {convertedOrders.has(o.order_no)
                      ? t("membership.orderConverted")
                      : t("membership.orderPaidSuccess")}
                    <span className="ml-2 text-muted-foreground">
                      ¥{formatAmount(o.topup_amount)}
                    </span>
                  </p>
                  <button
                    type="button"
                    onClick={() =>
                      setPayingOrders((prev) =>
                        prev.filter((x) => x.order_no !== o.order_no)
                      )
                    }
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
                    {t("membership.orderFailed")}
                    <span className="ml-2 text-muted-foreground">
                      ¥{formatAmount(o.topup_amount)}
                    </span>
                  </p>
                  <button
                    type="button"
                    onClick={() =>
                      setPayingOrders((prev) =>
                        prev.filter((x) => x.order_no !== o.order_no)
                      )
                    }
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
      {confirmPlan && (
        <div
          className="fixed inset-0 z-80 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm"
          onClick={() => !paying && setConfirmPlan(null)}
        >
          <div
            className="w-full max-w-sm rounded-xl border bg-background p-6 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="text-base font-semibold">
              {t("membership.confirmTitle", { name: confirmPlan.level.name })}
            </h2>
            <p className="mt-1 text-sm text-muted-foreground">
              {resolveAction(confirmPlan.level, membership) === "upgrade"
                ? t("membership.confirmDescUpgrade")
                : t("membership.confirmDesc")}
            </p>
            <div className="mt-5 space-y-4">
              <div className="flex items-center justify-between">
                <span className="text-sm text-muted-foreground">
                  {t("membership.confirmPlan")}
                </span>
                <span className="text-base font-medium">
                  {confirmPlan.level.name} · {periodLabel(confirmPlan.plan.period)}
                </span>
              </div>
              {Number(confirmPlan.plan.bonus_amount) > 0 && (
                <div className="flex items-center justify-between">
                  <span className="text-sm text-muted-foreground">
                    {t("membership.confirmBonus")}
                  </span>
                  <span className="text-base font-medium text-emerald-600 dark:text-emerald-400">
                    ¥{formatAmount(confirmPlan.plan.bonus_amount)}
                  </span>
                </div>
              )}
              <div className="flex items-center justify-between">
                <span className="text-sm text-muted-foreground">
                  {t("membership.confirmPay")}
                </span>
                <span className="text-2xl font-semibold">
                  {quoting ? (
                    <Loading size="sm" />
                  ) : quote ? (
                    `¥${formatAmount(quote.pay_amount)}`
                  ) : (
                    "—"
                  )}
                </span>
              </div>
              <div className="flex items-center justify-between border-t pt-4">
                <span className="text-sm text-muted-foreground">
                  {t("membership.confirmPaymentMethod")}
                </span>
                <span className="font-medium">{activePayment?.payment_name}</span>
              </div>
            </div>
            <div className="mt-6 flex justify-end gap-2">
              <Button
                variant="outline"
                onClick={() => setConfirmPlan(null)}
                disabled={paying}
              >
                {t("membership.cancel")}
              </Button>
              <Button onClick={onConfirmPay} disabled={paying || quoting || !quote}>
                {paying && <Loader2 className="size-4 animate-spin" />}
                {t("membership.confirmButton")}
              </Button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
