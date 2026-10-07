import { isLocale } from "@/i18n/config";

/** 从 pathname 中剥离 locale 前缀，返回裸路径（如 /console/api-keys） */
export function stripLocale(pathname: string): string {
  const seg = pathname.split("/")[1] ?? "";
  return isLocale(seg) ? pathname.slice(seg.length + 1) || "/" : pathname;
}
