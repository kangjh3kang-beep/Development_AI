"use client";

/**
 * 비전 배너 — 멀티모달 AI(VLLM) 기반 차세대 심의분석 엔진 비전을 영역별로 분산 명시한다.
 *
 * 차별화: 설계 '생성'(design-studio)과 중복을 피하려 **인허가/규제·회의방에만** 슬림 배너로 배치한다.
 * 심의분석엔진 본 페이지(/deliberation-review)는 자체 비전 히어로를 가지므로 배너 대상이 아니다.
 * 로케일은 URL([locale])에서 읽고, 딕셔너리 미로드 시 한국어 폴백으로 즉시 렌더(플래시 방지). SSOT=common.json `vision`.
 */

import { useParams } from "next/navigation";
import { useDictionary } from "@/hooks/use-dictionary";
import { defaultLocale, isValidLocale, type Locale } from "@/i18n/config";

export type VisionVariant = "permit" | "meeting";

type VisionCopy = {
  badge: string;
  title: string;
  lead: string;
  areas: Record<string, string>;
};

// 딕셔너리 미로드(초기/오프라인) 시 폴백 — 한국어 기준(SSOT는 common.json `vision`).
const FALLBACK: VisionCopy = {
  badge: "VLLM · 차세대 심의분석 엔진",
  title: "멀티모달 AI로 설계도서를 자동 해석하는 차세대 심의분석 엔진",
  lead: "미래확장형 아키텍처로 국내 상용·공공 시스템의 빈 프런티어를 선도합니다.",
  areas: {
    permit: "인허가·규제 판단의 근거추적 기반",
    meeting: "협업·심의 검증 허브",
  },
};

function useLocale(): Locale {
  const params = useParams();
  const raw = Array.isArray(params?.locale) ? params.locale[0] : params?.locale;
  return raw && isValidLocale(raw) ? raw : defaultLocale;
}

export function VisionBanner({ variant }: { variant: VisionVariant }) {
  const locale = useLocale();
  const { dictionary } = useDictionary(locale);
  const v = (dictionary?.vision as VisionCopy | undefined) ?? FALLBACK;
  const area = v.areas?.[variant] ?? FALLBACK.areas[variant];

  return (
    <section
      aria-label="비전"
      className="cc-panel cc-bracketed relative overflow-hidden rounded-[var(--radius-2xl)] p-4"
    >
      <i className="cc-bracket cc-bracket--tl" />
      <i className="cc-bracket cc-bracket--tr" />
      <i className="cc-bracket cc-bracket--bl" />
      <i className="cc-bracket cc-bracket--br" />
      <div className="cc-grid-bg opacity-30" />
      <div className="relative z-10 flex flex-wrap items-center gap-x-3 gap-y-1">
        <span className="cc-meta text-[var(--accent-strong)]">{v.badge}</span>
        <span className="text-[11px] text-[var(--text-tertiary)]">· {area}</span>
      </div>
      <p className="relative z-10 mt-1.5 text-sm font-black leading-snug text-[var(--text-primary)]">
        {v.title}
      </p>
      <p className="relative z-10 mt-0.5 text-xs text-[var(--text-secondary)]">{v.lead}</p>
    </section>
  );
}
