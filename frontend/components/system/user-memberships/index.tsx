"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Crown,
  Gift,
  History,
  Loader2,
  RefreshCw,
  Search,
  ShieldOff,
  Users,
  X,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Loading } from "@/components/ui/loading";
import { Pagination } from "@/components/ui/pagination";
import { Select } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { toast } from "@/components/ui/toaster";
import { cn } from "@/lib/utils";
import {
  grantMembership,
  listMembershipLevels,
  listMembershipRecords,
  listUserMemberships,
  revokeMembership,
  type AdminMembershipLevel,
  type MembershipRecord,
  type UserMembershipItem,
} from "@/lib/membership";

const PAGE_SIZE = 20;
const RECORDS_PAGE_SIZE = 20;

type Translate = (key: string, options?: Record<string, unknown>) => string;

const formatTime = (locale: string, value: string | null) =>
  value ? new Date(value).toLocaleString(locale, { hour12: false }) : "—";

/** 金额格式化：纯字符串截取两位小数 */
const formatAmount = (raw: string) => {
  const [intPart = "0", fracPart = ""] = String(raw).trim().split(".");
  return `${intPart}.${`${fracPart}00`.slice(0, 2)}`;
};

/** 流水来源标签 */
const sourceLabel = (t: Translate, source: MembershipRecord["source"]) =>
  t(`userMembership.source.${source}`);

const sourceVariant = (
  source: MembershipRecord["source"]
): "default" | "secondary" | "outline" | "destructive" =>
  source === "purchase"
    ? "default"
    : source === "purchase_converted"
      ? "secondary"
      : source === "admin_grant"
        ? "outline"
        : "destructive";

/* ---------------- 授予会员弹窗 ---------------- */

function GrantDialog({
  userId,
  levels,
  onClose,
  onGranted,
}: {
  userId: string;
  levels: AdminMembershipLevel[];
  onClose: () => void;
  onGranted: () => void;
}) {
  const { t } = useTranslation("console");
  // 可选套餐：全部启用等级下的启用套餐（含隐藏等级，供管理员授予）
  const planOptions = useMemo(
    () =>
      levels
        .filter((lv) => lv.is_active)
        .flatMap((lv) =>
          lv.plans
            .filter((p) => p.is_active)
            .map((p) => ({
              value: p.id,
              label: `${lv.name} · ${p.period === "week" ? t("userMembership.periodWeek") : t("userMembership.periodMonth")}（¥${formatAmount(p.price)}）`,
            }))
        ),
    [levels, t]
  );

  const [planId, setPlanId] = useState("");
  const [quantity, setQuantity] = useState("1");
  const [grantBonus, setGrantBonus] = useState(false);
  const [reason, setReason] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!planId) {
      toast.warning(t("userMembership.planRequired"));
      return;
    }
    const qty = Number(quantity);
    if (!Number.isInteger(qty) || qty < 1 || qty > 12) {
      toast.warning(t("userMembership.quantityInvalid"));
      return;
    }
    setSubmitting(true);
    try {
      await grantMembership({
        user_id: userId,
        plan_id: planId,
        quantity: qty,
        grant_bonus: grantBonus,
        reason: reason.trim() || undefined,
      });
      toast.success(t("userMembership.grantSuccess"));
      onGranted();
      onClose();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t("userMembership.grantFailed"));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-80 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm"
      onClick={() => !submitting && onClose()}
    >
      <div
        className="w-full max-w-sm rounded-xl border bg-background p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-base font-semibold">{t("userMembership.grantTitle")}</h2>
        <p className="mt-1 break-all text-sm text-muted-foreground">
          {t("userMembership.grantDesc", { userId })}
        </p>
        <form onSubmit={onSubmit} className="mt-5 space-y-4">
          <div className="space-y-1.5">
            <label className="text-sm font-medium">{t("userMembership.plan")}</label>
            <Select
              value={planId}
              onValueChange={setPlanId}
              options={planOptions}
              placeholder={t("userMembership.planPlaceholder")}
              emptyText={t("userMembership.planEmpty")}
            />
          </div>
          <div className="space-y-1.5">
            <label className="text-sm font-medium">{t("userMembership.quantity")}</label>
            <Input
              value={quantity}
              onChange={(e) => setQuantity(e.target.value)}
              inputMode="numeric"
              placeholder="1-12"
            />
            <p className="text-xs text-muted-foreground">
              {t("userMembership.quantityHint")}
            </p>
          </div>
          <label className="flex items-center gap-2 text-sm">
            <Switch checked={grantBonus} onCheckedChange={setGrantBonus} />
            {t("userMembership.grantBonus")}
          </label>
          <div className="space-y-1.5">
            <label className="text-sm font-medium">{t("userMembership.reason")}</label>
            <Input
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder={t("userMembership.reasonPlaceholder")}
              maxLength={256}
            />
          </div>
          <div className="flex justify-end gap-2 border-t pt-4">
            <Button
              type="button"
              variant="outline"
              onClick={onClose}
              disabled={submitting}
            >
              {t("userMembership.cancel")}
            </Button>
            <Button type="submit" disabled={submitting}>
              {submitting && <Loader2 className="size-4 animate-spin" />}
              {t("userMembership.grantConfirm")}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}

