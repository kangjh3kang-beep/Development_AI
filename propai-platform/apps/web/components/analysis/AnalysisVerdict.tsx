"use client";

/**
 * AnalysisVerdict — 검증 배지 + AI 해석을 단일 카드로 결합(표준).
 *
 * 노출 비대칭(검증 배지 12곳 vs AI 해석 카드 3곳) 해소를 위한 표준 컴포넌트.
 *   - 상단: 기존 VerificationBadge 재사용(중복 구현 없음) → pass/warn/fail + 계산검증.
 *   - 하단: AI 해석 요약(접기/펼치기). interpretation은 문자열 또는
 *     섹션 라벨→본문 레코드(예: SiteAnalysisInterpreter 10섹션)를 모두 수용.
 *
 * 검증/해석 어느 한쪽만 있어도 동작한다. 디자인 토큰만 사용.
 */

import { useMemo, useState } from "react";
import { VerificationBadge } from "@/components/common/VerificationBadge";

/** 해석 입력: 단순 문자열, 라벨 매핑된 섹션 배열, 또는 자유 레코드 모두 지원. */
export type Interpretation =
  | string
  | Array<{ label: string; text: string }>
  | Record<string, unknown>
  | null
  | undefined;

const s = (v: unknown): string => (typeof v === "string" ? v.trim() : v == null ? "" : String(v));

/** 다양한 해석 입력을 {label, text} 행으로 정규화. */
function normalize(
  interpretation: Interpretation,
  sectionLabels?: Array<[string, string]>,
): Array<{ label: string; text: string }> {
  if (!interpretation) return [];
  if (typeof interpretation === "string") {
    const text = interpretation.trim();
    return text ? [{ label: "AI 해석", text }] : [];
  }
  if (Array.isArray(interpretation)) {
    return interpretation.map((r) => ({ label: r.label, text: s(r.text) })).filter((r) => r.text);
  }
  const obj = interpretation as Record<string, unknown>;
  // 명시 섹션 라벨이 주어지면 그 순서/이름으로, 아니면 객체 키 순서로.
  const entries: Array<[string, string]> = sectionLabels
    ? sectionLabels
    : Object.keys(obj).map((k) => [k, k]);
  return entries
    .map(([key, label]) => ({ label, text: s(obj[key]) }))
    .filter((r) => r.text);
}

export function AnalysisVerdict({
  analysisType,
  context,
  interpretation,
  sectionLabels,
  interpretationTitle = "AI 해석",
  defaultOpen = false,
  autoRunVerification = true,
  className = "",
}: {
  /** 검증 종류(VerificationBadge로 전달). */
  analysisType: string;
  /** 검증 컨텍스트(원본+출력). null이면 검증 배지 숨김. */
  context: Record<string, unknown> | null;
  /** AI 해석(문자열/섹션배열/레코드). 없으면 해석부 숨김. */
  interpretation?: Interpretation;
  /** 레코드형 해석을 정렬·라벨링할 [키, 라벨] 목록(선택). */
  sectionLabels?: Array<[string, string]>;
  interpretationTitle?: string;
  defaultOpen?: boolean;
  autoRunVerification?: boolean;
  className?: string;
}) {
  const rows = useMemo(
    () => normalize(interpretation, sectionLabels),
    [interpretation, sectionLabels],
  );
  const [open, setOpen] = useState(defaultOpen);

  const hasInterp = rows.length > 0;
  if (!context && !hasInterp) return null;

  return (
    <div
      className={`overflow-hidden rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] ${className}`}
    >
      {/* 검증 배지(기존 컴포넌트 재사용) */}
      {context && (
        <div className="border-b border-[var(--line)]">
          <VerificationBadge
            analysisType={analysisType}
            context={context}
            autoRun={autoRunVerification}
          />
        </div>
      )}

      {/* AI 해석부 (접기/펼치기) */}
      {hasInterp && (
        <div className="px-4 py-2.5">
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            aria-expanded={open}
            className="flex w-full items-center justify-between gap-2 text-left"
          >
            <span className="flex items-center gap-2">
              <span className="text-[11px] font-bold text-[var(--accent-strong)]">✦ {interpretationTitle}</span>
              <span className="rounded-full border border-[var(--line)] bg-[var(--surface-muted)] px-2 py-0.5 text-[10px] font-bold text-[var(--text-secondary)]">
                {rows.length}개 섹션
              </span>
            </span>
            <span className="text-[11px] font-semibold text-[var(--accent-strong)] hover:underline">
              {open ? "접기" : "해석 보기"}
            </span>
          </button>

          {open && (
            <div className="mt-2.5 space-y-2 border-t border-[var(--line)] pt-2.5">
              {rows.map((r, i) => (
                <div
                  key={`${r.label}-${i}`}
                  className="rounded-lg border border-[var(--accent-strong)]/15 bg-[var(--accent-soft)] p-3"
                >
                  <p className="mb-1 text-[10px] font-bold text-[var(--accent-strong)]">{r.label}</p>
                  <p className="whitespace-pre-wrap text-[12px] leading-relaxed text-[var(--text-secondary)]">
                    {r.text}
                  </p>
                </div>
              ))}
              <p className="text-[10px] text-[var(--text-hint)]">AI 생성 · Claude · 참고용</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
