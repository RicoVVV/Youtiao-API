"use client";

import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Boxes, Pencil, Plus, RefreshCw, Search, Trash2, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Loading } from "@/components/ui/loading";
import { Pagination } from "@/components/ui/pagination";
import { Select } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { toast } from "@/components/ui/toaster";
import { cn } from "@/lib/utils";
import { get, post } from "@/lib/request";

type GroupUser = {
  id: string;
  username: string;
};

type TokenGroup = {
  id: number;
  name: string;
  /** 分组介绍：仅用于展示，最长 512 字符 */
  description?: string;
  visibility: string;
  is_active: boolean;
  /** 分组价格倍率（Decimal 字符串，实际计费金额按该倍率缩放） */
  price_multiplier: string;
  users: GroupUser[];
};

/** 展示倍率：保留两位小数（如 0.850000 → 0.85，1 → 1.00） */
function formatMultiplier(m: string | undefined | null): string {
  const n = Number(m ?? "1");
  return Number.isFinite(n) ? n.toFixed(2) : "1.00";
}

/** 倍率标签配色：折扣（<1）绿色，加价（>1）琥珀色，原价（=1）灰色 */
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

/** 校验倍率：大于 0、最多 6 位小数 */
function isValidMultiplier(v: string): boolean {
  if (!/^\d+(\.\d{1,6})?$/.test(v.trim())) return false;
  return Number(v) > 0;
}

const PAGE_SIZE = 20;

/** 兼容多种分页响应：数组 / { items, total } / { groups, total } */
function normalize(data: unknown): { groups: TokenGroup[]; total: number } {
  if (Array.isArray(data)) return { groups: data, total: data.length };
  if (data && typeof data === "object") {
    const d = data as Record<string, unknown>;
    const list = (d.items ?? d.groups ?? d.list ?? []) as TokenGroup[];
    const total = typeof d.total === "number" ? d.total : list.length;
    return { groups: list, total };
  }
  return { groups: [], total: 0 };
}

type Translate = (key: string, options?: Record<string, unknown>) => string;

/** 可见性展示文案，未识别值显示原始值 */
function visibilityLabel(t: Translate, visibility: string): string {
  if (visibility === "restricted") return t("groups.visibilityRestricted");
  if (visibility === "public") return t("groups.visibilityPublic");
  return visibility;
}