/* ---------------- 撤销会员弹窗 ---------------- */

function RevokeDialog({
  userId,
  onClose,
  onRevoked,
}: {
  userId: string;
  onClose: () => void;
  onRevoked: () => void;
}) {
  const { t } = useTranslation("console");
  const [reason, setReason] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      await revokeMembership({ user_id: userId, reason: reason.trim() || undefined });
      toast.success(t("userMembership.revokeSuccess"));
      onRevoked();
      onClose();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t("userMembership.revokeFailed"));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-80 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm"
      onClick={() => !submitting && onClose()}
    >
      <div
        className="w-full max-w-sm rounded-xl border bg-background p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-base font-semibold">{t("userMembership.revokeTitle")}</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          {t("userMembership.revokeDesc")}
        </p>
        <form onSubmit={onSubmit} className="mt-5 space-y-4">
          <div className="space-y-1.5">
            <label className="text-sm font-medium">{t("userMembership.reason")}</label>
            <Input
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder={t("userMembership.reasonPlaceholder")}
              maxLength={256}
            />
          </div>
          <div className="flex justify-end gap-2 border-t pt-4">
            <Button
              type="button"
              variant="outline"
              onClick={onClose}
              disabled={submitting}
            >
              {t("userMembership.cancel")}
            </Button>
            <Button type="submit" variant="destructive" disabled={submitting}>
              {submitting && <Loader2 className="size-4 animate-spin" />}
              {t("userMembership.revokeConfirm")}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}

/* ---------------- 会员流水弹窗 ---------------- */

