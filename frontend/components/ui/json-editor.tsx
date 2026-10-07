"use client";

import * as React from "react";
import {
  Braces,
  Check,
  CircleAlert,
  CircleCheck,
  CodeXml,
  Copy,
} from "lucide-react";

import { toast } from "@/components/ui/toaster";
import { cn } from "@/lib/utils";
import { useTranslation } from "react-i18next";

type JsonEditorProps = {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  /** 可视行数，决定编辑区高度（默认 14 行） */
  rows?: number;
  className?: string;
  "aria-label"?: string;
  id?: string;
};

/** 行高与垂直内边距须与 textarea 保持一致，行号才能逐行对齐 */
const LINE_HEIGHT = 20; // leading-5
const PADDING_Y = 16; // py-2 上下合计

/** 由光标位置（selectionStart）推算 行:列（均从 1 开始） */
function cursorLineCol(value: string, pos: number): { line: number; col: number } {
  const before = value.slice(0, pos);
  const line = before.split("\n").length;
  const col = pos - before.lastIndexOf("\n");
  return { line, col };
}

/**
 * 智能 JSON 编辑器：工具栏（格式标识 / 光标行列 / 合法性校验 / 复制 / 格式化）
 * + 行号槽 + 等宽编辑区；Tab 键插入两个空格。
 */
function JsonEditor({
  value,
  onChange,
  placeholder,
  rows = 14,
  className,
  ...rest
}: JsonEditorProps) {
  const { t } = useTranslation("common");
  const textareaRef = React.useRef<HTMLTextAreaElement | null>(null);
  const gutterRef = React.useRef<HTMLDivElement | null>(null);
  const [cursor, setCursor] = React.useState({ line: 1, col: 1 });
  const [copied, setCopied] = React.useState(false);

  const lineCount = Math.max(1, value.split("\n").length);
  const height = rows * LINE_HEIGHT + PADDING_Y;

  /** 合法性：空内容不提示，合法显绿、非法显红 */
  const trimmed = value.trim();
  let validity: "empty" | "valid" | "invalid" = "empty";
  if (trimmed) {
    try {
      JSON.parse(trimmed);
      validity = "valid";
    } catch {
      validity = "invalid";
    }
  }

  const syncCursor = () => {
    const ta = textareaRef.current;
    if (!ta) return;
    setCursor(cursorLineCol(value, ta.selectionStart ?? 0));
  };

  /** 编辑区滚动时同步行号槽位置 */
  const syncScroll = (e: React.UIEvent<HTMLTextAreaElement>) => {
    if (gutterRef.current) {
      gutterRef.current.scrollTop = e.currentTarget.scrollTop;
    }
  };

  /** Tab 插入两个空格并保持光标位置 */
  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key !== "Tab") return;
    e.preventDefault();
    const ta = e.currentTarget;
    const { selectionStart: s, selectionEnd: end } = ta;
    onChange(value.slice(0, s) + "  " + value.slice(end));
    requestAnimationFrame(() => {
      ta.selectionStart = ta.selectionEnd = s + 2;
    });
  };

  const copyValue = async () => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      setTimeout(() => setCopied(false), 1200);
    } catch {
      toast.error(t("jsonEditor.copyFailed"));
    }
  };

  const formatValue = () => {
    try {
      onChange(JSON.stringify(JSON.parse(trimmed), null, 2));
    } catch {
      toast.error(t("jsonEditor.formatFailed"));
    }
  };

  const toolButtonClass =
    "inline-flex cursor-pointer items-center gap-1 rounded px-1.5 py-0.5 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground";

  return (
    <div
      data-slot="json-editor"
      className={cn(
        "border-input dark:bg-input/30 overflow-hidden rounded-md border bg-transparent shadow-xs transition-[color,box-shadow,border-color]",
        "focus-within:border-ring focus-within:ring-ring/50 focus-within:ring-[3px]",
        className
      )}
    >
      {/* 工具栏 */}
      <div className="flex items-center justify-between gap-2 border-b border-border/60 bg-muted/30 px-3 py-1.5">
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <Braces className="size-3.5" />
          <span className="font-medium">JSON</span>
          <span className="tabular-nums">
            {cursor.line}:{cursor.col}
          </span>
        </div>
        <div className="flex items-center gap-1.5">
          {validity === "valid" && (
            <span className="inline-flex items-center gap-1 text-xs text-emerald-600 dark:text-emerald-400">
              <CircleCheck className="size-3.5" />
              JSON
            </span>
          )}
          {validity === "invalid" && (
            <span className="inline-flex items-center gap-1 text-xs text-destructive">
              <CircleAlert className="size-3.5" />
              {t("jsonEditor.invalid")}
            </span>
          )}
          <button
            type="button"
            onClick={copyValue}
            className={toolButtonClass}
            aria-label={t("jsonEditor.copyAria")}
          >
            {copied ? (
              <Check className="size-3.5 text-success" />
            ) : (
              <Copy className="size-3.5" />
            )}
            {t("jsonEditor.copy")}
          </button>
          <button
            type="button"
            onClick={formatValue}
            className={toolButtonClass}
            aria-label={t("jsonEditor.format")}
          >
            <CodeXml className="size-3.5" />
            {t("jsonEditor.format")}
          </button>
        </div>
      </div>

      {/* 行号 + 编辑区 */}
      <div className="flex" style={{ height }}>
        <div
          ref={gutterRef}
          aria-hidden
          className="shrink-0 select-none overflow-hidden border-r border-border/40 bg-muted/20 py-2 pr-2 pl-3 text-right font-mono text-xs leading-5 text-muted-foreground/50"
        >
          {Array.from({ length: lineCount }, (_, i) => (
            <div key={i}>{i + 1}</div>
          ))}
        </div>
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => {
            onChange(e.target.value);
            syncCursor();
          }}
          onScroll={syncScroll}
          onSelect={syncCursor}
          onKeyDown={onKeyDown}
          placeholder={placeholder}
          wrap="off"
          spellCheck={false}
          autoCapitalize="off"
          autoCorrect="off"
          className="min-w-0 flex-1 resize-none overflow-auto bg-transparent py-2 pr-3 pl-3 font-mono text-xs leading-5 whitespace-pre text-foreground outline-none placeholder:text-muted-foreground/60"
          {...rest}
        />
      </div>
    </div>
  );
}

export { JsonEditor };
