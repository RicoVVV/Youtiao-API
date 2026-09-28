"use client";

import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { ShieldAlert } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

/** 拆分为「用户需输入」和「固定标点」交替的段落 */
function buildSegments(text: string): Array<{ type: "input"; expected: string } | { type: "literal"; value: string }> {
  const segments: Array<{ type: "input"; expected: string } | { type: "literal"; value: string }> = [];

  // 按用户需要手动输入的部分拆分，标点作为 literal
  const splitPattern = /([，、])/;
  const rawSegments = text.split(splitPattern);

  for (const seg of rawSegments) {
    if (!seg) continue;
    if (/^[，、]$/.test(seg)) {
      // 纯标点 → literal
      segments.push({ type: "literal", value: seg });
    } else {
      // 需要用户输入的部分 —— 再按 "，并" 这种组合标点拆开
      // "确认相关法律风险，并确认承担因部署"
      const innerSplit = seg.split(/(，并)/);
      for (const inner of innerSplit) {
        if (!inner) continue;
        if (/^，并$/.test(inner)) {
          segments.push({ type: "literal", value: inner });
        } else {
          segments.push({ type: "input", expected: inner });
        }
      }
    }
  }

  return segments;
}

/** 当前语言（zh/en） */
function useLang(): "zh" | "en" {
  const { i18n } = useTranslation();
  return i18n.language === "zh" ? "zh" : "en";
}

/** 合规条款（按语言） */
function useComplianceTerms(): string[] {
  const lang = useLang();
  return useMemo(
    () =>
      lang === "zh"
        ? [
            "你已合法取得所连接模型 API、账户、密钥和额度的授权。",
            "你承诺仅在从上游服务提供商、模型服务提供商或相关权利人处获得合法授权的范围内使用上游 API、账户、密钥、额度和服务能力，并不会进行未经授权的转售、倒卖、分发或其他不合规商业化行为。",
            "如果你在中国大陆向公众提供生成式人工智能服务，你将履行备案、安全评估、内容安全、投诉处理、生成内容标识、日志留存和个人信息保护等法律义务。",
            "你承诺不会使用本系统实施、协助实施或间接实施违反适用法律法规、监管要求、平台规则、公共利益或第三方合法权益的行为。",
            "你理解并独立承担因部署、运营和收费行为产生的法律责任。",
            "你理解此合规提醒仅用于风险提示，不构成法律意见、合规审查结论或对你使用本系统合法性的保证；你应结合实际业务场景咨询专业法律或合规顾问。",
          ]
        : [
            "You have legally obtained authorization for the connected model APIs, accounts, keys, and quotas.",
            "You promise to only use upstream APIs, accounts, keys, quotas, and service capabilities within the scope of legal authorization obtained from upstream service providers, model service providers, or relevant rights holders, and will not engage in unauthorized resale, trafficking, distribution, or other non-compliant commercialization activities.",
            "If you provide generative artificial intelligence services to the public in mainland China, you will fulfill legal obligations such as filing, security assessment, content safety, complaint handling, generated content labeling, log retention, and personal information protection.",
            "You promise not to use this system to implement, assist in implementing, or indirectly implement actions that violate applicable laws and regulations, regulatory requirements, platform rules, public interests, or the legitimate rights and interests of third parties.",
            "You understand and independently assume the legal responsibilities arising from deployment, operation, and charging activities.",
            "You understand that this compliance reminder is only for risk warning and does not constitute legal advice, compliance review conclusions, or a guarantee of the legality of your use of this system; you should consult professional legal or compliance advisors based on your actual business scenario.",
          ],
    [lang]
  );
}

/** 确认文本（按语言） */
function useConfirmFullText(): string {
  const lang = useLang();
  return lang === "zh"
    ? "我已阅读并理解上述合规提醒，确认相关法律风险，并确认承担因部署、运营和收费行为产生的法律责任"
    : "I have read and understood the above compliance reminders, confirm the relevant legal risks, and confirm that I will bear the legal responsibilities arising from deployment, operation, and charging activities";
}

/** 拆分后的段落（按语言） */
function useSegments() {
  const text = useConfirmFullText();
  return useMemo(() => buildSegments(text), [text]);
}

/* ── Banner 组件 ── */
export function ComplianceBanner({ onOpen }: { onOpen: () => void }) {
  const { t } = useTranslation("console");
  const terms = useComplianceTerms();
  return (
    <div className="rounded-xl border-2 border-red-200 bg-red-50/60 p-5">
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1">
          <div className="mb-2 flex items-center gap-2 text-red-600">
            <ShieldAlert className="size-5 shrink-0" />
            <span className="text-base font-semibold">{t("paymentGateway.compliance.bannerTitle")}</span>
          </div>
          <p className="mb-3 text-sm text-red-600/80">
            {t("paymentGateway.compliance.bannerDesc")}
          </p>
          <ol className="list-inside list-decimal space-y-1.5 text-sm text-red-600/90">
            {terms.map((term, i) => (
              <li key={i}>{term}</li>
            ))}
          </ol>
        </div>
        <Button
          variant="outline"
          className="shrink-0 border-red-200 text-red-600 hover:bg-red-100 hover:text-red-700"
          onClick={onOpen}
        >
          {t("paymentGateway.compliance.bannerButton")}
        </Button>
      </div>
    </div>
  );
}

