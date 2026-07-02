"use client";

/**
 * UpzoningScenarioList — 종상향/종변경 잠재 시나리오 리스트 공용 렌더 컴포넌트.
 *
 * 배경(U1 사용자 지적 "실현가능성 하는 굳이 제시할필요없지않아?"): 종상향 시나리오를 feasibility
 *   등급과 무관하게 전량 무조건 렌더하면, 자연녹지 소형 필지(면적 미달)처럼 3안 모두 "하"인 부지도
 *   상단에 강조돼 오도한다. 이 공용 컴포넌트는 저실현("하"·미확인) 시나리오를 강등·접기 처리한다:
 *
 *   - 상/중 시나리오가 하나도 없으면(전량 "하"/미확인) → 리스트 전체를 기본 접힘으로 강등하고
 *     "단독 종상향 가능성 낮음(면적·요건 미달)" 요약만 헤더에 노출, "저실현 N건 자세히"로 펼침.
 *   - 상/중과 하가 혼재하면 → 상/중은 항상 노출, "하"만 별도 접힘그룹으로 분리(기본 접힘).
 *
 * 공용화(단발 국소패치 금지): 종상향 시나리오를 렌더하는 모든 소비처가 이 컴포넌트를 재사용해
 *   같은 강등/접기 규약을 전역 일관 적용한다. 근거법령 렌더(verified 딥링크·죽은 링크 금지)도 내장.
 *
 * 무날조: 강등은 실제 feasibility 등급 근거로만. 데이터는 그대로 표시(수치 조작 없음).
 */

import { useMemo, useState } from "react";
import { LegalRefChip } from "@/components/common/LegalRefChip";
import type { BackendLegalRef } from "@/lib/evidence/adaptEvidence";

/** 종상향 시나리오(백엔드 snake_case 계약 — 단일/통합 응답 공용). */
export interface UpzoningScenarioView {
  path?: string;
  target_zone?: string;
  expected_far_pct_low?: number | null;
  expected_far_pct_high?: number | null;
  expected_far_source?: string;
  conditions?: string[];
  feasibility?: string;
  feasibility_reason?: string;
  legal_basis?: string;
  legal_refs?: BackendLegalRef[] | null;
  timeline_est?: string;
  caveats?: string[];
  is_estimate?: boolean;
}

/** 가능성 등급 → 의미색(상=success/중=warning/하·미확인=muted). site-analysis feasibilityStyle과 동형. */
function feasibilityStyle(f?: string): string {
  if (f === "상") return "sa-chip--success";
  if (f === "중") return "sa-chip--warning";
  return "bg-[var(--surface-muted)] text-[var(--text-hint)] border-[var(--line)]";
}

/** 상/중만 "고실현"으로 간주(그 외 하·미확인·미상은 저실현). */
function isHighFeasibility(f?: string): boolean {
  const g = (f ?? "").trim();
  return g === "상" || g === "중";
}

/** 종상향 시나리오 근거법령 렌더 — verified law.go.kr 딥링크만 칩(클릭), 미verified는 텍스트(죽은 링크 금지). */
function UpzoningLegalRefs({
  legalRefs,
  legalBasis,
}: {
  legalRefs?: BackendLegalRef[] | null;
  legalBasis?: string | null;
}) {
  const verified = (legalRefs || []).filter(
    (r) => r && (r.url_status || "").trim() === "verified" && (r.url || "").trim(),
  );
  if (verified.length === 0) {
    if (!legalBasis) return null;
    return (
      <div className="mt-2 text-[9px] text-[var(--text-hint)]">
        근거법령: {legalBasis}
      </div>
    );
  }
  return (
    <div className="mt-2 flex flex-wrap items-center gap-1.5">
      <span className="text-[9px] font-bold text-[var(--text-hint)]">근거법령:</span>
      {verified.map((r, i) => (
        <LegalRefChip
          key={`${r.key || r.law_name || "ref"}-${i}`}
          lawName={r.law_name || ""}
          article={r.article}
          title={r.title}
          url={r.url}
        />
      ))}
    </div>
  );
}

/** 용적률 퍼센트 안전 포맷. */
const pct = (v: number | null | undefined): string => (v == null ? "—" : `${Math.round(v)}%`);

