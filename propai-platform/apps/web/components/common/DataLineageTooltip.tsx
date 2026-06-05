"use client";

/**
 * 데이터 계보(Data Lineage) 툴팁 — 교차모듈 값의 출처·신선도 노출.
 *
 * 스토어 타입에 이미 존재하나 화면 미노출이던 dataSource / fetchedAt 를
 * 값 옆 작은 ⓘ 아이콘으로 표시한다(hover/focus/tap). 출처·수집시각(상대시간)을 보여
 * "이 숫자가 언제·어디서 온 값인지" 추적 가능하게 한다(할루시네이션 방지 서사).
 *
 * 디자인 토큰만 사용, 접근성(aria) 준수.
 */

import { useId, useState } from "react";

/** ISO/타임스탬프를 상대시간 문자열로 변환(한국어). */
function relativeTime(value?: string | null): string | null {
  if (!value) return null;
  const t = new Date(value).getTime();
  if (Number.isNaN(t)) return null;
  const diffMs = Date.now() - t;
  const sec = Math.round(diffMs / 1000);
  if (sec < 0) return "방금";
  if (sec < 60) return "방금 전";
  const min = Math.round(sec / 60);
  if (min < 60) return `${min}분 전`;
  const hr = Math.round(min / 60);
  if (hr < 24) return `${hr}시간 전`;
  const day = Math.round(hr / 24);
  if (day < 30) return `${day}일 전`;
  const mon = Math.round(day / 30);
  if (mon < 12) return `${mon}개월 전`;
  return `${Math.round(mon / 12)}년 전`;
}

/** 절대 시각(로컬 표기) — 툴팁 보조 표시. */
function absoluteTime(value?: string | null): string | null {
  if (!value) return null;
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleString("ko-KR", { dateStyle: "medium", timeStyle: "short" });
}

export function DataLineageTooltip({
  dataSource,
  fetchedAt,
  className = "",
}: {
  dataSource?: string | null;
  fetchedAt?: string | null;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const tipId = useId();

  // 출처·시각 둘 다 없으면 렌더하지 않음(불필요한 아이콘 방지).
  const rel = relativeTime(fetchedAt);
  const abs = absoluteTime(fetchedAt);
  if (!dataSource && !rel) return null;

  return (
    <span className={`relative inline-flex items-center align-middle ${className}`}>
      <button
        type="button"
        aria-label="데이터 출처 및 수집 시각"
        aria-describedby={open ? tipId : undefined}
        aria-expanded={open}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onClick={(e) => {
          e.preventDefault();
          setOpen((v) => !v);
        }}
        className="inline-flex h-3.5 w-3.5 items-center justify-center rounded-full text-[var(--text-hint)] transition-colors hover:text-[var(--accent-strong)] focus:text-[var(--accent-strong)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-strong)]/40"
      >
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <circle cx="12" cy="12" r="10" />
          <path d="M12 16v-4" />
          <path d="M12 8h.01" />
        </svg>
      </button>

      {open && (
        <span
          id={tipId}
          role="tooltip"
          className="pointer-events-none absolute bottom-full left-1/2 z-50 mb-1.5 w-max max-w-[220px] -translate-x-1/2 rounded-lg border border-[var(--line)] bg-[var(--surface-strong)] px-3 py-2 text-left shadow-[var(--shadow-lg)]"
        >
          <span className="block text-[10px] font-black uppercase tracking-[0.18em] text-[var(--accent-strong)]">
            데이터 계보
          </span>
          {dataSource && (
            <span className="mt-1 block text-[11px] font-semibold text-[var(--text-primary)]">
              출처: {dataSource}
            </span>
          )}
          {rel && (
            <span className="mt-0.5 block text-[11px] text-[var(--text-secondary)]">
              수집: {rel}
              {abs && <span className="text-[var(--text-hint)]"> ({abs})</span>}
            </span>
          )}
        </span>
      )}
    </span>
  );
}
