"use client";

import { useState, useCallback, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useParams, useRouter } from "next/navigation";
import { TiltCard } from "@/components/ui/TiltCard";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { useFeasibilityV2Store } from "@/store/use-feasibility-v2-store";
import { apiClient } from "@/lib/api-client";
import { BusinessModelRefineModal } from "./BusinessModelRefineModal";

/* ── Types ── */

export interface RecommendedModel {
  rank: number;
  type_code: string;
  type_name: string;
  profit_rate_pct: number;
  roi_pct: number;
  grade: string;
  permit_ease: string;
  total_revenue_won: number;
  net_profit_won: number;
  project_months: number;
  total_gfa_sqm: number;
  total_households: number;
  avg_sale_price_per_pyeong: number;
  composite_score: number;
  ai_summary: string;
}

interface AutoRecommendResponse {
  recommendations: RecommendedModel[];
  all_models: RecommendedModel[];
  analysis_count: number;
}

/* ── Constants ── */

const REGIONS = [
  "서울특별시",
  "경기도",
  "인천광역시",
  "부산광역시",
  "대구광역시",
  "대전광역시",
  "광주광역시",
  "울산광역시",
  "세종특별자치시",
  "강원도",
  "충청북도",
  "충청남도",
  "전라북도",
  "전라남도",
  "경상북도",
  "경상남도",
  "제주특별자치도",
] as const;

const GRADE_COLORS: Record<string, string> = {
  A: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30",
  B: "bg-blue-500/15 text-blue-400 border-blue-500/30",
  C: "bg-amber-500/15 text-amber-400 border-amber-500/30",
  D: "bg-orange-500/15 text-orange-400 border-orange-500/30",
  F: "bg-red-500/15 text-red-400 border-red-500/30",
};

const PERMIT_COLORS: Record<string, string> = {
  "매우쉬움": "bg-emerald-500/15 text-emerald-400",
  "쉬움": "bg-green-500/15 text-green-400",
  "보통": "bg-yellow-500/15 text-yellow-400",
  "어려움": "bg-red-500/15 text-red-400",
  "매우어려움": "bg-red-600/15 text-red-500",
};

const RANK_STYLES = [
  {
    emoji: "\uD83E\uDD47",
    label: "1위",
    border: "border-yellow-500/40",
    glow: "rgba(234,179,8,0.6)",
    bg: "bg-yellow-500/5",
    accent: "text-yellow-400",
  },
  {
    emoji: "\uD83E\uDD48",
    label: "2위",
    border: "border-slate-400/40",
    glow: "rgba(148,163,184,0.5)",
    bg: "bg-slate-400/5",
    accent: "text-slate-300",
  },
  {
    emoji: "\uD83E\uDD49",
    label: "3위",
    border: "border-amber-700/40",
    glow: "rgba(180,83,9,0.5)",
    bg: "bg-amber-800/5",
    accent: "text-amber-600",
  },
];

/* ── Helpers ── */

function formatBillionWon(won: number): string {
  const eok = won / 100_000_000;
  if (eok >= 10000) return `${(eok / 10000).toFixed(1)}조`;
  if (eok >= 1) return `${eok.toFixed(0)}억`;
  return `${(won / 10_000).toFixed(0)}만`;
}

/* ── Component ── */

interface AutoRecommendPanelProps {
  onClose?: () => void;
  isModal?: boolean;
}

