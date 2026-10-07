"use client";

import * as React from "react";
import { Calendar, ChevronLeft, ChevronRight } from "lucide-react";

import { cn } from "@/lib/utils";
import { Select } from "@/components/ui/select";

type DateTimePickerProps = {
  /** 值格式："YYYY-MM-DDTHH:mm"（与 datetime-local 一致） */
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  disabled?: boolean;
  id?: string;
  className?: string;
};

const WEEKDAYS = ["一", "二", "三", "四", "五", "六", "日"];
const HOUR_OPTIONS = Array.from({ length: 24 }, (_, i) => ({
  value: String(i).padStart(2, "0"),
  label: String(i).padStart(2, "0"),
}));
const MINUTE_OPTIONS = Array.from({ length: 60 }, (_, i) => ({
  value: String(i).padStart(2, "0"),
  label: String(i).padStart(2, "0"),
}));

const pad = (n: number) => String(n).padStart(2, "0");

/** Date 转 datetime-local 格式字符串 */
function formatValue(d: Date): string {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function parseValue(v: string): Date | null {
  if (!v) return null;
  const d = new Date(v);
  return Number.isNaN(d.getTime()) ? null : d;
}

function isSameDay(a: Date, b: Date): boolean {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  );
}

/**
 * 自研日期时间选择器：触发器与 Input 风格一致，整个输入框可点击唤起；
 * 弹出层使用项目卡片样式，替代原生 datetime-local 不可美化的面板。
 */
