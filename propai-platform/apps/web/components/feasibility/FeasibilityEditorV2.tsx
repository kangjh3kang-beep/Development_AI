"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useFeasibilityV2Store } from "@/store/use-feasibility-v2-store";
import { ProjectTypeSelector } from "./ProjectTypeSelector";
import { ModuleInputForm } from "./ModuleInputForm";
import { FeasibilityResultView } from "./FeasibilityResultView";
import { MonteCarloPanel } from "./MonteCarloPanel";
import { VersionHistoryView } from "./VersionHistoryView";
import { AIRecommendationPanel } from "./AIRecommendationPanel";
import { ExcelExportButton } from "./ExcelExportButton";
import { AutoRecommendPanel } from "./AutoRecommendPanel";
import { EnvironmentSummaryCard } from "@/components/environment/EnvironmentSummaryCard";
import { useProjectContextStore } from "@/store/useProjectContextStore";

interface Props {
  projectId: string;
}

const TABS = [
  { key: "input" as const, label: "Intelligence Input", icon: "⌨️" },
  { key: "result" as const, label: "Analysis Report", icon: "📊" },
  { key: "montecarlo" as const, label: "Risk Simulation", icon: "🎲" },
  { key: "version" as const, label: "History Ledger", icon: "📜" },
] as const;

