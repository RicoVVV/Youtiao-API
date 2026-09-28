"use client";

import * as React from "react";
import { Check, ChevronDown } from "lucide-react";

import { cn } from "@/lib/utils";

export type SelectOption = {
  value: string;
  label: React.ReactNode;
};

type SelectProps = {
  value: string;
  onValueChange: (value: string) => void;
  options: SelectOption[];
  placeholder?: string;
  /** 选项为空时面板内的提示文案 */
  emptyText?: string;
  disabled?: boolean;
  className?: string;
  /** 自定义触发器：传入则替换默认按钮内容（保留 combobox 行为与弹出逻辑） */
  trigger?: (state: { open: boolean; selected?: SelectOption }) => React.ReactNode;
  "aria-label"?: string;
  id?: string;
};

/**
 * 自研下拉选择器：触发器与 Input 风格一致，弹出层使用项目卡片样式，
 * 规避原生 <select> 下拉列表不可美化的问题。
 */
function Select({
  value,
  onValueChange,
  options,
  placeholder = "请选择",
  emptyText = "暂无可选项",
  disabled,
  className,
  trigger,
  id,
  ...rest
}: SelectProps) {
  const [open, setOpen] = React.useState(false);
  const [placement, setPlacement] = React.useState<"top" | "bottom">("bottom");
  const rootRef = React.useRef<HTMLDivElement | null>(null);

  const selected = options.find((o) => o.value === value);

  /** 打开时根据视口剩余空间决定面板向上还是向下展开 */
  const toggleOpen = () => {
    if (!open) {
      const rect = rootRef.current?.getBoundingClientRect();
      if (rect) {
        // 面板预估高度（选项数 * 项高 + 内边距，上限 15rem；空态按 2 行估算）
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

  return (
    <div ref={rootRef} data-slot="select" className="relative">
      <button
        type="button"
        id={id}
        role="combobox"
        aria-expanded={open}
        aria-haspopup="listbox"
        disabled={disabled}
        onClick={toggleOpen}
        className={cn(
          "flex h-9 items-center rounded-md text-sm whitespace-nowrap outline-none cursor-pointer transition-[color,box-shadow,border-color]",
          trigger
            ? "justify-center"
            : "border-input dark:bg-input/30 w-full justify-between gap-2 border bg-transparent px-3 py-1 shadow-xs hover:border-ring/60",
          "disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50",
          "focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px]",
          open && "border-ring ring-ring/50 ring-[3px]",
          className
        )}
        {...rest}
      >
        {trigger ? (
          trigger({ open, selected })
        ) : (
          <>
            <span
              className={cn(
                "min-w-0 truncate",
                !selected && "text-muted-foreground"
              )}
            >
              {selected ? selected.label : placeholder}
            </span>
            <ChevronDown
              aria-hidden
              className={cn(
                "size-4 shrink-0 text-muted-foreground transition-transform duration-200",
                open && "rotate-180"
              )}
            />
          </>
        )}
      </button>

      {open && (
        <div
          role="listbox"
          className={cn(
            "border-border/60 bg-popover text-popover-foreground animate-in fade-in-0 zoom-in-95 absolute z-50 min-w-full overflow-y-auto overflow-x-hidden rounded-lg border p-1 shadow-lg",
            trigger && "min-w-44 w-max",
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
              const active = opt.value === value;
              return (
                <button
                  key={opt.value}
                  type="button"
                  role="option"
                  aria-selected={active}
                  onClick={() => {
                    onValueChange(opt.value);
                    setOpen(false);
                  }}
                  className={cn(
                    "flex w-full items-center justify-between gap-2 rounded-md px-2.5 py-1.5 text-left text-sm whitespace-nowrap transition-colors outline-none cursor-pointer",
                    "hover:bg-accent hover:text-accent-foreground focus-visible:bg-accent focus-visible:text-accent-foreground",
                    active && "text-primary font-medium"
                  )}
                >
                  <span className="min-w-0 truncate">{opt.label}</span>
                  {active && <Check className="size-4 shrink-0 text-primary" />}
                </button>
              );
            })
          )}
        </div>
      )}
    </div>
  );
}

export { Select };
