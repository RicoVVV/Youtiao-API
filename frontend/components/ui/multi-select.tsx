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
  className,
  id,
  ...rest
}: MultiSelectProps) {
  const [open, setOpen] = React.useState(false);
  const [placement, setPlacement] = React.useState<"top" | "bottom">("bottom");
  const rootRef = React.useRef<HTMLDivElement | null>(null);

  const selected = options.filter((o) => values.includes(o.value));

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

  return (
    <div ref={rootRef} data-slot="multi-select" className="relative">
      <button
        type="button"
        id={id}
        role="combobox"
        aria-expanded={open}
        aria-haspopup="listbox"
        aria-multiselectable="true"
        disabled={disabled}
        onClick={toggleOpen}
        className={cn(
          "border-input dark:bg-input/30 flex min-h-9 w-full items-center justify-between gap-2 rounded-md border bg-transparent px-3 py-1 text-sm shadow-xs transition-[color,box-shadow,border-color] outline-none cursor-pointer",
          "hover:border-ring/60 disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50",
          "focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px]",
          open && "border-ring ring-ring/50 ring-[3px]",
          className
        )}
        {...rest}
      >
        <span
          className={cn(
            "min-w-0 flex-1 flex flex-wrap items-center gap-1 text-left",
            selected.length === 0 && "text-muted-foreground"
          )}
        >
          {selected.length > 0
            ? selected.map((o) => (
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
              ))
            : placeholder}
        </span>
        <ChevronDown
          aria-hidden
          className={cn(
            "size-4 shrink-0 text-muted-foreground transition-transform duration-200",
            open && "rotate-180"
          )}
        />
      </button>

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
          ) : (
            options.map((opt) => {
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
