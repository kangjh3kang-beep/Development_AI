"use client";

/**
 * UtilizationMaximizerCard — 토지 활용성 극대화 + AI 현실최적조합 추천 카드.
 *
 * 비전: 법규·조례 종합으로 용적률 극대화·기부채납 최소화 방안을 제시하고, AI가 현실적 최적조합을
 *   자동 추천(이론최대 vs 현실최적). 사람은 검토·조정만. 토지특성(U2) 다음 레이어.
 *
 * SSOT 소비: useProjectContextStore.siteAnalysis → optimizeUtilization(순수 파생). 새 fetch·writer 없음.
 * 설명가능성: 완화 근거(법령) + 포함/제외 사유 + 신뢰도, 미산정 "—". 디자인 토큰만 · WCAG AA · 통상어.
 */

import { useMemo } from "react";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import {
  optimizeUtilization,
  utilizationToEvidence,
  type UtilFeasibility,
} from "@/lib/land/utilization-optimizer";
import { EvidencePanel } from "@/components/common/EvidencePanel";

function feasibilityChip(f: UtilFeasibility): string {
  if (f === "상")
    return "border-[color-mix(in_srgb,var(--status-success)_36%,transparent)] bg-[color-mix(in_srgb,var(--status-success)_12%,transparent)] text-[var(--status-success)]";
  if (f === "중")
    return "border-[color-mix(in_srgb,var(--status-warning)_36%,transparent)] bg-[color-mix(in_srgb,var(--status-warning)_12%,transparent)] text-[var(--status-warning)]";
  return "border-[var(--line)] bg-[var(--surface-muted)] text-[var(--text-hint)]";
}

function FarTile({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-muted)] p-3 text-center">
      <p className="mb-1 text-[9px] font-black uppercase tracking-widest text-[var(--text-hint)]">{label}</p>
      <p className={`text-lg font-black ${accent ? "text-[var(--accent-strong)]" : "text-[var(--text-primary)]"}`}>
        {value}
      </p>
    </div>
  );
}