function DateTimePicker({
  value,
  onChange,
  placeholder = "请选择日期时间",
  disabled,
  id,
  className,
}: DateTimePickerProps) {
  const [open, setOpen] = React.useState(false);
  const [placement, setPlacement] = React.useState<"top" | "bottom">("bottom");
  const rootRef = React.useRef<HTMLDivElement | null>(null);

  const selected = parseValue(value);
  const now = new Date();

  // 面板当前展示的月份：优先跟随已选值，否则当前月
  const [viewYear, setViewYear] = React.useState(
    () => (selected ?? now).getFullYear()
  );
  const [viewMonth, setViewMonth] = React.useState(
    () => (selected ?? now).getMonth()
  );

  /** 打开时根据视口剩余空间决定面板向上还是向下展开 */
  const toggleOpen = () => {
    if (!open) {
      const rect = rootRef.current?.getBoundingClientRect();
      if (rect) {
        const panelH = 340;
        const spaceBelow = window.innerHeight - rect.bottom;
        const spaceAbove = rect.top;
        setPlacement(
          spaceBelow < panelH + 8 && spaceAbove > spaceBelow
            ? "top"
            : "bottom"
        );
        // 每次打开都回到已选值所在月份
        const base = parseValue(value) ?? new Date();
        setViewYear(base.getFullYear());
        setViewMonth(base.getMonth());
      }
    }
    setOpen((v) => !v);
  };

  React.useEffect(() => {
    if (!open) return;
    const onPointerDown = (e: PointerEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  const shiftMonth = (delta: number) => {
    const d = new Date(viewYear, viewMonth + delta, 1);
    setViewYear(d.getFullYear());
    setViewMonth(d.getMonth());
  };

  /** 选中某天：保留已选时间，无已选值时默认 00:00，选完保持面板打开以便调时间 */
  const pickDay = (day: Date) => {
    const base = selected ?? new Date(0, 0, 1, 0, 0);
    onChange(
      formatValue(
        new Date(
          day.getFullYear(),
          day.getMonth(),
          day.getDate(),
          base.getHours(),
          base.getMinutes()
        )
      )
    );
  };

  /** 修改时间：无已选日期时默认取今天 */
  const pickTime = (part: "hour" | "minute", v: string) => {
    const base = selected ?? new Date();
    const next = new Date(base);
    if (part === "hour") next.setHours(Number(v));
    else next.setMinutes(Number(v));
    onChange(formatValue(next));
  };

  // 生成 6x7 日历格子（周一开头，包含前后月补位天）
  const firstDay = new Date(viewYear, viewMonth, 1);
  const startOffset = (firstDay.getDay() + 6) % 7;
  const cells = Array.from({ length: 42 }, (_, i) => {
    const d = new Date(viewYear, viewMonth, 1 - startOffset + i);
    return d;
  });

  return (
    <div ref={rootRef} data-slot="datetime-picker" className="relative">
      <button
        type="button"
        id={id}
        disabled={disabled}
        aria-expanded={open}
        aria-haspopup="dialog"
        onClick={toggleOpen}
        className={cn(
          "border-input dark:bg-input/30 flex h-9 w-full items-center justify-between gap-2 rounded-md border bg-transparent px-3 py-1 text-sm whitespace-nowrap shadow-xs transition-[color,box-shadow,border-color] outline-none cursor-pointer",
          "hover:border-ring/60 disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50",
          "focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px]",
          open && "border-ring ring-ring/50 ring-[3px]",
          className
        )}
      >
        <span
          className={cn("min-w-0 truncate", !selected && "text-muted-foreground")}
        >
          {selected
            ? `${selected.getFullYear()}/${pad(selected.getMonth() + 1)}/${pad(selected.getDate())} ${pad(selected.getHours())}:${pad(selected.getMinutes())}`
            : placeholder}
        </span>
        <Calendar aria-hidden className="size-4 shrink-0 text-muted-foreground" />
      </button>

      {open && (
        <div
          role="dialog"
          aria-label="选择日期时间"
          className={cn(
            "border-border/60 bg-popover text-popover-foreground animate-in fade-in-0 zoom-in-95 absolute z-50 w-72 rounded-lg border p-3 shadow-lg",
            placement === "bottom" ? "top-full mt-1.5" : "bottom-full mb-1.5"
          )}
        >
          {/* 月份导航 */}
          <div className="flex items-center justify-between">
            <button
              type="button"
              onClick={() => shiftMonth(-1)}
              aria-label="上一月"
              className="rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
            >
              <ChevronLeft className="size-4" />
            </button>
            <p className="text-sm font-medium">
              {viewYear}年{viewMonth + 1}月
            </p>
            <button
              type="button"
              onClick={() => shiftMonth(1)}
              aria-label="下一月"
              className="rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
            >
              <ChevronRight className="size-4" />
            </button>
          </div>

          {/* 星期表头 */}
          <div className="mt-2 grid grid-cols-7 text-center text-xs text-muted-foreground">
            {WEEKDAYS.map((w) => (
              <span key={w} className="py-1">
                {w}
              </span>
            ))}
          </div>

          {/* 日期格子 */}
          <div className="grid grid-cols-7 gap-y-0.5">
            {cells.map((d) => {
              const inMonth = d.getMonth() === viewMonth;
              const isSelected = selected !== null && isSameDay(d, selected);
              const isToday = isSameDay(d, now);
              return (
                <button
                  key={d.getTime()}
                  type="button"
                  onClick={() => pickDay(d)}
                  aria-pressed={isSelected}
                  className={cn(
                    "mx-auto flex size-8 items-center justify-center rounded-md text-sm transition-colors outline-none",
                    "hover:bg-accent hover:text-accent-foreground focus-visible:bg-accent",
                    !inMonth && "text-muted-foreground/40",
                    isToday && !isSelected && "border border-primary/50 text-primary",
                    isSelected &&
                      "bg-primary text-primary-foreground font-medium hover:bg-primary hover:text-primary-foreground"
                  )}
                >
                  {d.getDate()}
                </button>
              );
            })}
          </div>

          {/* 时间选择 */}
          <div className="mt-2 flex items-center gap-2 border-t border-border/60 pt-3">
            <span className="shrink-0 text-xs text-muted-foreground">时间</span>
            <div className="w-20">
              <Select
                aria-label="小时"
                value={pad((selected ?? now).getHours())}
                onValueChange={(v) => pickTime("hour", v)}
                options={HOUR_OPTIONS}
              />
            </div>
            <span className="text-muted-foreground">:</span>
            <div className="w-20">
              <Select
                aria-label="分钟"
                value={pad((selected ?? now).getMinutes())}
                onValueChange={(v) => pickTime("minute", v)}
                options={MINUTE_OPTIONS}
              />
            </div>
          </div>

          {/* 快捷操作 */}
          <div className="mt-2 flex items-center justify-between border-t border-border/60 pt-2">
            <button
              type="button"
              onClick={() => {
                onChange("");
                setOpen(false);
              }}
              className="px-1 text-xs text-muted-foreground transition-colors hover:text-foreground"
            >
              清除
            </button>
            <button
              type="button"
              onClick={() => onChange(formatValue(new Date()))}
              className="px-1 text-xs text-primary transition-colors hover:underline"
            >
              此刻
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export { DateTimePicker };
