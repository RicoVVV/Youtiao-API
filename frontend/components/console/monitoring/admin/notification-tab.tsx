"use client";

import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Send } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Loading } from "@/components/ui/loading";
import { Switch } from "@/components/ui/switch";
import { toast } from "@/components/ui/toaster";
import { get, post } from "@/lib/request";

import type {
  NotificationConfig,
  NotificationTestResult,
  NotificationTestScope,
} from "../types";

/**
 * 钉钉推送配置：所有字段不接受 null；
 * webhook_url / sign_secret 不传即保持原值，传空字符串表示清空。
 */
export function AdminNotificationTab() {
  const { t } = useTranslation("console");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  /** 正在发送测试通知的通道 */
  const [testing, setTesting] = useState<NotificationTestScope | null>(null);

  const [notifyGroupAlerts, setNotifyGroupAlerts] = useState(false);
  const [notifyResourceAlerts, setNotifyResourceAlerts] = useState(false);
  const [webhookUrl, setWebhookUrl] = useState("");
  const [keyword, setKeyword] = useState("");
  const [timeoutSeconds, setTimeoutSeconds] = useState("10");
  const [silenceMinutes, setSilenceMinutes] = useState("30");
  const [notifyOnResolved, setNotifyOnResolved] = useState(false);
  /** 密钥不回显：只记录是否已配置；输入新值即替换，勾选清除提交空串 */
  const [secretConfigured, setSecretConfigured] = useState(false);
  const [signSecret, setSignSecret] = useState("");
  const [clearSecret, setClearSecret] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await get<NotificationConfig>(
        "/admin/monitoring/notification/detail"
      );
      setNotifyGroupAlerts(data.notify_group_alerts ?? false);
      setNotifyResourceAlerts(data.notify_resource_alerts ?? false);
      setWebhookUrl(data.webhook_url ?? "");
      setKeyword(data.keyword ?? "");
      setTimeoutSeconds(String(data.timeout_seconds));
      setSilenceMinutes(String(data.silence_minutes));
      setNotifyOnResolved(data.notify_on_resolved);
      setSecretConfigured(data.sign_secret_configured);
      setSignSecret("");
      setClearSecret(false);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t("monitoring.loadFailed"));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    load();
  }, [load]);

  const save = async () => {
    const timeout = Number(timeoutSeconds);
    if (!Number.isInteger(timeout) || timeout < 1 || timeout > 60) {
      toast.warning(t("monitoring.errTimeout"));
      return;
    }
    const silence = Number(silenceMinutes);
    if (!Number.isInteger(silence) || silence < 0 || silence > 1440) {
      toast.warning(t("monitoring.errSilence"));
      return;
    }
    setSaving(true);
    try {
      await post("/admin/monitoring/notification/update", {
        notify_group_alerts: notifyGroupAlerts,
        notify_resource_alerts: notifyResourceAlerts,
        webhook_url: webhookUrl.trim(),
        keyword: keyword.trim(),
        timeout_seconds: timeout,
        silence_minutes: silence,
        notify_on_resolved: notifyOnResolved,
        // sign_secret：留空且未勾选清除 → 不传保持原值；勾选清除 → 传空串；否则传新值
        ...(clearSecret
          ? { sign_secret: "" }
          : signSecret.trim()
            ? { sign_secret: signSecret.trim() }
            : {}),
      });
      toast.success(t("monitoring.notifSaveSuccess"));
      load();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t("monitoring.notifSaveFailed"));
    } finally {
      setSaving(false);
    }
  };

  const sendTest = async (scope: NotificationTestScope) => {
    setTesting(scope);
    try {
      const res = await post<NotificationTestResult>(
        "/admin/monitoring/notification/test",
        { scope }
      );
      if (res.status === "sent") toast.success(t("monitoring.testSent"));
      else if (res.status === "skipped")
        toast.warning(
          t(
            scope === "server"
              ? "monitoring.testSkippedServer"
              : "monitoring.testSkippedGroup"
          )
        );
      else
        toast.error(t("monitoring.testFailed", { error: res.error ?? "unknown" }));
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t("monitoring.testFailed", { error: "" }));
    } finally {
      setTesting(null);
    }
  };

  if (loading) {
    return (
      <div className="flex justify-center rounded-xl border border-border/60 bg-card/40 py-16">
        <Loading size="md" />
      </div>
    );
  }

  return (
    <section className="rounded-xl border border-border/60 bg-card/40 p-4">
      <div className="mb-5">
        <h2 className="text-sm font-medium">{t("monitoring.notifTitle")}</h2>
        <p className="mt-0.5 text-xs text-muted-foreground">
          {t("monitoring.notifDesc")}
        </p>
      </div>

      <div className="grid max-w-3xl grid-cols-1 gap-5">
        <div className="flex items-center justify-between rounded-lg border border-border/60 px-3 py-2.5">
          <div>
            <p className="text-sm font-medium">{t("monitoring.groupNotifyLabel")}</p>
            <p className="text-xs text-muted-foreground">
              {t("monitoring.groupNotifyHint")}
            </p>
          </div>
          <Switch checked={notifyGroupAlerts} onCheckedChange={setNotifyGroupAlerts} />
        </div>

        <div className="flex items-center justify-between rounded-lg border border-border/60 px-3 py-2.5">
          <div>
            <p className="text-sm font-medium">{t("monitoring.resourceNotifyLabel")}</p>
            <p className="text-xs text-muted-foreground">
              {t("monitoring.resourceNotifyHint")}
            </p>
          </div>
          <Switch
            checked={notifyResourceAlerts}
            onCheckedChange={setNotifyResourceAlerts}
          />
        </div>

        <div className="space-y-1.5">
          <label htmlFor="notif-webhook" className="text-sm font-medium">
            {t("monitoring.webhookLabel")}
          </label>
          <Input
            id="notif-webhook"
            value={webhookUrl}
            onChange={(e) => setWebhookUrl(e.target.value)}
            placeholder="https://oapi.dingtalk.com/robot/send?access_token=..."
            autoComplete="off"
          />
          <p className="text-xs text-muted-foreground">
            {t("monitoring.webhookHint")}
          </p>
        </div>

        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
          <div className="space-y-1.5">
            <label htmlFor="notif-keyword" className="text-sm font-medium">
              {t("monitoring.keywordLabel")}
            </label>
            <Input
              id="notif-keyword"
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
              placeholder={t("monitoring.keywordPlaceholder")}
              autoComplete="off"
            />
            <p className="text-xs text-muted-foreground">
              {t("monitoring.keywordHint")}
            </p>
          </div>
          <div className="space-y-1.5">
            <label htmlFor="notif-secret" className="text-sm font-medium">
              {t("monitoring.secretLabel")}
            </label>
            <Input
              id="notif-secret"
              type="password"
              value={signSecret}
              onChange={(e) => {
                setSignSecret(e.target.value);
                if (e.target.value) setClearSecret(false);
              }}
              placeholder={
                secretConfigured
                  ? t("monitoring.secretPlaceholderConfigured")
                  : t("monitoring.secretPlaceholderEmpty")
              }
              autoComplete="off"
              disabled={clearSecret}
            />
            {secretConfigured && (
              <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <input
                  type="checkbox"
                  checked={clearSecret}
                  onChange={(e) => setClearSecret(e.target.checked)}
                  className="size-3.5 accent-current"
                />
                {t("monitoring.clearSecret")}
              </label>
            )}
          </div>
        </div>

        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
          <div className="space-y-1.5">
            <label htmlFor="notif-timeout" className="text-sm font-medium">
              {t("monitoring.timeoutLabel")}
            </label>
            <Input
              id="notif-timeout"
              value={timeoutSeconds}
              onChange={(e) => setTimeoutSeconds(e.target.value)}
              inputMode="numeric"
              autoComplete="off"
            />
          </div>
          <div className="space-y-1.5">
            <label htmlFor="notif-silence" className="text-sm font-medium">
              {t("monitoring.silenceLabel")}
            </label>
            <Input
              id="notif-silence"
              value={silenceMinutes}
              onChange={(e) => setSilenceMinutes(e.target.value)}
              inputMode="numeric"
              autoComplete="off"
            />
            <p className="text-xs text-muted-foreground">
              {t("monitoring.silenceHint")}
            </p>
          </div>
        </div>

        <div className="flex items-center justify-between rounded-lg border border-border/60 px-3 py-2.5">
          <div>
            <p className="text-sm font-medium">{t("monitoring.resolvedLabel")}</p>
            <p className="text-xs text-muted-foreground">
              {t("monitoring.resolvedHint")}
            </p>
          </div>
          <Switch checked={notifyOnResolved} onCheckedChange={setNotifyOnResolved} />
        </div>

        <div className="flex flex-wrap items-center gap-2 pt-1">
          <Button onClick={save} disabled={saving || testing !== null}>
            {saving && <Loading size="sm" />}
            {saving ? t("monitoring.saving") : t("monitoring.saveConfig")}
          </Button>
          <Button
            variant="outline"
            onClick={() => sendTest("group")}
            disabled={saving || testing !== null}
          >
            {testing === "group" ? <Loading size="sm" /> : <Send className="size-4" />}
            {testing === "group"
              ? t("monitoring.testing")
              : t("monitoring.testGroupButton")}
          </Button>
          <Button
            variant="outline"
            onClick={() => sendTest("server")}
            disabled={saving || testing !== null}
          >
            {testing === "server" ? <Loading size="sm" /> : <Send className="size-4" />}
            {testing === "server"
              ? t("monitoring.testing")
              : t("monitoring.testServerButton")}
          </Button>
        </div>
      </div>
    </section>
  );
}