/** 按用户名查询并添加成员：芯片显示用户名，实际提交用户 ID */
function UserIdsField({
  id,
  value,
  onChange,
  initialUsers = [],
}: {
  id: string;
  value: string;
  onChange: (v: string) => void;
  /** 已有成员（编辑场景），用于初始化 ID → 用户名映射 */
  initialUsers?: GroupUser[];
}) {
  const { t } = useTranslation("console");
  const [username, setUsername] = useState("");
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState("");
  const [names, setNames] = useState<Record<string, string>>(() =>
    Object.fromEntries(initialUsers.map((u) => [u.id, u.username]))
  );

  const userIds = value.split(/[,，\s]+/).filter(Boolean);

  const search = async () => {
    const name = username.trim();
    if (!name) return;
    setSearching(true);
    setError("");
    try {
      const data = await get<{ id?: string; username?: string }>(
        "/admin/user/by-username",
        { params: { username: name } }
      );
      const uid = data?.id;
      if (!uid) {
        setError(t("groups.userNotFound"));
        return;
      }
      if (userIds.includes(uid)) {
        setError(t("groups.userAlreadyAdded"));
        return;
      }
      setNames((prev) => ({ ...prev, [uid]: data.username ?? name }));
      onChange([...userIds, uid].join(", "));
      setUsername("");
    } catch (err) {
      setError(err instanceof Error ? err.message : t("groups.searchFailed"));
    } finally {
      setSearching(false);
    }
  };

  const remove = (uid: string) => {
    onChange(userIds.filter((v) => v !== uid).join(", "));
  };

  return (
    <div className="space-y-1.5">
      <label htmlFor={id} className="text-sm font-medium">
        {t("groups.memberLabel")}
      </label>
      <div className="flex gap-2">
        <Input
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              e.stopPropagation();
              search();
            }
          }}
          placeholder={t("groups.searchPlaceholder")}
          autoComplete="off"
        />
        <button
          type="button"
          onClick={(e) => {
            e.preventDefault();
            search();
          }}
          disabled={searching || !username.trim()}
          className="border-input hover:bg-accent hover:text-accent-foreground inline-flex h-9 shrink-0 items-center justify-center gap-2 rounded-md border bg-transparent px-3 text-sm font-medium shadow-xs transition-colors outline-none focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px] disabled:pointer-events-none disabled:opacity-50"
        >
          {searching ? <Loading size="sm" /> : <Search className="size-4" />}
          {t("groups.searchAndAdd")}
        </button>
      </div>
      {error && <p className="text-xs text-destructive">{error}</p>}
      {userIds.length > 0 && (
        <div className="flex flex-wrap gap-1.5 pt-0.5">
          {userIds.map((uid) => (
            <span
              key={uid}
              title={uid}
              className="inline-flex items-center gap-1 rounded-md border border-border/60 bg-muted/50 px-2 py-0.5 text-xs"
            >
              <span className="max-w-56 truncate">{names[uid] ?? uid}</span>
              <button
                type="button"
                onClick={() => remove(uid)}
                aria-label={t("groups.removeUser", { name: names[uid] ?? uid })}
                className="text-muted-foreground transition-colors hover:text-destructive"
              >
                <X className="size-3" />
              </button>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

/** 新建分组弹窗 */
function CreateGroupDialog({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: () => void;
}) {
  const { t } = useTranslation("console");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [visibility, setVisibility] = useState("public");
  const [isActive, setIsActive] = useState(true);
  const [userIds, setUserIds] = useState("");
  const [priceMultiplier, setPriceMultiplier] = useState("1.000000");
  const [submitting, setSubmitting] = useState(false);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) {
      toast.warning(t("groups.nameRequired"));
      return;
    }
    if (!isValidMultiplier(priceMultiplier)) {
      toast.warning(t("groups.priceMultiplierInvalid"));
      return;
    }
    setSubmitting(true);
    try {
      await post("/admin/token/groups/create", {
        // 标识不再手动填写，直接使用分组名称
        code: name.trim(),
        name: name.trim(),
        description: description.trim(),
        visibility,
        is_active: isActive,
        price_multiplier: priceMultiplier.trim(),
        // 支持逗号/空白分隔的用户 ID 列表
        user_ids: userIds.split(/[,，\s]+/).filter(Boolean),
      });
      toast.success(t("groups.createSuccess"));
      onCreated();
      onClose();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t("groups.createFailed"));
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
        <h2 className="text-base font-semibold">{t("groups.createTitle")}</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          {t("groups.createDesc")}
        </p>
        <form onSubmit={onSubmit} className="mt-5 space-y-4">
          <div className="space-y-1.5">
            <label htmlFor="create-name" className="text-sm font-medium">
              {t("groups.groupName")}
            </label>
            <Input
              id="create-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={t("groups.namePlaceholder")}
              autoComplete="off"
            />
          </div>
          <div className="space-y-1.5">
            <label htmlFor="create-description" className="text-sm font-medium">
              {t("groups.description")}
            </label>
            <textarea
              id="create-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder={t("groups.descriptionPlaceholder")}
              maxLength={512}
              rows={2}
              autoComplete="off"
              className="border-input placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-ring/50 flex min-h-16 w-full resize-none rounded-md border bg-transparent px-3 py-2 text-sm shadow-xs outline-none focus-visible:ring-[3px]"
            />
            <p className="text-xs text-muted-foreground">
              {t("groups.descriptionHint")}
            </p>
          </div>
          <div className="space-y-1.5">
            <label htmlFor="create-visibility" className="text-sm font-medium">
              {t("groups.visibility")}
            </label>
            <Select
              id="create-visibility"
              value={visibility}
              onValueChange={setVisibility}
              options={[
                { value: "restricted", label: t("groups.visibilityRestrictedOption") },
                { value: "public", label: t("groups.visibilityPublicOption") },
              ]}
            />
          </div>
          <div className="space-y-1.5">
            <label htmlFor="create-price-multiplier" className="text-sm font-medium">
              {t("groups.priceMultiplier")}
            </label>
            <Input
              id="create-price-multiplier"
              type="number"
              min="0.000001"
              step="0.000001"
              value={priceMultiplier}
              onChange={(e) => setPriceMultiplier(e.target.value)}
              autoComplete="off"
            />
            <p className="text-xs text-muted-foreground">
              {t("groups.priceMultiplierHint")}
            </p>
          </div>
          <UserIdsField
            id="create-user-ids"
            value={userIds}
            onChange={setUserIds}
          />
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium">{t("groups.enable")}</span>
            <Switch checked={isActive} onCheckedChange={setIsActive} />
          </div>
          <div className="flex justify-end gap-2 pt-1">
            <Button type="button" variant="outline" onClick={onClose}>
              {t("groups.cancel")}
            </Button>
            <Button type="submit" disabled={submitting}>
              {submitting && <Loading size="sm" />}
              {t("groups.create")}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}

/** 编辑分组弹窗 */
function EditGroupDialog({
  group,
  onClose,
  onUpdated,
}: {
  group: TokenGroup;
  onClose: () => void;
  onUpdated: () => void;
}) {
  const { t } = useTranslation("console");
  const [name, setName] = useState(group.name);
  const [description, setDescription] = useState(group.description ?? "");
  const [visibility, setVisibility] = useState(group.visibility);
  const [isActive, setIsActive] = useState(group.is_active);
  const [userIds, setUserIds] = useState(
    (group.users ?? []).map((u) => u.id).join(", ")
  );
  const [priceMultiplier, setPriceMultiplier] = useState(
    group.price_multiplier ?? "1.000000"
  );
  const [submitting, setSubmitting] = useState(false);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) {
      toast.warning(t("groups.nameRequired"));
      return;
    }
    if (!isValidMultiplier(priceMultiplier)) {
      toast.warning(t("groups.priceMultiplierInvalid"));
      return;
    }
    setSubmitting(true);
    try {
      await post("/admin/token/groups/update", {
        group_id: group.id,
        name: name.trim(),
        description: description.trim(),
        visibility,
        is_active: isActive,
        price_multiplier: priceMultiplier.trim(),
        // 支持逗号/空白分隔的用户 ID 列表
        user_ids: userIds.split(/[,，\s]+/).filter(Boolean),
      });
      toast.success(t("groups.updateSuccess"));
      onUpdated();
      onClose();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t("groups.updateFailed"));
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
        <h2 className="text-base font-semibold">{t("groups.editTitle")}</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          {t("groups.editDesc")}
        </p>
        <form onSubmit={onSubmit} className="mt-5 space-y-4">
          <div className="space-y-1.5">
            <label htmlFor="edit-name" className="text-sm font-medium">
              {t("groups.groupName")}
            </label>
            <Input
              id="edit-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              autoComplete="off"
            />
          </div>
          <div className="space-y-1.5">
            <label htmlFor="edit-description" className="text-sm font-medium">
              {t("groups.description")}
            </label>
            <textarea
              id="edit-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder={t("groups.descriptionPlaceholder")}
              maxLength={512}
              rows={2}
              autoComplete="off"
              className="border-input placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-ring/50 flex min-h-16 w-full resize-none rounded-md border bg-transparent px-3 py-2 text-sm shadow-xs outline-none focus-visible:ring-[3px]"
            />
            <p className="text-xs text-muted-foreground">
              {t("groups.descriptionHint")}
            </p>
          </div>
          <div className="space-y-1.5">
            <label htmlFor="edit-visibility" className="text-sm font-medium">
              {t("groups.visibility")}
            </label>
            <Select
              id="edit-visibility"
              value={visibility}
              onValueChange={setVisibility}
              options={[
                { value: "restricted", label: t("groups.visibilityRestrictedOption") },
                { value: "public", label: t("groups.visibilityPublicOption") },
              ]}
            />
          </div>
          <div className="space-y-1.5">
            <label htmlFor="edit-price-multiplier" className="text-sm font-medium">
              {t("groups.priceMultiplier")}
            </label>
            <Input
              id="edit-price-multiplier"
              type="number"
              min="0.000001"
              step="0.000001"
              value={priceMultiplier}
              onChange={(e) => setPriceMultiplier(e.target.value)}
              autoComplete="off"
            />
            <p className="text-xs text-muted-foreground">
              {t("groups.priceMultiplierHint")}
            </p>
          </div>
          <UserIdsField
            id="edit-user-ids"
            value={userIds}
            onChange={setUserIds}
            initialUsers={group.users ?? []}
          />
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium">{t("groups.enable")}</span>
            <Switch checked={isActive} onCheckedChange={setIsActive} />
          </div>
          <div className="flex justify-end gap-2 pt-1">
            <Button type="button" variant="outline" onClick={onClose}>
              {t("groups.cancel")}
            </Button>
            <Button type="submit" disabled={submitting}>
              {submitting && <Loading size="sm" />}
              {t("groups.save")}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}

/** 删除分组确认弹窗 */
function DeleteGroupDialog({
  group,
  onClose,
  onDeleted,
}: {
  group: TokenGroup;
  onClose: () => void;
  onDeleted: () => void;
}) {
  const { t } = useTranslation("console");
  const [submitting, setSubmitting] = useState(false);

  const onConfirm = async () => {
    setSubmitting(true);
    try {
      await post("/admin/token/groups/delete", { group_id: group.id });
      toast.success(t("groups.deleteSuccess"));
      onDeleted();
      onClose();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t("groups.deleteFailed"));
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
        <h2 className="text-base font-semibold">{t("groups.deleteTitle")}</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          {t("groups.deleteConfirm", { name: group.name })}
        </p>
        <div className="mt-6 flex justify-end gap-2">
          <Button variant="outline" onClick={onClose}>
            {t("groups.cancel")}
          </Button>
          <Button
            variant="destructive"
            onClick={onConfirm}
            disabled={submitting}
          >
            {submitting && <Loading size="sm" />}
            {t("groups.confirmDelete")}
          </Button>
        </div>
      </div>
    </div>
  );
}

export function GroupsPanel() {
  const { t } = useTranslation("console");
  const [groups, setGroups] = useState<TokenGroup[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingGroup, setEditingGroup] = useState<TokenGroup | null>(null);
  const [deletingGroup, setDeletingGroup] = useState<TokenGroup | null>(null);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const load = useCallback(async (p: number) => {
    setLoading(true);
    setError("");
    try {
      const data = await get<unknown>("/admin/token/groups/list", {
        params: { page: p, page_size: PAGE_SIZE },
      });
      const { groups, total } = normalize(data);
      setGroups(groups);
      setTotal(total);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("groups.loadFailed"));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    load(page);
  }, [load, page]);

  const onDeleted = () => {
    // 删除当前页最后一条时回退到上一页
    if (groups.length === 1 && page > 1) {
      setPage(page - 1);
    } else {
      load(page);
    }
  };

  return (
    <div className="flex min-h-[calc(100vh-7.5rem)] w-full flex-col gap-6">
      {/* 页头 */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold">{t("groups.title")}</h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            {t("groups.totalGroups", { total })}
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
            {t("groups.refresh")}
          </Button>
          <Button size="sm" onClick={() => setDialogOpen(true)}>
            <Plus className="size-4" />
            {t("groups.createGroup")}
          </Button>
        </div>
      </div>

      {/* 分组列表 */}
      <div className="relative overflow-hidden rounded-xl border border-border/60 bg-card/40">
        {error && groups.length === 0 ? (
          <div className="flex flex-col items-center gap-2 py-16 text-sm text-muted-foreground">
            <p>{t("groups.loadFailedWithReason", { error })}</p>
            <Button
              variant="outline"
              size="sm"
              onClick={() => load(page)}
            >
              {t("groups.retry")}
            </Button>
          </div>
        ) : groups.length === 0 ? (
          <div className="flex items-center justify-center py-16 text-muted-foreground">
            {loading ? (
              <Loading size="lg" />
            ) : (
              <div className="flex flex-col items-center gap-2">
                <Boxes className="size-8 text-muted-foreground/50" />
                <p className="text-sm">{t("groups.empty")}</p>
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
                  <th className="px-6 py-3 text-left font-medium">{t("groups.colName")}</th>
                  <th className="px-6 py-3 text-left font-medium">{t("groups.colDescription")}</th>
                  <th className="px-6 py-3 font-medium">{t("groups.colVisibility")}</th>
                  <th className="px-6 py-3 font-medium">{t("groups.colStatus")}</th>
                  <th className="px-6 py-3 font-medium">{t("groups.colPriceMultiplier")}</th>
                  <th className="px-6 py-3 text-left font-medium">{t("groups.colMembers")}</th>
                  <th className="sticky right-0 border-l border-border/60 bg-muted px-6 py-3 font-medium">
                    {t("groups.colActions")}
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/60">
                {groups.map((g) => (
                  <tr
                    key={g.id}
                    className="transition-colors hover:bg-accent/40"
                  >
                    <td className="px-6 py-3 font-medium">{g.name}</td>
                    <td className="max-w-64 px-6 py-3 text-muted-foreground">
                      {g.description ? (
                        <span className="block truncate" title={g.description}>
                          {g.description}
                        </span>
                      ) : (
                        "-"
                      )}
                    </td>
                    <td className="px-6 py-3 text-center">
                      <Badge
                        variant={
                          g.visibility === "restricted" ? "secondary" : "default"
                        }
                      >
                        {visibilityLabel(t, g.visibility)}
                      </Badge>
                    </td>
                    <td className="px-6 py-3 text-center">
                      <Badge variant={g.is_active ? "default" : "destructive"}>
                        {g.is_active ? t("groups.statusActive") : t("groups.statusInactive")}
                      </Badge>
                    </td>
                    <td className="px-6 py-3 text-center">
                      <span
                        className={cn(
                          "inline-flex items-center rounded-md border px-2 py-0.5 font-mono text-xs font-medium",
                          multiplierBadgeClass(g.price_multiplier)
                        )}
                      >
                        {formatMultiplier(g.price_multiplier)}
                      </span>
                    </td>
                    <td className="px-6 py-3">
                      {g.users?.length ? (
                        g.users.map((u) => u.username).join("、")
                      ) : (
                        <span className="text-muted-foreground">-</span>
                      )}
                    </td>
                    <td className="sticky right-0 bg-card shadow-[-10px_0_12px_-10px_rgba(0,0,0,0.12)] px-6 py-3 text-center">
                      <div className="flex items-center justify-center gap-1.5">
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => setEditingGroup(g)}
                          aria-label={t("groups.editGroup")}
                        >
                          <Pencil className="size-4" />
                          {t("groups.edit")}
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          className="text-destructive hover:bg-destructive/10 hover:text-destructive"
                          onClick={() => setDeletingGroup(g)}
                          aria-label={t("groups.deleteGroup")}
                        >
                          <Trash2 className="size-4" />
                          {t("groups.delete")}
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

      {/* 分页：mt-auto 固定吸底，不随列表高度跳动 */}
      {!error && groups.length > 0 && (
        <Pagination
          page={page}
          totalPages={totalPages}
          loading={loading}
          onChange={setPage}
          className="mt-auto"
        />
      )}

      {dialogOpen && (
        <CreateGroupDialog
          onClose={() => setDialogOpen(false)}
          onCreated={() => load(page)}
        />
      )}
      {editingGroup && (
        <EditGroupDialog
          group={editingGroup}
          onClose={() => setEditingGroup(null)}
          onUpdated={() => load(page)}
        />
      )}
      {deletingGroup && (
        <DeleteGroupDialog
          group={deletingGroup}
          onClose={() => setDeletingGroup(null)}
          onDeleted={onDeleted}
        />
      )}
    </div>
  );
}
