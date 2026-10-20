"use client";

import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Ban,
  BellRing,
  CircleCheck,
  Eye,
  Mail,
  Pencil,
  Plus,
  RefreshCw,
  Search,
  Trash2,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Loading } from "@/components/ui/loading";
import { MultiSelect } from "@/components/ui/multi-select";
import { Pagination } from "@/components/ui/pagination";
import { Select } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { DateTimePicker } from "@/components/ui/datetime-picker";
import { toast } from "@/components/ui/toaster";
import { cn } from "@/lib/utils";
import { get } from "@/lib/request";
import {
  MESSAGE_TYPES,
  createMessage,
  createNotification,
  deleteMessage,
  deleteNotification,
  listAdminMessages,
  listAdminNotifications,
  updateMessage,
  updateMessageStatus,
  updateNotification,
  updateNotificationStatus,
  type AdminMessage,
  type AdminNotification,
  type MessageTargets,
  type MessageType,
} from "@/lib/messages";

const PAGE_SIZE = 10;

const TYPE_VARIANT: Record<
  MessageType,
  "default" | "secondary" | "destructive" | "outline"
> = {
  notice: "default",
  maintenance: "destructive",
  update: "secondary",
  activity: "outline",
};

const formatTime = (locale: string, value: string | null) =>
  value ? new Date(value).toLocaleString(locale, { hour12: false }) : "—";

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

/** 定向目标数量合计 */
const targetCount = (targets: MessageTargets) =>
  (targets.user_ids?.length ?? 0) + (targets.token_group_ids?.length ?? 0);

/** 定向目标选项 */
type TargetOptions = {
  users: { value: string; label: string }[];
  groups: { value: string; label: string }[];
};

/** 加载定向目标候选：用户、Token 分组（各取前 100 条） */
async function loadTargetOptions(): Promise<TargetOptions> {
  const pickItems = (data: unknown): Record<string, unknown>[] => {
    if (Array.isArray(data)) return data;
    if (data && typeof data === "object") {
      const d = data as Record<string, unknown>;
      const list = d.items ?? d.users ?? d.list;
      if (Array.isArray(list)) return list;
    }
    return [];
  };
  const [users, groups] = await Promise.all([
    get<unknown>("/admin/user/list", { params: { page: 1, page_size: 100 } }).catch(() => null),
    get<unknown>("/admin/token/groups/list", { params: { page: 1, page_size: 100 } }).catch(() => null),
  ]);
  return {
    users: pickItems(users).map((u) => ({
      value: String(u.id),
      label: String(u.username ?? u.id),
    })),
    groups: pickItems(groups).map((g) => ({
      value: String(g.id),
      label: String(g.name ?? g.id),
    })),
  };
}

/** 资源类型：消息（带 type 枚举）/ 通知（无 type，全局仅一条生效） */
type Kind = "message" | "notification";
type AdminItem = AdminMessage | AdminNotification;

