"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Loading } from "@/components/ui/loading";
import { Select } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { toast } from "@/components/ui/toaster";
import { get, post } from "@/lib/request";

import { fmtRate, type AlertRule } from "../types";
import { useGroupMetricsList } from "../use-group-metrics";

/** 规则表单：阈值字段留空表示不评估该指标（提交为 null） */
type RuleForm = {
  enabled: boolean;
  success_rate_min: string;
  avg_duration_ms_max: string;
  avg_first_token_ms_max: string;
  min_sample_count: string;
  consecutive_hits: string;
  /** @ 手机号，英文逗号分隔；分组行留空表示沿用全局默认 */
  at_mobiles: string;
  at_all: boolean;
};

const ruleToForm = (r: AlertRule): RuleForm => ({
  enabled: r.enabled,
  success_rate_min: r.success_rate_min == null ? "" : String(r.success_rate_min),
  avg_duration_ms_max: r.avg_duration_ms_max == null ? "" : String(r.avg_duration_ms_max),
  avg_first_token_ms_max: r.avg_first_token_ms_max == null ? "" : String(r.avg_first_token_ms_max),
  min_sample_count: String(r.min_sample_count),
  consecutive_hits: String(r.consecutive_hits),
  at_mobiles: r.at_mobiles ?? "",
  at_all: r.at_all ?? false,
});

/** 单个手机号：11 位大陆号码，1[3-9] 开头 */
const MOBILE_RE = /^1[3-9]\d{9}$/;

/** 校验并组装提交体；返回错误消息 key 或请求体 */
function buildBody(
  form: RuleForm,
  t: (key: string) => string
): { error: string } | { body: Record<string, unknown> } {
  // 成功率下限：0~1、最多 4 位小数；留空 → null（不评估）
  let successRateMin: number | null = null;
  if (form.success_rate_min.trim()) {
    const v = Number(form.success_rate_min);
    if (!Number.isFinite(v) || v < 0 || v > 1 || !/^\d+(\.\d{1,4})?$/.test(form.success_rate_min.trim()))
      return { error: t("monitoring.errRate") };
    successRateMin = v;
  }
  const parseMax = (s: string): number | null | "err" => {
    if (!s.trim()) return null;
    const v = Number(s);
    return Number.isInteger(v) && v >= 1 && v <= 86400000 ? v : "err";
  };
  const avgDurationMax = parseMax(form.avg_duration_ms_max);
  if (avgDurationMax === "err") return { error: t("monitoring.errDuration") };
  const firstTokenMax = parseMax(form.avg_first_token_ms_max);
  if (firstTokenMax === "err") return { error: t("monitoring.errFirstToken") };

  const minSamples = Number(form.min_sample_count);
  if (!Number.isInteger(minSamples) || minSamples < 1 || minSamples > 1000000)
    return { error: t("monitoring.errMinSamples") };
  const hits = Number(form.consecutive_hits);
  if (!Number.isInteger(hits) || hits < 1 || hits > 288)
    return { error: t("monitoring.errHits") };

  // @ 手机号：英文逗号分隔，最多 20 个；留空 → 空串（分组行表示沿用全局默认）
  const atMobiles = form.at_mobiles
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
  if (atMobiles.length > 20 || atMobiles.some((m) => !MOBILE_RE.test(m)))
    return { error: t("monitoring.errAtMobiles") };

  return {
    body: {
      enabled: form.enabled,
      success_rate_min: successRateMin,
      avg_duration_ms_max: avgDurationMax,
      avg_first_token_ms_max: firstTokenMax,
      min_sample_count: minSamples,
      consecutive_hits: hits,
      at_mobiles: atMobiles.join(","),
      at_all: form.at_all,
    },
  };
}

