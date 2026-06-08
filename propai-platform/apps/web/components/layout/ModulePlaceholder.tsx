import React from "react";

type ModulePlaceholderProps = {
  eyebrow: string;
  title: string;
  description: string;
  localeLabel: string;
  statusLabel: string;
  items: string[];
};

/**
 * 모듈 안내 플레이스홀더 — 스페이셜 커맨드센터 톤.
 * 21개 모듈 페이지가 공유하는 순수 시각 컴포넌트(로직 없음).
 * HUD 코너 브래킷 + 정밀 그리드 + 모노 메타 라벨로 관제 콘솔 일관성 부여.
 */
export function ModulePlaceholder({
  eyebrow,
  title,
  description,
  localeLabel,
  statusLabel,
  items,
}: ModulePlaceholderProps) {
  return (
    <div className="cc-bracketed relative overflow-hidden rounded-[var(--radius-2xl)] bg-[var(--surface-strong)] p-8 sm:p-12 lg:p-16 shadow-[var(--shadow-2xl)] border border-[var(--line-strong)]">
      {/* 정밀 그리드 + 미세 스캔라인 배경(관제감) */}
      <div className="cc-grid-bg cc-grid-bg--radial opacity-50" aria-hidden="true" />
      <div className="cc-scanline" aria-hidden="true" />
      {/* HUD 코너 브래킷 */}
      <i className="cc-bracket cc-bracket--tl" aria-hidden="true" />
      <i className="cc-bracket cc-bracket--tr" aria-hidden="true" />
      <i className="cc-bracket cc-bracket--bl" aria-hidden="true" />
      <i className="cc-bracket cc-bracket--br" aria-hidden="true" />

      <div className="relative z-10 grid gap-10 lg:grid-cols-[1.2fr_0.8fr] items-center">
        <div className="space-y-7">
          <div className="flex flex-wrap items-center gap-3">
            <span className="cc-live">
              <i aria-hidden="true" />
              <span className="cc-meta">{eyebrow}</span>
            </span>
            <span className="cc-label rounded-md border border-[var(--line)] bg-[var(--surface-soft)] px-3 py-1.5">
              {localeLabel}
            </span>
            <span className="cc-chip-data">{statusLabel}</span>
          </div>

          <div className="space-y-4">
            <h2 className="max-w-2xl text-3xl font-[900] text-[var(--text-primary)] tracking-tighter sm:text-4xl lg:text-[40px] leading-[1.15]">
              {title}
              <span className="text-[var(--data-accent)]">.</span>
            </h2>
            <p className="max-w-2xl text-lg font-medium leading-relaxed text-[var(--text-secondary)] tracking-tight">
              &quot;{description}&quot;
            </p>
          </div>
        </div>

        <div className="cc-panel relative rounded-[var(--radius-lg)] border border-[var(--line-strong)] bg-[var(--surface)] p-8 lg:p-10 shadow-[var(--shadow-xl)]">
          <div className="cc-panel__head flex items-center gap-3 mb-7">
            <div className="h-10 w-10 rounded-2xl bg-[var(--data-accent-soft)] flex items-center justify-center text-[var(--data-accent)] ring-1 ring-[var(--data-accent-line)] shadow-inner">
              <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><path d="m12 3-1.912 5.813a2 2 0 0 0 1.275 1.275L21 12l-5.813 1.912a2 2 0 0 0-1.275 1.275L12 21l-1.912-5.813a2 2 0 0 0-1.275-1.275L3 12l5.813-1.912a2 2 0 0 0 1.275-1.275L12 3Z"/></svg>
            </div>
            <p className="cc-label">이 단계에서 하는 일</p>
          </div>

          <ul className="space-y-4">
            {items.map((item, i) => (
              <li key={i} className="flex items-start gap-3 text-sm font-medium text-[var(--text-secondary)] leading-relaxed group/item">
                <span className="mt-1.5 h-2 w-2 rounded-full bg-[var(--data-accent)] shadow-[var(--data-glow)] opacity-50 group-hover/item:opacity-100 group-hover/item:scale-125 transition-all shrink-0" />
                {item}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}
