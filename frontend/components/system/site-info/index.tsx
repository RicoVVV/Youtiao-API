"use client";

import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Ban,
  CircleCheck,
  Globe,
  Pencil,
  Plus,
  RefreshCw,
  Search,
  Trash2,
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
  BADGE_COLORS,
  badgeDotClass,
  createSiteInfo,
  deleteSiteInfo,
  listAdminSiteInfos,
  updateSiteInfo,
  updateSiteInfoStatus,
  type AdminSiteInfo,
} from "@/lib/overview";

const PAGE_SIZE = 10;

const formatTime = (locale: string, value: string | null) =>
  value ? new Date(value).toLocaleString(locale, { hour12: false }) : "—";

/** 表单弹窗：创建 / 编辑共用 */
function SiteInfoFormDialog({
  item,
  onClose,
  onSaved,
}: {
  /** null 表示创建 */
  item: AdminSiteInfo | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { t } = useTranslation("console");
  const ns = "siteInfo.admin";
  const [routeName, setRouteName] = useState(item?.route_name ?? "");
  const [apiUrl, setApiUrl] = useState(item?.api_url ?? "");
  const [description, setDescription] = useState(item?.description ?? "");
  const [badgeColor, setBadgeColor] = useState(item?.badge_color ?? "blue");
  const [sortOrder, setSortOrder] = useState(String(item?.sort_order ?? 0));
  const [isActive, setIsActive] = useState(item?.is_active ?? true);
  const [submitting, setSubmitting] = useState(false);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmedName = routeName.trim();
    const trimmedUrl = apiUrl.trim();
    if (!trimmedName) {
      toast.warning(t(`${ns}.routeNameRequired`));
      return;
    }
    if (!trimmedUrl) {
      toast.warning(t(`${ns}.apiUrlRequired`));
      return;
    }
    const order = Number(sortOrder);
    if (!Number.isInteger(order) || order < 0) {
      toast.warning(t(`${ns}.sortOrderInvalid`));
      return;
    }
    setSubmitting(true);
    try {
      const base = {
        route_name: trimmedName,
        api_url: trimmedUrl,
        description: description.trim(),
        badge_color: badgeColor,
        sort_order: order,
        is_active: isActive,
      };
      if (item) {
        await updateSiteInfo({ ...base, site_info_id: item.id });
        toast.success(t(`${ns}.updateSuccess`));
      } else {
        await createSiteInfo(base);
        toast.success(t(`${ns}.createSuccess`));
      }
      onSaved();
      onClose();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t(`${ns}.saveFailed`));
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
        className="flex max-h-[90vh] w-full max-w-lg flex-col rounded-xl border bg-background p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-base font-semibold">
          {item ? t(`${ns}.editTitle`) : t(`${ns}.createTitle`)}
        </h2>
        <form
          onSubmit={onSubmit}
          className="no-scrollbar mt-5 flex-1 space-y-4 overflow-y-auto pr-1"
        >
          <div className="space-y-1.5">
            <label htmlFor="si-route-name" className="text-sm font-medium">
              {t(`${ns}.fieldRouteName`)}
              <span className="text-destructive">*</span>
            </label>
            <Input
              id="si-route-name"
              value={routeName}
              onChange={(e) => setRouteName(e.target.value)}
              maxLength={255}
              placeholder={t(`${ns}.routeNamePlaceholder`)}
            />
          </div>
          <div className="space-y-1.5">
            <label htmlFor="si-api-url" className="text-sm font-medium">
              {t(`${ns}.fieldApiUrl`)}
              <span className="text-destructive">*</span>
            </label>
            <Input
              id="si-api-url"
              value={apiUrl}
              onChange={(e) => setApiUrl(e.target.value)}
              maxLength={2048}
              placeholder={t(`${ns}.apiUrlPlaceholder`)}
            />
          </div>
          <div className="space-y-1.5">
            <label htmlFor="si-description" className="text-sm font-medium">
              {t(`${ns}.fieldDescription`)}
            </label>
            <textarea
              id="si-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              maxLength={2000}
              placeholder={t(`${ns}.descriptionPlaceholder`)}
              className="border-input dark:bg-input/30 w-full rounded-md border bg-transparent px-3 py-2 text-sm shadow-xs outline-none focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px]"
            />
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <label htmlFor="si-badge-color" className="text-sm font-medium">
                {t(`${ns}.fieldBadgeColor`)}
              </label>
              <Select
                id="si-badge-color"
                value={badgeColor}
                onValueChange={setBadgeColor}
                options={BADGE_COLORS.map((color) => ({
                  value: color,
                  label: (
                    <span className="flex items-center gap-2">
                      <span
                        className={cn(
                          "size-2 rounded-full",
                          badgeDotClass(color)
                        )}
                      />
                      {t(`siteInfo.colors.${color}`)}
                    </span>
                  ),
                }))}
                className="w-full"
                aria-label={t(`${ns}.fieldBadgeColor`)}
              />
            </div>
            <div className="space-y-1.5">
              <label htmlFor="si-sort-order" className="text-sm font-medium">
                {t(`${ns}.fieldSortOrder`)}
              </label>
              <Input
                id="si-sort-order"
                type="number"
                min={0}
                step={1}
                value={sortOrder}
                onChange={(e) => setSortOrder(e.target.value)}
              />
              <p className="text-xs text-muted-foreground">
                {t(`${ns}.sortOrderHint`)}
              </p>
            </div>
          </div>
          <label className="flex cursor-pointer items-center gap-2 text-sm font-medium">
            <Switch checked={isActive} onCheckedChange={setIsActive} />
            {t(`${ns}.isActive`)}
          </label>
          <div className="flex justify-end gap-2 pt-1">
            <Button type="button" variant="outline" onClick={onClose}>
              {t(`${ns}.cancel`)}
            </Button>
            <Button type="submit" disabled={submitting}>
              {submitting && <Loading size="sm" />}
              {item ? t(`${ns}.save`) : t(`${ns}.create`)}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}

/** 删除确认弹窗 */
function DeleteDialog({
  item,
  onClose,
  onDeleted,
}: {
  item: AdminSiteInfo;
  onClose: () => void;
  onDeleted: () => void;
}) {
  const { t } = useTranslation("console");
  const ns = "siteInfo.admin";
  const [submitting, setSubmitting] = useState(false);

  const onDelete = async () => {
    setSubmitting(true);
    try {
      await deleteSiteInfo(item.id);
      toast.success(t(`${ns}.deleteSuccess`));
      onDeleted();
      onClose();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t(`${ns}.deleteFailed`));
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
        <h2 className="text-base font-semibold">{t(`${ns}.deleteTitle`)}</h2>
        <p className="mt-2 text-sm text-muted-foreground">
          {t(`${ns}.deleteConfirm`, { name: item.route_name })}
        </p>
        <div className="mt-6 flex justify-end gap-2">
          <Button variant="outline" onClick={onClose}>
            {t(`${ns}.cancel`)}
          </Button>
          <Button variant="destructive" disabled={submitting} onClick={onDelete}>
            {submitting && <Loading size="sm" />}
            {t(`${ns}.delete`)}
          </Button>
        </div>
      </div>
    </div>
  );
}

/** 站点信息管理面板 */
export function SiteInfoPanel() {
  const { t, i18n } = useTranslation("console");
  const locale = i18n.language === "zh" ? "zh-CN" : "en-US";
  const ns = "siteInfo.admin";
  const [items, setItems] = useState<AdminSiteInfo[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [keyword, setKeyword] = useState("");
  const [appliedKeyword, setAppliedKeyword] = useState("");
  const [statusFilter, setStatusFilter] = useState<"" | "active" | "inactive">("");
  const [formItem, setFormItem] = useState<AdminSiteInfo | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [deleting, setDeleting] = useState<AdminSiteInfo | null>(null);
  const [togglingId, setTogglingId] = useState<string | null>(null);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const load = useCallback(
    async (p: number) => {
      setLoading(true);
      setError("");
      try {
        const data = await listAdminSiteInfos({
          page: p,
          page_size: PAGE_SIZE,
          keyword: appliedKeyword || undefined,
          is_active: statusFilter === "" ? undefined : statusFilter === "active",
        });
        setItems(data.items);
        setTotal(data.total);
      } catch (err) {
        setError(err instanceof Error ? err.message : t(`${ns}.loadFailed`));
      } finally {
        setLoading(false);
      }
    },
    [appliedKeyword, statusFilter, ns, t]
  );

  useEffect(() => {
    load(page);
  }, [load, page]);

  const onSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setPage(1);
    setAppliedKeyword(keyword.trim());
  };

  const onToggleActive = async (item: AdminSiteInfo) => {
    setTogglingId(item.id);
    try {
      await updateSiteInfoStatus({
        site_info_id: item.id,
        is_active: !item.is_active,
      });
      toast.success(
        item.is_active ? t(`${ns}.disabledToast`) : t(`${ns}.enabledToast`)
      );
      load(page);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t(`${ns}.toggleFailed`));
    } finally {
      setTogglingId(null);
    }
  };

  return (
    <div className="flex min-h-[calc(100vh-7.5rem)] w-full flex-col gap-6">
      {/* 页头 */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold">{t(`${ns}.title`)}</h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            {t(`${ns}.totalItems`, { total })}
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
            {t(`${ns}.refresh`)}
          </Button>
          <Button
            size="sm"
            onClick={() => {
              setFormItem(null);
              setFormOpen(true);
            }}
          >
            <Plus className="size-4" />
            {t(`${ns}.createButton`)}
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
          placeholder={t(`${ns}.searchPlaceholder`)}
          className="w-56"
        />
        <Select
          value={statusFilter}
          onValueChange={(v) => {
            setStatusFilter(v as "" | "active" | "inactive");
            setPage(1);
          }}
          options={[
            { value: "", label: t(`${ns}.statusAll`) },
            { value: "active", label: t(`${ns}.statusActive`) },
            { value: "inactive", label: t(`${ns}.statusInactive`) },
          ]}
          className="w-auto"
          aria-label={t(`${ns}.statusFilterAria`)}
        />
        <Button type="submit" size="sm" variant="outline" disabled={loading}>
          <Search className="size-4" />
          {t(`${ns}.search`)}
        </Button>
      </form>

      {/* 列表 */}
      <div className="relative overflow-hidden rounded-xl border border-border/60 bg-card/40">
        {error && items.length === 0 ? (
          <div className="flex flex-col items-center gap-2 py-16 text-sm text-muted-foreground">
            <p>{t(`${ns}.loadFailedWithReason`, { error })}</p>
            <Button variant="outline" size="sm" onClick={() => load(page)}>
              {t(`${ns}.retry`)}
            </Button>
          </div>
        ) : items.length === 0 ? (
          <div className="flex items-center justify-center py-16 text-muted-foreground">
            {loading ? (
              <Loading size="lg" />
            ) : (
              <div className="flex flex-col items-center gap-2">
                <Globe className="size-8 text-muted-foreground/50" />
                <p className="text-sm">{t(`${ns}.empty`)}</p>
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
                      {t(`${ns}.colRouteName`)}
                    </th>
                    <th className="px-6 py-3 text-left font-medium">
                      {t(`${ns}.colApiUrl`)}
                    </th>
                    <th className="px-6 py-3 font-medium">
                      {t(`${ns}.colSortOrder`)}
                    </th>
                    <th className="px-6 py-3 font-medium">
                      {t(`${ns}.colStatus`)}
                    </th>
                    <th className="px-6 py-3 font-medium">
                      {t(`${ns}.colUpdatedAt`)}
                    </th>
                    <th className="sticky right-0 z-20 bg-muted shadow-[-10px_0_12px_-10px_rgba(0,0,0,0.12)] px-6 py-3 font-medium">
                      {t(`${ns}.colActions`)}
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/60">
                  {items.map((item) => (
                    <tr key={item.id} className="transition-colors hover:bg-accent/40">
                      <td className="max-w-56 px-6 py-3">
                        <div className="flex items-center gap-2">
                          <span
                            className={cn(
                              "size-2 shrink-0 rounded-full",
                              badgeDotClass(item.badge_color)
                            )}
                            aria-hidden
                          />
                          <span className="truncate" title={item.route_name}>
                            {item.route_name}
                          </span>
                        </div>
                        {item.description && (
                          <p
                            className="mt-0.5 truncate pl-4 text-xs text-muted-foreground"
                            title={item.description}
                          >
                            {item.description}
                          </p>
                        )}
                      </td>
                      <td className="max-w-64 truncate px-6 py-3 text-muted-foreground" title={item.api_url}>
                        {item.api_url}
                      </td>
                      <td className="px-6 py-3 text-center text-muted-foreground">
                        {item.sort_order}
                      </td>
                      <td className="px-6 py-3 text-center">
                        <Badge variant={item.is_active ? "default" : "secondary"}>
                          {item.is_active
                            ? t(`${ns}.statusActive`)
                            : t(`${ns}.statusInactive`)}
                        </Badge>
                      </td>
                      <td className="px-6 py-3 text-center text-muted-foreground">
                        {formatTime(locale, item.updated_at ?? item.created_at)}
                      </td>
                      <td className="sticky right-0 bg-card shadow-[-10px_0_12px_-10px_rgba(0,0,0,0.12)] px-6 py-3 text-center">
                        <div className="flex items-center justify-center gap-1.5">
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => {
                              setFormItem(item);
                              setFormOpen(true);
                            }}
                          >
                            <Pencil className="size-4" />
                            {t(`${ns}.edit`)}
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
                              ? t(`${ns}.disable`)
                              : t(`${ns}.enable`)}
                          </Button>
                          <Button
                            variant="outline"
                            size="sm"
                            className="text-destructive hover:bg-destructive/10 hover:text-destructive"
                            onClick={() => setDeleting(item)}
                          >
                            <Trash2 className="size-4" />
                            {t(`${ns}.delete`)}
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
        <SiteInfoFormDialog
          item={formItem}
          onClose={() => setFormOpen(false)}
          onSaved={() => load(formItem ? page : 1)}
        />
      )}
      {deleting && (
        <DeleteDialog
          item={deleting}
          onClose={() => setDeleting(null)}
          onDeleted={() => load(page)}
        />
      )}
    </div>
  );
}
