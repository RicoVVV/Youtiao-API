"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useTranslation } from "react-i18next";
import {
  CheckCircle2,
  Eye,
  EyeOff,
  Loader2,
  Lock,
  ShieldCheck,
  User,
} from "lucide-react";

import { SiteLogo } from "@/components/site-logo";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Loading } from "@/components/ui/loading";
import { toast } from "@/components/ui/toaster";
import { get, post, setToken, setCachedUsername } from "@/lib/request";
import { useLocale } from "@/i18n/client";

/** 与 SetupGuard 保持一致的响应解析 */
function needsSetup(data: unknown): boolean {
  if (!data || typeof data !== "object") return false;
  const d = data as Record<string, unknown>;
  if (typeof d.needs_setup === "boolean") return d.needs_setup;
  if (typeof d.setup_required === "boolean") return d.setup_required;
  if (typeof d.initialized === "boolean") return !d.initialized;
  if (typeof d.has_admin === "boolean") return !d.has_admin;
  return false;
}

/** 首次安装：创建管理员账号引导页 */
export function SetupPanel() {
  const router = useRouter();
  const locale = useLocale();
  const { t } = useTranslation("auth");

  const [checking, setChecking] = useState(true);
  const [allowed, setAllowed] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [status, setStatus] = useState<"idle" | "loading" | "success">("idle");
  const [error, setError] = useState("");

  // 已有管理员时无需初始化，直接去登录页
  useEffect(() => {
    let cancelled = false;
    get<unknown>("/auth/setup-status")
      .then((data) => {
        if (cancelled) return;
        if (needsSetup(data)) {
          setAllowed(true);
        } else {
          router.replace(`/${locale}/login`);
        }
      })
      .catch(() => {
        // 接口异常时允许停留在本页，由提交时的后端校验兜底
        if (!cancelled) setAllowed(true);
      })
      .finally(() => {
        if (!cancelled) setChecking(false);
      });
    return () => {
      cancelled = true;
    };
  }, [router, locale]);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");

    if (!username.trim()) {
      setError(t("requiredUsername"));
      return;
    }
    if (!password) {
      setError(t("setupRequiredPassword"));
      return;
    }
    if (password !== confirm) {
      setError(t("passwordMismatch"));
      return;
    }

    setStatus("loading");
    try {
      // 创建管理员成功后直接返回 access_token，保存并进入控制台
      const data = await post<{ access_token: string }>("/auth/setup-admin", {
        username: username.trim(),
        password,
      });
      setToken(data.access_token);
      // 缓存用户名：进入控制台后 HeaderAuth 可立即渲染头像
      setCachedUsername(username.trim());
      setStatus("success");
      toast.success(t("setupSuccess"));
      setTimeout(() => router.replace(`/${locale}/console`), 800);
    } catch (err) {
      setStatus("idle");
      setError(err instanceof Error ? err.message : t("networkError"));
    }
  };

  if (checking) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Loading size="lg" text={t("setupChecking")} />
      </div>
    );
  }
  if (!allowed) return null;

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden px-4 py-12">
      {/* 背景光斑（inset-0 裁剪，避免撑出滚动条） */}
      <div className="animate-float-a absolute left-0 top-0 size-96 -translate-x-1/3 -translate-y-1/4 rounded-full bg-[#4c6fff]/20 blur-3xl" />
      <div className="animate-float-b absolute bottom-0 right-0 size-[26rem] translate-x-1/3 rounded-full bg-[#129dc2]/20 blur-3xl" />

      <div className="animate-rise-in relative w-full max-w-sm">
        <div className="mb-8 text-center">
          <SiteLogo className="mx-auto mb-4 size-11" />
          <h1 className="text-2xl font-bold tracking-tight">{t("setupTitle")}</h1>
          <p className="mt-1.5 text-sm text-muted-foreground">
            {t("setupSubtitle")}
          </p>
        </div>

        <form onSubmit={onSubmit} className="space-y-4">
          <div className="relative">
            <User className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              type="text"
              placeholder={t("setupUsername")}
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="h-11 pl-9"
              autoComplete="username"
            />
          </div>
          <div className="relative">
            <Lock className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              type={showPassword ? "text" : "password"}
              placeholder={t("password")}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="h-11 pl-9 pr-10"
              autoComplete="new-password"
            />
            <button
              type="button"
              onClick={() => setShowPassword((v) => !v)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground transition-colors hover:text-foreground"
              aria-label={showPassword ? t("hidePassword") : t("showPassword")}
            >
              {showPassword ? <Eye className="size-4" /> : <EyeOff className="size-4" />}
            </button>
          </div>
          <div className="relative">
            <Lock className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              type={showPassword ? "text" : "password"}
              placeholder={t("confirmPassword")}
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              className="h-11 pl-9"
              autoComplete="new-password"
            />
          </div>

          {error && (
            <p key={error} className="animate-shake text-sm text-destructive">
              {error}
            </p>
          )}

          <Button
            type="submit"
            size="lg"
            disabled={status !== "idle"}
            className="h-11 w-full cursor-pointer"
          >
            {status === "loading" && (
              <>
                <Loader2 className="size-4 animate-spin" />
                {t("setupCreating")}
              </>
            )}
            {status === "success" && (
              <>
                <CheckCircle2 className="size-4 animate-scale-in" />
                {t("setupCreatedRedirect")}
              </>
            )}
            {status === "idle" && (
              <>
                <ShieldCheck className="size-4" />
                {t("setupSubmit")}
              </>
            )}
          </Button>
        </form>

        <p className="mt-6 text-center text-xs leading-relaxed text-muted-foreground">
          {t("setupFooter")}
        </p>
      </div>
    </div>
  );
}