export function AutoRecommendPanel({ onClose, isModal = false }: AutoRecommendPanelProps) {
  const { locale, id: projectId } = useParams() as { locale: string; id: string };
  const router = useRouter();
  const ctxStore = useProjectContextStore();
  // 분석 완료 후 주소를 컨텍스트 스토어에 저장하여 다른 모듈에서 공유 (모세혈관 네트워크 주소 공유 패턴)
  const updateSiteAnalysis = useProjectContextStore((s) => s.updateSiteAnalysis);
  const feasibilityStore = useFeasibilityV2Store();

  // Input state
  const [address, setAddress] = useState(ctxStore.siteAnalysis?.address ?? "");
  const [region, setRegion] = useState("서울특별시");
  const [landArea, setLandArea] = useState(ctxStore.siteAnalysis?.landAreaSqm?.toString() ?? "");
  const [equity, setEquity] = useState("");

  // Result state
  const [isLoading, setIsLoading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [topModels, setTopModels] = useState<RecommendedModel[]>([]);
  const [allModels, setAllModels] = useState<RecommendedModel[]>([]);
  const [analysisCount, setAnalysisCount] = useState(0);
  const [showFullTable, setShowFullTable] = useState(false);

  // Modal state
  const [selectedModel, setSelectedModel] = useState<RecommendedModel | null>(null);
  const [showRefineModal, setShowRefineModal] = useState(false);

  const progressRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const handleAnalyze = useCallback(async () => {
    if (!address.trim()) {
      setError("주소를 입력해주세요.");
      return;
    }

    setIsLoading(true);
    setError(null);
    setProgress(0);
    setTopModels([]);
    setAllModels([]);

    // Simulate progress
    progressRef.current = setInterval(() => {
      setProgress((p) => {
        if (p >= 90) {
          if (progressRef.current) clearInterval(progressRef.current);
          return 90;
        }
        return p + Math.random() * 15;
      });
    }, 300);

    try {
      // 실제 백엔드 /auto-recommend API 호출
      const response = await apiClient.postV2<AutoRecommendResponse>("/feasibility/auto-recommend", {
        body: {
          address: address.trim(),
          land_area_sqm: landArea ? parseFloat(landArea) : undefined,
          region,
          equity_won: equity ? parseFloat(equity) * 1e8 : undefined,
        },
      });

      if (progressRef.current) clearInterval(progressRef.current);
      setProgress(100);
      setTopModels(response.recommendations.slice(0, 3));
      setAllModels(response.all_models ?? response.recommendations);
      setAnalysisCount(response.analysis_count);

      // 분석 완료 후 주소를 컨텍스트 스토어에 저장하여 다른 모듈에서 공유
      updateSiteAnalysis({
        ...ctxStore.siteAnalysis,
        estimatedValue: ctxStore.siteAnalysis?.estimatedValue ?? null,
        landAreaSqm: landArea ? parseFloat(landArea) : ctxStore.siteAnalysis?.landAreaSqm ?? null,
        zoneCode: ctxStore.siteAnalysis?.zoneCode ?? null,
        address: address,
        pnu: ctxStore.siteAnalysis?.pnu ?? null,
      });
    } catch (e: unknown) {
      if (progressRef.current) clearInterval(progressRef.current);
      setError(e instanceof Error ? e.message : "분석에 실패했습니다. 다시 시도해주세요.");
    } finally {
      setIsLoading(false);
    }
  }, [address, region, landArea, equity]);

  const handleSelectModel = useCallback((model: RecommendedModel) => {
    setSelectedModel(model);
    setShowRefineModal(true);
  }, []);

  const handleRefineConfirm = useCallback(
    (refined: {
      total_gfa_sqm: number;
      total_households: number;
      avg_sale_price_per_pyeong: number;
      equity_won: number;
      project_months: number;
      discount_rate: number;
    }) => {
      if (!selectedModel) return;

      // Save to project context store
      ctxStore.updateFeasibilityData({
        totalCostWon: null,
        totalRevenueWon: selectedModel.total_revenue_won,
        profitRatePct: selectedModel.profit_rate_pct,
        grade: selectedModel.grade,
      });

      // Save to feasibility store
      feasibilityStore.setSelectedModule(selectedModel.type_code);
      feasibilityStore.setInput({
        development_type: selectedModel.type_code,
        total_land_area_sqm: landArea ? parseFloat(landArea) : 0,
        total_gfa_sqm: refined.total_gfa_sqm,
        total_households: refined.total_households,
        avg_sale_price_per_pyeong: refined.avg_sale_price_per_pyeong,
        equity_won: refined.equity_won,
        project_months: refined.project_months,
        discount_rate: refined.discount_rate,
        sido_name: region,
      });

      setShowRefineModal(false);

      // Navigate to feasibility editor
      router.push(`/${locale}/projects/${projectId}/feasibility`);
    },
    [selectedModel, ctxStore, feasibilityStore, landArea, region, locale, projectId, router],
  );

  return (
    <div className="flex flex-col gap-8">
      {/* ── Header ── */}
      <div className="flex items-start justify-between">
        <div className="space-y-3">
          <div className="flex items-center gap-3">
            <span className="text-3xl">{"\uD83C\uDFD7\uFE0F"}</span>
            <h2 className="text-3xl font-[1000] tracking-tight text-[var(--text-primary)]">
              최적 사업모델 자동 추천
            </h2>
          </div>
          <p className="text-sm text-[var(--text-secondary)] max-w-xl">
            부지 정보를 입력하면 AI가 최적의 사업모델 Top 3를 추천합니다.
            수익률, ROI, 인허가 난이도, 시장성을 종합적으로 분석합니다.
          </p>
        </div>
        {isModal && onClose && (
          <button
            onClick={onClose}
            className="rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-soft)] p-3 text-[var(--text-hint)] hover:text-[var(--text-primary)] transition-colors"
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <path d="M18 6L6 18M6 6l12 12" />
            </svg>
          </button>
        )}
      </div>

      {/* ── Input Form ── */}
      <div className="rounded-[2rem] border border-[var(--line-strong)] bg-[var(--surface-strong)] p-8 shadow-[var(--shadow-xl)]">
        <div className="flex flex-col gap-6">
          {/* Row 1: Address + Region */}
          <div className="flex flex-col gap-4 lg:flex-row">
            <div className="flex-1">
              <label className="mb-2 block text-[10px] font-[900] uppercase tracking-[0.3em] text-[var(--text-hint)]">
                주소 입력
              </label>
              {/* 주소 검색 입력: 부지분석 주소를 기본값으로 사용하며, 분석 완료 시 스토어에 저장 */}
              <div className="relative">
                <svg className="absolute left-4 top-1/2 -translate-y-1/2 text-[var(--text-hint)]" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>
                <input
                  type="text"
                  value={address}
                  onChange={(e) => setAddress(e.target.value)}
                  placeholder="주소를 검색하세요 (예: 서울특별시 강남구 삼성동)"
                  className="w-full rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] pl-11 pr-5 py-3.5 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-hint)] focus:border-[var(--accent-strong)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-strong)]/20 transition-all"
                />
              </div>
              {ctxStore.siteAnalysis?.address && address === ctxStore.siteAnalysis.address && (
                <p className="text-[10px] text-[var(--text-hint)] -mt-1">
                  📍 부지분석에서 설정된 주소입니다
                </p>
              )}
            </div>
            <div className="w-full lg:w-56">
              <label className="mb-2 block text-[10px] font-[900] uppercase tracking-[0.3em] text-[var(--text-hint)]">
                지역 선택
              </label>
              <select
                value={region}
                onChange={(e) => setRegion(e.target.value)}
                className="w-full rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] px-5 py-3.5 text-sm text-[var(--text-primary)] focus:border-[var(--accent-strong)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-strong)]/20 transition-all appearance-none cursor-pointer"
              >
                {REGIONS.map((r) => (
                  <option key={r} value={r}>
                    {r}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Row 2: Land Area + Equity + Button */}
          <div className="flex flex-col gap-4 lg:flex-row lg:items-end">
            <div className="flex-1">
              <label className="mb-2 block text-[10px] font-[900] uppercase tracking-[0.3em] text-[var(--text-hint)]">
                대지면적 (m{"\u00B2"})
              </label>
              <input
                type="number"
                value={landArea}
                onChange={(e) => setLandArea(e.target.value)}
                placeholder="1,500"
                className="w-full rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] px-5 py-3.5 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-hint)] focus:border-[var(--accent-strong)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-strong)]/20 transition-all"
              />
            </div>
            <div className="flex-1">
              <label className="mb-2 block text-[10px] font-[900] uppercase tracking-[0.3em] text-[var(--text-hint)]">
                자기자본 (억원)
              </label>
              <input
                type="number"
                value={equity}
                onChange={(e) => setEquity(e.target.value)}
                placeholder="100"
                className="w-full rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] px-5 py-3.5 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-hint)] focus:border-[var(--accent-strong)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-strong)]/20 transition-all"
              />
            </div>
            <button
              onClick={handleAnalyze}
              disabled={isLoading || !address.trim()}
              className="flex items-center justify-center gap-3 rounded-xl bg-[var(--accent-strong)] px-8 py-3.5 text-sm font-[900] text-white shadow-[var(--shadow-glow)] transition-all hover:brightness-110 hover:shadow-lg disabled:opacity-50 disabled:cursor-not-allowed whitespace-nowrap"
            >
              {isLoading ? (
                <div className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
              ) : (
                <span>{"\uD83D\uDD0D"}</span>
              )}
              분석 시작
            </button>
          </div>
        </div>
      </div>

      {/* ── Error ── */}
      <AnimatePresence>
        {error && (
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.95 }}
            className="rounded-2xl border border-rose-500/20 bg-rose-500/10 p-5 text-sm font-bold text-rose-400 flex items-center gap-3"
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <circle cx="12" cy="12" r="10" />
              <line x1="12" x2="12" y1="8" y2="12" />
              <line x1="12" x2="12.01" y1="16" y2="16" />
            </svg>
            {error}
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Progress Bar ── */}
      <AnimatePresence>
        {isLoading && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            className="space-y-3"
          >
            <div className="flex items-center justify-between text-xs">
              <span className="font-[900] text-[var(--accent-strong)]">
                {analysisCount > 0 ? `${analysisCount}개` : "12개"} 사업모델 시뮬레이션 중...
              </span>
              <span className="text-[var(--text-hint)] font-bold tabular-nums">
                {Math.min(Math.round(progress), 100)}%
              </span>
            </div>
            <div className="h-2 w-full overflow-hidden rounded-full bg-[var(--surface-muted)]">
              <motion.div
                className="h-full rounded-full bg-gradient-to-r from-[var(--accent-strong)] to-blue-500"
                initial={{ width: "0%" }}
                animate={{ width: `${Math.min(progress, 100)}%` }}
                transition={{ ease: "easeOut" }}
              />
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Top 3 Cards ── */}
      <AnimatePresence>
        {topModels.length > 0 && (
          <motion.div
            initial={{ opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 }}
            className="grid gap-6 lg:grid-cols-3"
          >
            {topModels.map((model, idx) => {
              const style = RANK_STYLES[idx] ?? RANK_STYLES[2];
              const gradeColor = GRADE_COLORS[model.grade] ?? GRADE_COLORS.C;
              const permitColor = PERMIT_COLORS[model.permit_ease] ?? PERMIT_COLORS["보통"];

              return (
                <TiltCard
                  key={model.type_code}
                  glowColor={style.glow}
                  className="rounded-[2.5rem]"
                >
                  <motion.div
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.1 * (idx + 1) }}
                    className={`relative flex flex-col gap-6 rounded-[2.5rem] border-2 ${style.border} ${style.bg} p-8 backdrop-blur-xl shadow-[var(--shadow-xl)] h-full`}
                  >
                    {/* Rank Badge */}
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        <span className="text-2xl">{style.emoji}</span>
                        <span className={`text-[10px] font-[1000] uppercase tracking-[0.4em] ${style.accent}`}>
                          {style.label}
                        </span>
                      </div>
                      <span className={`rounded-xl border px-3 py-1 text-[11px] font-[900] ${gradeColor}`}>
                        {model.grade}등급
                      </span>
                    </div>

                    {/* Model Name */}
                    <div>
                      <p className="text-[10px] font-bold text-[var(--text-hint)] tracking-wider">
                        {model.type_code}
                      </p>
                      <h3 className="text-2xl font-[1000] tracking-tight text-[var(--text-primary)]">
                        {model.type_name}
                      </h3>
                    </div>

                    {/* Key Metrics */}
                    <div className="grid grid-cols-2 gap-4">
                      <div className="rounded-xl bg-[var(--surface-muted)]/50 p-4">
                        <p className="text-[10px] font-bold text-[var(--text-hint)] tracking-wider mb-1">수익률</p>
                        <p className="text-xl font-[1000] text-[var(--accent-strong)] tabular-nums">
                          {model.profit_rate_pct.toFixed(1)}%
                        </p>
                      </div>
                      <div className="rounded-xl bg-[var(--surface-muted)]/50 p-4">
                        <p className="text-[10px] font-bold text-[var(--text-hint)] tracking-wider mb-1">ROI</p>
                        <p className="text-xl font-[1000] text-[var(--text-primary)] tabular-nums">
                          {model.roi_pct.toFixed(1)}%
                        </p>
                      </div>
                    </div>

                    {/* Details */}
                    <div className="space-y-3 text-sm">
                      <div className="flex items-center justify-between">
                        <span className="text-[var(--text-hint)]">인허가</span>
                        <span className={`rounded-lg px-3 py-0.5 text-xs font-[800] ${permitColor}`}>
                          {model.permit_ease}
                        </span>
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="text-[var(--text-hint)]">총수입</span>
                        <span className="font-[800] text-[var(--text-primary)] tabular-nums">
                          {formatBillionWon(model.total_revenue_won)}원
                        </span>
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="text-[var(--text-hint)]">순이익</span>
                        <span className="font-[800] text-[var(--accent-strong)] tabular-nums">
                          {formatBillionWon(model.net_profit_won)}원
                        </span>
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="text-[var(--text-hint)]">사업기간</span>
                        <span className="font-[800] text-[var(--text-primary)]">
                          {model.project_months}개월
                        </span>
                      </div>
                    </div>

                    {/* CTA */}
                    <button
                      onClick={() => handleSelectModel(model)}
                      className={`mt-auto w-full rounded-xl border ${style.border} bg-[var(--surface-strong)] px-6 py-3.5 text-sm font-[900] text-[var(--text-primary)] transition-all hover:bg-[var(--accent-strong)] hover:text-white hover:border-[var(--accent-strong)] hover:shadow-[var(--shadow-glow)]`}
                    >
                      이 모델로 시작 {"\u2192"}
                    </button>
                  </motion.div>
                </TiltCard>
              );
            })}
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Full Comparison Table ── */}
      {allModels.length > 0 && (
        <div className="space-y-4">
          <button
            onClick={() => setShowFullTable((v) => !v)}
            className="flex items-center gap-3 text-sm font-[900] text-[var(--text-secondary)] hover:text-[var(--accent-strong)] transition-colors"
          >
            <span>{"\uD83D\uDCCA"}</span>
            전체 {allModels.length}개 모델 비교표
            <svg
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.5"
              className={`transition-transform ${showFullTable ? "rotate-180" : ""}`}
            >
              <polyline points="6 9 12 15 18 9" />
            </svg>
          </button>

          <AnimatePresence>
            {showFullTable && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: "auto" }}
                exit={{ opacity: 0, height: 0 }}
                className="overflow-hidden"
              >
                <div className="overflow-x-auto rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-strong)] shadow-[var(--shadow-xl)]">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-[var(--line)] text-left">
                        {["순위", "모델", "수익률", "ROI", "등급", "인허가", "총수입", "순이익", "기간", "종합점수"].map(
                          (h) => (
                            <th
                              key={h}
                              className="px-4 py-3 text-[10px] font-[1000] uppercase tracking-[0.3em] text-[var(--text-hint)] whitespace-nowrap"
                            >
                              {h}
                            </th>
                          ),
                        )}
                      </tr>
                    </thead>
                    <tbody>
                      {allModels.map((model, idx) => {
                        const gradeColor = GRADE_COLORS[model.grade] ?? GRADE_COLORS.C;
                        const permitColor = PERMIT_COLORS[model.permit_ease] ?? PERMIT_COLORS["보통"];
                        const isTop3 = idx < 3;

                        return (
                          <tr
                            key={model.type_code}
                            className={`border-b border-[var(--line)]/50 transition-colors hover:bg-[var(--surface-soft)] ${isTop3 ? "bg-[var(--accent-soft)]/30" : ""}`}
                          >
                            <td className="px-4 py-3 font-[900] text-[var(--text-primary)] tabular-nums">
                              {idx + 1}
                            </td>
                            <td className="px-4 py-3">
                              <div>
                                <span className="font-[800] text-[var(--text-primary)]">{model.type_name}</span>
                                <span className="ml-2 text-[var(--text-hint)] text-xs">{model.type_code}</span>
                              </div>
                            </td>
                            <td className="px-4 py-3 font-[800] text-[var(--accent-strong)] tabular-nums">
                              {model.profit_rate_pct.toFixed(1)}%
                            </td>
                            <td className="px-4 py-3 font-[800] text-[var(--text-primary)] tabular-nums">
                              {model.roi_pct.toFixed(1)}%
                            </td>
                            <td className="px-4 py-3">
                              <span className={`inline-block rounded-lg border px-2 py-0.5 text-xs font-[800] ${gradeColor}`}>
                                {model.grade}
                              </span>
                            </td>
                            <td className="px-4 py-3">
                              <span className={`inline-block rounded-lg px-2 py-0.5 text-xs font-[800] ${permitColor}`}>
                                {model.permit_ease}
                              </span>
                            </td>
                            <td className="px-4 py-3 font-[700] text-[var(--text-primary)] tabular-nums whitespace-nowrap">
                              {formatBillionWon(model.total_revenue_won)}원
                            </td>
                            <td className="px-4 py-3 font-[700] text-[var(--accent-strong)] tabular-nums whitespace-nowrap">
                              {formatBillionWon(model.net_profit_won)}원
                            </td>
                            <td className="px-4 py-3 text-[var(--text-secondary)] tabular-nums">
                              {model.project_months}개월
                            </td>
                            <td className="px-4 py-3">
                              <div className="flex items-center gap-2">
                                <div className="h-1.5 w-16 overflow-hidden rounded-full bg-[var(--surface-muted)]">
                                  <div
                                    className="h-full rounded-full bg-[var(--accent-strong)]"
                                    style={{ width: `${Math.min(model.composite_score, 100)}%` }}
                                  />
                                </div>
                                <span className="text-xs font-[800] text-[var(--text-primary)] tabular-nums">
                                  {model.composite_score.toFixed(1)}
                                </span>
                              </div>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      )}

      {/* ── Refine Modal ── */}
      <AnimatePresence>
        {showRefineModal && selectedModel && (
          <BusinessModelRefineModal
            model={selectedModel}
            equity={equity ? parseFloat(equity) : 100}
            onConfirm={handleRefineConfirm}
            onClose={() => setShowRefineModal(false)}
          />
        )}
      </AnimatePresence>
    </div>
  );
}