/* ── 弹框组件 ── */
export function ComplianceModal({
  open,
  onClose,
  onConfirm,
  submitting,
}: {
  open: boolean;
  onClose: () => void;
  onConfirm: () => Promise<void>;
  submitting: boolean;
}) {
  const { t } = useTranslation("console");
  const terms = useComplianceTerms();
  const confirmText = useConfirmFullText();
  const segments = useSegments();
  const [values, setValues] = useState<string[]>(() =>
    segments.map((s) => (s.type === "input" ? "" : s.value))
  );
  const [errors, setErrors] = useState<boolean[]>(() =>
    segments.map(() => false)
  );

  /* 语言变化时重置输入 */
  useEffect(() => {
    setValues(segments.map((s) => (s.type === "input" ? "" : s.value)));
    setErrors(segments.map(() => false));
  }, [segments]);

  const inputSegments = useMemo(
    () => segments.map((s, i) => ({ ...s, index: i })).filter((s) => s.type === "input"),
    [segments]
  );

  const allCorrect = useMemo(() => {
    return inputSegments.every(
      (s) => values[s.index] === s.expected
    );
  }, [values, inputSegments]);

  if (!open) return null;

  const handleChange = (index: number, value: string) => {
    setValues((prev) => {
      const next = [...prev];
      next[index] = value;
      return next;
    });
    setErrors((prev) => {
      const next = [...prev];
      next[index] = false;
      return next;
    });
  };

  const handleConfirm = () => {
    const newErrors = segments.map((s, i) =>
      s.type === "input" && values[i] !== s.expected
    );
    setErrors(newErrors);

    if (newErrors.some(Boolean)) return;

    onConfirm();
  };

  const handleBackdropClick = (e: React.MouseEvent) => {
    if (e.target === e.currentTarget) onClose();
  };

  return (
    <div
      className="fixed inset-0 z-200 flex items-center justify-center"
      onClick={handleBackdropClick}
    >
      <div className="absolute inset-0 bg-black/40" />
      <div className="relative z-10 flex max-h-[90vh] w-full max-w-2xl flex-col rounded-xl border bg-background shadow-xl">
        {/* Header */}
        <div className="shrink-0 px-6 pt-6 pb-2">
          <h2 className="text-lg font-semibold">{t("paymentGateway.compliance.modalTitle")}</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            {t("paymentGateway.compliance.modalDesc")}
          </p>
        </div>

        {/* Scrollable body */}
        <div className="min-h-0 flex-1 overflow-y-auto px-6 py-4">
          {/* 条款列表 */}
          <div className="max-h-52 overflow-y-auto rounded-lg border bg-muted/30 p-4">
            <ol className="list-inside list-decimal space-y-2 text-sm text-foreground/90">
              {terms.map((term, i) => (
                <li key={i} className="leading-relaxed">
                  {term}
                </li>
              ))}
            </ol>
          </div>

          {/* 确认输入区域 */}
          <div className="mt-4 rounded-lg border-2 border-red-200 bg-red-50/60 p-4">
            <p className="mb-3 text-sm font-semibold text-foreground">
              {t("paymentGateway.compliance.inputPrompt")}
            </p>

            {/* 完整参考文本 */}
            <div className="mb-4 rounded-md border bg-background p-3 text-sm text-foreground/80">
              {confirmText}
            </div>

            {/* 逐段输入 */}
            <div className="flex flex-wrap items-center gap-2">
              {segments.map((seg, i) => {
                if (seg.type === "literal") {
                  return (
                    <span
                      key={i}
                      className="flex size-8 items-center justify-center rounded-md border bg-background text-sm text-muted-foreground"
                    >
                      {seg.value}
                    </span>
                  );
                }
                return (
                  <div key={i} className="w-full">
                    <Input
                      value={values[i]}
                      onChange={(e) => handleChange(i, e.target.value)}
                      placeholder={seg.expected}
                      className={cn(
                        "text-sm",
                        errors[i] && "border-red-400 focus-visible:ring-red-400"
                      )}
                    />
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="shrink-0 flex justify-end gap-3 border-t px-6 py-4">
          <Button variant="outline" onClick={onClose}>
            {t("paymentGateway.compliance.cancel")}
          </Button>
          <Button
            disabled={!allCorrect || submitting}
            onClick={handleConfirm}
          >
            {submitting ? t("paymentGateway.compliance.confirming") : t("paymentGateway.compliance.confirmEnable")}
          </Button>
        </div>
      </div>
    </div>
  );
}
