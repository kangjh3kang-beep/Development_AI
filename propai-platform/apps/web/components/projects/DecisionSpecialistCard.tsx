"use client";

/**
 * SpecialistAgent 결정론 교차검증 카드 — Stage1 통합 브리프 소비처 연결.
 *
 * 백엔드 decision_brief_service._run_specialists(zoning/permit)가 결정론 도구로 산출한
 * findings·원장 cite·prior 모순(contradictions)을 표시한다. LLM·과금 없음(결정론 도메인만).
 * specialists가 비면 렌더하지 않는다(graceful·구 응답 무영향).
 */

import type { DecisionSpecialist } from "@/components/projects/decision-brief-types";

const SPECIALIST_LABEL: Record<string, string> = {
  zoning: "용도지역 허용용도",
  permit: "인허가 가능성",
  far: "실효 용적률",
  cost: "공사비",
  market: "시장",
  심의: "심의",
  설계: "설계",
};

/** 결정론 finding에서 표시용 텍스트를 best-effort 추출(키 형태 변동에 견고). */
function findingText(f: Record<string, unknown>): string {
  for (const k of ["claim", "label", "text", "message", "name", "title"]) {
    const v = f[k];
    if (typeof v === "string" && v.trim()) return v.trim();
  }
  const label = f.label ?? f.key;
  const value = f.value;
  if (label != null && value != null) return `${String(label)}: ${String(value)}`;
  return "";
}

/** contradictions(형태 다양: list/obj/falsy)에서 모순 존재 여부 판정. */
function hasContradiction(c: unknown): boolean {
  if (!c) return false;
  if (Array.isArray(c)) return c.length > 0;
  if (typeof c === "object") return Object.keys(c as object).length > 0;
  return Boolean(c);
}

export function DecisionSpecialistCard({
  specialists, deployPending,
}: { specialists?: DecisionSpecialist[]; deployPending?: boolean }) {
  const items = (specialists ?? []).filter((s) => s && s.domain);
  if (items.length === 0) return null;
  return (
    <div className="flex flex-col gap-3 rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)]/40 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs font-black text-[var(--accent-strong)]">전문가 에이전트 결정론 교차검증</p>
        <span className="text-[10px] font-semibold text-[var(--text-hint)]">LLM·과금 없음 · 분석 원장 기록</span>
      </div>
      <div className="grid gap-2 md:grid-cols-2">
        {items.map((sp, i) => {
          const label = SPECIALIST_LABEL[sp.domain] ?? sp.domain;
          // 시도했으나 실패한 도메인 — 조용히 누락하지 않고 정직하게 '교차검증 불가' 표시.
          if (sp.status === "unavailable") {
            return (
              <div key={`${sp.domain}-${i}`} className="rounded-xl border border-dashed border-[var(--line-strong)] bg-[var(--surface)] p-3">
                <div className="flex items-center justify-between gap-2">
                  <p className="text-xs font-bold text-[var(--text-secondary)]">{label}</p>
                  <span className="rounded-full border border-[var(--line-strong)] px-2 py-0.5 text-[10px] font-semibold text-[var(--text-hint)]">교차검증 불가</span>
                </div>
                <p className="mt-1.5 text-[11px] text-[var(--text-hint)]">{sp.reason || "결정론 도구를 호출하지 못했습니다."}</p>
              </div>
            );
          }
          const findings = (sp.findings ?? []).map(findingText).filter(Boolean).slice(0, 4);
          const contradiction = hasContradiction(sp.contradictions);
          const recorded = sp.ledger?.ok;
          return (
            <div key={`${sp.domain}-${i}`} className="rounded-xl border border-[var(--line)] bg-[var(--surface)] p-3">
              <div className="flex items-center justify-between gap-2">
                <p className="text-xs font-bold text-[var(--text-primary)]">{label}</p>
                <div className="flex items-center gap-1.5">
                  {contradiction && (
                    <span className="rounded-full border border-[color-mix(in_srgb,var(--status-warning)_40%,transparent)] bg-[color-mix(in_srgb,var(--status-warning)_12%,transparent)] px-2 py-0.5 text-[10px] font-bold text-[var(--status-warning)]">
                      이전 분석과 차이
                    </span>
                  )}
                  {recorded ? (
                    <span className="rounded-full border border-[var(--line-strong)] px-2 py-0.5 text-[10px] font-semibold text-[var(--text-tertiary)]">원장 기록</span>
                  ) : deployPending ? (
                    <span className="rounded-full border border-dashed border-[var(--line-strong)] px-2 py-0.5 text-[10px] font-semibold text-[var(--text-hint)]">배포 후 원장 기록</span>
                  ) : null}
                </div>
              </div>
              {findings.length > 0 ? (
                <ul className="mt-1.5 space-y-0.5 text-[11px] text-[var(--text-secondary)]">
                  {findings.map((t, idx) => <li key={idx}>· {t}</li>)}
                </ul>
              ) : (
                <p className="mt-1.5 text-[11px] text-[var(--text-hint)]">결정론 판정 결과 없음(데이터 기준).</p>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
