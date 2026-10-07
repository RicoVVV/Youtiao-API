"use client";

import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  ArrowLeft,
  CheckCircle2,
  Eye,
  EyeOff,
  Loader2,
  Lock,
  Mail,
  User,
} from "lucide-react";

import { SiteLogo } from "@/components/site-logo";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { post, setToken, getToken, setCachedUsername, ApiError } from "@/lib/request";
import { usePublicSystemSettings } from "@/lib/use-system-settings";
import { cn } from "@/lib/utils";
import { toast } from "../ui/toaster";
import { useLocale } from "@/i18n/client";
import { LocaleLink } from "@/components/locale-link";
import { useTranslation } from "react-i18next";

type Mode = "login" | "register";

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
/** 注册验证码同邮箱发送冷却（秒），与服务端限制一致 */
const RESEND_COOLDOWN = 60;

const floatingChips = [
  { label: "minimax-h3", className: "left-[12%] top-[18%]", delay: "0s", rotate: "-6deg" },
  { label: "gpt-5", className: "right-[10%] top-[30%]", delay: "0.8s", rotate: "4deg" },
  { label: "deepseek-v3.2", className: "left-[18%] bottom-[26%]", delay: "1.6s", rotate: "3deg" },
  { label: "sk-···", className: "right-[16%] bottom-[16%]", delay: "2.4s", rotate: "-4deg" },
];

/** 左侧品牌视觉面板 */
function BrandPanel() {
  const { t } = useTranslation("auth");
  return (
    <div className="relative hidden overflow-hidden bg-gradient-to-br from-[#4c6fff] via-[#5560f5] to-[#129dc2] lg:flex lg:flex-col lg:justify-between lg:p-12">
      {/* 漂浮光斑 */}
      <div className="animate-float-a absolute -left-24 top-[-10%] size-96 rounded-full bg-white/20 blur-3xl" />
      <div className="animate-float-b absolute bottom-[-15%] right-[-10%] size-[28rem] rounded-full bg-cyan-300/30 blur-3xl" />
      {/* 慢速旋转光环 */}
      <div className="animate-spin-slow absolute left-1/2 top-1/2 size-[36rem] -translate-x-1/2 -translate-y-1/2 rounded-full border border-dashed border-white/20" />
      {/* 网格 */}
      <div className="absolute inset-0 bg-[linear-gradient(to_right,rgb(255_255_255/8%)_1px,transparent_1px),linear-gradient(to_bottom,rgb(255_255_255/8%)_1px,transparent_1px)] bg-[size:48px_48px] [mask-image:radial-gradient(ellipse_70%_60%_at_50%_40%,black,transparent)]" />
      {/* 星星闪烁 */}
      {["left-[20%] top-[12%]", "right-[24%] top-[16%]", "left-[30%] top-[46%]", "right-[14%] top-[58%]", "left-[12%] top-[70%]", "right-[30%] bottom-[10%]"].map(
        (pos) => (
          <span
            key={pos}
            className={cn("animate-twinkle absolute size-1.5 rounded-full bg-white", pos)}
          />
        )
      )}
      {/* 漂浮模型徽章 */}
      {floatingChips.map((chip) => (
        <span
          key={chip.label}
          style={{ animationDelay: chip.delay, ["--chip-rotate" as string]: chip.rotate }}
          className={cn(
            "animate-float-chip absolute rounded-full border border-white/30 bg-white/10 px-3 py-1 font-mono text-xs text-white/90 backdrop-blur-sm",
            chip.className
          )}
        >
          {chip.label}
        </span>
      ))}

      {/* 内容 */}
      <LocaleLink href="/" className="relative flex items-center gap-2 font-semibold text-white">
        <SiteLogo className="size-8" />
        Youtiao API
      </LocaleLink>
      <div className="relative">
        <h2 className="text-3xl font-bold leading-snug text-white xl:text-4xl">
          {t("brandTitleLine1")}
          <br />
          {t("brandTitleLine2")}
        </h2>
        <p className="mt-4 max-w-sm text-sm leading-relaxed text-white/70">
          {t("brandDescription")}
        </p>
      </div>
      <p className="relative font-mono text-xs text-white/50">
        base_url = "https://api.youtiao.dev/v1"
      </p>
    </div>
  );
}

