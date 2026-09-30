export const locales = ["zh", "en"] as const;
export type Locale = (typeof locales)[number];
export const defaultLocale: Locale = "zh";

export const namespaces = [
  "common",
  "home",
  "auth",
  "console",
  "canvas",
  "models",
  "api-docs",
  "errors",
  "payment-records",
] as const;
export type Namespace = (typeof namespaces)[number];

export function isLocale(value: string): value is Locale {
  return (locales as readonly string[]).includes(value);
}