function RecordsDialog({
  userId,
  onClose,
}: {
  /** 空字符串表示查询全部用户 */
  userId: string;
  onClose: () => void;
}) {
  const { t, i18n } = useTranslation("console");
  const locale = i18n.language === "zh" ? "zh-CN" : "en-US";
  const [records, setRecords] = useState<MembershipRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);

  const load = useCallback(
    async (p: number) => {
      setLoading(true);
      try {
        const res = await listMembershipRecords({
          user_id: userId || undefined,
          page: p,
          page_size: RECORDS_PAGE_SIZE,
        });
        setRecords(res.items);
        setTotal(res.total);
      } catch (err) {
        toast.error(err instanceof Error ? err.message : t("userMembership.recordsFailed"));
      } finally {
        setLoading(false);
      }
    },
    [userId, t]
  );

  useEffect(() => {
    void Promise.resolve().then(() => load(page));
  }, [load, page]);

  return (
    <div
      className="fixed inset-0 z-80 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="flex max-h-[85vh] w-full max-w-4xl flex-col rounded-xl border bg-background shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b px-6 py-4">
          <h2 className="text-base font-semibold">
            {t("userMembership.recordsTitle")}
            <span className="ml-2 text-sm font-normal text-muted-foreground">
              {t("userMembership.recordsTotal", { total })}
            </span>
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="text-muted-foreground hover:text-foreground"
          >
            <X className="size-5" />
          </button>
        </div>
        <div className="flex-1 overflow-auto px-6 py-4">
          <table className="w-full min-w-max text-sm">
            <thead>
              <tr className="border-b text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
                <th className="pb-2 font-medium">{t("userMembership.colTime")}</th>
                <th className="pb-2 font-medium">{t("userMembership.colUserId")}</th>
                <th className="pb-2 font-medium">{t("userMembership.colSource")}</th>
                <th className="pb-2 font-medium">{t("userMembership.colLevel")}</th>
                <th className="pb-2 font-medium">{t("userMembership.colExpiresChange")}</th>
                <th className="pb-2 font-medium">{t("userMembership.colBonus")}</th>
                <th className="pb-2 font-medium">{t("userMembership.colReason")}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/60">
              {loading && records.length === 0 ? (
                <tr>
                  <td colSpan={7} className="py-16 text-center text-muted-foreground">
                    <Loading />
                  </td>
                </tr>
              ) : records.length === 0 ? (
                <tr>
                  <td colSpan={7} className="py-16 text-center text-muted-foreground">
                    {t("userMembership.recordsEmpty")}
                  </td>
                </tr>
              ) : (
                records.map((r) => (
                  <tr key={r.id} className="text-sm">
                    <td className="whitespace-nowrap py-3 text-xs text-muted-foreground">
                      {formatTime(locale, r.created_at)}
                    </td>
                    <td
                      className="max-w-28 truncate py-3 font-mono text-xs"
                      title={r.user_id}
                    >
                      {r.user_id}
                    </td>
                    <td className="py-3">
                      <Badge variant={sourceVariant(r.source)}>
                        {sourceLabel(t, r.source)}
                      </Badge>
                    </td>
                    <td className="whitespace-nowrap py-3">
                      {r.level_name}
                      {r.quantity > 1 && ` ×${r.quantity}`}
                    </td>
                    <td className="whitespace-nowrap py-3 text-xs text-muted-foreground">
                      {formatTime(locale, r.expires_before)} →{" "}
                      {formatTime(locale, r.expires_after)}
                    </td>
                    <td className="whitespace-nowrap py-3 tabular-nums">
                      {Number(r.bonus_amount) > 0 ? `¥${formatAmount(r.bonus_amount)}` : "—"}
                    </td>
                    <td className="max-w-32 truncate py-3 text-xs" title={r.reason}>
                      {r.reason || "—"}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
        {total > RECORDS_PAGE_SIZE && (
          <div className="border-t px-6 py-3">
            <Pagination
              page={page}
              totalPages={Math.ceil(total / RECORDS_PAGE_SIZE)}
              loading={loading}
              onChange={setPage}
            />
          </div>
        )}
      </div>
    </div>
  );
}

/* ---------------- 主面板 ---------------- */

export function UserMembershipsPanel() {
  const { t, i18n } = useTranslation("console");
  const locale = i18n.language === "zh" ? "zh-CN" : "en-US";

  const [items, setItems] = useState<UserMembershipItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // 筛选
  const [filterUserId, setFilterUserId] = useState("");
  const [filterLevelId, setFilterLevelId] = useState("");
  const [filterActive, setFilterActive] = useState("");
  // 已生效的筛选（点击查询后生效）
  const [applied, setApplied] = useState<{ user_id?: string; level_id?: string; is_active?: boolean }>({});

  // 等级选项（授予 + 筛选）
  const [levels, setLevels] = useState<AdminMembershipLevel[]>([]);

  // 弹窗
  const [grantUserId, setGrantUserId] = useState<string | null>(null);
  const [revokeUserId, setRevokeUserId] = useState<string | null>(null);
  const [recordsUserId, setRecordsUserId] = useState<string | null>(null);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const load = useCallback(
    async (p: number) => {
      setLoading(true);
      setError("");
      try {
        const data = await listUserMemberships({ ...applied, page: p, page_size: PAGE_SIZE });
        setItems(data.items);
        setTotal(data.total);
      } catch (err) {
        setError(err instanceof Error ? err.message : t("userMembership.loadFailed"));
      } finally {
        setLoading(false);
      }
    },
    [applied, t]
  );

  useEffect(() => {
    void Promise.resolve().then(() => load(page));
  }, [load, page]);

  // 加载全部等级（含隐藏），用于授予与筛选
  useEffect(() => {
    listMembershipLevels({ page: 1, page_size: 100 })
      .then((res) => setLevels(res.items))
      .catch(() => {});
  }, []);

  const onSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setPage(1);
    setApplied({
      user_id: filterUserId.trim() || undefined,
      level_id: filterLevelId || undefined,
      is_active: filterActive === "" ? undefined : filterActive === "true",
    });
  };

  const levelOptions = useMemo(
    () => [
      { value: "", label: t("userMembership.filterLevelAll") },
      ...levels.map((lv) => ({ value: lv.id, label: lv.name })),
    ],
    [levels, t]
  );

  return (
    <div className="flex min-h-[calc(100vh-7.5rem)] w-full flex-col gap-6">
      {/* 页头 */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold">{t("userMembership.title")}</h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            {t("userMembership.totalRecords", { total })}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setRecordsUserId("")}
          >
            <History className="size-4" />
            {t("userMembership.allRecords")}
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => load(page)}
            disabled={loading}
          >
            <RefreshCw className={cn("size-4", loading && "animate-spin")} />
            {t("userMembership.refresh")}
          </Button>
        </div>
      </div>

      {/* 筛选 */}
      <form
        onSubmit={onSearch}
        className="flex flex-wrap items-center gap-3 rounded-xl border border-border/60 bg-card/40 p-4"
      >
        <Input
          value={filterUserId}
          onChange={(e) => setFilterUserId(e.target.value)}
          placeholder={t("userMembership.filterByUserId")}
          className="w-64"
        />
        <Select
          value={filterLevelId}
          onValueChange={setFilterLevelId}
          options={levelOptions}
          className="w-36"
          aria-label={t("userMembership.filterByLevel")}
        />
        <Select
          value={filterActive}
          onValueChange={setFilterActive}
          options={[
            { value: "", label: t("userMembership.filterActiveAll") },
            { value: "true", label: t("userMembership.statusActive") },
            { value: "false", label: t("userMembership.statusExpired") },
          ]}
          className="w-36"
          aria-label={t("userMembership.filterByStatus")}
        />
        <Button type="submit" size="sm" variant="outline" disabled={loading}>
          <Search className="size-4" />
          {t("userMembership.search")}
        </Button>
      </form>

      {/* 列表 */}
      <div className="relative overflow-hidden rounded-xl border border-border/60 bg-card/40">
        {error && items.length === 0 ? (
          <div className="flex flex-col items-center gap-2 py-16 text-sm text-muted-foreground">
            <p>{t("userMembership.loadFailedWithReason", { error })}</p>
            <Button variant="outline" size="sm" onClick={() => load(page)}>
              {t("userMembership.retry")}
            </Button>
          </div>
        ) : items.length === 0 ? (
          <div className="flex items-center justify-center py-16 text-muted-foreground">
            {loading ? (
              <Loading size="lg" />
            ) : (
              <div className="flex flex-col items-center gap-2">
                <Users className="size-8 text-muted-foreground/50" />
                <p className="text-sm">{t("userMembership.empty")}</p>
              </div>
            )}
          </div>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table
                className={cn(
                  "w-full min-w-max text-sm transition-opacity duration-300",
                  loading && "pointer-events-none opacity-40"
                )}
              >
                <thead>
                  <tr className="border-b border-border/60 bg-muted/40 text-center text-xs text-muted-foreground">
                    <th className="px-4 py-3 text-left font-medium">
                      {t("userMembership.colUserId")}
                    </th>
                    <th className="px-4 py-3 font-medium">{t("userMembership.colLevel")}</th>
                    <th className="px-4 py-3 font-medium">
                      {t("userMembership.colStartedAt")}
                    </th>
                    <th className="px-4 py-3 font-medium">
                      {t("userMembership.colExpiresAt")}
                    </th>
                    <th className="px-4 py-3 font-medium">{t("userMembership.colStatus")}</th>
                    <th className="px-4 py-3 font-medium">
                      {t("userMembership.colActions")}
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/60">
                  {items.map((item) => (
                    <tr key={item.id} className="transition-colors hover:bg-accent/40">
                      <td
                        className="max-w-44 truncate px-4 py-3 font-mono text-xs"
                        title={item.user_id}
                      >
                        {item.user_id}
                      </td>
                      <td className="px-4 py-3 text-center">
                        <Badge variant="secondary" className="gap-1">
                          <Crown className="size-3" />
                          {item.level_name}
                        </Badge>
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 text-center text-xs text-muted-foreground">
                        {formatTime(locale, item.started_at)}
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 text-center text-xs text-muted-foreground">
                        {formatTime(locale, item.expires_at)}
                      </td>
                      <td className="px-4 py-3 text-center">
                        <Badge variant={item.is_active ? "default" : "outline"}>
                          {item.is_active
                            ? t("userMembership.statusActive")
                            : t("userMembership.statusExpired")}
                        </Badge>
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center justify-center gap-1">
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => setGrantUserId(item.user_id)}
                          >
                            <Gift className="size-4" />
                            {t("userMembership.grant")}
                          </Button>
                          {item.is_active && (
                            <Button
                              size="sm"
                              variant="ghost"
                              className="text-destructive hover:text-destructive"
                              onClick={() => setRevokeUserId(item.user_id)}
                            >
                              <ShieldOff className="size-4" />
                              {t("userMembership.revoke")}
                            </Button>
                          )}
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => setRecordsUserId(item.user_id)}
                          >
                            <History className="size-4" />
                            {t("userMembership.records")}
                          </Button>
                        </div>
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

      {/* 分页 */}
      {!error && items.length > 0 && (
        <Pagination
          page={page}
          totalPages={totalPages}
          loading={loading}
          onChange={setPage}
          className="mt-auto"
        />
      )}

      {/* 授予弹窗 */}
      {grantUserId && (
        <GrantDialog
          userId={grantUserId}
          levels={levels}
          onClose={() => setGrantUserId(null)}
          onGranted={() => load(page)}
        />
      )}

      {/* 撤销弹窗 */}
      {revokeUserId && (
        <RevokeDialog
          userId={revokeUserId}
          onClose={() => setRevokeUserId(null)}
          onRevoked={() => load(page)}
        />
      )}

      {/* 流水弹窗 */}
      {recordsUserId !== null && (
        <RecordsDialog userId={recordsUserId} onClose={() => setRecordsUserId(null)} />
      )}
    </div>
  );
}
