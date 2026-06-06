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
  // 접힘 상태 프리뷰: 첫 섹션 본문 일부(line-clamp로 2줄 노출).
  const firstPreview = useMemo(() => {
    const first = rows[0]?.text ?? "";
    return first.replace(/\s+/g, " ").trim().slice(0, 160);
  }, [rows]);
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
        <div className="p-3 sm:p-4">
          {/* 접힘: 눈에 띄는 CTA 카드 — "클릭하면 AI 해석을 본다"를 즉시 유추 */}
          {!open ? (
            <button
              type="button"
              onClick={() => setOpen(true)}
              aria-expanded={false}
              className="group flex min-h-[64px] w-full items-center gap-3 rounded-xl border border-[var(--accent-strong)]/40 bg-[var(--accent-soft)] p-3 text-left shadow-[var(--shadow-sm)] transition-colors hover:border-[var(--accent-strong)] hover:bg-[color-mix(in_srgb,var(--accent-strong)_14%,var(--surface-soft))] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-strong)] sm:p-4"
            >
              {/* 아이콘 배지 (펄스로 주목 유도 — prefers-reduced-motion 시 전역 비활성) */}
              <span className="relative flex h-11 w-11 shrink-0 items-center justify-center rounded-lg bg-[var(--accent-strong)] text-[18px] text-white shadow-[var(--shadow-glow)]">
                <span className="pointer-events-none absolute inset-0 animate-ping rounded-lg bg-[var(--accent-strong)] opacity-20" />
                <span className="relative">✨</span>
              </span>

              <span className="min-w-0 flex-1">
                <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
                  <span className="text-[13px] font-bold text-[var(--text-primary)] sm:text-[14px]">
                    {interpretationTitle}
                  </span>
                  <span className="rounded-full border border-[var(--accent-strong)]/40 bg-[var(--surface-soft)] px-2 py-0.5 text-[10px] font-bold text-[var(--accent-strong)]">
                    {rows.length}개 섹션
                  </span>
                </span>
                {/* 첫 섹션 프리뷰 — "내용이 더 있다"를 시각적으로 암시 */}
                {firstPreview ? (
                  <span className="mt-1 line-clamp-2 block text-[12px] leading-relaxed text-[var(--text-secondary)]">
                    {firstPreview}
                  </span>
                ) : (
                  <span className="mt-1 block text-[12px] text-[var(--text-secondary)]">
                    종합요약 · 용적 · 시세 · 입지 · 개발계획 등
                  </span>
                )}
                <span className="mt-1.5 inline-flex items-center gap-1 text-[11px] font-semibold text-[var(--accent-strong)]">
                  탭하여 AI 상세 해석 보기
                  <span className="transition-transform group-hover:translate-y-0.5" aria-hidden>
                    ▾
                  </span>
                </span>
              </span>
            </button>
          ) : (
            /* 펼침: 기존 10섹션 + 접기 버튼 */
            <div>
              <button
                type="button"
                onClick={() => setOpen(false)}
                aria-expanded
                className="flex w-full items-center justify-between gap-2 rounded-lg px-1 py-1 text-left transition-colors hover:bg-[var(--surface-muted)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-strong)]"
              >
                <span className="flex items-center gap-2">
                  <span className="text-[13px] font-bold text-[var(--accent-strong)]">✨ {interpretationTitle}</span>
                  <span className="rounded-full border border-[var(--line)] bg-[var(--surface-muted)] px-2 py-0.5 text-[10px] font-bold text-[var(--text-secondary)]">
                    {rows.length}개 섹션
                  </span>
                </span>
                <span className="inline-flex items-center gap-1 text-[12px] font-semibold text-[var(--accent-strong)]">
                  접기
                  <span aria-hidden>▴</span>
                </span>
              </button>

              <div className="mt-2.5 space-y-2 border-t border-[var(--line)] pt-2.5">
                {rows.map((r, i) => (
                  <div
                    key={`${r.label}-${i}`}
                    className="rounded-lg border border-[var(--accent-strong)]/15 bg-[var(--accent-soft)] p-3"
                  >
                    <p className="mb-1 text-[11px] font-bold text-[var(--accent-strong)]">{r.label}</p>
                    <p className="whitespace-pre-wrap text-[12px] leading-relaxed text-[var(--text-secondary)]">
                      {r.text}
                    </p>
                  </div>
                ))}
                <p className="text-[10px] text-[var(--text-hint)]">AI 생성 · Claude · 참고용</p>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
