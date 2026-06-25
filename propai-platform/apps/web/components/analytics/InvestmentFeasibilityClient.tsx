"use client";

/**
 * 투자 수익성 분석 (ROI 뷰) — 프로젝트 수지(SSOT) 읽기전용 표시.
 *
 * SSOT 정합: 수지의 단일 진실원은 프로젝트 수지분석(FeasibilityEditorV2 + use-feasibility-v2-store)이며,
 * 그 결과가 모세혈관(useProjectContextStore.feasibilityData)에 반영된다. 본 화면은 별도 계산을 하지 않고
 * 해당 store를 구독해 동일한 숫자(순이익·수익률·ROI·ROE·NPV·총사업비·등급)를 표시한다.
 *  ① 수지 미산출 시 "프로젝트 수지분석으로 이동" CTA(무목업: 가짜 0 표기 금지)
 *  ② ROI/ROE/실효 LTV 파생 표시(ROE는 자기자본 입력이 있을 때만, 없으면 "—")
 *  ③ 할루시네이션 검증 + 전문가 패널(회계사·세무사·MBA·디벨로퍼·시공사·증권·저축은행)
 */

import { useMemo } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { Link2 } from "lucide-react";
import { ExpertPanelCard } from "@/components/common/ExpertPanelCard";
import { VerificationBadge } from "@/components/common/VerificationBadge";
import { DecisionReuseBanner } from "@/components/projects/DecisionReuseBanner";
import { findDecisionPart } from "@/components/projects/decision-brief-types";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { isValidLocale } from "@/i18n/config";

function fmtKrw(won: number | null | undefined): string {
  if (won == null || isNaN(won)) return "—";
  const abs = Math.abs(won);
  const sign = won < 0 ? "-" : "";
  if (abs >= 1e8) return `${sign}${(abs / 1e8).toFixed(1)}억`;
  if (abs >= 1e4) return `${sign}${Math.round(abs / 1e4).toLocaleString()}만`;
  return `${sign}${Math.round(abs).toLocaleString()}원`;
}

