"use client";

import { useEffect } from "react";
import type { Locale } from "@/i18n/config";
import { getHtmlLang } from "@/i18n/config";

/**
 * <html lang> 속성을 현재 로캘에 맞게 동적으로 설정합니다.
 * Next.js App Router에서 루트 레이아웃의 <html> 태그는 정적이므로,
 * 클라이언트 측에서 document.documentElement.lang을 업데이트합니다.
 */
export function HtmlLangSetter({ locale }: { locale: Locale }) {
  useEffect(() => {
    const htmlLang = getHtmlLang(locale);
    document.documentElement.lang = htmlLang;
  }, [locale]);

  return null;
}
