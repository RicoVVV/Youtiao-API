"use client";

import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Gauge, Plus, RefreshCw, Search, Users as UsersIcon, Wallet, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Loading } from "@/components/ui/loading";
import { Pagination } from "@/components/ui/pagination";
import { Select, type SelectOption } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { toast } from "@/components/ui/toaster";
import { cn } from "@/lib/utils";
import { get, post } from "@/lib/request";
import {
  getUserModelConcurrency,
  updateUserModelConcurrency,
  type UserModelConcurrencyOverride,
  type UserModelConcurrencyUsage,
} from "@/lib/concurrency";

type AdminUser = {
  id: string;
  username: string;
  is_active: boolean;
  is_admin: boolean;
  balance: string;
  usage: string;
  /** 该用户所有模型的活跃租约总数，仅用于运行情况查看 */
  active_lease_count: number;
  created_at: string;
};

const PAGE_SIZE = 10;

/** 兼容多种分页响应：数组 / { items, total } / { users, total } */
function normalize(data: unknown): { users: AdminUser[]; total: number } {
  if (Array.isArray(data)) return { users: data, total: data.length };
  if (data && typeof data === "object") {
    const d = data as Record<string, unknown>;
    const list = (d.items ?? d.users ?? d.list ?? []) as AdminUser[];
    const total = typeof d.total === "number" ? d.total : list.length;
    return { users: list, total };
  }
  return { users: [], total: 0 };
}

/** 新建用户弹窗 */
function CreateUserDialog({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: () => void;
}) {
  const { t } = useTranslation("console");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!username.trim() || !password) {
      toast.warning(t("users.fillCredentials"));
      return;
    }
    setSubmitting(true);
    try {
      await post("/admin/user/create", { username: username.trim(), password });
      toast.success(t("users.createSuccess"));
      onCreated();
      onClose();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t("users.createFailed"));
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
        <h2 className="text-base font-semibold">{t("users.createTitle")}</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          {t("users.createDesc")}
        </p>
        <form onSubmit={onSubmit} className="mt-5 space-y-4">
          <div className="space-y-1.5">
            <label htmlFor="create-username" className="text-sm font-medium">
              {t("users.username")}
            </label>
            <Input
              id="create-username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder={t("users.usernamePlaceholder")}
              autoComplete="off"
            />
          </div>
          <div className="space-y-1.5">
            <label htmlFor="create-password" className="text-sm font-medium">
              {t("users.password")}
            </label>
            <Input
              id="create-password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={t("users.passwordPlaceholder")}
              autoComplete="new-password"
            />
          </div>
          <div className="flex justify-end gap-2 pt-1">
            <Button type="button" variant="outline" onClick={onClose}>
              {t("users.cancel")}
            </Button>
            <Button type="submit" disabled={submitting}>
              {submitting && <Loading size="sm" />}
              {t("users.create")}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}

