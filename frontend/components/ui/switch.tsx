"use client";

import * as React from "react";

import { cn } from "@/lib/utils";

type SwitchProps = {
  /** 开关状态 */
  checked: boolean;
  /** 状态切换回调（内部不维护状态，由调用方控制） */
  onCheckedChange?: (checked: boolean) => void;
  disabled?: boolean;
  /** 开启时的文案，如 "启用" */
  checkedLabel?: string;
  /** 关闭时的文案，如 "禁用" */
  uncheckedLabel?: string;
  className?: string;
};

/**
 * 通用开关组件：绿色开 / 灰色关，带滑动动画，
 * 支持在滑块两侧显示状态文案（checkedLabel / uncheckedLabel）
 */
export function Switch({
  checked,
  onCheckedChange,
  disabled,
  checkedLabel,
  uncheckedLabel,
  className,
}: SwitchProps) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onCheckedChange?.(!checked)}
      className={cn(
        "relative inline-flex h-6 w-11 shrink-0 cursor-pointer items-center rounded-full transition-colors duration-300",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background",
        "disabled:cursor-not-allowed disabled:opacity-40",
        checked ? "bg-success" : "bg-muted-foreground/30",
        // 有文案时加宽并内嵌文字
        (checkedLabel || uncheckedLabel) && "h-6 w-16",
        className
      )}
    >
      {/* 状态文案：开启时文字在左，关闭时在右 */}
      {(checkedLabel || uncheckedLabel) && (
        <span
          className={cn(
            "absolute text-[10px] font-medium leading-none transition-colors",
            checked
              ? "left-2 text-white"
              : "right-2 text-muted-foreground"
          )}
        >
          {checked ? checkedLabel : uncheckedLabel}
        </span>
      )}
      <span
        className={cn(
          "inline-block size-4 transform rounded-full bg-white shadow transition-transform duration-300",
          checkedLabel || uncheckedLabel
            ? checked
              ? "translate-x-[42px]"
              : "translate-x-[3px]"
            : checked
              ? "translate-x-[26px]"
              : "translate-x-[3px]"
        )}
      />
    </button>
  );
}
