"use client";

/**
 * LandProfileCard — 토지특성(부지 생명력) foundation 카드.
 *
 * 비전(land-vitality-foundational-analysis): 토지특성 분석 = 모든 분석의 1번·중심.
 *   Stage A 현시점(현실적 용적/건폐율·건축가능분류·제한사항) → Stage B 미래(종상향 가능성·재산정 한도).
 *
 * SSOT 소비: useProjectContextStore.siteAnalysis → buildLandProfile(순수 파생). 새 fetch·writer 없음.
 * 설명가능성(explainability-by-default): 미해소는 "—"로 정직 표기, EvidencePanel로 근거(도출이유·법령) 동반.
 * 디자인 토큰(CSS 변수)만 · WCAG AA · 통상어.
 */

import { useMemo } from "react";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import {
  buildLandProfile,
  landProfileToEvidence,
  type LandFeasibility,
  type LandMetric,
  type LandRestriction,
} from "@/lib/land/land-profile";
import { EvidencePanel } from "@/components/common/EvidencePanel";

/** 가능성 등급 → 의미색 칩 클래스(상=성공/중=주의/하=중립). */
function feasibilityChip(f: LandFeasibility | null): string {
  if (f === "상")
    return "border-[color-mix(in_srgb,var(--status-success)_36%,transparent)] bg-[color-mix(in_srgb,var(--status-success)_12%,transparent)] text-[var(--status-success)]";
  if (f === "중")
    return "border-[color-mix(in_srgb,var(--status-warning)_36%,transparent)] bg-[color-mix(in_srgb,var(--status-warning)_12%,transparent)] text-[var(--status-warning)]";
  return "border-[var(--line)] bg-[var(--surface-muted)] text-[var(--text-hint)]";
}

/** 제한사항 영향도 → 의미색 점. */
function severityDot(s: LandRestriction["severity"]): string {
  if (s === "blocker") return "var(--status-error)";
  if (s === "caution") return "var(--status-warning)";
  return "var(--text-hint)";
}

/** 건축가능분류 → 의미색 칩(불가/제한=error, 조건부=warning, 개발가능=success, 분석 전=중립). */
function buildableChip(code: string | null, label: string): string {
  if (code === "BLOCKED" || code === "RESTRICTED")
    return "border-[color-mix(in_srgb,var(--status-error)_36%,transparent)] bg-[color-mix(in_srgb,var(--status-error)_10%,transparent)] text-[var(--status-error)]";
  if (code)
    return "border-[color-mix(in_srgb,var(--status-warning)_36%,transparent)] bg-[color-mix(in_srgb,var(--status-warning)_10%,transparent)] text-[var(--status-warning)]";
  if (label === "분석 전")
    return "border-[var(--line)] bg-[var(--surface-muted)] text-[var(--text-hint)]";
  return "border-[color-mix(in_srgb,var(--status-success)_36%,transparent)] bg-[color-mix(in_srgb,var(--status-success)_10%,transparent)] text-[var(--status-success)]";
}

function MetricTile({ metric }: { metric: LandMetric }) {
  const isEffective = metric.basis?.startsWith("실효");
  return (
    <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-muted)] p-4 text-center">
      <p className="mb-1 text-[9px] font-black uppercase tracking-widest text-[var(--accent-strong)]">
        현실적 {metric.label}
        {metric.value != null ? (isEffective ? " (실효)" : " (법정상한)") : ""}
      </p>
      <p className="text-2xl font-black text-[var(--text-primary)]">
        {metric.value != null ? metric.value : "—"}
        {metric.value != null && <span className="ml-0.5 text-xs">{metric.unit}</span>}
      </p>
    </div>
  );
}

