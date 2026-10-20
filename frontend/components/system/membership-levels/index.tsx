"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Crown,
  Loader2,
  Pencil,
  Plus,
  RefreshCw,
  Trash2,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Loading } from "@/components/ui/loading";
import { MultiSelect } from "@/components/ui/multi-select";
import { Pagination } from "@/components/ui/pagination";
import { Select } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { toast } from "@/components/ui/toaster";
import { cn } from "@/lib/utils";
import { get } from "@/lib/request";
import {
  createMembershipLevel,
  createMembershipPlan,
  deleteMembershipLevel,
  deleteMembershipPlan,
  listMembershipLevels,
  updateMembershipLevel,
  updateMembershipLevelStatus,
  updateMembershipPlan,
  updateMembershipPlanStatus,
  type AdminMembershipLevel,
} from "@/lib/membership";

/** 受限分组选项（group_ids 必须是受限分组） */
type RestrictedGroup = {
  id: number;
  name: string;
  visibility?: string;
};

const PAGE_SIZE = 20;

type Translate = (key: string, options?: Record<string, unknown>) => string;

/** 金额格式化：纯字符串截取两位小数 */
const formatAmount = (raw: string) => {
  const [intPart = "0", fracPart = ""] = String(raw).trim().split(".");
  return `${intPart}.${`${fracPart}00`.slice(0, 2)}`;
};

/** 金额输入校验：非负、最多两位小数；公开等级要求 > 0 时由调用方另判 */
const normalizePrice = (raw: string): string | null => {
  const text = raw.trim();
  if (!/^\d+(\.\d{1,2})?$/.test(text)) return null;
  return text;
};

const isPositivePrice = (raw: string) => /[1-9]/.test(raw.replace(".", ""));

const formatTime = (locale: string, value: string | null) =>
  value ? new Date(value).toLocaleString(locale, { hour12: false }) : "—";

const periodLabel = (t: Translate, p: "week" | "month") =>
  p === "week" ? t("membershipAdmin.periodWeek") : t("membershipAdmin.periodMonth");

/* ---------------- 套餐编辑子表单 ---------------- */

type PlanDraft = {
  /** 已存在的套餐 id；新增为 null */
  id: string | null;
  period: "week" | "month";
  price: string;
  bonus_amount: string;
  is_active: boolean;
  /** 标记删除（仅已有套餐） */
  removed: boolean;
};

/* ---------------- 等级编辑/创建弹窗 ---------------- */