export function UtilizationMaximizerCard() {
  const siteAnalysis = useProjectContextStore((s) => s.siteAnalysis);
  const result = useMemo(() => optimizeUtilization(siteAnalysis), [siteAnalysis]);
  const evidence = useMemo(() => utilizationToEvidence(result), [result]);

  if (!result) return null;

  const { incentives, donationMinimized, realisticGainPct } = result;
  const pct = (v: number | null) => (v != null ? `${v}%` : "—");

  return (
    <div className="rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-strong)] p-6 shadow-[var(--shadow-xl)]">
      {/* 헤더 */}
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-[var(--accent-soft)] text-[var(--accent-strong)]">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <polyline points="22 7 13.5 15.5 8.5 10.5 2 17" />
            <polyline points="16 7 22 7 22 13" />
          </svg>
        </div>
        <div className="flex-1">
          <h4 className="text-sm font-black text-[var(--text-primary)]">토지 활용성 극대화 (AI 현실최적조합)</h4>
          <p className="text-[9px] font-bold uppercase tracking-widest text-[var(--accent-strong)]">
            용적률 극대화 · 기부채납 최소화
          </p>
        </div>
        {donationMinimized ? (
          <span className="rounded-full border border-[color-mix(in_srgb,var(--status-success)_36%,transparent)] bg-[color-mix(in_srgb,var(--status-success)_10%,transparent)] px-2.5 py-1 text-[10px] font-black text-[var(--status-success)]">
            기부채납 없음
          </span>
        ) : (
          <span className="rounded-full border border-[color-mix(in_srgb,var(--status-warning)_36%,transparent)] bg-[color-mix(in_srgb,var(--status-warning)_10%,transparent)] px-2.5 py-1 text-[10px] font-black text-[var(--status-warning)]">
            기부채납 동반(고가치)
          </span>
        )}
      </div>

      {/* 용적률 비교: 현재 실효 → 법정상한 → 현실최적 → 이론상 상한 */}
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <FarTile label="현재 실효" value={pct(result.currentEffectiveFar)} />
        <FarTile label="법정상한" value={pct(result.legalFar ?? result.legalCapFar)} />
        <FarTile label="현실최적(추천)" value={pct(result.realisticOptimalFar)} accent />
        <FarTile label="이론상 상한" value={pct(result.theoreticalMaxFar)} />
      </div>
      {realisticGainPct != null && realisticGainPct > 0 && (
        <p className="mt-2 text-[11px] font-bold text-[var(--accent-strong)]">
          현실최적 채택 시 기준 대비 +{realisticGainPct}% 상향
        </p>
      )}
      {/* U2: 법정상한 캡 고지(오도방지) — 단순가산치가 법정상한에 걸려 캡됐음을 정직 표기 */}
      {result.isCapped && result.legalCapFar != null && (
        <p className="mt-2 rounded-lg border border-[color-mix(in_srgb,var(--status-warning)_30%,transparent)] bg-[color-mix(in_srgb,var(--status-warning)_8%,transparent)] px-3 py-1.5 text-[10px] font-bold text-[var(--status-warning)]">
          ⚠ 이론상 상한은 법정상한 {result.legalCapFar}%로 캡됨(단순가산 {result.theoreticalUncappedFar}% → 중복적용·법정상한 미반영 이론치 아님)
        </p>
      )}
      {/* F5: 층수 바인딩 지역(녹지 등) 고지 — 인센티브 실현에 층수완화 선행 필요 */}
      {result.floorBound && (
        <p className="mt-2 rounded-lg border border-dashed border-[color-mix(in_srgb,var(--status-warning)_30%,transparent)] bg-[var(--surface-soft)] px-3 py-1.5 text-[10px] font-bold text-[var(--text-secondary)]">
          층수 바인딩 지역(녹지·관리 등): 건폐·층수상한이 실질 바인딩이라 완화 용적률 실현에 층수완화(도시·군계획·심의)가 선행돼야 합니다.
        </p>
      )}

      {/* 인센티브 방안 — 채택/제외 + 사유 + 신뢰도 + 기부채납 */}
      <div className="mt-4 space-y-2">
        <p className="text-[10px] font-black uppercase tracking-widest text-[var(--text-hint)]">
          인센티브 방안 (채택/제외 사유)
        </p>
        {incentives.map((inc) => (
          <div
            key={inc.key}
            className={`rounded-lg border p-3 ${
              inc.included
                ? "border-[color-mix(in_srgb,var(--status-success)_28%,transparent)] bg-[color-mix(in_srgb,var(--status-success)_6%,transparent)]"
                : "border-[var(--line)] bg-[var(--surface-soft)]"
            }`}
          >
            <div className="flex flex-wrap items-center gap-2">
              <span className={`text-xs font-black ${inc.included ? "text-[var(--text-primary)]" : "text-[var(--text-secondary)]"}`}>
                {inc.included ? "✓ " : "· "}
                {inc.label}
              </span>
              <span className={`rounded-full border px-2 py-0.5 text-[9px] font-black ${feasibilityChip(inc.feasibility)}`}>
                가능성 {inc.feasibility}
              </span>
              {inc.bonusFarPoints != null && (
                <span className="rounded-full bg-[var(--surface-muted)] px-2 py-0.5 text-[9px] font-bold text-[var(--text-secondary)]">
                  +{inc.bonusFarPoints}%p
                </span>
              )}
              {inc.donationRequired && (
                <span className="rounded-full border border-[color-mix(in_srgb,var(--status-warning)_30%,transparent)] px-2 py-0.5 text-[9px] font-bold text-[var(--status-warning)]">
                  기부채납
                </span>
              )}
            </div>
            <p className="mt-1 text-[10px] text-[var(--text-hint)]">{inc.reason}</p>
            <p className="mt-0.5 text-[9px] text-[var(--text-hint)]">근거: {inc.legalBasis}</p>
          </div>
        ))}
      </div>

      {/* 산출 근거(설명가능성 표준) */}
      <EvidencePanel className="mt-4" items={evidence} title="활용성 극대화 산출 근거" />

      {/* 한계 정직 고지 */}
      <p className="mt-3 rounded-lg border border-dashed border-[var(--line)] bg-[var(--surface-soft)] px-3 py-2 text-[10px] leading-relaxed text-[var(--text-hint)]">
        {result.honestNote}
      </p>
    </div>
  );
}
