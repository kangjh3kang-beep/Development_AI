export const locales = ["ko", "en", "zh-CN"] as const;

export type Locale = (typeof locales)[number];

export const localeOptions = [
  { value: "ko", label: "한국어" },
  { value: "en", label: "English" },
  { value: "zh-CN", label: "简体中文" },
] as const;

export const defaultLocale: Locale = "ko";
export const localeCookieName = "NEXT_LOCALE";

export function isValidLocale(value: string): value is Locale {
  return locales.includes(value as Locale);
}

export function getHtmlLang(value: string): string {
  if (value === "zh-CN") {
    return "zh-CN";
  }

  if (value === "en") {
    return "en";
  }

  return defaultLocale;
}

export function getLocaleFromPathname(pathname: string): Locale | null {
  const segment = pathname.split("/").filter(Boolean)[0];

  if (!segment) {
    return null;
  }

  if (isValidLocale(segment)) {
    return segment;
  }

  return null;
}
