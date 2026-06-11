"use client";

/**
 * EvidencePanel — 산출 근거 트레이스 패널 (공용).
 *
 * "이 수치 = 입력 × 산식 × 법정값" 한 줄 근거를 핵심 수치마다 보여, "용적률 200%가
 * 왜 나왔나?"에 `label = value (basis)` + 법령 원문 링크로 답한다(할루시네이션 방지 서사).
 *
 * 각 항목:
 *   label  — 수치 이름 (예: "적용 용적률")
 *   value  — 결과값      (예: "200%")
 *   basis? — 산식·근거 한 줄 (예: "min(법정 250%, 조례 200%)")
 *   legalRef? — 법령 원문 칩(LegalRefChip) — url 없으면 자동으로 텍스트만(정직성)
 *
 * 접이식(기본 펼침). 순수 presentational — 데이터 fetch·store 접근 없음.
 * 디자인 토큰(CSS 변수)만 사용. 항목이 없으면 렌더하지 않는다(빈 패널 방지).
 */

import { useState } from "react";
import { LegalRefChip } from "@/components/common/LegalRefChip";

/** 항목당 법령 근거 — LegalRefChip props와 구조 호환(className 제외). */
export type EvidenceLegalRef = {
  lawName: string;
  article?: string | null;
  title?: string | null;
  url?: string | null;
};

export type EvidenceItem = {
  /** 수치 이름 (예: "적용 용적률"). */
  label: string;
  /** 결과값 — 문자열/숫자 모두 허용(예: "200%", 1320). */
  value: string | number;
  /** 산식·근거 한 줄 (예: "min(법정 250%, 조례 200%)"). 없으면 생략. */
  basis?: string | null;
  /** 법령 원문 칩 데이터. 없으면 칩 미표시. */
  legalRef?: EvidenceLegalRef | null;
};

export function EvidencePanel({
  title = "산출 근거",
  items,
  defaultOpen = true,
  className = "",
}: {
  title?: string;
  items: EvidenceItem[];
  /** 초기 펼침 여부(기본 펼침). */
  defaultOpen?: boolean;
  className?: string;
}) {
  const [open, setOpen] = useState(defaultOpen);

  // 표시할 근거가 없으면 렌더하지 않음(빈 패널 방지).
  const rows = Array.isArray(items) ? items.filter((it) => it && it.label) : [];
  if (rows.length === 0) return null;

  return (
    <div className={`rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] px-4 py-2.5 ${className}`}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center justify-between gap-2 text-left"
      >
        <span className="inline-flex items-center gap-1.5 text-[11px] font-bold text-[var(--text-secondary)]">
          {/* 근거·검토 아이콘 (돋보기) */}
          <svg
            width="13"
            height="13"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.2"
            strokeLinecap="round"
            strokeLinejoin="round"
            className="shrink-0 text-[var(--accent-strong)]"
            aria-hidden="true"
          >
            <circle cx="11" cy="11" r="7" />
            <path d="m21 21-4.3-4.3" />
          </svg>
          {title}
          <span className="text-[var(--text-hint)]">· {rows.length}건</span>
        </span>
        <span className="text-[11px] font-semibold text-[var(--accent-strong)]">{open ? "접기" : "펼치기"}</span>
      </button>

      {open && (
        <div className="mt-2 space-y-2 border-t border-[var(--line)] pt-2">
          {rows.map((it, i) => (
            <div key={i} className="flex flex-wrap items-baseline gap-x-1.5 gap-y-1 text-[11px]">
              <span className="font-semibold text-[var(--text-secondary)]">{it.label}</span>
              <span className="text-[var(--text-hint)]">=</span>
              <span className="font-bold text-[var(--text-primary)]">
                {typeof it.value === "number" ? it.value.toLocaleString() : it.value}
              </span>
              {it.basis?.trim() && (
                <span className="text-[var(--text-tertiary)]">({it.basis.trim()})</span>
              )}
              {it.legalRef?.lawName && (
                <LegalRefChip
                  lawName={it.legalRef.lawName}
                  article={it.legalRef.article}
                  title={it.legalRef.title}
                  url={it.legalRef.url}
                />
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