/** 新增/编辑规则弹窗 */
function RuleModal({
  title,
  desc,
  mode,
  groupId,
  groupOptions,
  globalAtMobiles,
  initial,
  onClose,
  onSaved,
}: {
  title: string;
  desc: string;
  /** create：新增分组覆盖（需选择分组）；edit：编辑已有规则（含全局默认） */
  mode: "create" | "edit";
  /** 编辑场景：规则所属分组（null = 全局默认） */
  groupId: number | null;
  /** 新增场景：可选分组 */
  groupOptions: Array<{ value: string; label: string }>;
  /** 全局默认行当前 @ 手机号，用于分组行的继承提示 */
  globalAtMobiles?: string;
  initial: RuleForm;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { t } = useTranslation("console");
  const [form, setForm] = useState<RuleForm>(initial);
  const [selectedGroup, setSelectedGroup] = useState("");
  const [submitting, setSubmitting] = useState(false);

  /** 编辑全局默认行时为 true；分组行（含新增覆盖）的 @ 手机号留空表示沿用全局 */
  const isGlobalRow = mode === "edit" && groupId === null;

  const set = (patch: Partial<RuleForm>) => setForm((f) => ({ ...f, ...patch }));

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (mode === "create" && !selectedGroup) {
      toast.warning(t("monitoring.selectGroupRequired"));
      return;
    }
    const built = buildBody(form, t);
    if ("error" in built) {
      toast.warning(built.error);
      return;
    }
    setSubmitting(true);
    try {
      await post("/admin/monitoring/alert-rules/update", {
        // 编辑时沿用原分组（全局默认为 null，等价于不传）；新增时传所选分组
        group_id: mode === "edit" ? (groupId ?? undefined) : Number(selectedGroup),
        ...built.body,
      });
      toast.success(t("monitoring.saveSuccess"));
      onSaved();
      onClose();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t("monitoring.saveFailed"));
    } finally {
      setSubmitting(false);
    }
  };

  const thresholdField = (
    id: string,
    label: string,
    placeholder: string,
    value: string,
    onChange: (v: string) => void
  ) => (
    <div className="space-y-1.5">
      <label htmlFor={id} className="text-sm font-medium">
        {label}
      </label>
      <Input
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        inputMode="decimal"
        autoComplete="off"
      />
    </div>
  );

  return (
    <div
      className="fixed inset-0 z-[80] flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="max-h-[90vh] w-full max-w-md overflow-y-auto rounded-xl border bg-background p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-base font-semibold">{title}</h2>
        <p className="mt-1 text-sm text-muted-foreground">{desc}</p>
        <form onSubmit={submit} className="mt-5 space-y-4">
          {mode === "create" && (
            <div className="space-y-1.5">
              <label className="text-sm font-medium">
                {t("monitoring.selectGroup")}
              </label>
              <Select
                value={selectedGroup}
                onValueChange={setSelectedGroup}
                options={groupOptions}
                placeholder={t("monitoring.selectGroupPlaceholder")}
                className="w-full"
              />
            </div>
          )}
          <div className="flex items-center justify-between rounded-lg border border-border/60 px-3 py-2.5">
            <span className="text-sm font-medium">{t("monitoring.enabledLabel")}</span>
            <Switch
              checked={form.enabled}
              onCheckedChange={(v) => set({ enabled: v })}
            />
          </div>
          {thresholdField(
            "rule-rate",
            t("monitoring.successRateMinLabel"),
            t("monitoring.successRateMinPlaceholder"),
            form.success_rate_min,
            (v) => set({ success_rate_min: v })
          )}
          {thresholdField(
            "rule-duration",
            t("monitoring.avgDurationMaxLabel"),
            t("monitoring.avgDurationMaxPlaceholder"),
            form.avg_duration_ms_max,
            (v) => set({ avg_duration_ms_max: v })
          )}
          {thresholdField(
            "rule-first-token",
            t("monitoring.firstTokenMaxLabel"),
            t("monitoring.firstTokenMaxPlaceholder"),
            form.avg_first_token_ms_max,
            (v) => set({ avg_first_token_ms_max: v })
          )}
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <label htmlFor="rule-min-samples" className="text-sm font-medium">
                {t("monitoring.minSamplesLabel")}
              </label>
              <Input
                id="rule-min-samples"
                value={form.min_sample_count}
                onChange={(e) => set({ min_sample_count: e.target.value })}
                inputMode="numeric"
                autoComplete="off"
              />
            </div>
            <div className="space-y-1.5">
              <label htmlFor="rule-hits" className="text-sm font-medium">
                {t("monitoring.hitsLabel")}
              </label>
              <Input
                id="rule-hits"
                value={form.consecutive_hits}
                onChange={(e) => set({ consecutive_hits: e.target.value })}
                inputMode="numeric"
                autoComplete="off"
              />
            </div>
          </div>
          <div className="space-y-1.5">
            <label htmlFor="rule-at-mobiles" className="text-sm font-medium">
              {t("monitoring.atMobilesLabel")}
            </label>
            <Input
              id="rule-at-mobiles"
              value={form.at_mobiles}
              onChange={(e) => set({ at_mobiles: e.target.value })}
              placeholder={t("monitoring.atMobilesPlaceholder")}
              autoComplete="off"
            />
            <p className="text-xs text-muted-foreground">
              {isGlobalRow
                ? t("monitoring.atMobilesGlobalHint")
                : t("monitoring.atMobilesInheritHint", {
                    mobiles: globalAtMobiles?.trim()
                      ? globalAtMobiles
                      : t("monitoring.atNone"),
                  })}
            </p>
          </div>
          <div className="flex items-center justify-between rounded-lg border border-border/60 px-3 py-2.5">
            <span className="text-sm font-medium">{t("monitoring.atAllLabel")}</span>
            <Switch
              checked={form.at_all}
              onCheckedChange={(v) => set({ at_all: v })}
            />
          </div>
          <p className="text-xs text-muted-foreground">
            {t("monitoring.ruleFormHint")}
          </p>
          <div className="flex justify-end gap-2 pt-1">
            <Button type="button" variant="outline" onClick={onClose}>
              {t("monitoring.cancel")}
            </Button>
            <Button type="submit" disabled={submitting}>
              {submitting && <Loading size="sm" />}
              {t("monitoring.save")}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}