/** 表单弹窗：创建 / 编辑共用 */
function ItemFormDialog({
  kind,
  item,
  onClose,
  onSaved,
}: {
  kind: Kind;
  /** null 表示创建 */
  item: AdminItem | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { t } = useTranslation("console");
  const ns = kind === "message" ? "messages" : "notifications";
  const hasType = kind === "message";
  const [title, setTitle] = useState(item?.title ?? "");
  const [content, setContent] = useState(item?.content ?? "");
  const [type, setType] = useState<MessageType>(
    item && "type" in item ? item.type : "notice"
  );
  const [isPublic, setIsPublic] = useState(item?.is_public ?? true);
  const [isActive, setIsActive] = useState(item?.is_active ?? true);
  const [startAt, setStartAt] = useState(() =>
    item ? isoToLocal(item.start_at) : isoToLocal(new Date().toISOString())
  );
  const [expiresAt, setExpiresAt] = useState(isoToLocal(item?.expires_at ?? null));
  const [userIds, setUserIds] = useState<string[]>(item?.targets.user_ids ?? []);
  const [groupIds, setGroupIds] = useState<string[]>(
    (item?.targets.token_group_ids ?? []).map(String)
  );
  const [options, setOptions] = useState<TargetOptions>({ users: [], groups: [] });
  const [submitting, setSubmitting] = useState(false);

  // 加载定向目标候选，并把已选中但不在候选中的值补进选项（避免标签丢失）
  useEffect(() => {
    loadTargetOptions().then((opts) => {
      const merge = (
        list: { value: string; label: string }[],
        selected: string[]
      ) => {
        const known = new Set(list.map((o) => o.value));
        return [
          ...list,
          ...selected.filter((v) => !known.has(v)).map((v) => ({ value: v, label: v })),
        ];
      };
      setOptions({
        users: merge(opts.users, item?.targets.user_ids ?? []),
        groups: merge(opts.groups, (item?.targets.token_group_ids ?? []).map(String)),
      });
    });
  }, [item]);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmedTitle = title.trim();
    if (!trimmedTitle) {
      toast.warning(t(`${ns}.admin.titleRequired`));
      return;
    }
    if (!content.trim()) {
      toast.warning(t(`${ns}.admin.contentRequired`));
      return;
    }
    if (!startAt) {
      toast.warning(t(`${ns}.admin.startAtRequired`));
      return;
    }
    const startIso = localToIso(startAt);
    const expiresIso = localToIso(expiresAt);
    if (startIso && expiresIso && expiresIso <= startIso) {
      toast.warning(t(`${ns}.admin.expiresInvalid`));
      return;
    }
    const targets: MessageTargets = {
      user_ids: userIds,
      token_group_ids: groupIds.map(Number),
    };
    if (!isPublic && targetCount(targets) === 0) {
      toast.warning(t(`${ns}.admin.targetRequired`));
      return;
    }
    setSubmitting(true);
    try {
      const base = {
        title: trimmedTitle,
        content,
        is_public: isPublic,
        is_active: isActive,
        start_at: startIso!,
        expires_at: expiresIso,
        targets,
      };
      if (item) {
        if (kind === "message") {
          await updateMessage({ ...base, type, message_id: item.id });
        } else {
          await updateNotification({ ...base, notification_id: item.id });
        }
        toast.success(t(`${ns}.admin.updateSuccess`));
      } else {
        if (kind === "message") {
          await createMessage({ ...base, type });
        } else {
          await createNotification(base);
        }
        toast.success(t(`${ns}.admin.createSuccess`));
      }
      onSaved();
      onClose();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t(`${ns}.admin.saveFailed`));
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
        className="flex max-h-[90vh] w-full max-w-2xl flex-col rounded-xl border bg-background p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-base font-semibold">
          {item ? t(`${ns}.admin.editTitle`) : t(`${ns}.admin.createTitle`)}
        </h2>
        <form onSubmit={onSubmit} className="no-scrollbar mt-5 flex-1 space-y-4 overflow-y-auto pr-1">
          <div className={cn("grid gap-4", hasType && "sm:grid-cols-2")}>
            <div className="space-y-1.5">
              <label htmlFor="msg-title" className="text-sm font-medium">
                {t(`${ns}.admin.fieldTitle`)}
                <span className="text-destructive">*</span>
              </label>
              <Input
                id="msg-title"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                maxLength={255}
                placeholder={t(`${ns}.admin.titlePlaceholder`)}
              />
            </div>
            {hasType && (
              <div className="space-y-1.5">
                <label htmlFor="msg-type" className="text-sm font-medium">
                  {t(`${ns}.admin.fieldType`)}
                  <span className="text-destructive">*</span>
                </label>
                <Select
                  value={type}
                  onValueChange={(v) => setType(v as MessageType)}
                  options={MESSAGE_TYPES.map((tp) => ({
                    value: tp,
                    label: t(`messages.type.${tp}`),
                  }))}
                  className="w-full"
                  aria-label={t(`${ns}.admin.fieldType`)}
                />
              </div>
            )}
          </div>
          <div className="space-y-1.5">
            <label htmlFor="msg-content" className="text-sm font-medium">
              {t(`${ns}.admin.fieldContent`)}
              <span className="text-destructive">*</span>
            </label>
            <textarea
              id="msg-content"
              value={content}
              onChange={(e) => setContent(e.target.value)}
              rows={6}
              placeholder={t(`${ns}.admin.contentPlaceholder`)}
              className="border-input dark:bg-input/30 w-full rounded-md border bg-transparent px-3 py-2 text-sm shadow-xs outline-none focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px]"
            />
            <p className="text-xs text-muted-foreground">
              {t(`${ns}.admin.contentHint`)}
            </p>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <label htmlFor="msg-start" className="text-sm font-medium">
                {t(`${ns}.admin.fieldStartAt`)}
                <span className="text-destructive">*</span>
              </label>
              <DateTimePicker
                id="msg-start"
                value={startAt}
                onChange={setStartAt}
                placeholder={t(`${ns}.admin.startAtPlaceholder`)}
              />
            </div>
            <div className="space-y-1.5">
              <label htmlFor="msg-expires" className="text-sm font-medium">
                {t(`${ns}.admin.fieldExpiresAt`)}
              </label>
              <DateTimePicker
                id="msg-expires"
                value={expiresAt}
                onChange={setExpiresAt}
                placeholder={t(`${ns}.admin.expiresAtPlaceholder`)}
              />
              <p className="text-xs text-muted-foreground">
                {t(`${ns}.admin.expiresAtHint`)}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-6">
            <label className="flex cursor-pointer items-center gap-2 text-sm font-medium">
              <Switch checked={isPublic} onCheckedChange={setIsPublic} />
              {t(`${ns}.admin.isPublic`)}
            </label>
            <label className="flex cursor-pointer items-center gap-2 text-sm font-medium">
              <Switch checked={isActive} onCheckedChange={setIsActive} />
              {t(`${ns}.admin.isActive`)}
            </label>
          </div>
          {kind === "notification" && isActive && (
            <p className="rounded-lg border border-warning/40 bg-warning/10 px-3 py-2 text-xs text-warning">
              {t("notifications.admin.exclusiveHint")}
            </p>
          )}
          {!isPublic && (
            <div className="space-y-3 rounded-lg border border-border/60 bg-muted/30 p-4">
              <p className="text-sm font-medium">{t(`${ns}.admin.targets`)}</p>
              <div className="space-y-1.5">
                <label className="text-xs text-muted-foreground">
                  {t(`${ns}.admin.targetUsers`)}
                </label>
                <MultiSelect
                  values={userIds}
                  onValuesChange={setUserIds}
                  options={options.users}
                  searchable
                  placeholder={t(`${ns}.admin.targetUsersPlaceholder`)}
                  searchPlaceholder={t(`${ns}.admin.targetUsersSearch`)}
                  emptyText={t(`${ns}.admin.targetsEmpty`)}
                />
              </div>
              <div className="space-y-1.5">
                <label className="text-xs text-muted-foreground">
                  {t(`${ns}.admin.targetGroups`)}
                </label>
                <MultiSelect
                  values={groupIds}
                  onValuesChange={setGroupIds}
                  options={options.groups}
                  placeholder={t(`${ns}.admin.targetGroupsPlaceholder`)}
                  emptyText={t(`${ns}.admin.targetsEmpty`)}
                />
              </div>
            </div>
          )}
          <div className="flex justify-end gap-2 pt-1">
            <Button type="button" variant="outline" onClick={onClose}>
              {t(`${ns}.admin.cancel`)}
            </Button>
            <Button type="submit" disabled={submitting}>
              {submitting && <Loading size="sm" />}
              {item ? t(`${ns}.admin.save`) : t(`${ns}.admin.create`)}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}

/** 详情弹窗：markdown 预览 + 定向目标概览 */
function DetailDialog({
  item,
  onClose,
}: {
  item: AdminItem;
  onClose: () => void;
}) {
  const { t, i18n } = useTranslation("console");
  const locale = i18n.language === "zh" ? "zh-CN" : "en-US";
  const ns = "type" in item ? "messages" : "notifications";
  const type = "type" in item ? item.type : null;

  return (
    <div
      className="fixed inset-0 z-[80] flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="flex max-h-[85vh] w-full max-w-lg flex-col rounded-xl border bg-background p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-3">
          <h2 className="text-base font-semibold">{item.title}</h2>
          {type && (
            <Badge variant={TYPE_VARIANT[type]} className="shrink-0">
              {t(`messages.type.${type}`)}
            </Badge>
          )}
        </div>
        <p className="mt-1 text-xs text-muted-foreground">
          {item.is_public
            ? t(`${ns}.admin.visibilityPublic`)
            : t(`${ns}.admin.visibilityTargeted`, { count: targetCount(item.targets) })}
          {" · "}
          {formatTime(locale, item.start_at)}
          {" ~ "}
          {formatTime(locale, item.expires_at)}
        </p>
        <div className="markdown-body mt-4 flex-1 overflow-y-auto border-t border-border/60 pt-4">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{item.content}</ReactMarkdown>
        </div>
        <div className="mt-6 flex justify-end">
          <Button variant="outline" onClick={onClose}>
            {t("messages.close")}
          </Button>
        </div>
      </div>
    </div>
  );
}

/** 删除确认弹窗 */
function DeleteDialog({
  kind,
  item,
  onClose,
  onDeleted,
}: {
  kind: Kind;
  item: AdminItem;
  onClose: () => void;
  onDeleted: () => void;
}) {
  const { t } = useTranslation("console");
  const ns = kind === "message" ? "messages" : "notifications";
  const [submitting, setSubmitting] = useState(false);

  const onDelete = async () => {
    setSubmitting(true);
    try {
      if (kind === "message") {
        await deleteMessage(item.id);
      } else {
        await deleteNotification(item.id);
      }
      toast.success(t(`${ns}.admin.deleteSuccess`));
      onDeleted();
      onClose();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t(`${ns}.admin.deleteFailed`));
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
        <h2 className="text-base font-semibold">{t(`${ns}.admin.deleteTitle`)}</h2>
        <p className="mt-2 text-sm text-muted-foreground">
          {t(`${ns}.admin.deleteConfirm`, { title: item.title })}
        </p>
        <div className="mt-6 flex justify-end gap-2">
          <Button variant="outline" onClick={onClose}>
            {t(`${ns}.admin.cancel`)}
          </Button>
          <Button variant="destructive" disabled={submitting} onClick={onDelete}>
            {submitting && <Loading size="sm" />}
            {t(`${ns}.admin.delete`)}
          </Button>
        </div>
      </div>
    </div>
  );
}

/** 消息 / 通知管理面板（kind 区分） */
function ResourcePanel({ kind }: { kind: Kind }) {
  const { t, i18n } = useTranslation("console");
  const locale = i18n.language === "zh" ? "zh-CN" : "en-US";
  const ns = kind === "message" ? "messages" : "notifications";
  const hasType = kind === "message";
  const [items, setItems] = useState<AdminItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [keyword, setKeyword] = useState("");
  const [appliedKeyword, setAppliedKeyword] = useState("");
  const [typeFilter, setTypeFilter] = useState<"" | MessageType>("");
  const [statusFilter, setStatusFilter] = useState<"" | "active" | "inactive">("");
  const [formItem, setFormItem] = useState<AdminItem | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [detail, setDetail] = useState<AdminItem | null>(null);
  const [deleting, setDeleting] = useState<AdminItem | null>(null);
  const [togglingId, setTogglingId] = useState<string | null>(null);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const load = useCallback(
    async (p: number) => {
      setLoading(true);
      setError("");
      try {
        const base = {
          page: p,
          page_size: PAGE_SIZE,
          keyword: appliedKeyword || undefined,
          is_active:
            statusFilter === "" ? undefined : statusFilter === "active",
        };
        const data =
          kind === "message"
            ? await listAdminMessages({
                ...base,
                type: typeFilter || undefined,
              })
            : await listAdminNotifications(base);
        setItems(data.items);
        setTotal(data.total);
      } catch (err) {
        setError(err instanceof Error ? err.message : t(`${ns}.admin.loadFailed`));
      } finally {
        setLoading(false);
      }
    },
    [kind, appliedKeyword, typeFilter, statusFilter, ns, t]
  );

  useEffect(() => {
    load(page);
  }, [load, page]);

  const onSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setPage(1);
    setAppliedKeyword(keyword.trim());
  };

  const onToggleActive = async (item: AdminItem) => {
    setTogglingId(item.id);
    try {
      const isActive = !item.is_active;
      if (kind === "message") {
        await updateMessageStatus({ message_id: item.id, is_active: isActive });
      } else {
        await updateNotificationStatus({
          notification_id: item.id,
          is_active: isActive,
        });
      }
      toast.success(
        item.is_active
          ? t(`${ns}.admin.disabledToast`)
          : t(`${ns}.admin.enabledToast`)
      );
      load(page);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t(`${ns}.admin.toggleFailed`));
    } finally {
      setTogglingId(null);
    }
  };

  const EmptyIcon = kind === "message" ? Mail : BellRing;

  return (
    <div className="flex min-h-[calc(100vh-7.5rem)] w-full flex-col gap-6">
      {/* 页头 */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold">{t(`${ns}.admin.title`)}</h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            {t(`${ns}.admin.totalItems`, { total })}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => load(page)} disabled={loading}>
            <RefreshCw className={cn("size-4", loading && "animate-spin")} />
            {t(`${ns}.admin.refresh`)}
          </Button>
          <Button
            size="sm"
            onClick={() => {
              setFormItem(null);
              setFormOpen(true);
            }}
          >
            <Plus className="size-4" />
            {t(`${ns}.admin.createButton`)}
          </Button>
        </div>
      </div>

      {/* 筛选 */}
      <form
        onSubmit={onSearch}
        className="flex items-center gap-3 rounded-xl border border-border/60 bg-card/40 p-4"
      >
        <Input
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          placeholder={t(`${ns}.admin.searchPlaceholder`)}
          className="w-56"
        />
        {hasType && (
          <Select
            value={typeFilter}
            onValueChange={(v) => {
              setTypeFilter(v as "" | MessageType);
              setPage(1);
            }}
            options={[
              { value: "", label: t("messages.typeAll") },
              ...MESSAGE_TYPES.map((tp) => ({
                value: tp,
                label: t(`messages.type.${tp}`),
              })),
            ]}
            className="w-auto"
            aria-label={t("messages.typeFilterAria")}
          />
        )}
        <Select
          value={statusFilter}
          onValueChange={(v) => {
            setStatusFilter(v as "" | "active" | "inactive");
            setPage(1);
          }}
          options={[
            { value: "", label: t(`${ns}.admin.statusAll`) },
            { value: "active", label: t(`${ns}.admin.statusActive`) },
            { value: "inactive", label: t(`${ns}.admin.statusInactive`) },
          ]}
          className="w-auto"
          aria-label={t(`${ns}.admin.statusFilterAria`)}
        />
        <Button type="submit" size="sm" variant="outline" disabled={loading}>
          <Search className="size-4" />
          {t(`${ns}.admin.search`)}
        </Button>
      </form>

      {/* 列表 */}
      <div className="relative overflow-hidden rounded-xl border border-border/60 bg-card/40">
        {error && items.length === 0 ? (
          <div className="flex flex-col items-center gap-2 py-16 text-sm text-muted-foreground">
            <p>{t(`${ns}.admin.loadFailedWithReason`, { error })}</p>
            <Button variant="outline" size="sm" onClick={() => load(page)}>
              {t(`${ns}.admin.retry`)}
            </Button>
          </div>
        ) : items.length === 0 ? (
          <div className="flex items-center justify-center py-16 text-muted-foreground">
            {loading ? (
              <Loading size="lg" />
            ) : (
              <div className="flex flex-col items-center gap-2">
                <EmptyIcon className="size-8 text-muted-foreground/50" />
                <p className="text-sm">{t(`${ns}.admin.empty`)}</p>
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
                    <th className="px-6 py-3 text-left font-medium">
                      {t(`${ns}.admin.colTitle`)}
                    </th>
                    {hasType && (
                      <th className="px-6 py-3 font-medium">
                        {t(`${ns}.admin.colType`)}
                      </th>
                    )}
                    <th className="px-6 py-3 font-medium">
                      {t(`${ns}.admin.colVisibility`)}
                    </th>
                    <th className="px-6 py-3 font-medium">
                      {t(`${ns}.admin.colStatus`)}
                    </th>
                    <th className="px-6 py-3 font-medium">
                      {t(`${ns}.admin.colStartAt`)}
                    </th>
                    <th className="px-6 py-3 font-medium">
                      {t(`${ns}.admin.colExpiresAt`)}
                    </th>
                    <th className="sticky right-0 z-20 bg-muted shadow-[-10px_0_12px_-10px_rgba(0,0,0,0.12)] px-6 py-3 font-medium">
                      {t(`${ns}.admin.colActions`)}
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/60">
                  {items.map((item) => (
                    <tr key={item.id} className="transition-colors hover:bg-accent/40">
                      <td className="max-w-56 truncate px-6 py-3" title={item.title}>
                        {item.title}
                      </td>
                      {hasType && "type" in item && (
                        <td className="px-6 py-3 text-center">
                          <Badge variant={TYPE_VARIANT[item.type]}>
                            {t(`messages.type.${item.type}`)}
                          </Badge>
                        </td>
                      )}
                      <td className="px-6 py-3 text-center text-muted-foreground">
                        {item.is_public
                          ? t(`${ns}.admin.visibilityPublic`)
                          : t(`${ns}.admin.visibilityTargeted`, {
                              count: targetCount(item.targets),
                            })}
                      </td>
                      <td className="px-6 py-3 text-center">
                        <Badge variant={item.is_active ? "default" : "secondary"}>
                          {item.is_active
                            ? t(`${ns}.admin.statusActive`)
                            : t(`${ns}.admin.statusInactive`)}
                        </Badge>
                      </td>
                      <td className="px-6 py-3 text-center text-muted-foreground">
                        {formatTime(locale, item.start_at)}
                      </td>
                      <td className="px-6 py-3 text-center text-muted-foreground">
                        {formatTime(locale, item.expires_at)}
                      </td>
                      <td className="sticky right-0 bg-card shadow-[-10px_0_12px_-10px_rgba(0,0,0,0.12)] px-6 py-3 text-center">
                        <div className="flex items-center justify-center gap-1.5">
                          <Button variant="outline" size="sm" onClick={() => setDetail(item)}>
                            <Eye className="size-4" />
                            {t(`${ns}.admin.detail`)}
                          </Button>
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => {
                              setFormItem(item);
                              setFormOpen(true);
                            }}
                          >
                            <Pencil className="size-4" />
                            {t(`${ns}.admin.edit`)}
                          </Button>
                          <Button
                            variant="outline"
                            size="sm"
                            className={
                              item.is_active
                                ? "text-warning hover:bg-warning/10 hover:text-warning"
                                : "text-success hover:bg-success/10 hover:text-success"
                            }
                            disabled={togglingId === item.id}
                            onClick={() => onToggleActive(item)}
                          >
                            {togglingId === item.id ? (
                              <Loading size="sm" />
                            ) : item.is_active ? (
                              <Ban className="size-4" />
                            ) : (
                              <CircleCheck className="size-4" />
                            )}
                            {item.is_active
                              ? t(`${ns}.admin.disable`)
                              : t(`${ns}.admin.enable`)}
                          </Button>
                          <Button
                            variant="outline"
                            size="sm"
                            className="text-destructive hover:bg-destructive/10 hover:text-destructive"
                            onClick={() => setDeleting(item)}
                          >
                            <Trash2 className="size-4" />
                            {t(`${ns}.admin.delete`)}
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

      {/* 分页：mt-auto 固定吸底 */}
      {!error && items.length > 0 && (
        <Pagination
          page={page}
          totalPages={totalPages}
          loading={loading}
          onChange={setPage}
          className="mt-auto"
        />
      )}

      {formOpen && (
        <ItemFormDialog
          kind={kind}
          item={formItem}
          onClose={() => setFormOpen(false)}
          onSaved={() => load(formItem ? page : 1)}
        />
      )}
      {detail && <DetailDialog item={detail} onClose={() => setDetail(null)} />}
      {deleting && (
        <DeleteDialog
          kind={kind}
          item={deleting}
          onClose={() => setDeleting(null)}
          onDeleted={() => load(page)}
        />
      )}
    </div>
  );
}

export function MessagesPanel() {
  return <ResourcePanel kind="message" />;
}

export function NotificationsPanel() {
  return <ResourcePanel kind="notification" />;
}