export function AuthPanel() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const locale = useLocale();
  const { t } = useTranslation("auth");
  const mode: Mode = searchParams.get("mode") === "register" ? "register" : "login";

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [email, setEmail] = useState("");
  const [emailCode, setEmailCode] = useState("");
  const [sendCodeStatus, setSendCodeStatus] = useState<"idle" | "sending">("idle");
  const [resendIn, setResendIn] = useState(0);
  const [showPassword, setShowPassword] = useState(false);
  const [status, setStatus] = useState<"idle" | "loading" | "success">("idle");
  const [error, setError] = useState("");

  // 公开系统设置：email_verification_enabled 决定注册是否展示邮箱与验证码
  const settings = usePublicSystemSettings();
  const emailVerificationEnabled = settings?.email_verification_enabled ?? false;

  // 登录成功后的目标页：仅允许站内路径，防开放重定向
  const redirectParam = searchParams.get("redirect");
  const redirectTo =
    redirectParam && redirectParam.startsWith("/") && !redirectParam.startsWith("//")
      ? redirectParam
      : `/${locale}/console`;

  // 已登录用户访问登录页时直接进入控制台
  // 仅在挂载时判断一次：登录成功后 setToken 会写入令牌，
  // 若持续监听会因 redirectTo 重建再次触发本 effect，抢先于成功页的延迟跳转，导致路由冲突卡住
  useEffect(() => {
    if (getToken()) {
      router.replace(redirectTo);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const switchMode = (next: Mode) => {
    setError("");
    // 切换登录/注册时清空邮箱验证相关状态，避免串用
    setEmail("");
    setEmailCode("");
    setResendIn(0);
    router.replace(next === "register" ? `/${locale}/login?mode=register` : `/${locale}/login`);
  };

  // 验证码重发倒计时
  useEffect(() => {
    if (resendIn <= 0) return;
    const timer = setTimeout(() => setResendIn((s) => s - 1), 1000);
    return () => clearTimeout(timer);
  }, [resendIn]);

  // 发送注册邮箱验证码（仅注册模式且开关开启时可用）
  const onSendEmailCode = async () => {
    setError("");
    const value = email.trim();
    if (!EMAIL_RE.test(value)) {
      setError(t("invalidEmail"));
      return;
    }
    setSendCodeStatus("sending");
    try {
      await post("/auth/email-verification-codes/send", { email: value });
      setResendIn(RESEND_COOLDOWN);
    } catch (err) {
      // 429 限流：按 Retry-After 进入倒计时，按钮保持禁用
      if (err instanceof ApiError && err.status === 429 && err.retryAfter) {
        setResendIn(err.retryAfter);
      }
      setError(err instanceof Error ? err.message : t("networkError"));
    } finally {
      setSendCodeStatus("idle");
    }
  };

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");

    if (!username.trim()) {
      setError(t("requiredUsername"));
      return;
    }
    if (mode === "register" && /\s/.test(username)) {
      setError(t("usernameNoSpaces"));
      return;
    }
    // 注册密码长度以后端契约为准（8–256）；登录仅做基础预校验
    const minPassword = mode === "register" ? 8 : 6;
    if (password.length < minPassword) {
      setError(t("passwordMinLength", { min: minPassword }));
      return;
    }
    if (mode === "register" && password !== confirm) {
      setError(t("passwordMismatch"));
      return;
    }
    if (mode === "register" && emailVerificationEnabled) {
      if (!EMAIL_RE.test(email.trim())) {
        setError(t("invalidEmail"));
        return;
      }
      // verification_code 固定 6 位数字，保留可能的前导零
      if (!/^\d{6}$/.test(emailCode.trim())) {
        setError(t("invalidEmailCode"));
        return;
      }
    }

    setStatus("loading");
    try {
      if (mode === "register") {
        // 注册（username 重复时后端返回 409，错误信息直接展示）
        await post("/auth/register", {
          username,
          password,
          // 开关开启时必填；关闭时不传（传了也会被后端忽略）
          ...(emailVerificationEnabled
            ? { email: email.trim(), verification_code: emailCode.trim() }
            : {}),
        });
      }
      // 登录（注册成功后自动登录），后端同时写入 HttpOnly 刷新 Cookie
      const data = await post<{ access_token: string }>("/auth/login", {
        username,
        password,
      });
      setToken(data.access_token);
      // 缓存用户名：跳转到控制台后 HeaderAuth 可立即渲染头像，无需等 /user/info
      setCachedUsername(username.trim());
      setStatus("success");
      // 硬跳转而非 router.push：页面长期停留后 Next 预取的 RSC 缓存可能已过期/被 404 污染，
      // 软导航会复用该缓存导致卡住不跳转；硬跳转强制整页加载，彻底规避
      setTimeout(() => {
        window.location.href = redirectTo;
      }, 800);
      toast.success(t("loginSuccess"));
    } catch (err) {
      setStatus("idle");
      setError(err instanceof Error ? err.message : t("networkError"));
    }
  };

  return (
    <div className="grid min-h-screen lg:grid-cols-2">
      <BrandPanel />

      {/* 右侧表单 */}
      <div className="relative flex items-center justify-center px-4 py-12 sm:px-8">
        <LocaleLink
          href="/"
          className="absolute left-6 top-6 flex items-center gap-1 text-sm text-muted-foreground transition-colors hover:text-foreground"
        >
          <ArrowLeft className="size-4" /> {t("backHome")}
        </LocaleLink>

        <div className="animate-rise-in w-full max-w-sm">
          <div className="mb-8 text-center">
            <SiteLogo className="mx-auto mb-4 size-11" />
            <h1 className="text-2xl font-bold tracking-tight">
              {mode === "login" ? t("welcomeBack") : t("createAccount")}
            </h1>
            <p className="mt-1.5 text-sm text-muted-foreground">
              {mode === "login" ? t("loginSubtitle") : t("registerSubtitle")}
            </p>
          </div>

          {/* 模式切换（滑动指示器） */}
          <div className="relative mb-6 grid grid-cols-2 rounded-full border bg-muted p-1 text-sm font-medium">
            <span
              className={cn(
                "absolute inset-y-1 left-1 w-[calc(50%-4px)] rounded-full bg-white shadow-sm transition-transform duration-300 ease-[cubic-bezier(.22,.61,.36,1)] dark:bg-slate-200",
                mode === "register" && "translate-x-full"
              )}
            />
            {(["login", "register"] as const).map((m) => (
              <button
                key={m}
                type="button"
                onClick={() => switchMode(m)}
                className={cn(
                  "relative z-10 cursor-pointer rounded-full py-2 transition-colors duration-300",
                  mode === m
                    ? "text-foreground dark:text-slate-900"
                    : "text-muted-foreground hover:text-foreground"
                )}
              >
                {m === "login" ? t("login") : t("register")}
              </button>
            ))}
          </div>

          {/* 表单（切换模式时重播入场动画） */}
          <form key={mode} onSubmit={onSubmit} className="animate-rise-in space-y-4">
            <div className="relative">
              <User className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                type="text"
                placeholder={t("username")}
                value={username}
                onChange={(e) => {
                  const value = e.target.value;
                  if (mode === "register") {
                    // 注册时用户名不允许包含空格：输入空格时提示并过滤
                    if (/\s/.test(value)) {
                      setError(t("usernameNoSpaces"));
                      setUsername(value.replace(/\s/g, ""));
                      return;
                    }
                    if (error === t("usernameNoSpaces")) setError("");
                  }
                  setUsername(value);
                }}
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
                autoComplete={mode === "login" ? "current-password" : "new-password"}
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
            {mode === "register" && (
              <div className="animate-rise-in relative">
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
            )}
            {/* 注册邮箱验证：开关开启时邮箱与验证码必填 */}
            {mode === "register" && emailVerificationEnabled && (
              <>
                <div className="animate-rise-in relative">
                  <Mail className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    type="email"
                    inputMode="email"
                    placeholder={t("email")}
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    className="h-11 pl-9"
                    autoComplete="email"
                  />
                </div>
                <div className="animate-rise-in flex gap-2">
                  <Input
                    inputMode="numeric"
                    maxLength={6}
                    placeholder={t("emailCodePlaceholder")}
                    value={emailCode}
                    onChange={(e) => setEmailCode(e.target.value.replace(/\D/g, ""))}
                    className="h-11 flex-1"
                    autoComplete="one-time-code"
                  />
                  <Button
                    type="button"
                    variant="outline"
                    onClick={onSendEmailCode}
                    disabled={resendIn > 0 || sendCodeStatus === "sending"}
                    className="h-11 shrink-0"
                  >
                    {sendCodeStatus === "sending" && (
                      <Loader2 className="size-4 animate-spin" />
                    )}
                    {resendIn > 0
                      ? t("resendAfter", { seconds: resendIn })
                      : t("sendCode")}
                  </Button>
                </div>
              </>
            )}

            {error && (
              <p key={error} className="animate-shake text-sm text-destructive">
                {error}
              </p>
            )}

            <Button
              type="submit"
              size="lg"
              disabled={status !== "idle"}
              className={cn(
                "h-11 w-full cursor-pointer transition-all",
                status === "success" && "[background-image:none] bg-success"
              )}
            >
              {status === "loading" && (
                <>
                  <Loader2 className="size-4 animate-spin" />
                  {mode === "login" ? t("loggingIn") : t("registering")}
                  {/* 跳动的省略点 */}
                  <span className="flex items-end gap-0.5 pb-0.5" aria-hidden>
                    {[0, 1, 2].map((i) => (
                      <span
                        key={i}
                        style={{ animationDelay: `${i * 150}ms` }}
                        className="size-1 animate-bounce rounded-full bg-current"
                      />
                    ))}
                  </span>
                </>
              )}
              {status === "success" && (
                <>
                  <CheckCircle2 className="size-4 animate-scale-in" />
                  <span>{t("successRedirect")}</span>
                  {/* 跳动的省略点 */}
                  <span className="flex items-end gap-0.5 pb-0.5" aria-hidden>
                    {[0, 1, 2].map((i) => (
                      <span
                        key={i}
                        style={{ animationDelay: `${i * 150}ms` }}
                        className="size-1 animate-bounce rounded-full bg-current"
                      />
                    ))}
                  </span>
                </>
              )}
              {status === "idle" &&
                (mode === "login" ? t("login") : t("registerAndEnter"))}
            </Button>
          </form>

          <p className="mt-6 text-center text-xs leading-relaxed text-muted-foreground">
            {t("terms")}
          </p>
        </div>
      </div>
    </div>
  );
}