function LevelFormDialog({
  level,
  groups,
  onClose,
  onSaved,
}: {
  /** null 表示创建 */
  level: AdminMembershipLevel | null;
  groups: RestrictedGroup[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const { t } = useTranslation("console");
  const isEdit = level !== null;

  const [code, setCode] = useState(level?.code ?? "");
  const [name, setName] = useState(level?.name ?? "");
  const [description, setDescription] = useState(level?.description ?? "");
  const [rank, setRank] = useState(String(level?.rank ?? 1));
  const [isPublic, setIsPublic] = useState(level?.is_public ?? false);
  const [isActive, setIsActive] = useState(level?.is_active ?? true);
  const [groupIds, setGroupIds] = useState<string[]>(
    (level?.groups ?? []).map((g) => String(g.id))
  );
  const [plans, setPlans] = useState<PlanDraft[]>(
    (level?.plans ?? []).map((p) => ({
      id: p.id,
      period: p.period,
      price: p.price,
      bonus_amount: p.bonus_amount,
      is_active: p.is_active,
      removed: false,
    }))
  );
  const [submitting, setSubmitting] = useState(false);

  const groupOptions = useMemo(
    () => groups.map((g) => ({ value: String(g.id), label: g.name })),
    [groups]
  );

  const usedPeriods = plans.filter((p) => !p.removed).map((p) => p.period);

  const addPlan = (period: "week" | "month") => {
    setPlans((prev) => [
      ...prev,
      { id: null, period, price: "", bonus_amount: "", is_active: true, removed: false },
    ]);
  };

  const updatePlan = (idx: number, patch: Partial<PlanDraft>) => {
    setPlans((prev) => prev.map((p, i) => (i === idx ? { ...p, ...patch } : p)));
  };

  const removePlan = (idx: number) => {
    setPlans((prev) =>
      prev.map((p, i) =>
        i === idx ? (p.id ? { ...p, removed: true } : { ...p, removed: true }) : p
      ).filter((p, i) => i !== idx || p.id !== null)
    );
  };

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) {
      toast.warning(t("membershipAdmin.nameRequired"));
      return;
    }
    if (!isEdit && !/^[a-z0-9_-]{1,32}$/.test(code.trim())) {
      toast.warning(t("membershipAdmin.codeInvalid"));
      return;
    }
    const rankNum = Number(rank);
    if (!Number.isInteger(rankNum) || rankNum < 1) {
      toast.warning(t("membershipAdmin.rankInvalid"));
      return;
    }
    // 校验套餐金额
    const activePlans = plans.filter((p) => !p.removed);
    for (const p of activePlans) {
      const price = normalizePrice(p.price);
      if (price === null || (isPublic && !isPositivePrice(price))) {
        toast.warning(
          t("membershipAdmin.priceInvalid", {
            period: periodLabel(t, p.period),
          })
        );
        return;
      }
      if (p.bonus_amount.trim() && normalizePrice(p.bonus_amount) === null) {
        toast.warning(
          t("membershipAdmin.bonusInvalid", {
            period: periodLabel(t, p.period),
          })
        );
        return;
      }
    }

    setSubmitting(true);
    try {
      const group_ids = groupIds.map(Number);
      if (!isEdit) {
        await createMembershipLevel({
          code: code.trim(),
          name: name.trim(),
          description: description.trim(),
          rank: rankNum,
          is_public: isPublic,
          is_active: isActive,
          plans: activePlans.map((p) => ({
            period: p.period,
            price: p.price.trim(),
            bonus_amount: p.bonus_amount.trim() || undefined,
            is_active: p.is_active,
          })),
          group_ids,
        });
        toast.success(t("membershipAdmin.createSuccess"));
      } else {
        await updateMembershipLevel({
          level_id: level.id,
          name: name.trim(),
          description: description.trim(),
          rank: rankNum,
          is_public: isPublic,
          is_active: isActive,
          group_ids,
        });
        // 增量处理套餐：新增 / 更新 / 状态 / 删除
        for (const p of plans) {
          if (p.removed && p.id) {
            await deleteMembershipPlan({ plan_id: p.id });
          } else if (!p.removed && !p.id) {
            await createMembershipPlan({
              level_id: level.id,
              period: p.period,
              price: p.price.trim(),
              bonus_amount: p.bonus_amount.trim() || undefined,
              is_active: p.is_active,
            });
          } else if (!p.removed && p.id) {
            const original = level.plans.find((o) => o.id === p.id);
            if (
              original &&
              (original.price !== p.price.trim() ||
                original.bonus_amount !== (p.bonus_amount.trim() || "0.00"))
            ) {
              await updateMembershipPlan({
                plan_id: p.id,
                price: p.price.trim(),
                bonus_amount: p.bonus_amount.trim() || undefined,
              });
            }
            if (original && original.is_active !== p.is_active) {
              await updateMembershipPlanStatus({ plan_id: p.id, is_active: p.is_active });
            }
          }
        }
        toast.success(t("membershipAdmin.updateSuccess"));
      }
      onSaved();
      onClose();
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : t("membershipAdmin.saveFailed")
      );
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
        className="max-h-[85vh] w-full max-w-lg overflow-y-auto rounded-xl border bg-background p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-base font-semibold">
          {isEdit ? t("membershipAdmin.editTitle") : t("membershipAdmin.createTitle")}
        </h2>
        <p className="mt-1 text-sm text-muted-foreground">
          {isEdit ? t("membershipAdmin.editDesc") : t("membershipAdmin.createDesc")}
        </p>
        <form onSubmit={onSubmit} className="mt-5 space-y-4">
          {!isEdit && (
            <div className="space-y-1.5">
              <label className="text-sm font-medium">{t("membershipAdmin.code")}</label>
              <Input
                value={code}
                onChange={(e) => setCode(e.target.value)}
                placeholder={t("membershipAdmin.codePlaceholder")}
                maxLength={32}
                autoComplete="off"
              />
              <p className="text-xs text-muted-foreground">
                {t("membershipAdmin.codeHint")}
              </p>
            </div>
          )}
          <div className="space-y-1.5">
            <label className="text-sm font-medium">{t("membershipAdmin.name")}</label>
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={t("membershipAdmin.namePlaceholder")}
              maxLength={64}
            />
          </div>
          <div className="space-y-1.5">
            <label className="text-sm font-medium">
              {t("membershipAdmin.description")}
            </label>
            <Input
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder={t("membershipAdmin.descriptionPlaceholder")}
              maxLength={512}
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <label className="text-sm font-medium">{t("membershipAdmin.rank")}</label>
              <Input
                value={rank}
                onChange={(e) => setRank(e.target.value)}
                inputMode="numeric"
              />
              <p className="text-xs text-muted-foreground">
                {t("membershipAdmin.rankHint")}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-6">
            <label className="flex items-center gap-2 text-sm">
              <Switch checked={isPublic} onCheckedChange={setIsPublic} />
              {t("membershipAdmin.isPublic")}
            </label>
            <label className="flex items-center gap-2 text-sm">
              <Switch checked={isActive} onCheckedChange={setIsActive} />
              {t("membershipAdmin.isActive")}
            </label>
          </div>
          <div className="space-y-1.5">
            <label className="text-sm font-medium">
              {t("membershipAdmin.exclusiveGroups")}
            </label>
            <MultiSelect
              values={groupIds}
              onValuesChange={setGroupIds}
              options={groupOptions}
              placeholder={t("membershipAdmin.groupsPlaceholder")}
              emptyText={t("membershipAdmin.groupsEmpty")}
            />
            <p className="text-xs text-muted-foreground">
              {t("membershipAdmin.groupsHint")}
            </p>
          </div>

          {/* 套餐 */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <label className="text-sm font-medium">{t("membershipAdmin.plans")}</label>
              <div className="flex gap-1.5">
                {(["week", "month"] as const)
                  .filter((p) => !usedPeriods.includes(p))
                  .map((p) => (
                    <Button
                      key={p}
                      type="button"
                      size="sm"
                      variant="outline"
                      onClick={() => addPlan(p)}
                    >
                      <Plus className="size-3.5" />
                      {periodLabel(t, p)}
                    </Button>
                  ))}
              </div>
            </div>
            {plans.filter((p) => !p.removed).length === 0 ? (
              <p className="rounded-lg border border-dashed px-3 py-4 text-center text-xs text-muted-foreground">
                {t("membershipAdmin.plansEmpty")}
              </p>
            ) : (
              <div className="space-y-2">
                {plans.map((p, idx) =>
                  p.removed ? null : (
                    <div
                      key={p.id ?? `new-${p.period}`}
                      className="flex items-center gap-2 rounded-lg border p-3"
                    >
                      <span className="w-14 shrink-0 text-xs font-medium text-muted-foreground">
                        {periodLabel(t, p.period)}
                      </span>
                      <Input
                        value={p.price}
                        onChange={(e) => updatePlan(idx, { price: e.target.value })}
                        placeholder={t("membershipAdmin.pricePlaceholder")}
                        inputMode="decimal"
                        className="h-8"
                      />
                      <Input
                        value={p.bonus_amount}
                        onChange={(e) =>
                          updatePlan(idx, { bonus_amount: e.target.value })
                        }
                        placeholder={t("membershipAdmin.bonusPlaceholder")}
                        inputMode="decimal"
                        className="h-8"
                      />
                      <Switch
                        checked={p.is_active}
                        onCheckedChange={(v) => updatePlan(idx, { is_active: v })}
                      />
                      <button
                        type="button"
                        onClick={() => removePlan(idx)}
                        className="shrink-0 text-muted-foreground hover:text-destructive"
                        aria-label={t("membershipAdmin.removePlan")}
                      >
                        <Trash2 className="size-4" />
                      </button>
                    </div>
                  )
                )}
              </div>
            )}
            <p className="text-xs text-muted-foreground">
              {t("membershipAdmin.plansHint")}
            </p>
          </div>

          <div className="flex justify-end gap-2 border-t pt-4">
            <Button
              type="button"
              variant="outline"
              onClick={onClose}
              disabled={submitting}
            >
              {t("membershipAdmin.cancel")}
            </Button>
            <Button type="submit" disabled={submitting}>
              {submitting && <Loader2 className="size-4 animate-spin" />}
              {isEdit ? t("membershipAdmin.save") : t("membershipAdmin.create")}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}

/* ---------------- 主面板 ---------------- */

export function MembershipLevelsPanel() {
  const { t, i18n } = useTranslation("console");
  const locale = i18n.language === "zh" ? "zh-CN" : "en-US";

  const [levels, setLevels] = useState<AdminMembershipLevel[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // 筛选
  const [filterPublic, setFilterPublic] = useState("");
  const [filterActive, setFilterActive] = useState("");

  // 受限分组选项
  const [groups, setGroups] = useState<RestrictedGroup[]>([]);

  // 弹窗
  const [formLevel, setFormLevel] = useState<AdminMembershipLevel | null | "create">(
    null
  );
  const [deleteTarget, setDeleteTarget] = useState<AdminMembershipLevel | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [togglingId, setTogglingId] = useState<string | null>(null);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const load = useCallback(
    async (p: number) => {
      setLoading(true);
      setError("");
      try {
        const data = await listMembershipLevels({
          is_public: filterPublic === "" ? undefined : filterPublic === "true",
          is_active: filterActive === "" ? undefined : filterActive === "true",
          page: p,
          page_size: PAGE_SIZE,
        });
        setLevels(data.items);
        setTotal(data.total);
      } catch (err) {
        setError(err instanceof Error ? err.message : t("membershipAdmin.loadFailed"));
      } finally {
        setLoading(false);
      }
    },
    [filterPublic, filterActive, t]
  );

  useEffect(() => {
    void Promise.resolve().then(() => load(page));
  }, [load, page]);

  // 加载受限分组（用于专享分组多选）
  useEffect(() => {
    get<{ items: RestrictedGroup[] } | RestrictedGroup[]>("/admin/token/groups/list", {
      params: { page: 1, page_size: 100 },
    })
      .then((res) => {
        const items = Array.isArray(res) ? res : (res.items ?? []);
        setGroups(items.filter((item) => item.visibility === "restricted"));
      })
      .catch(() => {});
  }, []);

  const onToggleActive = async (level: AdminMembershipLevel) => {
    setTogglingId(level.id);
    try {
      await updateMembershipLevelStatus({
        level_id: level.id,
        is_active: !level.is_active,
      });
      toast.success(
        level.is_active
          ? t("membershipAdmin.disabledToast")
          : t("membershipAdmin.enabledToast")
      );
      void load(page);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t("membershipAdmin.toggleFailed"));
    } finally {
      setTogglingId(null);
    }
  };

  const onDelete = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await deleteMembershipLevel({ level_id: deleteTarget.id });
      toast.success(t("membershipAdmin.deleteSuccess"));
      setDeleteTarget(null);
      void load(page);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t("membershipAdmin.deleteFailed"));
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div className="flex min-h-[calc(100vh-7.5rem)] w-full flex-col gap-6">
      {/* 页头 */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold">{t("membershipAdmin.title")}</h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            {t("membershipAdmin.totalLevels", { total })}
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
            {t("membershipAdmin.refresh")}
          </Button>
          <Button size="sm" onClick={() => setFormLevel("create")}>
            <Plus className="size-4" />
            {t("membershipAdmin.createButton")}
          </Button>
        </div>
      </div>

      {/* 筛选 */}
      <div className="flex flex-wrap items-center gap-3 rounded-xl border border-border/60 bg-card/40 p-4">
        <Select
          value={filterPublic}
          onValueChange={(v) => {
            setFilterPublic(v);
            setPage(1);
          }}
          options={[
            { value: "", label: t("membershipAdmin.filterPublicAll") },
            { value: "true", label: t("membershipAdmin.filterPublicYes") },
            { value: "false", label: t("membershipAdmin.filterPublicNo") },
          ]}
          className="w-36"
          aria-label={t("membershipAdmin.filterPublicAria")}
        />
        <Select
          value={filterActive}
          onValueChange={(v) => {
            setFilterActive(v);
            setPage(1);
          }}
          options={[
            { value: "", label: t("membershipAdmin.filterActiveAll") },
            { value: "true", label: t("membershipAdmin.statusActive") },
            { value: "false", label: t("membershipAdmin.statusInactive") },
          ]}
          className="w-36"
          aria-label={t("membershipAdmin.filterActiveAria")}
        />
      </div>

      {/* 列表 */}
      <div className="relative overflow-hidden rounded-xl border border-border/60 bg-card/40">
        {error && levels.length === 0 ? (
          <div className="flex flex-col items-center gap-2 py-16 text-sm text-muted-foreground">
            <p>{t("membershipAdmin.loadFailedWithReason", { error })}</p>
            <Button variant="outline" size="sm" onClick={() => load(page)}>
              {t("membershipAdmin.retry")}
            </Button>
          </div>
        ) : levels.length === 0 ? (
          <div className="flex items-center justify-center py-16 text-muted-foreground">
            {loading ? (
              <Loading size="lg" />
            ) : (
              <div className="flex flex-col items-center gap-2">
                <Crown className="size-8 text-muted-foreground/50" />
                <p className="text-sm">{t("membershipAdmin.empty")}</p>
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
                      {t("membershipAdmin.colName")}
                    </th>
                    <th className="px-4 py-3 font-medium">{t("membershipAdmin.colRank")}</th>
                    <th className="px-4 py-3 font-medium">
                      {t("membershipAdmin.colVisibility")}
                    </th>
                    <th className="px-4 py-3 text-left font-medium">
                      {t("membershipAdmin.colPlans")}
                    </th>
                    <th className="px-4 py-3 text-left font-medium">
                      {t("membershipAdmin.colGroups")}
                    </th>
                    <th className="px-4 py-3 font-medium">
                      {t("membershipAdmin.colStatus")}
                    </th>
                    <th className="px-4 py-3 font-medium">
                      {t("membershipAdmin.colCreatedAt")}
                    </th>
                    <th className="px-4 py-3 font-medium">
                      {t("membershipAdmin.colActions")}
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/60">
                  {levels.map((level) => (
                    <tr key={level.id} className="transition-colors hover:bg-accent/40">
                      <td className="px-4 py-3">
                        <div className="space-y-0.5">
                          <p className="font-medium">{level.name}</p>
                          <p className="font-mono text-xs text-muted-foreground">
                            {level.code}
                          </p>
                        </div>
                      </td>
                      <td className="px-4 py-3 text-center tabular-nums">{level.rank}</td>
                      <td className="px-4 py-3 text-center">
                        <Badge variant={level.is_public ? "default" : "secondary"}>
                          {level.is_public
                            ? t("membershipAdmin.visibilityPublic")
                            : t("membershipAdmin.visibilityHidden")}
                        </Badge>
                      </td>
                      <td className="px-4 py-3">
                        <div className="space-y-1">
                          {level.plans.length === 0 ? (
                            <span className="text-xs text-muted-foreground">—</span>
                          ) : (
                            level.plans.map((p) => (
                              <p
                                key={p.id}
                                className={cn(
                                  "whitespace-nowrap text-xs",
                                  !p.is_active && "text-muted-foreground line-through"
                                )}
                              >
                                {periodLabel(t, p.period)} ¥{formatAmount(p.price)}
                                {Number(p.bonus_amount) > 0 &&
                                  ` · ${t("membershipAdmin.bonusShort", { amount: formatAmount(p.bonus_amount) })}`}
                              </p>
                            ))
                          )}
                        </div>
                      </td>
                      <td className="max-w-40 px-4 py-3">
                        {level.groups.length === 0 ? (
                          <span className="text-xs text-muted-foreground">—</span>
                        ) : (
                          <p
                            className="truncate text-xs"
                            title={level.groups.map((g) => g.name).join("、")}
                          >
                            {level.groups.map((g) => g.name).join("、")}
                          </p>
                        )}
                      </td>
                      <td className="px-4 py-3 text-center">
                        <Switch
                          checked={level.is_active}
                          disabled={togglingId === level.id}
                          onCheckedChange={() => onToggleActive(level)}
                        />
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 text-center text-xs text-muted-foreground">
                        {formatTime(locale, level.created_at)}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center justify-center gap-1">
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => setFormLevel(level)}
                          >
                            <Pencil className="size-4" />
                            {t("membershipAdmin.edit")}
                          </Button>
                          <Button
                            size="sm"
                            variant="ghost"
                            className="text-destructive hover:text-destructive"
                            onClick={() => setDeleteTarget(level)}
                          >
                            <Trash2 className="size-4" />
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
      {!error && levels.length > 0 && (
        <Pagination
          page={page}
          totalPages={totalPages}
          loading={loading}
          onChange={setPage}
          className="mt-auto"
        />
      )}

      {/* 创建/编辑弹窗 */}
      {formLevel !== null && (
        <LevelFormDialog
          level={formLevel === "create" ? null : formLevel}
          groups={groups}
          onClose={() => setFormLevel(null)}
          onSaved={() => load(page)}
        />
      )}

      {/* 删除确认 */}
      {deleteTarget && (
        <div
          className="fixed inset-0 z-80 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm"
          onClick={() => !deleting && setDeleteTarget(null)}
        >
          <div
            className="w-full max-w-sm rounded-xl border bg-background p-6 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="text-base font-semibold">
              {t("membershipAdmin.deleteTitle")}
            </h2>
            <p className="mt-1 text-sm text-muted-foreground">
              {t("membershipAdmin.deleteConfirm", { name: deleteTarget.name })}
            </p>
            <div className="mt-6 flex justify-end gap-2">
              <Button
                variant="outline"
                onClick={() => setDeleteTarget(null)}
                disabled={deleting}
              >
                {t("membershipAdmin.cancel")}
              </Button>
              <Button variant="destructive" onClick={onDelete} disabled={deleting}>
                {deleting && <Loader2 className="size-4 animate-spin" />}
                {t("membershipAdmin.confirmDelete")}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
