"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  CircleDollarSign,
  Copy,
  Eye,
  Pencil,
  Plus,
  RefreshCw,
  SlidersHorizontal,
  Trash2,
  X,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Loading } from "@/components/ui/loading";
import { Pagination } from "@/components/ui/pagination";
import { toast } from "@/components/ui/toaster";
import { cn } from "@/lib/utils";
import { get, post } from "@/lib/request";
import { type ModelOption } from "@/components/console/models-panel";
import {
  DeletePricingRuleDialog,
  normalize,
  PricingModifierDrawer,
  PricingRuleDetailDialog,
  PricingRuleFormDialog,
  useOptions,
  type PricingRule,
} from "@/components/console/pricing-shared";

const PAGE_SIZE = 20;

/** 模型定价抽屉：在模型页内管理当前模型的价格规则与修正项 */
export function ModelPricingDrawer({
  model,
  onClose,
}: {
  model: ModelOption;
  onClose: () => void;
}) {
  const { t } = useTranslation("console", { keyPrefix: "pricing" });
  const [rules, setRules] = useState<PricingRule[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [keyword, setKeyword] = useState("");
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingRule, setEditingRule] = useState<PricingRule | null>(null);
  const [detailRuleId, setDetailRuleId] = useState<string | null>(null);
  const [deletingRule, setDeletingRule] = useState<PricingRule | null>(null);
  const [modifierRule, setModifierRule] = useState<PricingRule | null>(null);
  const { models, groups } = useOptions();
  /** 记录 mousedown 是否发生在遮罩上：避免从面板内拖选文本、在遮罩上松手时误关闭抽屉 */
  const overlayMouseDown = useRef(false);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const load = useCallback(
    async (p: number, nameKeyword: string, modelId: string) => {
      setLoading(true);
      setError("");
      try {
        const data = await get<unknown>("/admin/pricing-rules/list", {
          params: {
            page: p,
            page_size: PAGE_SIZE,
            model_id: modelId,
            keyword: nameKeyword.trim() || undefined,
          },
        });
        const { rules, total } = normalize(data);
        setRules(rules);
        setTotal(total);
      } catch (err) {
        setError(err instanceof Error ? err.message : t("loadFailed"));
      } finally {
        setLoading(false);
      }
    },
    [t]
  );

  /** 初始 mount 立即加载第一页；setState 推迟到微任务，避免在 effect 体内同步触发级联渲染 */
  useEffect(() => {
    void Promise.resolve().then(() => load(page, keyword, model.id));
  }, [load, page, keyword, model.id]);

  /** 模型 ID → 名称：抽屉固定展示当前模型 */
  const modelName = useCallback(() => model.name, [model.name]);

  /** 分组 ID → 名称，未命中时回退为 #id */
  const groupName = useCallback(
    (id: number) => groups.find((g) => g.id === id)?.name ?? `#${id}`,
    [groups]
  );

  const onKeywordChange = (v: string) => {
    setPage(1);
    setKeyword(v);
  };

  const onDeleted = () => {
    // 删除当前页最后一条时回退到上一页
    if (rules.length === 1 && page > 1) {
      setPage(page - 1);
    } else {
      load(page, keyword, model.id);
    }
  };

  return (
    <div
      className="fixed inset-0 z-[70] flex justify-end bg-black/50 backdrop-blur-sm animate-in fade-in-0 duration-200"
      onMouseDown={(e) => {
        overlayMouseDown.current = e.target === e.currentTarget;
      }}
      onClick={(e) => {
        // 只有按下和抬起都在遮罩自身上才关闭；从面板内拖选文本到遮罩松手不关闭
        if (overlayMouseDown.current && e.target === e.currentTarget) onClose();
      }}
    >
      <div
        className="flex h-full w-full max-w-5xl flex-col border-l border-border/80 bg-background shadow-2xl animate-in slide-in-from-right duration-300"
        onClick={(e) => e.stopPropagation()}
      >
        {/* 抽屉头部：固定吸顶 */}
        <div className="flex items-center justify-between border-b border-border/60 px-6 py-4">
          <div>
            <h2 className="text-base font-semibold">{t("drawerTitle", { name: model.name })}</h2>
            <p className="mt-0.5 text-xs text-muted-foreground">
              {t("drawerDesc")}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label={t("close")}
            className="rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          >
            <X className="size-4" />
          </button>
        </div>

        {/* 工具栏 */}
        <div className="flex items-center justify-end gap-2 px-6 pt-4">
          <Input
            aria-label={t("filterByName")}
            value={keyword}
            onChange={(e) => onKeywordChange(e.target.value)}
            placeholder={t("filterName")}
            autoComplete="off"
            className="w-44"
          />
          <Button
            variant="outline"
            size="sm"
            onClick={() => load(page, keyword, model.id)}
            disabled={loading}
          >
            <RefreshCw className={cn("size-4", loading && "animate-spin")} />
            {t("refresh")}
          </Button>
          <Button size="sm" onClick={() => setDialogOpen(true)}>
            <Plus className="size-4" />
            {t("createRule")}
          </Button>
        </div>

        {/* 规则列表 */}
        <div className="min-h-0 flex-1 overflow-y-auto p-6">
          <div className="relative overflow-hidden rounded-xl border border-border/60 bg-card/40">
            {error && rules.length === 0 ? (
              <div className="flex flex-col items-center gap-2 py-16 text-sm text-muted-foreground">
                <p>{t("loadFailedColon")}{error}</p>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => load(page, keyword, model.id)}
                >
                  {t("retry")}
                </Button>
              </div>
            ) : rules.length === 0 ? (
              <div className="flex items-center justify-center py-16 text-muted-foreground">
                {loading ? (
                  <Loading size="lg" />
                ) : (
                  <div className="flex flex-col items-center gap-2">
                    <CircleDollarSign className="size-8 text-muted-foreground/50" />
                    <p className="text-sm">{t("emptyRules")}</p>
                    <Button size="sm" onClick={() => setDialogOpen(true)}>
                      <Plus className="size-4" />
                      {t("createRuleAction")}
                    </Button>
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
                      <th className="px-6 py-3 text-left font-medium">{t("colName")}</th>
                      <th className="px-6 py-3 font-medium">{t("colGroup")}</th>
                      <th className="px-6 py-3 font-medium">{t("colPriority")}</th>
                      <th className="px-6 py-3 text-left font-medium">{t("colItems")}</th>
                      <th className="px-6 py-3 font-medium">{t("colStatus")}</th>
                      <th className="sticky right-0 z-20 bg-muted shadow-[-10px_0_12px_-10px_rgba(0,0,0,0.12)] px-6 py-3 font-medium">
                        {t("colActions")}
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/60">
                    {rules.map((r) => (
                      <tr
                        key={r.id}
                        className="transition-colors hover:bg-accent/40"
                      >
                        <td className="px-6 py-3 font-medium">{r.name}</td>
                        <td className="px-6 py-3 text-center">
                          <Badge variant="secondary">
                            {groupName(r.token_group_id)}
                          </Badge>
                        </td>
                        <td className="px-6 py-3 text-center font-mono text-xs">
                          {r.priority}
                        </td>
                        <td className="px-6 py-3">
                          {r.items && r.items.length > 0 ? (
                            <div className="flex flex-wrap gap-1">
                              {r.items.map((it) => (
                                <Badge
                                  key={it.id}
                                  variant="secondary"
                                  className="text-xs"
                                >
                                  {it.label}
                                </Badge>
                              ))}
                            </div>
                          ) : (
                            <span className="text-xs text-muted-foreground">
                              {t("noItems")}
                            </span>
                          )}
                        </td>
                        <td className="px-6 py-3 text-center">
                          <Badge variant={r.active ? "default" : "destructive"}>
                            {r.active ? t("active") : t("inactive")}
                          </Badge>
                        </td>
                        <td className="sticky right-0 bg-card shadow-[-10px_0_12px_-10px_rgba(0,0,0,0.12)] px-6 py-3 text-center">
                          <div className="flex items-center justify-center gap-1.5">
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => setDetailRuleId(r.id)}
                              aria-label={t("viewDetail")}
                            >
                              <Eye className="size-4" />
                              {t("detail")}
                            </Button>
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => {
                                void post("/admin/pricing-rules/copy", { pricing_rule_id: r.id })
                                  .then(() => {
                                    toast.success(t("copySuccess"));
                                    load(page, keyword, model.id);
                                  })
                                  .catch((err) => toast.error(err instanceof Error ? err.message : t("copyFailed")));
                              }}
                              aria-label={t("copyRuleAria")}
                            >
                              <Copy className="size-4" />
                              {t("copy")}
                            </Button>
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => setModifierRule(r)}
                              aria-label={t("manageModifiers")}
                            >
                              <SlidersHorizontal className="size-4" />
                              {t("modifiers")}
                            </Button>
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => setEditingRule(r)}
                              aria-label={t("editRuleAria")}
                            >
                              <Pencil className="size-4" />
                              {t("edit")}
                            </Button>
                            <Button
                              variant="outline"
                              size="sm"
                              className="text-destructive hover:bg-destructive/10 hover:text-destructive"
                              onClick={() => setDeletingRule(r)}
                              aria-label={t("deleteRuleAria")}
                            >
                              <Trash2 className="size-4" />
                              {t("delete")}
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
        </div>

        {/* 分页：固定吸底，不随列表高度跳动 */}
        {!error && rules.length > 0 && (
          <div className="border-t border-border/60 px-6 py-3.5">
            <Pagination
              page={page}
              totalPages={totalPages}
              loading={loading}
              onChange={setPage}
            />
          </div>
        )}
      </div>

      {/* 弹窗层：阻止点击冒泡到抽屉遮罩，避免关闭弹窗时连带关闭抽屉 */}
      <div onClick={(e) => e.stopPropagation()}>
        {dialogOpen && (
          <PricingRuleFormDialog
            rule={null}
            models={models}
            groups={groups}
            defaultModelId={model.id}
            onClose={() => setDialogOpen(false)}
            onSaved={() => load(page, keyword, model.id)}
          />
        )}
        {editingRule && (
          <PricingRuleFormDialog
            rule={editingRule}
            models={models}
            groups={groups}
            defaultModelId={model.id}
            onClose={() => setEditingRule(null)}
            onSaved={() => load(page, keyword, model.id)}
          />
        )}
        {detailRuleId && (
          <PricingRuleDetailDialog
            ruleId={detailRuleId}
            modelName={modelName}
            groupName={groupName}
            onClose={() => setDetailRuleId(null)}
          />
        )}
        {deletingRule && (
          <DeletePricingRuleDialog
            rule={deletingRule}
            onClose={() => setDeletingRule(null)}
            onDeleted={onDeleted}
          />
        )}
        {modifierRule && (
          <PricingModifierDrawer
            rule={modifierRule}
            onClose={() => setModifierRule(null)}
          />
        )}
      </div>
    </div>
  );
}