/** 用户模型并发覆盖弹窗：按模型查询、创建、更新和停用覆盖；停用后回退到模型默认值 */
function UserModelConcurrencyDialog({
  user,
  onClose,
}: {
  user: AdminUser;
  onClose: () => void;
}) {
  const { t } = useTranslation("console");
  const [usage, setUsage] = useState<UserModelConcurrencyUsage | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [updatingId, setUpdatingId] = useState<string | null>(null);
  // 表单
  const [modelId, setModelId] = useState("");
  const [limit, setLimit] = useState("");
  const [active, setActive] = useState(true);
  // 模型下拉数据
  const [modelOptions, setModelOptions] = useState<SelectOption[]>([]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getUserModelConcurrency(user.id);
      setUsage(data);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t("users.loadFailed"));
    } finally {
      setLoading(false);
    }
  }, [user.id, t]);

  useEffect(() => {
    load();
  }, [load]);

  // 拉取模型列表供覆盖目标选择
  useEffect(() => {
    get<unknown>("/admin/models/list", { params: { page: 1, page_size: 100 } })
      .then((data) => {
        const list = (Array.isArray(data)
          ? data
          : ((data as Record<string, unknown>).items ??
            (data as Record<string, unknown>).models ??
            (data as Record<string, unknown>).list ??
            [])) as { id: string; name: string }[];
        setModelOptions(list.map((m) => ({ value: m.id, label: m.name })));
      })
      .catch(() => {});
  }, []);

  const modelLabel = (id: string) =>
    modelOptions.find((o) => o.value === id)?.label ?? id;

  const activeCount = (id: string) => usage?.active_lease_counts[id] ?? 0;

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const value = Number(limit);
    if (!limit.trim() || !Number.isInteger(value) || value < 0 || value > 10000) {
      toast.warning(t("users.limitRange"));
      return;
    }
    if (!modelId) {
      toast.warning(t("users.selectModelRequired"));
      return;
    }
    setSubmitting(true);
    try {
      await updateUserModelConcurrency({
        user_id: user.id,
        model_id: modelId,
        concurrency_limit: value,
        active,
      });
      toast.success(t("users.overrideSaved"));
      setLimit("");
      setModelId("");
      await load();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t("users.saveFailed"));
    } finally {
      setSubmitting(false);
    }
  };

  const toggleOverride = async (
    item: UserModelConcurrencyOverride,
    nextActive: boolean
  ) => {
    setUpdatingId(item.id);
    try {
      await updateUserModelConcurrency({
        user_id: user.id,
        model_id: item.model_id,
        concurrency_limit: item.concurrency_limit,
        active: nextActive,
      });
      toast.success(nextActive ? t("users.overrideEnabled") : t("users.overrideDisabled"));
      await load();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t("users.updateFailed"));
    } finally {
      setUpdatingId(null);
    }
  };

  return (
    <div
      className="fixed inset-0 z-[80] flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="flex max-h-[85vh] w-full max-w-2xl flex-col rounded-xl border bg-background shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="border-b px-6 py-4">
          <h2 className="text-base font-semibold">{t("users.concurrencyTitle")}</h2>
          <p className="mt-0.5 text-sm text-muted-foreground">
            {t("users.concurrencyDesc", { username: user.username })}
          </p>
        </div>

        <div className="flex-1 space-y-6 overflow-y-auto px-6 py-5">
          {loading ? (
            <div className="flex justify-center py-10">
              <Loading size="md" />
            </div>
          ) : (
            <>
              {/* 新增/更新覆盖 */}
              <form onSubmit={onSubmit}>
                <div className="flex flex-wrap items-end gap-4">
                  <div className="min-w-[180px] flex-1 space-y-1.5">
                    <span className="text-sm font-medium">{t("users.model")}</span>
                    <Select
                      aria-label={t("users.model")}
                      value={modelId}
                      onValueChange={setModelId}
                      options={modelOptions}
                      placeholder={t("users.modelPlaceholder")}
                      emptyText={t("users.modelEmpty")}
                    />
                  </div>
                  <div className="w-[160px] space-y-1.5">
                    <label htmlFor="override-limit" className="text-sm font-medium">
                      {t("users.limit")}
                    </label>
                    <Input
                      id="override-limit"
                      type="number"
                      min={0}
                      max={10000}
                      step={1}
                      value={limit}
                      onChange={(e) => setLimit(e.target.value)}
                      placeholder="0-10000"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <span className="block text-sm font-medium">{t("users.enable")}</span>
                    <div className="flex h-9 items-center">
                      <Switch checked={active} onCheckedChange={setActive} />
                    </div>
                  </div>
                </div>
              </form>

              {/* 覆盖列表 */}
              <div className="space-y-2">
                <p className="text-sm font-medium">{t("users.existingOverrides")}</p>
                {usage && usage.items.length > 0 ? (
                  <div className="overflow-hidden rounded-lg border border-border/60">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b border-border/60 bg-muted/40 text-center text-xs text-muted-foreground">
                          <th className="px-4 py-2.5 text-left font-medium">{t("users.model")}</th>
                          <th className="px-4 py-2.5 font-medium">{t("users.colLimit")}</th>
                          <th className="px-4 py-2.5 font-medium">{t("users.colActiveTasks")}</th>
                          <th className="px-4 py-2.5 font-medium">{t("users.colStatus")}</th>
                          <th className="px-4 py-2.5 font-medium">{t("users.colActions")}</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-border/60">
                        {usage.items.map((item) => (
                          <tr key={item.id} className="transition-colors hover:bg-accent/40">
                            <td className="px-4 py-2.5">
                              <span className="font-medium">{modelLabel(item.model_id)}</span>
                            </td>
                            <td className="px-4 py-2.5 text-center font-mono text-xs">
                              {item.concurrency_limit}
                            </td>
                            <td className="px-4 py-2.5 text-center font-mono text-xs">
                              {activeCount(item.model_id)}
                            </td>
                            <td className="px-4 py-2.5 text-center">
                              <Badge variant={item.active ? "default" : "secondary"}>
                                {item.active ? t("users.statusActive") : t("users.statusInactive")}
                              </Badge>
                            </td>
                            <td className="px-4 py-2.5 text-center">
                              <Button
                                variant="outline"
                                size="sm"
                                disabled={updatingId === item.id}
                                onClick={() => toggleOverride(item, !item.active)}
                              >
                                {updatingId === item.id && <Loading size="sm" />}
                                {item.active ? t("users.deactivate") : t("users.activate")}
                              </Button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <p className="rounded-lg border border-dashed border-border/60 py-6 text-center text-sm text-muted-foreground">
                    {t("users.noOverrides")}
                  </p>
                )}
              </div>
            </>
          )}
        </div>

        <div className="flex justify-end gap-2 border-t px-6 py-4">
          <Button
            type="submit"
            form="override-form"
            disabled={submitting || loading}
          >
            {submitting && <Loading size="sm" />}
            {t("users.saveOverride")}
          </Button>
          <Button variant="outline" onClick={onClose}>
            {t("users.close")}
          </Button>
        </div>
      </div>
    </div>
  );
}

/** 调整余额弹窗 */
function AdjustBalanceDialog({
  user,
  onClose,
  onAdjusted,
}: {
  user: AdminUser;
  onClose: () => void;
  onAdjusted: () => void;
}) {
  const { t } = useTranslation("console");
  const [amount, setAmount] = useState("");
  const [reason, setReason] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const value = Number(amount);
    if (!amount.trim() || !Number.isFinite(value) || value === 0) {
      toast.warning(t("users.invalidAmount"));
      return;
    }
    setSubmitting(true);
    try {
      const body: Record<string, unknown> = {
        user_id: user.id,
        amount: value,
      };
      // 非必填字段未填写时不传
      if (reason.trim()) body.reason = reason.trim();
      await post("/admin/billing/balances/adjust", body);
      toast.success(t("users.adjustSuccess"));
      onAdjusted();
      onClose();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t("users.adjustFailed"));
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
        <h2 className="text-base font-semibold">{t("users.adjustTitle")}</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          {t("users.adjustDesc", { username: user.username, balance: user.balance })}
        </p>
        <form onSubmit={onSubmit} className="mt-5 space-y-4">
          <div className="space-y-1.5">
            <label htmlFor="adjust-amount" className="text-sm font-medium">
              {t("users.adjustAmount")}
            </label>
            <Input
              id="adjust-amount"
              type="number"
              step="0.01"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              placeholder={t("users.adjustAmountPlaceholder")}
            />
          </div>
          <div className="space-y-1.5">
            <label htmlFor="adjust-reason" className="text-sm font-medium">
              {t("users.adjustReason")}
            </label>
            <Input
              id="adjust-reason"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder={t("users.adjustReasonPlaceholder")}
            />
          </div>
          <div className="flex justify-end gap-2 pt-1">
            <Button type="button" variant="outline" onClick={onClose}>
              {t("users.cancel")}
            </Button>
            <Button type="submit" disabled={submitting}>
              {submitting && <Loading size="sm" />}
              {t("users.confirmAdjust")}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}

export function UsersPanel() {
  const { t, i18n } = useTranslation("console");
  const locale = i18n.language === "zh" ? "zh-CN" : "en-US";
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [dialogOpen, setDialogOpen] = useState(false);
  const [adjustTarget, setAdjustTarget] = useState<AdminUser | null>(null);
  const [concurrencyTarget, setConcurrencyTarget] = useState<AdminUser | null>(null);
  // keyword 为输入框实时值，appliedKeyword 为已提交查询条件
  const [keyword, setKeyword] = useState("");
  const [appliedKeyword, setAppliedKeyword] = useState("");

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const load = useCallback(async (p: number, name: string) => {
    setLoading(true);
    setError("");
    try {
      if (name) {
        // 按用户名精确查询，命中时仅返回单个用户
        const data = await get<unknown>("/admin/user/by-username", {
          params: { username: name },
        });
        const user = data as AdminUser;
        setUsers([user]);
        setTotal(1);
      } else {
        const data = await get<unknown>("/admin/user/list", {
          params: { page: p, page_size: PAGE_SIZE },
        });
        const { users, total } = normalize(data);
        setUsers(users);
        setTotal(total);
      }
    } catch (err) {
      setUsers([]);
      setTotal(0);
      setError(err instanceof Error ? err.message : t("users.loadFailed"));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    load(page, appliedKeyword);
  }, [load, page, appliedKeyword]);

  const onSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setPage(1);
    setAppliedKeyword(keyword.trim());
  };

  const onClearSearch = () => {
    setKeyword("");
    setPage(1);
    setAppliedKeyword("");
  };

  return (
    <div className="flex min-h-[calc(100vh-7.5rem)] w-full flex-col gap-6">
      {/* 页头 */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold">{t("users.title")}</h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            {t("users.totalUsers", { total })}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <form onSubmit={onSearch} className="relative">
            <Search className="absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
              placeholder={t("users.searchPlaceholder")}
              className="h-8 w-56 pr-8 pl-9"
            />
            {keyword && (
              <button
                type="button"
                onClick={onClearSearch}
                aria-label={t("users.clearSearch")}
                className="absolute top-1/2 right-2 -translate-y-1/2 rounded-full p-0.5 text-muted-foreground hover:text-foreground"
              >
                <X className="size-4" />
              </button>
            )}
          </form>
          <Button
            variant="outline"
            size="sm"
            onClick={() => load(page, appliedKeyword)}
            disabled={loading}
          >
            <RefreshCw className={cn("size-4", loading && "animate-spin")} />
            {t("users.refresh")}
          </Button>
          <Button size="sm" onClick={() => setDialogOpen(true)}>
            <Plus className="size-4" />
            {t("users.createUser")}
          </Button>
        </div>
      </div>

      {/* 用户列表 */}
      <div className="relative overflow-hidden rounded-xl border border-border/60 bg-card/40">
        {error && users.length === 0 ? (
          <div className="flex flex-col items-center gap-2 py-16 text-sm text-muted-foreground">
            <p>{error}</p>
            <Button
              variant="outline"
              size="sm"
              onClick={() => load(page, appliedKeyword)}
            >
              {t("users.retry")}
            </Button>
          </div>
        ) : users.length === 0 ? (
          <div className="flex items-center justify-center py-16 text-muted-foreground">
            {loading ? (
              <Loading size="lg" />
            ) : (
              <div className="flex flex-col items-center gap-2">
                <UsersIcon className="size-8 text-muted-foreground/50" />
                <p className="text-sm">
                  {appliedKeyword
                    ? t("users.noUserFound", { keyword: appliedKeyword })
                    : t("users.empty")}
                </p>
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
                  <th className="px-6 py-3 text-left font-medium">{t("users.colUser")}</th>
                  <th className="px-6 py-3 font-medium">{t("users.colStatus")}</th>
                  <th className="px-6 py-3 font-medium">{t("users.colRole")}</th>
                  <th className="px-6 py-3 font-medium">{t("users.colBalance")}</th>
                  <th className="px-6 py-3 font-medium">{t("users.colUsage")}</th>
                  <th className="px-6 py-3 font-medium">{t("users.colActiveTasks")}</th>
                  <th className="px-6 py-3 font-medium">{t("users.colRegisteredAt")}</th>
                  <th className="sticky right-0 border-l border-border/60 bg-muted px-6 py-3 font-medium">
                    {t("users.colActions")}
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/60">
                {users.map((u) => (
                  <tr
                    key={u.id}
                    className="transition-colors hover:bg-accent/40"
                  >
                    <td className="px-6 py-3">
                      <div className="flex items-center gap-3">
                        <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-primary/10 text-xs font-semibold text-primary">
                          {u.username.charAt(0).toUpperCase()}
                        </span>
                        <span className="font-medium">{u.username}</span>
                      </div>
                    </td>
                    <td className="px-6 py-3 text-center">
                      <Badge variant={u.is_active ? "default" : "destructive"}>
                        {u.is_active ? t("users.statusNormal") : t("users.statusDisabled")}
                      </Badge>
                    </td>
                    <td className="px-6 py-3 text-center">
                      {u.is_admin ? (
                        <Badge variant="secondary">{t("users.roleAdmin")}</Badge>
                      ) : (
                        <span className="text-muted-foreground">{t("users.roleUser")}</span>
                      )}
                    </td>
                    <td className="px-6 py-3 text-center font-mono text-xs">
                      {u.balance}
                    </td>
                    <td className="px-6 py-3 text-center font-mono text-xs">
                      {u.usage}
                    </td>
                    <td className="px-6 py-3 text-center font-mono text-xs text-muted-foreground">
                      {u.active_lease_count}
                    </td>
                    <td className="px-6 py-3 text-center text-muted-foreground">
                      {new Date(u.created_at).toLocaleString(locale, {
                        hour12: false,
                      })}
                    </td>
                    <td className="sticky right-0 bg-card shadow-[-10px_0_12px_-10px_rgba(0,0,0,0.12)] px-6 py-3 text-center">
                      <div className="flex items-center justify-center gap-2">
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => setAdjustTarget(u)}
                        >
                          <Wallet className="size-4" />
                          {t("users.adjustBalance")}
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => setConcurrencyTarget(u)}
                        >
                          <Gauge className="size-4" />
                          {t("users.concurrencyOverride")}
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

      {/* 分页：mt-auto 固定吸底，不随列表高度跳动；筛选结果仅一条时隐藏 */}
      {!error && !appliedKeyword && users.length > 0 && (
        <Pagination
          page={page}
          totalPages={totalPages}
          loading={loading}
          onChange={setPage}
          className="mt-auto"
        />
      )}

      {dialogOpen && (
        <CreateUserDialog
          onClose={() => setDialogOpen(false)}
          onCreated={() => load(page, appliedKeyword)}
        />
      )}

      {adjustTarget && (
        <AdjustBalanceDialog
          user={adjustTarget}
          onClose={() => setAdjustTarget(null)}
          onAdjusted={() => load(page, appliedKeyword)}
        />
      )}

      {concurrencyTarget && (
        <UserModelConcurrencyDialog
          user={concurrencyTarget}
          onClose={() => setConcurrencyTarget(null)}
        />
      )}
    </div>
  );
}