/** 阈值规则：全局默认 + 分组覆盖；分组有覆盖时使用覆盖值 */
export function AdminRulesTab() {
  const { t } = useTranslation("console");
  const { groups } = useGroupMetricsList("/admin");

  const [rules, setRules] = useState<AlertRule[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  /** 弹窗状态：编辑已有规则 / 新增分组覆盖 */
  const [editing, setEditing] = useState<AlertRule | null>(null);
  const [creating, setCreating] = useState(false);
  const [deleting, setDeleting] = useState<AlertRule | null>(null);
  const [deleteSubmitting, setDeleteSubmitting] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const res = await get<{ items: AlertRule[] }>(
        "/admin/monitoring/alert-rules/list"
      );
      setRules(res.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("monitoring.loadFailed"));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    load();
  }, [load]);

  const globalRule = rules.find((r) => r.group_id === null) ?? null;
  const overrides = rules.filter((r) => r.group_id !== null);

  /** 还没有覆盖规则的分组，供新增弹窗选择 */
  const availableGroups = useMemo(() => {
    const covered = new Set(overrides.map((r) => r.group_id));
    return groups
      .filter((g) => !covered.has(g.id))
      .map((g) => ({ value: String(g.id), label: g.name }));
  }, [groups, overrides]);

  const removeOverride = async () => {
    if (!deleting?.group_id) return;
    setDeleteSubmitting(true);
    try {
      await post("/admin/monitoring/alert-rules/delete", {
        group_id: deleting.group_id,
      });
      toast.success(t("monitoring.deleteSuccess"));
      setDeleting(null);
      load();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t("monitoring.deleteFailed"));
    } finally {
      setDeleteSubmitting(false);
    }
  };

  const renderRow = (r: AlertRule) => (
    <tr key={r.id} className="transition-colors hover:bg-accent/40">
      <td className="py-2.5 pr-4">
        {r.group_id === null ? (
          <Badge variant="secondary">{t("monitoring.globalRule")}</Badge>
        ) : (
          <span className="font-medium">{r.group_name}</span>
        )}
      </td>
      <td className="px-4 py-2.5 text-center">
        <Badge
          variant="outline"
          className={
            r.enabled
              ? "border-success/50 text-success"
              : "border-border text-muted-foreground"
          }
        >
          {r.enabled ? t("monitoring.ruleOn") : t("monitoring.ruleOff")}
        </Badge>
      </td>
      <td className="px-4 py-2.5 text-center">{fmtRate(r.success_rate_min)}</td>
      <td className="px-4 py-2.5 text-center text-muted-foreground">
        {r.avg_duration_ms_max ?? t("monitoring.notEvaluated")}
      </td>
      <td className="px-4 py-2.5 text-center text-muted-foreground">
        {r.avg_first_token_ms_max ?? t("monitoring.notEvaluated")}
      </td>
      <td className="px-4 py-2.5 text-center">{r.min_sample_count}</td>
      <td className="px-4 py-2.5 text-center">{r.consecutive_hits}</td>
      <td
        className="max-w-[160px] truncate px-4 py-2.5 text-center text-muted-foreground"
        title={r.at_mobiles || undefined}
      >
        {r.at_mobiles ? (
          r.at_mobiles
        ) : r.group_id !== null ? (
          t("monitoring.atInherit")
        ) : (
          "—"
        )}
      </td>
      <td className="px-4 py-2.5 text-center">
        {r.at_all ? (
          <Badge
            variant="outline"
            className="border-success/50 text-success"
          >
            {t("monitoring.atAllBadge")}
          </Badge>
        ) : (
          <span className="text-muted-foreground">—</span>
        )}
      </td>
      <td className="py-2.5 pl-4 text-center whitespace-nowrap">
        <div className="flex items-center justify-center gap-1.5">
          <Button variant="outline" size="sm" onClick={() => setEditing(r)}>
            {t("monitoring.edit")}
          </Button>
          {r.group_id !== null && (
            <Button variant="ghost" size="sm" onClick={() => setDeleting(r)}>
              {t("monitoring.deleteOverride")}
            </Button>
          )}
        </div>
      </td>
    </tr>
  );

  return (
    <section className="rounded-xl border border-border/60 bg-card/40 p-4">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-medium">{t("monitoring.rulesTitle")}</h2>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {t("monitoring.rulesDesc")}
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => setCreating(true)}
          disabled={availableGroups.length === 0 || !globalRule}
        >
          {t("monitoring.createOverride")}
        </Button>
      </div>

      {loading ? (
        <div className="flex justify-center py-10">
          <Loading size="md" />
        </div>
      ) : error ? (
        <div className="flex flex-col items-center gap-2 py-10 text-sm text-muted-foreground">
          <p>{t("monitoring.loadFailedWithReason", { error })}</p>
          <Button variant="outline" size="sm" onClick={load}>
            {t("monitoring.retry")}
          </Button>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border/60 text-xs text-muted-foreground">
                <th className="py-2.5 pr-4 text-left font-medium">
                  {t("monitoring.colGroup")}
                </th>
                <th className="px-4 py-2.5 text-center font-medium">
                  {t("monitoring.colEnabled")}
                </th>
                <th className="px-4 py-2.5 text-center font-medium">
                  {t("monitoring.colSuccessRateMin")}
                </th>
                <th className="px-4 py-2.5 text-center font-medium">
                  {t("monitoring.colAvgDurationMax")}
                </th>
                <th className="px-4 py-2.5 text-center font-medium">
                  {t("monitoring.colFirstTokenMax")}
                </th>
                <th className="px-4 py-2.5 text-center font-medium">
                  {t("monitoring.colMinSamples")}
                </th>
                <th className="px-4 py-2.5 text-center font-medium">
                  {t("monitoring.colHits")}
                </th>
                <th className="px-4 py-2.5 text-center font-medium">
                  {t("monitoring.colAtMobiles")}
                </th>
                <th className="px-4 py-2.5 text-center font-medium">
                  {t("monitoring.colAtAll")}
                </th>
                <th className="py-2.5 pl-4 text-center font-medium">
                  {t("monitoring.colActions")}
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/60">
              {globalRule && renderRow(globalRule)}
              {overrides.map(renderRow)}
            </tbody>
          </table>
        </div>
      )}

      {/* 编辑已有规则 */}
      {editing && (
        <RuleModal
          title={
            editing.group_id === null
              ? t("monitoring.editGlobalTitle")
              : t("monitoring.editGroupTitle", { name: editing.group_name })
          }
          desc={t("monitoring.ruleFormHint")}
          mode="edit"
          groupId={editing.group_id}
          groupOptions={[]}
          globalAtMobiles={globalRule?.at_mobiles ?? ""}
          initial={ruleToForm(editing)}
          onClose={() => setEditing(null)}
          onSaved={load}
        />
      )}

      {/* 新增分组覆盖：阈值以全局默认值为初始值；@ 手机号留空表示沿用全局默认 */}
      {creating && globalRule && (
        <RuleModal
          title={t("monitoring.createTitle")}
          desc={t("monitoring.createDesc")}
          mode="create"
          groupId={null}
          groupOptions={availableGroups}
          globalAtMobiles={globalRule.at_mobiles ?? ""}
          initial={{ ...ruleToForm(globalRule), at_mobiles: "" }}
          onClose={() => setCreating(false)}
          onSaved={load}
        />
      )}

      {/* 删除覆盖确认 */}
      {deleting && (
        <div
          className="fixed inset-0 z-[80] flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm"
          onClick={() => setDeleting(null)}
        >
          <div
            className="w-full max-w-sm rounded-xl border bg-background p-6 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="text-base font-semibold">
              {t("monitoring.deleteTitle")}
            </h2>
            <p className="mt-1 text-sm text-muted-foreground">
              {t("monitoring.deleteConfirm", { name: deleting.group_name })}
            </p>
            <div className="mt-6 flex justify-end gap-2">
              <Button variant="outline" onClick={() => setDeleting(null)}>
                {t("monitoring.cancel")}
              </Button>
              <Button
                variant="destructive"
                onClick={removeOverride}
                disabled={deleteSubmitting}
              >
                {deleteSubmitting && <Loading size="sm" />}
                {t("monitoring.confirmDelete")}
              </Button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
