"use client";

/**
 * 면책 고지 — 분석/추정 결과 페이지에만 노출.
 *
 * 분석 결과는 참고용이며 사통팔땅은 책임을 지지 않고 최종판단은 사용자에게 있음을 고지한다.
 * dashboard layout에 전역 1회 배치하되, 운영(비-분석) 화면(분양 ERP·토지조서·설정 등)에서는
 * 분석결과가 아니므로 숨긴다(usePathname 기준).
 */

import { usePathname } from "next/navigation";
import { AlertTriangle } from "lucide-react";

export const DISCLAIMER_TEXT =
  "본 분석결과는 참고용이며, 오류가 있을 수 있습니다. 이와 관련해 사통팔땅은 어떠한 책임도 지지 않습니다. 최종판단은 사용자가 최종 결정하는 것입니다.";

// 분석결과가 아닌 운영 화면 — 면책 고지 비노출 섹션(로케일 다음 첫 경로 세그먼트)
const NON_ANALYSIS_SECTIONS = new Set(["sales", "settings", "land-schedule"]);

export function Disclaimer({ className = "" }: { className?: string }) {
  const pathname = usePathname() || "";
  const section = pathname.split("/").filter(Boolean)[1]; // [locale, section, ...]
  if (section && NON_ANALYSIS_SECTIONS.has(section)) return null;

  return (
    <p
      role="note"
      className={`flex items-start gap-2 rounded-[var(--radius-lg)] border border-[var(--line)] bg-[var(--surface-soft)] px-4 py-3 text-[11px] leading-relaxed text-[var(--text-tertiary)] ${className}`}
    >
      <AlertTriangle aria-hidden className="mt-0.5 size-3.5 shrink-0" />
      <span>{DISCLAIMER_TEXT}</span>
    </p>
  );
}