export function InvestmentFeasibilityClient() {
  const params = useParams() as { locale?: string };
  const locale = isValidLocale(params?.locale ?? "") ? (params.locale as string) : "ko";
  const siteAnalysis = useProjectContextStore((s) => s.siteAnalysis);
  const feasibilityData = useProjectContextStore((s) => s.feasibilityData);
  const costData = useProjectContextStore((s) => s.costData);
  const projectId = useProjectContextStore((s) => s.projectId);
  // ★Tier2 재사용(P2): Stage1 통합 브리프의 '인허가·사업모델 Top3'(Top1·ROI) 도메인 요약을
  //   읽어 'Stage1 통합분석 기반' 배너로 재사용한다(중복 재분석 회피). 브리프 없으면 폴백(미렌더).
  const decisionBrief = useProjectContextStore((s) => s.decisionBrief);
  const briefStale = useProjectContextStore((s) => s.isStale("decisionBrief"));
  const permitBriefPart = findDecisionPart(decisionBrief, "permit_design");

  // 수지 산출 여부(무목업): 매출 또는 총사업비가 실제로 채워졌을 때만 결과로 인정.
  const hasResult = !!(
    feasibilityData &&
    ((feasibilityData.totalRevenueWon ?? 0) > 0 ||
      (feasibilityData.totalCostWon ?? 0) > 0)
  );

  // 파생 지표: 순이익·자기자본수익률(ROE)·타인자본·실효 LTV.
  const derived = useMemo(() => {
    if (!feasibilityData) return null;
    const revenue = feasibilityData.totalRevenueWon ?? null;
    const cost = feasibilityData.totalCostWon ?? null;
    const netProfit =
      revenue != null && cost != null ? revenue - cost : null;
    const equity = feasibilityData.equityWon ?? null;
    const debt =
      cost != null && equity != null ? Math.max(0, cost - equity) : null;
    const roe =
      netProfit != null && equity != null && equity > 0
        ? (netProfit / equity) * 100
        : null;
    const ltv =
      cost != null && cost > 0 && debt != null ? (debt / cost) * 100 : null;
    return { revenue, cost, netProfit, equity, debt, roe, ltv };
  }, [feasibilityData]);

  const feasibilityHref = projectId
    ? `/${locale}/projects/${projectId}/feasibility`
    : `/${locale}/projects`;

  return (
    <section className="grid grid-cols-1 gap-6 min-w-0">
      <div>
        <div className="flex items-center gap-3 mb-1.5">
          <span className="cc-meta">ROI · SSOT FEED</span>
          {hasResult && <span className="cc-live"><i />SYNCED</span>}
        </div>
        <h1 className="text-2xl font-black text-[var(--text-primary)]">투자 수익성 분석 (개발사업 수지 기반)</h1>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">
          프로젝트 <b className="text-[var(--text-primary)]">수지분석</b>에서 산출한 결과를 단일 진실원으로 표시합니다(순이익·수익률·ROI·자기자본수익률·NPV·총사업비). 입력·재계산은 수지분석 화면에서 수행합니다.
        </p>
      </div>

      {/* ★Stage1 통합분석 기반 — 인허가·Top3(Top1·ROI) 도메인 요약 재사용(없으면 미렌더·폴백) */}
      <DecisionReuseBanner part={permitBriefPart} stale={briefStale} />

      {/* 수지 미산출 — CTA(무목업: 가짜 0 대신 정직 안내) */}
      {!hasResult && (
        <div className="rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-soft)] p-6">
          <p className="text-sm font-bold text-[var(--text-primary)]">아직 수지분석 결과가 없습니다.</p>
          <p className="mt-1 text-xs text-[var(--text-secondary)]">
            프로젝트 수지분석에서 토지비·공사비·일반사업비·금융 레버리지·분양매출을 입력하고 계산하면, 그 결과가 이 화면에 자동 반영됩니다.
          </p>
          <Link
            href={feasibilityHref}
            className="mt-4 inline-flex items-center gap-2 rounded-xl bg-[var(--accent-strong)] px-6 py-2.5 text-sm font-black text-white shadow-[var(--shadow-glow)] hover:opacity-90"
          >
            프로젝트 수지분석으로 이동 →
          </Link>
        </div>
      )}

      {/* 결과(읽기전용) */}
      {hasResult && derived && (
        <>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {([
              ["순이익", fmtKrw(derived.netProfit), (derived.netProfit ?? 0) >= 0 ? "text-emerald-400" : "text-rose-400"],
              ["수익률", feasibilityData?.profitRatePct != null ? `${feasibilityData.profitRatePct.toFixed(1)}%` : "—", "text-[var(--accent-strong)]"],
              ["ROI", feasibilityData?.roiPct != null ? `${feasibilityData.roiPct.toFixed(1)}%` : "—", "text-[var(--text-primary)]"],
              ["자기자본수익률(ROE)", derived.roe != null ? `${derived.roe.toFixed(1)}%` : "—", "text-indigo-400"],
              ["NPV", fmtKrw(feasibilityData?.npvWon), (feasibilityData?.npvWon ?? 0) >= 0 ? "text-emerald-400" : "text-rose-400"],
              ["총 분양매출", fmtKrw(derived.revenue), "text-[var(--text-primary)]"],
              ["총 사업비", fmtKrw(derived.cost), "text-[var(--text-primary)]"],
              ["사업성 등급", feasibilityData?.grade || "—", "text-amber-400"],
            ] as [string, string, string][]).map(([k, v, cls]) => (
              <div key={k} className="cc-panel cc-bracketed cc-interactive">
                <i className="cc-bracket cc-bracket--tl" />
                <i className="cc-bracket cc-bracket--br" />
                <div className="cc-grid-bg opacity-30" />
                <div className="relative cc-panel__body p-5">
                  <p className="cc-label">{k}</p>
                  <p className={`cc-num mt-2 text-2xl font-[1000] tracking-tight ${cls}`}>{v}</p>
                </div>
              </div>
            ))}
          </div>

          {/* 총사업비 + 금융 레버리지 */}
          <div className="cc-panel">
            <div className="cc-panel__head">
              <h3 className="text-sm font-black text-[var(--text-primary)]">총사업비·레버리지</h3>
              <span className="cc-meta">CAPITAL STACK</span>
            </div>
            <div className="cc-panel__body">
            <div className="flex flex-wrap items-center gap-x-8 gap-y-2 text-xs">
              <span><b className="cc-label">총 사업비</b> <span className="cc-num text-[var(--text-primary)] font-bold">{fmtKrw(derived.cost)}</span></span>
              <span><b className="cc-label">자기자본</b> <span className="cc-num text-[var(--text-primary)] font-bold">{fmtKrw(derived.equity)}</span></span>
              <span><b className="cc-label">타인자본(추정)</b> <span className="cc-num text-[var(--text-primary)] font-bold">{fmtKrw(derived.debt)}</span></span>
              <span><b className="cc-label">실효 레버리지(LTV)</b> <span className="cc-num text-[var(--accent-strong)] font-bold">{derived.ltv != null ? `${derived.ltv.toFixed(0)}%` : "—"}</span></span>
            </div>
            {derived.equity == null && (
              <p className="mt-3 text-[11px] text-[var(--text-hint)]">※ 자기자본수익률(ROE)·타인자본·LTV는 수지분석에서 자기자본을 입력하면 표시됩니다.</p>
            )}
            {/* 공사비 정밀 분석 연동 표시(단일 데이터원) */}
            {costData?.totalConstructionCostWon != null && (
              <div className="mt-3 inline-flex flex-wrap items-center gap-1.5 rounded-lg bg-[var(--surface-strong)] px-3 py-2 text-[11px] text-[var(--accent-strong)]">
                <Link2 className="size-3.5 shrink-0" aria-hidden />공사비 정밀 분석 연동 — 정밀 총공사비 <b>{fmtKrw(costData.totalConstructionCostWon)}</b>
                {costData.rangeMinWon != null && costData.rangeMaxWon != null && <span className="text-[var(--text-tertiary)]"> (범위 {fmtKrw(costData.rangeMinWon)}~{fmtKrw(costData.rangeMaxWon)})</span>}
              </div>
            )}
            </div>
          </div>

          {/* 할루시네이션 검증 + 전문가 패널(회계사·세무사·MBA·디벨로퍼·시공사·증권·저축은행) */}
          <VerificationBadge analysisType="feasibility" context={{ result: feasibilityData, derived } as unknown as Record<string, unknown>} />
          <ExpertPanelCard
            analysisType="feasibility"
            address={siteAnalysis?.address || ""}
            context={{ result: feasibilityData, derived, requested_experts: ["회계사", "세무사", "MBA", "디벨로퍼", "시공사", "투자증권", "저축은행"] } as unknown as Record<string, unknown>}
          />
        </>
      )}
    </section>
  );
}
