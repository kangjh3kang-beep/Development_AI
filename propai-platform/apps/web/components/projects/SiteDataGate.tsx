"use client";

/**
 * 부지 데이터준비 게이트(공용).
 *
 * 다운스트림 단계(수지·공사비·금융·ESG 등)는 부지 핵심 입력(면적·정확한 주소)이 없으면
 * baseline이 0이라 빈 0/목업이 표시되기 쉽다(SPOF). 본 컴포넌트는 그 빈 상태 대신
 * "부지 데이터를 채우면 자동 산출된다"는 안내 + 부지분석으로 이동하는 CTA를 통일된
 * 형태로 제공한다(무목업). P0-C 수지 게이트를 공용화한 것.
 *
 * 디자인 토큰만 사용. locale/projectId가 주어지면 부지분석 라우트로 직접 이동하는
 * 링크를, 없으면(=같은 페이지 내 탭 이동 등) onCtaClick 콜백 버튼을 렌더한다.
 */

import Link from "next/link";

export interface SiteDataGateProps {
  /** 게이트 제목(무엇이 부족한지). */
  title?: string;
  /** 안내 문구(채우면 무엇이 자동 산출되는지). */
  description?: string;
  /** CTA 버튼 라벨. */
  ctaLabel?: string;
  /** 부지분석 라우트 직접 이동용 — locale/projectId가 모두 주어지면 Link 렌더. */
  locale?: string;
  projectId?: string;
  /** locale/projectId 대신 같은 페이지 내 동작(탭 전환 등)을 쓸 때의 콜백. */
  onCtaClick?: () => void;
}

const DEFAULT_TITLE = "부지 데이터가 필요합니다";
const DEFAULT_DESCRIPTION =
  "부지면적 또는 정확한 주소(시·구·동·번지)를 입력하면 자동 산출됩니다.";
const DEFAULT_CTA = "부지분석으로 이동 ↗";

export function SiteDataGate({
  title = DEFAULT_TITLE,
  description = DEFAULT_DESCRIPTION,
  ctaLabel = DEFAULT_CTA,
  locale,
  projectId,
  onCtaClick,
}: SiteDataGateProps) {
  const href =
    locale && projectId
      ? `/${locale}/projects/${projectId}/site-analysis`
      : null;

  return (
    <div className="rounded-[var(--radius-2xl)] border border-amber-500/30 bg-amber-500/5 p-10 text-center shadow-[var(--shadow-lg)]">
      <div className="mx-auto mb-5 flex h-14 w-14 items-center justify-center rounded-2xl bg-amber-500/15 text-amber-400">
        <svg
          xmlns="http://www.w3.org/2000/svg"
          width="26"
          height="26"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <path d="M12 9v4" />
          <path d="M12 17h.01" />
          <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
        </svg>
      </div>
      <p className="text-lg font-[900] text-[var(--text-primary)]">{title}</p>
      <p className="mt-3 text-sm leading-relaxed text-[var(--text-secondary)]">
        {description}
      </p>
      {href ? (
        <Link
          href={href}
          className="mt-7 inline-flex items-center gap-2 rounded-full bg-[var(--accent-strong)] px-7 py-3 text-xs font-[900] uppercase tracking-[0.2em] text-white shadow-[var(--shadow-glow)] transition-all hover:scale-105"
        >
          {ctaLabel}
        </Link>
      ) : onCtaClick ? (
        <button
          type="button"
          onClick={onCtaClick}
          className="mt-7 inline-flex items-center gap-2 rounded-full bg-[var(--accent-strong)] px-7 py-3 text-xs font-[900] uppercase tracking-[0.2em] text-white shadow-[var(--shadow-glow)] transition-all hover:scale-105"
        >
          {ctaLabel}
        </button>
      ) : null}
    </div>
  );
}
