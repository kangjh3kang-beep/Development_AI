"use client";

/**
 * StagePreview — 아직 분석하지 않은 단계용 컴팩트 미리보기 카드.
 *
 * 빈 필드("—"/"분석 전")를 줄줄이 나열하는 대신,
 *  · 이 단계에서 "무엇을 분석하는지"(items) 를 점·가운뎃점으로 한 줄에 요약하고,
 *  · 어떤 입력을 활용하는지(inputHint, 예: "부지분석 면적·용도지역 활용") 를 알려주고,
 *  · "분석 시작" CTA(route 링크)로 바로 진입하게 한다.
 *
 * "분석이 덜 됐나?"라는 혼동을 "이 단계는 이런 걸 분석한다 → 시작"으로 바꾸는 게 목적이다.
 * 디자인 토큰만 사용(다크 기본), 반응형. Link로 라우팅(데이터 fetch 없음 → #185 무관).
 */

import Link from "next/link";

export function StagePreview({
  title,
  items,
  inputHint,
  route,
  ctaLabel = "분석 시작",
}: {
  /** 단계 제목(예: "공사비 분석"). */
  title: string;
  /** 이 단계에서 분석하는 항목 라벨들(예: ["총공사비","평당단가","직접/간접","범위"]). */
  items: string[];
  /** 어떤 입력을 활용하는지에 대한 안내(선택). 예: "부지분석 면적·용도지역 활용". */
  inputHint?: string;
  /** "분석 시작" 진입 경로(절대경로). */
  route: string;
  /** CTA 버튼 라벨. */
  ctaLabel?: string;
}) {
  return (
    <div className="flex flex-col gap-3 rounded-2xl border border-dashed border-[var(--line-strong)] bg-[var(--surface-muted)] p-5">
      <div className="flex items-center gap-2">
        <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-[var(--surface-soft)] text-[var(--text-hint)]">
          {/* 미완료 단계 표시(점선 원) */}
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <circle cx="12" cy="12" r="9" strokeDasharray="3 3" />
            <path d="M12 8v8M8 12h8" />
          </svg>
        </span>
        <h4 className="text-sm font-bold text-[var(--text-secondary)]">{title}</h4>
        <span className="ml-auto rounded-full bg-[var(--surface-soft)] px-2 py-0.5 text-[10px] font-bold text-[var(--text-hint)]">
          분석 전
        </span>
      </div>

      <p className="text-xs leading-relaxed text-[var(--text-secondary)]">
        <span className="font-semibold text-[var(--text-primary)]">이 단계에서 분석:</span>{" "}
        {items.join(" · ")}
      </p>

      {inputHint && (
        <p className="text-[11px] text-[var(--text-hint)]">입력 근거: {inputHint}</p>
      )}

      <Link
        href={route}
        className="mt-1 inline-flex h-9 w-fit items-center gap-1.5 self-start whitespace-nowrap rounded-full border border-[var(--accent-strong)]/40 bg-[var(--accent-soft)] px-4 text-[11px] font-black uppercase tracking-[0.15em] text-[var(--accent-strong)] transition-all hover:scale-105"
      >
        {ctaLabel} ↗
      </Link>
    </div>
  );
}
