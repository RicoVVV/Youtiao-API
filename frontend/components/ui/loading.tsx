import { cn } from "@/lib/utils";

const SIZES = {
  sm: { dot: "size-1", gap: "gap-1" },
  md: { dot: "size-1.5", gap: "gap-1.5" },
  lg: { dot: "size-2", gap: "gap-2" },
} as const;

/**
 * 通用加载指示器：轻量三点跳动
 * 用法：<Loading size="md" /> / <Loading size="lg" text="加载中" />
 */
export function Loading({
  size = "md",
  text,
  className,
}: {
  size?: keyof typeof SIZES;
  text?: string;
  className?: string;
}) {
  const dotSize = SIZES[size];

  return (
    <span
      role="status"
      aria-label={text ?? "加载中"}
      className={cn("inline-flex flex-col items-center justify-center gap-2", className)}
    >
      <span aria-hidden="true" className={cn("flex items-center", dotSize.gap)}>
        {[0, 1, 2].map((index) => (
          <span
            key={index}
            className={cn(
              "animate-bounce rounded-full bg-primary/80 [animation-duration:0.8s]",
              dotSize.dot
            )}
            style={{ animationDelay: `${index * 0.12}s` }}
          />
        ))}
      </span>
      {text && <span className="text-xs text-muted-foreground">{text}</span>}
    </span>
  );
}