export function LandProfileCard() {
  const siteAnalysis = useProjectContextStore((s) => s.siteAnalysis);
  const profile = useMemo(() => buildLandProfile(siteAnalysis), [siteAnalysis]);
  const evidence = useMemo(() => landProfileToEvidence(profile), [profile]);

  // 표시할 토지특성이 없으면(주소/PNU/용도지역 미확보) 렌더하지 않음(빈 카드 방지).
  if (!profile) return null;

  const { stageA, stageB, honestNote } = profile;

  return (
    <div className="rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-strong)] p-6 shadow-[var(--shadow-xl)]">
      {/* 헤더 — 1번·중심 강조 */}
      <div className="mb-4 flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-[var(--accent-soft)] text-[var(--accent-strong)]">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M3 11l19-9-9 19-2-8-8-2z" />
          </svg>
        </div>
        <div className="flex-1">
          <h4 className="text-sm font-black text-[var(--text-primary)]">토지특성 분석 (부지 생명력)</h4>
          <p className="text-[9px] font-bold uppercase tracking-widest text-[var(--accent-strong)]">
            모든 분석의 출발점 · 현시점 → 미래
          </p>
        </div>
        {stageA.zoneCode && (
          <span className="shrink-0 rounded-full bg-[var(--accent-soft)] px-3 py-1 text-xs font-black text-[var(--accent-strong)]">
            {stageA.zoneCode}
            {stageA.zoneMixed && (
              <span className="ml-1 rounded-full bg-[color-mix(in_srgb,var(--status-warning)_18%,transparent)] px-1.5 py-0.5 text-[9px] text-[var(--status-warning)]">
                혼재
              </span>
            )}
          </span>
        )}
      </div>

      {/* ── Stage A 현시점 토지특성 ── */}
      <div className="mb-4">
        <p className="mb-2 text-[10px] font-black uppercase tracking-widest text-[var(--text-hint)]">
          ① 현시점 토지특성 <span className="normal-case tracking-normal">(지금 이 땅의 현실적 한도)</span>
        </p>
        <div className="grid grid-cols-2 gap-3">
          <MetricTile metric={stageA.far} />
          <MetricTile metric={stageA.bcr} />
        </div>

        {/* 건축가능분류 */}
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <span className="text-[10px] font-bold text-[var(--text-secondary)]">건축가능분류</span>
          <span
            className={`rounded-full border px-2.5 py-1 text-[10px] font-black ${buildableChip(
              stageA.buildableCategory.code,
              stageA.buildableCategory.label,
            )}`}
          >
            {stageA.buildableCategory.label}
          </span>
          {stageA.buildableCategory.rationale && (
            <span className="text-[10px] text-[var(--text-hint)]">{stageA.buildableCategory.rationale}</span>
          )}
        </div>

        {/* 제한사항 */}
        {stageA.restrictions.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1.5">
            {stageA.restrictions.map((r, i) => (
              <span
                key={`restriction-${i}`}
                className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--line)] bg-[var(--surface-muted)] px-2.5 py-1 text-[10px] font-bold text-[var(--text-secondary)]"
                title={r.detail ?? undefined}
              >
                <span className="inline-block h-1.5 w-1.5 rounded-full" style={{ background: severityDot(r.severity) }} />
                {r.label}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* ── Stage B 미래 토지특성 ── */}
      <div className="mb-4 rounded-xl border border-[color-mix(in_srgb,var(--accent-strong)_22%,transparent)] bg-[var(--surface-muted)] p-4">
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <p className="text-[10px] font-black uppercase tracking-widest text-[var(--text-hint)]">
            ② 미래 토지특성 <span className="normal-case tracking-normal">(조·종상향 가능성)</span>
          </p>
          {stageB.topFeasibility && (
            <span className={`rounded-full border px-2.5 py-1 text-[10px] font-black ${feasibilityChip(stageB.topFeasibility)}`}>
              최상 가능성 {stageB.topFeasibility}
              {stageB.potentialFarHigh != null && ` · 잠재 용적률 ~${stageB.potentialFarHigh}%`}
            </span>
          )}
        </div>

        {stageB.scenarios.length > 0 ? (
          <div className="space-y-2">
            {stageB.scenarios.map((sc, i) => (
              <div key={`scenario-${i}`} className="rounded-lg border border-[var(--line)] bg-[var(--surface-soft)] p-3">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1">
                    <p className="text-xs font-black text-[var(--text-primary)]">{sc.label}</p>
                    {sc.targetZone && (
                      <p className="mt-0.5 text-[10px] font-bold text-[var(--accent-strong)]">→ {sc.targetZone}</p>
                    )}
                  </div>
                  <span className={`shrink-0 rounded-full border px-2 py-0.5 text-[9px] font-black ${feasibilityChip(sc.feasibility)}`}>
                    가능성 {sc.feasibility ?? "—"}
                  </span>
                </div>
                <p className="mt-1 text-[10px] font-bold text-[var(--text-secondary)]">
                  예상 용적률{" "}
                  {sc.potentialFarLow != null ? `${sc.potentialFarLow}% ~ ` : ""}
                  {sc.potentialFarHigh != null ? `${sc.potentialFarHigh}%` : "—"}
                </p>
                {sc.rationale && <p className="mt-0.5 text-[10px] text-[var(--text-hint)]">사유: {sc.rationale}</p>}
                {sc.legalBasis && <p className="mt-0.5 text-[9px] text-[var(--text-hint)]">근거: {sc.legalBasis}</p>}
              </div>
            ))}
          </div>
        ) : (
          <p className="text-[11px] text-[var(--text-hint)]">
            종상향·종변경 잠재 시나리오가 아직 산정되지 않았습니다. 부지분석(토지특성)을 완료하면 자동 갱신됩니다.
          </p>
        )}

        {stageB.scenarios.length > 0 && (
          <p className="mt-2 text-[9px] leading-relaxed text-[var(--text-hint)]">{stageB.disclaimer}</p>
        )}
      </div>

      {/* 산출 근거(설명가능성 표준) */}
      <EvidencePanel items={evidence} title="토지특성 산출 근거" />

      {/* 미해소 정직 고지 */}
      {honestNote && (
        <p className="mt-3 rounded-lg border border-dashed border-[var(--line)] bg-[var(--surface-soft)] px-3 py-2 text-[10px] leading-relaxed text-[var(--text-hint)]">
          {honestNote}
        </p>
      )}
    </div>
  );
}