export function FeasibilityEditorV2({ projectId }: Props) {
  const {
    activeTab,
    setActiveTab,
    result,
    input,
    isCalculating,
    error,
    baselineNeedsInput,
    fetchModules,
    fetchCommitLog,
    calculate,
    runBaseline,
  } = useFeasibilityV2Store();

  const [showAutoRecommend, setShowAutoRecommend] = useState(false);
  const siteAnalysis = useProjectContextStore((s) => s.siteAnalysis);
  const costData = useProjectContextStore((s) => s.costData);
  const isStale = useProjectContextStore((s) => s.isStale);
  const feasibilityCompleteness = useProjectContextStore((s) => s.feasibilityCompleteness);
  const updateFeasibilityData = useProjectContextStore((s) => s.updateFeasibilityData);

  // 마지막 계산에 반영된 공사비(원) — 업스트림 변경(stale) 감지용.
  const [costAtCalc, setCostAtCalc] = useState<number | null>(null);
  // baseline 자동호출 시그니처 가드: 부지(주소+면적+PNU)가 바뀌면 1회 재시도 허용.
  // (이전: boolean 1회 가드 → 면적이 늦게 채워져도 재호출 안 됨. 시그니처로 self-reset)
  const baselineTriedSigRef = useRef<string | null>(null);

  useEffect(() => {
    fetchModules();
    fetchCommitLog(projectId);
  }, [fetchModules, fetchCommitLog, projectId]);

  // 결과가 산출되면 모세혈관(feasibilityData)에 반영 — 완성도/금융단계·stale 타임스탬프 갱신.
  useEffect(() => {
    if (!result) return;
    updateFeasibilityData({
      totalCostWon: result.total_cost_won ?? null,
      totalRevenueWon: result.total_revenue_won ?? null,
      profitRatePct: result.profit_rate_pct ?? null,
      grade: result.grade ?? null,
      // 투자수익성(ROI 뷰, analytics/investment) 정합용 — A를 단일 진실원으로.
      roiPct: result.roi_pct ?? null,
      npvWon: result.npv_won ?? null,
      equityWon: input.equity_won ?? null,
    });
    setCostAtCalc(costData?.totalConstructionCostWon ?? null);
    // costData는 의도적으로 제외(결과 변경 시에만 stamp, 무한루프 방지).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [result, updateFeasibilityData]);

  // baseline 자동 산출: 결과가 없고 부지 데이터(주소/면적)만 있을 때 추정 수지.
  // 시그니처 가드 — 동일 부지 입력으로는 1회만, 면적/주소/PNU가 늦게 채워지면(시그니처
  // 변경) 재시도 1회 허용. 무한루프 방지: 동일 시그니처면 skip, busy(isCalculating) 가드.
  useEffect(() => {
    if (result || isCalculating) return;
    const hasSite = !!(siteAnalysis?.address || (siteAnalysis?.landAreaSqm ?? 0) > 0);
    if (!hasSite) return;
    const sig = `${siteAnalysis?.address ?? ""}|${siteAnalysis?.landAreaSqm ?? 0}|${siteAnalysis?.pnu ?? ""}`;
    if (baselineTriedSigRef.current === sig) return;
    baselineTriedSigRef.current = sig;
    void runBaseline({
      address: siteAnalysis?.address ?? "",
      zone_code: siteAnalysis?.zoneCode ?? "",
      land_area_sqm: siteAnalysis?.landAreaSqm ?? 0,
      pnu: siteAnalysis?.pnu ?? "",
      official_price_per_sqm: siteAnalysis?.officialPrices?.[0]?.pricePerSqm ?? 0,
    });
  }, [result, isCalculating, siteAnalysis, runBaseline]);

  // 업스트림(공사비) 변경 stale 판정: 결과가 있고, 공사비가 수지보다 최신이거나
  // 직전 계산 공사비와 현재가 다르면 재계산 필요. baseline 결과는 stale 대상에서 제외.
  const isFeasibilityStale = useMemo(() => {
    if (!result || result.is_baseline) return false;
    const cur = costData?.totalConstructionCostWon ?? null;
    if (isStale("feasibility")) return true;
    return cur != null && costAtCalc != null && cur !== costAtCalc;
  }, [result, costData, costAtCalc, isStale]);

  // stale 시 1회 자동 재계산(무한루프 방지: 재계산 후 costAtCalc 갱신 → stale=false).
  // ★R2 가드(무목업): /feasibility/calculate는 매출입력(분양단가·세대수)이 비어 있으면
  // revenue=0을 반환해 ROI -100%로 다운스트림(ROI 뷰)을 오염시킨다. 매출 파라미터가
  // 없으면 자동재계산은 calculate 대신 baseline(zone역산: 실제 매출 추정)을 재실행해
  // 매출 0/적자위험 위양성을 막고 정직한 추정값을 유지한다. 사용자가 실제 매출입력을
  // 채운 경우에만 정밀 calculate로 재계산한다.
  const hasRevenueInputs =
    (input.avg_sale_price_per_pyeong ?? 0) > 0 &&
    ((input.total_households ?? 0) > 0 || (input.avg_area_pyeong ?? 0) > 0);
  useEffect(() => {
    if (!isFeasibilityStale || isCalculating) return;
    if (hasRevenueInputs) {
      void calculate({ constructionCostOverrideWon: costData?.totalConstructionCostWon });
    } else {
      // 면적 등 부지 시그니처를 self-reset해 baseline 재시도를 1회 허용.
      baselineTriedSigRef.current = null;
      void runBaseline({
        address: siteAnalysis?.address ?? "",
        zone_code: siteAnalysis?.zoneCode ?? "",
        land_area_sqm: siteAnalysis?.landAreaSqm ?? 0,
        pnu: siteAnalysis?.pnu ?? "",
        official_price_per_sqm: siteAnalysis?.officialPrices?.[0]?.pricePerSqm ?? 0,
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isFeasibilityStale]);

  const completeness = feasibilityCompleteness();

  return (
    <div className="flex flex-col gap-10">
      {/* ── 완성도/신뢰도(모세혈관 반영도) ── */}
      <div className="rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-soft)] px-5 py-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <span className="text-[10px] font-[1000] uppercase tracking-[0.3em] text-[var(--text-hint)]">
              데이터 반영도
            </span>
            {result?.is_baseline && (
              <span className="rounded-full bg-amber-500/15 px-2 py-0.5 text-[10px] font-bold text-amber-400">
                추정(시장표준){result.confidence ? ` · 신뢰도 ${result.confidence}` : ""}
              </span>
            )}
          </div>
          <span className="text-sm font-[900] text-[var(--accent-strong)]">{completeness.pct}%</span>
        </div>
        {/* 반영도 바 */}
        <div className="mt-2 h-2 w-full overflow-hidden rounded-full bg-[var(--surface-muted)]">
          <div
            className="h-full rounded-full bg-[var(--accent-strong)] transition-all duration-500"
            style={{ width: `${completeness.pct}%` }}
          />
        </div>
        {/* 단계 칩 */}
        <div className="mt-3 flex flex-wrap gap-2">
          {completeness.stages.map((st) => (
            <span
              key={st.key}
              className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-[11px] font-bold ${
                st.done
                  ? "bg-emerald-500/15 text-emerald-400"
                  : "bg-[var(--surface-muted)] text-[var(--text-tertiary)]"
              }`}
            >
              <span className={`inline-block h-1.5 w-1.5 rounded-full ${st.done ? "bg-emerald-400" : "bg-[var(--text-hint)]"}`} />
              {st.label} {st.done ? "반영" : "대기"}
            </span>
          ))}
        </div>
        <p className="mt-2 text-[10px] text-[var(--text-hint)]">
          단계가 완성될수록 수지분석이 자동으로 정교화됩니다(부지 30% → 설계 60% → 공사비 85% → 금융 100%).
        </p>
      </div>

      {/* ── 업스트림 변경(stale) 자동 재계산 배너 ── */}
      <AnimatePresence>
        {isFeasibilityStale && (
          <motion.div
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            className="-mb-6 flex items-center gap-3 rounded-xl border border-amber-500/30 bg-amber-500/10 px-5 py-3 text-xs font-bold text-amber-400"
          >
            <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-amber-400" />
            업스트림(공사비) 변경 감지 — 수지분석을 자동 재계산합니다.
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── 추정 입력 부족(422) 안내 배너 — 사일런트 금지, 입력 유도 ── */}
      <AnimatePresence>
        {baselineNeedsInput && !result && (
          <motion.div
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            className="-mb-6 flex flex-wrap items-center gap-3 rounded-xl border border-amber-500/30 bg-amber-500/10 px-5 py-3 text-xs font-bold text-amber-400"
          >
            <span className="inline-block h-2 w-2 rounded-full bg-amber-400" />
            부지면적 또는 정확한 주소(시·구·동·번지)를 입력하면 추정 수지가 자동 산출됩니다.
            {activeTab !== "input" && (
              <button
                onClick={() => setActiveTab("input")}
                className="ml-auto rounded-full bg-amber-500/20 px-3 py-1 font-[900] uppercase tracking-wider transition-colors hover:bg-amber-500/30"
              >
                입력 탭 →
              </button>
            )}
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Auto Recommend CTA ── */}
      <div className="flex items-center gap-4 px-2">
        <button
          onClick={() => setShowAutoRecommend(true)}
          className="flex items-center gap-3 rounded-2xl border border-[var(--accent-strong)]/30 bg-[var(--accent-soft)] px-6 py-3 text-sm font-[900] text-[var(--accent-strong)] shadow-[var(--shadow-sm)] transition-all hover:bg-[var(--accent-strong)] hover:text-white hover:shadow-[var(--shadow-glow)]"
        >
          <span>{"\uD83D\uDD0D"}</span>
          최적 모델 자동 추천
        </button>
        <span className="text-xs text-[var(--text-hint)]">
          AI가 12개 사업모델을 분석하여 최적 Top 3를 추천합니다
        </span>
      </div>

      {/* ── Auto Recommend Modal Overlay ── */}
      <AnimatePresence>
        {showAutoRecommend && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 overflow-y-auto bg-black/60 backdrop-blur-sm"
            onClick={(e) => {
              if (e.target === e.currentTarget) setShowAutoRecommend(false);
            }}
          >
            <div className="flex min-h-full items-start justify-center p-6 pt-20">
              <motion.div
                initial={{ opacity: 0, scale: 0.95, y: 20 }}
                animate={{ opacity: 1, scale: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.95, y: 20 }}
                className="w-full max-w-5xl rounded-[3rem] border border-[var(--line-strong)] bg-[var(--surface-strong)] p-10 shadow-2xl"
              >
                <AutoRecommendPanel isModal onClose={() => setShowAutoRecommend(false)} />
              </motion.div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── High-Fidelity Tab Navigation ── */}
      <div className="flex flex-col gap-6 lg:flex-row lg:items-center lg:justify-between px-2">
        <div className="flex items-center gap-2 rounded-[2.5rem] border border-[var(--line-strong)] bg-[var(--surface-strong)] p-1.5 backdrop-blur-xl shadow-[var(--shadow-xl)]">
          {TABS.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`relative flex items-center gap-3 rounded-full px-6 py-3 text-[11px] font-[1000] uppercase tracking-widest transition-all ${
                activeTab === tab.key
                  ? "text-white"
                  : "text-[var(--text-hint)] hover:text-[var(--text-secondary)] hover:bg-[var(--line)]/5"
              }`}
            >
              {activeTab === tab.key && (
                <motion.div
                  layoutId="activeTabFeasibility"
                  className="absolute inset-0 rounded-full bg-[var(--accent-strong)] shadow-[var(--shadow-glow)]"
                  transition={{ type: "spring", bounce: 0.2, duration: 0.6 }}
                />
              )}
              <span className="relative z-10">{tab.icon}</span>
              <span className="relative z-10">{tab.label}</span>
            </button>
          ))}
        </div>

        <div className="flex items-center gap-4">
          <AnimatePresence mode="wait">
            {isCalculating && (
              <motion.div 
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -20 }}
                className="flex items-center gap-3 rounded-xl border border-[var(--accent-strong)]/30 bg-[var(--accent-soft)] px-5 py-2.5 text-[10px] font-black uppercase tracking-widest text-[var(--accent-strong)] backdrop-blur-md"
              >
                <div className="h-2.5 w-2.5 animate-spin rounded-full border-2 border-[var(--accent-strong)] border-t-transparent" />
                Processing Engine...
              </motion.div>
            )}
          </AnimatePresence>
          {result && <ExcelExportButton />}
        </div>
      </div>

      {/* ── Status Messages ── */}
      <AnimatePresence>
        {error && (
          <motion.div 
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.95 }}
            className="rounded-[2rem] border border-rose-500/20 bg-rose-500/10 p-6 text-sm font-bold text-rose-400 backdrop-blur-3xl shadow-2xl flex items-center gap-4"
          >
            <div className="h-10 w-10 rounded-2xl bg-rose-500/20 flex items-center justify-center text-rose-400">
              <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" x2="12" y1="8" y2="12"/><line x1="12" x2="12.01" y1="16" y2="16"/></svg>
            </div>
            {error}
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Studio Content Area ── */}
      <div className="relative min-h-[600px]">
        <AnimatePresence mode="wait">
          {activeTab === "input" && (
            <motion.div
              key="input"
              initial={{ opacity: 0, y: 30 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -30, filter: "blur(10px)" }}
              className="grid gap-10 lg:grid-cols-[340px_1fr]"
            >
              <div className="space-y-6">
                 <div className="glass rounded-[2.5rem] p-8 border border-[var(--line-strong)] bg-[var(--surface-strong)] shadow-[var(--shadow-2xl)]">
                    <p className="text-[10px] font-[1000] uppercase tracking-[0.4em] text-[var(--text-hint)] mb-6">Execution Strategy</p>
                    <ProjectTypeSelector />
                 </div>
              </div>
              <div className="glass rounded-[3rem] p-1 border border-[var(--line)] bg-[var(--surface-soft)] overflow-hidden shadow-[var(--shadow-xl)]">
                 <div className="rounded-[3rem] p-10 bg-[var(--surface-strong)] backdrop-blur-3xl">
                    <ModuleInputForm />
                 </div>
              </div>
            </motion.div>
          )}

          {activeTab === "result" && (
            <motion.div
              key="result"
              initial={{ opacity: 0, y: 30 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -30, filter: "blur(10px)" }}
              className="space-y-10"
            >
              {/* 결과 없음 + 추정 입력 부족(422): 빈 0 대신 입력 유도 게이트(무목업). */}
              {!result && baselineNeedsInput ? (
                <div className="glass rounded-[3rem] border border-amber-500/30 bg-amber-500/5 p-12 text-center shadow-[var(--shadow-xl)]">
                  <div className="mx-auto mb-6 flex h-16 w-16 items-center justify-center rounded-2xl bg-amber-500/15 text-amber-400">
                    <svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 9v4" /><path d="M12 17h.01" /><path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" /></svg>
                  </div>
                  <p className="text-lg font-[900] text-[var(--text-primary)]">
                    수지 추정에 필요한 정보가 부족합니다
                  </p>
                  <p className="mt-3 text-sm leading-relaxed text-[var(--text-secondary)]">
                    부지면적 또는 정확한 주소(시·구·동·번지)를 입력하면 자동 산출됩니다.
                  </p>
                  <button
                    onClick={() => setActiveTab("input")}
                    className="mt-8 inline-flex items-center gap-2 rounded-full bg-[var(--accent-strong)] px-8 py-3 text-xs font-[900] uppercase tracking-[0.2em] text-white shadow-[var(--shadow-glow)] transition-all hover:scale-105"
                  >
                    입력 탭으로 이동 ↗
                  </button>
                </div>
              ) : (
                <FeasibilityResultView />
              )}
              {/* 조망·스카이라인 보조카드(분양가치 근거 — 환경3D 녹여내기) */}
              {(siteAnalysis?.address || siteAnalysis?.pnu) && (
                <EnvironmentSummaryCard
                  address={siteAnalysis?.address}
                  pnu={siteAnalysis?.pnu}
                  focus="view"
                />
              )}
              <div className="glass rounded-[3rem] p-1 border border-[var(--line)] bg-[var(--surface-soft)] overflow-hidden shadow-[var(--shadow-xl)]">
                <div className="rounded-[3rem] p-12 bg-[var(--surface-strong)] backdrop-blur-3xl">
                  <AIRecommendationPanel />
                </div>
              </div>
            </motion.div>
          )}

          {activeTab === "montecarlo" && (
            <motion.div
              key="montecarlo"
              initial={{ opacity: 0, scale: 0.98 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.98, filter: "blur(10px)" }}
            >
              <MonteCarloPanel />
            </motion.div>
          )}

          {activeTab === "version" && (
            <motion.div
              key="version"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
            >
              <VersionHistoryView projectId={projectId} />
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
