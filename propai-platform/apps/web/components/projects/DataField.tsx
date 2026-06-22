"use client";

/**
 * DataField — 값이 있을 때만 보이는 "라벨:값" 행.
 *
 * 핵심 규칙: value가 null/undefined/빈문자면 **아무것도 렌더하지 않는다(null 반환)**.
 *  - "—" / "분석 전" 같은 빈 자리표시는 절대 출력하지 않는다(빈 필드 나열 제거가 목적).
 *  - value가 있을 때만 한 줄(라벨 | 값)을 그리고, 선택적으로 근거(evidence) 토글을 붙인다.
 *
 * 분석이 덜 된 단계의 "—" 줄이 화면을 채워 "분석이 안 됐나?" 혼동을 주던 문제를 근본 차단한다.
 * 디자인 토큰만 사용(다크 기본·하드코딩 색상 금지).
 */

import { useId, useState } from "react";

/** value가 실질적으로 비었는지 판정 — null/undefined/빈문자/공백·자리표시 문자열은 "없음"으로 본다. */
function isEmpty(value: unknown): boolean {
  if (value == null) return true;
  if (typeof value === "string") {
    const t = value.trim();
    // 프로젝트 전반에서 "값 없음"으로 통용되던 자리표시들도 빈 값으로 취급해 숨긴다.
    return t === "" || t === "—" || t === "-" || t === "분석 전" || t === "N/A";
  }
  return false;
}

export function DataField({
  label,
  value,
  accent = false,
  evidence,
}: {
  /** 행 라벨(좌측). */
  label: string;
  /** 표시할 값. 비어 있으면 컴포넌트 전체가 렌더되지 않는다. */
  value: string | number | null | undefined;
  /** 값을 강조색으로 표시할지(예: 핵심 지표). */
  accent?: boolean;
  /** 선택적 근거 — 산식/출처/법령 등. 있으면 우측에 작은 토글(ⓘ)을 붙인다. */
  evidence?: string | null;
}) {
  const [open, setOpen] = useState(false);
  const tipId = useId();

  // 빈 값이면 줄 자체를 그리지 않는다(요구사항: '—'/'분석 전' 금지).
  if (isEmpty(value)) return null;

  const display = typeof value === "number" ? value.toLocaleString() : String(value);
  const hasEvidence = !isEmpty(evidence);

  return (
    <div className="flex items-start justify-between gap-3 py-2">
      <dt className="flex items-center gap-1 text-xs text-[var(--text-secondary)]">
        {label}
        {hasEvidence && (
          <span className="relative inline-flex items-center align-middle">
            <button
              type="button"
              aria-label={`${label} 근거 보기`}
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
                className="pointer-events-none absolute bottom-full left-1/2 z-50 mb-1.5 w-max max-w-[240px] -translate-x-1/2 rounded-lg border border-[var(--line)] bg-[var(--surface-strong)] px-3 py-2 text-left shadow-[var(--shadow-lg)]"
              >
                <span className="block text-[10px] font-black uppercase tracking-[0.18em] text-[var(--accent-strong)]">
                  근거
                </span>
                <span className="mt-1 block text-[11px] text-[var(--text-secondary)]">
                  {evidence}
                </span>
              </span>
            )}
          </span>
        )}
      </dt>
      <dd className={`text-right text-sm font-semibold ${accent ? "text-[var(--accent-strong)]" : "text-[var(--text-primary)]"}`}>
        {display}
      </dd>
    </div>
  );
}
