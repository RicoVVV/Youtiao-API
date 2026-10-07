import { cn } from "@/lib/utils";

/** 品牌色接近纯黑的供应商：深色底下反白显示（底托模式下无需反白） */
const DARK_BRAND_PROVIDERS = new Set(["openai", "anthropic"]);

/**
 * 供应商图标：地址直接来自后端 provider_logo_url（相对路径，同源解析）。
 * src 为 null 时渲染为空，由调用方回退为纯文字徽标。
 */
export function ProviderLogo({
  src,
  providerId,
  alt = "",
  pad = false,
  className,
}: {
  src: string | null | undefined;
  providerId?: string | null;
  alt?: string;
  /** 深色或强彩色底上套白色圆形底托，避免近黑品牌色不可见 */
  pad?: boolean;
  className?: string;
}) {
  if (!src) return null;
  if (pad) {
    return (
      <span
        className={cn(
          "inline-flex shrink-0 items-center justify-center rounded-full bg-white p-[2px]",
          className
        )}
      >
        <img src={src} alt={alt} loading="lazy" className="size-full" />
      </span>
    );
  }
  return (
    <img
      src={src}
      alt={alt}
      loading="lazy"
      className={cn(
        "inline-block shrink-0",
        providerId && DARK_BRAND_PROVIDERS.has(providerId) && "dark:invert",
        className
      )}
    />
  );
}
