"use client";

import * as React from "react";
import { Check, ChevronDown, X } from "lucide-react";

import { cn } from "@/lib/utils";

export type MultiSelectOption = {
  value: string;
  label: React.ReactNode;
};

type MultiSelectProps = {
  /** 当前选中的值集合 */
  values: string[];
  onValuesChange: (values: string[]) => void;
  options: MultiSelectOption[];
  placeholder?: string;
  /** 选项为空时面板内的提示文案 */
  emptyText?: string;
  disabled?: boolean;
  /** 开启后可直接在触发框内输入搜索，按选项 label/value 过滤 */
  searchable?: boolean;
  /** 展开时输入框的占位文案 */
  searchPlaceholder?: string;
  /** 搜索无结果时的提示文案，缺省回退 emptyText */
  noResultText?: string;
  className?: string;
  "aria-label"?: string;
  id?: string;
};

/**
 * 自研多选下拉：触发器与 Select 风格一致，面板内以勾选列表呈现，
 * 用于模型、令牌分组等多值选择场景。
 */
function MultiSelect({
  values,
  onValuesChange,
  options,
  placeholder = "请选择",
  emptyText = "暂无可选项",
  disabled,
  searchable = false,
  searchPlaceholder = "搜索",
  noResultText,
  className,
  id,
  ...rest
}: MultiSelectProps) {
  const [open, setOpen] = React.useState(false);
  const [placement, setPlacement] = React.useState<"top" | "bottom">("bottom");
  const [query, setQuery] = React.useState("");
  const rootRef = React.useRef<HTMLDivElement | null>(null);
  const inputRef = React.useRef<HTMLInputElement | null>(null);

  const selected = options.filter((o) => values.includes(o.value));

  /** 搜索过滤：匹配 label（ReactNode 取字符串）与 value */
  const q = query.trim().toLowerCase();
  const filteredOptions = q
    ? options.filter((o) => {
        const label =
          typeof o.label === "string" ? o.label : String(o.label ?? "");
        return (
          label.toLowerCase().includes(q) || o.value.toLowerCase().includes(q)
        );
      })
    : options;

  /** 打开时根据视口剩余空间决定面板向上还是向下展开 */
  const toggleOpen = () => {
    if (!open) {
      const rect = rootRef.current?.getBoundingClientRect();
      if (rect) {
        const panelH = Math.min(Math.max(options.length, 2) * 36 + 10, 240);
        const spaceBelow = window.innerHeight - rect.bottom;
        const spaceAbove = rect.top;
        setPlacement(
          spaceBelow < panelH + 8 && spaceAbove > spaceBelow
            ? "top"
            : "bottom"
        );
      }
    }
    setOpen((v) => !v);
  };

  /** 展开时聚焦内嵌输入框，收起时清空搜索词 */
  React.useEffect(() => {
    if (open && searchable) inputRef.current?.focus();
    if (!open) setQuery("");
  }, [open, searchable]);

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

  const toggleValue = (value: string) => {
    if (values.includes(value)) {
      onValuesChange(values.filter((v) => v !== value));
    } else {
      onValuesChange([...values, value]);
    }
  };

  const chips = selected.map((o) => (
    <span
      key={o.value}
      className="inline-flex items-center gap-0.5 rounded-md bg-primary/10 px-1.5 py-0.5 text-xs font-medium text-primary"
    >
      {o.label}
      <span
        role="button"
        aria-label={`移除 ${o.label}`}
        onClick={(e) => {
          e.stopPropagation();
          toggleValue(o.value);
        }}
        className="rounded-sm p-0.5 transition-colors hover:bg-primary/20 cursor-pointer"
      >
        <X className="size-3" />
      </span>
    </span>
  ));

  const chevron = (
    <ChevronDown
      aria-hidden
      className={cn(
        "size-4 shrink-0 text-muted-foreground transition-transform duration-200",
        open && "rotate-180"
      )}
    />
  );

  const triggerClass = cn(
    "border-input dark:bg-input/30 flex min-h-9 w-full items-center justify-between gap-2 rounded-md border bg-transparent px-3 py-1 text-sm shadow-xs transition-[color,box-shadow,border-color] outline-none cursor-pointer",
    "hover:border-ring/60 disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50",
    "focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px]",
    open && "border-ring ring-ring/50 ring-[3px]",
    className
  );

  return (
    <div ref={rootRef} data-slot="multi-select" className="relative">
      {searchable ? (
        /* 可搜索模式：触发框内联输入框，输入即过滤 */
        <div
          id={id}
          role="combobox"
          aria-expanded={open}
          aria-haspopup="listbox"
          aria-multiselectable="true"
          aria-disabled={disabled || undefined}
          onClick={() => {
            if (disabled) return;
            if (!open) toggleOpen();
            inputRef.current?.focus();
          }}
          className={cn(
            triggerClass,
            disabled && "pointer-events-none cursor-not-allowed opacity-50"
          )}
          {...rest}
        >
          <span
            className={cn(
              "min-w-0 flex-1 flex flex-wrap items-center gap-1 text-left",
              !open && selected.length === 0 && "text-muted-foreground"
            )}
          >
            {chips}
            <input
              ref={inputRef}
              type="text"
              value={open ? query : ""}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={
                open
                  ? searchPlaceholder
                  : selected.length === 0
                    ? placeholder
                    : ""
              }
              readOnly={!open}
              tabIndex={disabled ? -1 : 0}
              onFocus={() => {
                if (!disabled && !open) toggleOpen();
              }}
              onKeyDown={(e) => {
                // 阻止回车冒泡到外层表单触发提交
                if (e.key === "Enter") e.preventDefault();
              }}
              className="min-w-0 flex-1 basis-20 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
            />
          </span>
          {chevron}
        </div>
      ) : (
        <button
          type="button"
          id={id}
          role="combobox"
          aria-expanded={open}
          aria-haspopup="listbox"
          aria-multiselectable="true"
          disabled={disabled}
          onClick={toggleOpen}
          className={triggerClass}
          {...rest}
        >
          <span
            className={cn(
              "min-w-0 flex-1 flex flex-wrap items-center gap-1 text-left",
              selected.length === 0 && "text-muted-foreground"
            )}
          >
            {selected.length > 0 ? chips : placeholder}
          </span>
          {chevron}
        </button>
      )}

      {open && (
        <div
          role="listbox"
          aria-multiselectable="true"
          className={cn(
            "border-border/60 bg-popover text-popover-foreground animate-in fade-in-0 zoom-in-95 absolute z-50 min-w-full overflow-y-auto overflow-x-hidden rounded-lg border p-1 shadow-lg",
            placement === "bottom"
              ? "top-full mt-1.5"
              : "bottom-full mb-1.5"
          )}
          style={{ maxHeight: "15rem" }}
        >
          {options.length === 0 ? (
            <div className="flex flex-col items-center gap-1 px-2.5 py-6 text-center">
              <p className="text-sm text-muted-foreground">{emptyText}</p>
            </div>
          ) : filteredOptions.length === 0 ? (
            <div className="flex flex-col items-center gap-1 px-2.5 py-6 text-center">
              <p className="text-sm text-muted-foreground">
                {noResultText ?? emptyText}
              </p>
            </div>
          ) : (
            filteredOptions.map((opt) => {
              const checked = values.includes(opt.value);
              return (
                <button
                  key={opt.value}
                  type="button"
                  role="option"
                  aria-selected={checked}
                  onClick={() => toggleValue(opt.value)}
                  className={cn(
                    "flex w-full items-center justify-between gap-2 rounded-md px-2.5 py-1.5 text-left text-sm whitespace-nowrap transition-colors outline-none cursor-pointer",
                    "hover:bg-accent hover:text-accent-foreground focus-visible:bg-accent focus-visible:text-accent-foreground",
                    checked && "text-primary font-medium"
                  )}
                >
                  <span className="min-w-0 truncate">{opt.label}</span>
                  {checked && (
                    <Check className="size-4 shrink-0 text-primary" />
                  )}
                </button>
              );
            })
          )}
        </div>
      )}
    </div>
  );
}

export { MultiSelect };