/** 시나리오 1건 카드(내부 재사용). */
function ScenarioCard({ sc }: { sc: UpzoningScenarioView }) {
  return (
    <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-muted)] p-4">
      <div className="flex items-start justify-between gap-3 mb-2">
        <div className="flex-1">
          <p className="text-xs font-black text-[var(--text-primary)]">{sc.path || "잠재 경로"}</p>
          {sc.target_zone && (
            <p className="text-[10px] font-bold text-purple-400 mt-0.5">→ {sc.target_zone}</p>
          )}
        </div>
        <span className={`shrink-0 rounded-full border px-2.5 py-1 text-[9px] font-black ${feasibilityStyle(sc.feasibility)}`}>
          가능성 {sc.feasibility || "—"}
        </span>
      </div>
      {(sc.expected_far_pct_low != null || sc.expected_far_pct_high != null) && (
        <p className="text-[11px] font-bold text-[var(--text-secondary)] mb-1">
          예상 용적률 {sc.expected_far_pct_low != null ? pct(sc.expected_far_pct_low) : ""}{sc.expected_far_pct_high != null ? ` ~ ${pct(sc.expected_far_pct_high)}` : ""}
          {sc.expected_far_source ? ` (${sc.expected_far_source})` : ""}
        </p>
      )}
      {sc.feasibility_reason && (
        <p className="text-[10px] text-[var(--text-hint)] mb-1">사유: {sc.feasibility_reason}</p>
      )}
      {sc.conditions && sc.conditions.length > 0 && (
        <div className="flex flex-wrap gap-1 mt-1.5">
          {sc.conditions.map((c, ci) => (
            <span key={ci} className="rounded-md bg-[var(--surface-strong)] border border-[var(--line)] px-2 py-0.5 text-[9px] font-bold text-[var(--text-secondary)]">{c}</span>
          ))}
        </div>
      )}
      {/* 근거법령 — verified면 클릭 가능한 law.go.kr 딥링크 칩, 미verified는 텍스트(죽은 링크 금지) */}
      <UpzoningLegalRefs legalRefs={sc.legal_refs} legalBasis={sc.legal_basis} />
      <div className="flex flex-wrap gap-x-4 gap-y-1 mt-1.5 text-[9px] text-[var(--text-hint)]">
        {sc.timeline_est && <span>예상 기간: {sc.timeline_est}</span>}
      </div>
      {sc.caveats && sc.caveats.length > 0 && (
        <p className="mt-1.5 text-[9px] text-amber-400/80 italic">전제: {sc.caveats.join(" / ")}</p>
      )}
    </div>
  );
}

/**
 * 종상향 시나리오 리스트 — 저실현(하·미확인) 강등·접기 규약 내장 공용 렌더.
 *
 * @param scenarios 종상향 시나리오 배열(백엔드 snake_case).
 */
export function UpzoningScenarioList({ scenarios }: { scenarios: UpzoningScenarioView[] }) {
  // 고실현(상/중) vs 저실현(하/미확인) 분리 — 강등·접기 판정 근거.
  const { high, low } = useMemo(() => {
    const h: UpzoningScenarioView[] = [];
    const l: UpzoningScenarioView[] = [];
    for (const sc of scenarios) {
      if (isHighFeasibility(sc.feasibility)) h.push(sc);
      else l.push(sc);
    }
    return { high: h, low: l };
  }, [scenarios]);

  // 전량 저실현이면 리스트 전체 기본 접힘, 혼재면 저실현 그룹만 기본 접힘.
  const allLow = high.length === 0 && low.length > 0;
  const [expanded, setExpanded] = useState(false);

  if (scenarios.length === 0) return null;

  // 케이스 A: 전량 저실현(면적·요건 미달) → 요약만 노출 + "저실현 N건 자세히" 펼침.
  if (allLow) {
    return (
      <div className="rounded-xl border border-dashed border-[var(--line)] bg-[var(--surface-soft)] p-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="text-xs font-black text-[var(--text-secondary)]">단독 종상향 가능성 낮음 (면적·요건 미달)</p>
            <p className="text-[10px] text-[var(--text-hint)] mt-0.5">
              검토 시나리오 {low.length}건 모두 실현 가능성 &quot;하&quot; 또는 미확인 — 단독 종상향으로 실질 용적 상향 어려움.
            </p>
          </div>
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            className="shrink-0 rounded-lg border border-[var(--line)] bg-[var(--surface-muted)] px-3 py-1.5 text-[10px] font-black text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
            aria-expanded={expanded}
          >
            {expanded ? "접기" : `저실현 ${low.length}건 자세히`}
          </button>
        </div>
        {expanded && (
          <div className="mt-3 space-y-2">
            {low.map((sc, i) => (
              <ScenarioCard key={i} sc={sc} />
            ))}
          </div>
        )}
      </div>
    );
  }

  // 케이스 B: 상/중 존재 → 고실현은 항상 노출, 저실현("하"·미확인)은 별도 접힘그룹.
  return (
    <div className="space-y-2">
      {high.map((sc, i) => (
        <ScenarioCard key={`h-${i}`} sc={sc} />
      ))}
      {low.length > 0 && (
        <div className="rounded-xl border border-dashed border-[var(--line)] bg-[var(--surface-soft)] p-3">
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            className="flex w-full items-center justify-between gap-3 text-left"
            aria-expanded={expanded}
          >
            <span className="text-[10px] font-black text-[var(--text-hint)]">
              저실현 시나리오 {low.length}건 (가능성 하·미확인 — 참고용)
            </span>
            <span className="shrink-0 text-[10px] font-black text-[var(--text-secondary)]">
              {expanded ? "접기" : "펼치기"}
            </span>
          </button>
          {expanded && (
            <div className="mt-2 space-y-2">
              {low.map((sc, i) => (
                <ScenarioCard key={`l-${i}`} sc={sc} />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
