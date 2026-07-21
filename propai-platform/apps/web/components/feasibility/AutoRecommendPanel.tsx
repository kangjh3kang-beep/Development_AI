"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  AlertTriangle,
  Brain,
  CheckCircle2,
  Landmark,
  TrendingUp,
  Wallet,
  type LucideIcon,
} from "lucide-react";
import { useParams, useRouter } from "next/navigation";
import { TiltCard } from "@/components/ui/TiltCard";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { effectiveLandAreaSqm } from "@/lib/site-area";
import { parcelAddressList } from "@/lib/parcel-rows";
import { useFeasibilityV2Store } from "@/store/use-feasibility-v2-store";
import { apiClient } from "@/lib/api-client";
import { GlobalAddressSearch } from "@/components/common/GlobalAddressSearch";
import { DevelopmentScenarioCard } from "@/components/common/DevelopmentScenarioCard";
import { NumberInput } from "@/components/common/NumberInput";
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

// 백엔드 실제 응답 타입
interface BackendRecommendItem {
  development_type: string;
  type_name: string;
  feasibility: {
    total_revenue_won: number;
    total_cost_won: number;
    net_profit_won: number;
    profit_rate_pct: number;
    roi_pct: number;
    grade: string;
  };
  permit: {
    is_permitted: boolean;
    complexity_label: string;
    reason: string;
  };
  unit_summary: {
    total_gfa_sqm: number;
    total_households: number;
    avg_area_pyeong: number;
  };
  composite_score: number;
  input_used: { project_months: number; avg_sale_price_per_pyeong: number };
}

// LLM(Claude) 사업성 해석 — feasibility_interpreter 출력 5섹션
interface FeasibilityInterpretation {
  overall_recommendation?: string;
  risk_assessment?: string;
  profit_optimization?: string;
  market_timing?: string;
  financing_advice?: string;
}

interface AutoRecommendApiResponse {
  recommendations: BackendRecommendItem[];
  all_results: BackendRecommendItem[];
  total_types_analyzed: number;
  ai_interpretation?: FeasibilityInterpretation | null;
  // ★P3(침묵 폴백 정직화): 백엔드 가정치 폴백(면적 1000㎡·용적률 250%·공시지가 150만원/㎡)
  //   사용 시에만 채워지는 정직 고지 — 있으면 반드시 렌더한다(orphan 금지).
  area_disclosure?: string | null;
  far_disclosure?: string | null;
  land_price_disclosure?: string | null;
  // ★P1 미래속성(종상향 잠재) — 현행 추천에 더해 종상향 시 잠재 용적률(예상치·확정 아님).
  upzoning_potential?: {
    current_far_pct?: number;
    potential_far_range?: { min_pct?: number | null; max_pct?: number | null; note?: string } | null;
    scenarios?: Record<string, unknown>[] | null;
    summary?: string | null;
    disclaimer?: string | null;
  } | null;
}
type UpzoningPotential = AutoRecommendApiResponse["upzoning_potential"];

// ★100% 완성: IntegratedRecommender(/optimal-recommend) 현행+종상향 2축 통합 순위 후보.
//   종상향(far_basis='종상향') 후보는 '미래 토지속성 반영 추천'으로 랭킹에 실반영(배너 아닌 실후보).
interface OptimalRankedCandidate {
  method?: string;
  type_name?: string;
  applied_far_pct?: number | null;
  net_profit?: number | null;
  profit_rate_pct?: number | null;
  npv?: number | null;
  composite?: number | null;
  far_basis?: string; // "현행" | "종상향"
  target_zone?: string | null;
  tentative?: boolean;
}
interface OptimalRecommendResponse {
  ranked?: OptimalRankedCandidate[];
  integrated_area_sqm?: number;
  baseline_far_pct?: number;
  scenario_status?: string;
  honest_disclosure?: string | null;
}

// 백엔드 응답 → 프론트엔드 모델 변환
function mapToRecommendedModel(item: BackendRecommendItem, rank: number): RecommendedModel {
  return {
    rank,
    type_code: item.development_type,
    type_name: item.type_name,
    profit_rate_pct: item.feasibility.profit_rate_pct,
    roi_pct: item.feasibility.roi_pct,
    grade: item.feasibility.grade,
    permit_ease: item.permit.complexity_label,
    total_revenue_won: item.feasibility.total_revenue_won,
    net_profit_won: item.feasibility.net_profit_won,
    project_months: item.input_used?.project_months ?? 36,
    total_gfa_sqm: item.unit_summary.total_gfa_sqm,
    total_households: item.unit_summary.total_households,
    avg_sale_price_per_pyeong: item.input_used?.avg_sale_price_per_pyeong ?? 0,
    composite_score: item.composite_score,
    ai_summary: `${item.type_name}: ${item.permit.reason}`,
  };
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
  /** 통합 흐름(프로젝트 허브)에서 사용. 주소/지역/면적 입력 폼을 숨기고 store의 부지정보로 자동 분석한다. */
  embedded?: boolean;
}

export function AutoRecommendPanel({ onClose, isModal = false, embedded = false }: AutoRecommendPanelProps) {
  const { locale, id: projectId } = useParams() as { locale: string; id: string };
  const router = useRouter();
  const ctxStore = useProjectContextStore();
  // 분석 완료 후 주소를 컨텍스트 스토어에 저장하여 다른 모듈에서 공유 (모세혈관 네트워크 주소 공유 패턴)
  const updateSiteAnalysis = useProjectContextStore((s) => s.updateSiteAnalysis);
  const feasibilityStore = useFeasibilityV2Store();

  // Input state — siteAnalysis에서 자동 반영
  const [address, setAddress] = useState(ctxStore.siteAnalysis?.address ?? "");
  // 다필지: 검색·엑셀 등록 필지(2필지↑ 시 통합 개발방식 분석 노출)
  const [parcels, setParcels] = useState<string[]>([]);
  const [region, setRegion] = useState(() => {
    const addr = ctxStore.siteAnalysis?.address ?? "";
    const match = REGIONS.find((r) => addr.includes(r) || addr.includes(r.replace("특별시","").replace("광역시","").replace("도","")));
    return match ?? "서울특별시";
  });
  const [landArea, setLandArea] = useState(() => {
    // ★다필지면 통합 면적 — 대표값으로 추천·수지가 과소산출되지 않게.
    const area = effectiveLandAreaSqm(ctxStore.siteAnalysis);
    return area && area > 0 ? area.toString() : "";
  });

  // siteAnalysis가 나중에 복원되면 input 필드에 자동 반영
  useEffect(() => {
    const site = ctxStore.siteAnalysis;
    if (!site) return;
    if (site.address && !address) {
      setAddress(site.address);
    }
    const eff = effectiveLandAreaSqm(site);
    if (eff && eff > 0 && !landArea) {
      setLandArea(eff.toString());
    }
    // ★다필지 배선 절단 근본수정(2026-07-19 전역 스윕): 복원 effect가 address·landArea·region은
    //   챙기면서 parcels만 누락해, 다필지 컨텍스트로 진입 시 parcels=[] → 개발방식(Development
    //   ScenarioCard) 블록이 통째로 사라졌다. landArea를 통합면적으로 미리 채우는 것 자체가
    //   다필지 계승 의도이므로 parcels도 같은 규약(로컬 미입력일 때만)으로 동기화한다.
    if (parcels.length === 0) {
      const storeAddrs = parcelAddressList(site.parcels);
      if (storeAddrs.length > 1) setParcels(storeAddrs);
    }
    if (site.address) {
      const match = REGIONS.find((r) => site.address!.includes(r) || site.address!.includes(r.replace("특별시","").replace("광역시","").replace("도","")));
      if (match) setRegion(match);
    }
  }, [ctxStore.siteAnalysis]); // eslint-disable-line react-hooks/exhaustive-deps

  // Result state
  const [isLoading, setIsLoading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [topModels, setTopModels] = useState<RecommendedModel[]>([]);
  const [aiInterpretation, setAiInterpretation] = useState<FeasibilityInterpretation | null>(null);
  const [allModels, setAllModels] = useState<RecommendedModel[]>([]);
  const [analysisCount, setAnalysisCount] = useState(0);
  // ★P1: 종상향 잠재(미래 토지속성) — 현행 추천과 분리 표기(예상치·확정 아님).
  const [upzoning, setUpzoning] = useState<UpzoningPotential>(null);
  // ★P3: 백엔드 가정치 폴백 정직 고지(있을 때만 배너 렌더).
  const [disclosures, setDisclosures] = useState<string[]>([]);
  // ★100% 완성: 종상향 시 추천 사업방식(IntegratedRecommender 2축 랭킹의 종상향 후보) — 실랭킹 반영.
  const [upzoningRanked, setUpzoningRanked] = useState<OptimalRankedCandidate[]>([]);
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
    setUpzoning(null);
    setUpzoningRanked([]);
    setAiInterpretation(null);
    setDisclosures([]);

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
      const response = await apiClient.postV2<AutoRecommendApiResponse>("/feasibility/auto-recommend", {
        body: {
          address: address.trim(),
          land_area_sqm: landArea ? parseFloat(landArea) : undefined,
          region,
          equity_won: undefined,
        },
      });

      // 백엔드 응답 → 프론트엔드 모델 변환
      const mappedRecs = (response.recommendations ?? []).map((item, i) => mapToRecommendedModel(item, i + 1));
      const mappedAll = (response.all_results ?? response.recommendations ?? []).map((item, i) => mapToRecommendedModel(item, i + 1));

      if (progressRef.current) clearInterval(progressRef.current);
      setProgress(100);
      setTopModels(mappedRecs.slice(0, 3));
      setAllModels(mappedAll);
      setAnalysisCount(response.total_types_analyzed ?? mappedAll.length);
      setUpzoning(response.upzoning_potential ?? null);
      setAiInterpretation(response.ai_interpretation ?? null);
      setDisclosures(
        [response.area_disclosure, response.far_disclosure, response.land_price_disclosure]
          .filter((d): d is string => typeof d === "string" && d.length > 0),
      );

      // ★100% 완성: 종상향이 '실제 추천 사업방식'으로 랭킹에 반영되도록 IntegratedRecommender(2축)를
      //   ★fire-and-forget(메인 로딩을 막지 않음·외부수집 별도) — 종상향(far_basis='종상향') 후보를 비동기 surface.
      //   실패해도 본 추천 불변(graceful). 메인 추천은 위에서 이미 렌더 완료라 로딩 인디케이터는 즉시 해제된다.
      const _optAddrs = [address.trim(), ...parcels].filter(Boolean);
      void (async () => {
        try {
          const opt = await apiClient.post<OptimalRecommendResponse>("/development-methods/optimal-recommend", {
            body: { addresses: _optAddrs, parcel_subset_policy: "전체" },
            useMock: false,
          });
          setUpzoningRanked(
            (opt?.ranked ?? [])
              .filter((c) => c.far_basis === "종상향" && (c.net_profit != null || c.profit_rate_pct != null))
              .slice(0, 4),
          );
        } catch {
          setUpzoningRanked([]); // graceful — 종상향 랭킹 미확보(현행 추천은 정상)
        }
      })();

      // 분석 완료 후 주소를 컨텍스트 스토어에 저장 (partial merge)
      updateSiteAnalysis({
        address,
        ...(landArea ? { landAreaSqm: parseFloat(landArea) } : {}),
      });
    } catch (e: unknown) {
      if (progressRef.current) clearInterval(progressRef.current);
      setError(e instanceof Error ? e.message : "분석에 실패했습니다. 다시 시도해주세요.");
    } finally {
      setIsLoading(false);
    }
  }, [address, region, landArea, parcels]);

  // embedded 모드: 마운트 시 store의 주소로 1회 자동 분석 (통합 흐름의 "단계 확인 후" 진입점)
  const embeddedAutoRunRef = useRef(false);
  useEffect(() => {
    if (!embedded) return;
    if (embeddedAutoRunRef.current) return;
    if (!address.trim() || isLoading) return;
    embeddedAutoRunRef.current = true;
    handleAnalyze();
  }, [embedded, address, isLoading, handleAnalyze]);

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

      // Save to project context store — merge 패치(기존 totalCostWon 보존, null로 덮지 않음).
      ctxStore.updateFeasibilityData({
        totalRevenueWon: selectedModel.total_revenue_won,
        profitRatePct: selectedModel.profit_rate_pct,
        grade: selectedModel.grade,
      });

      // ── 선택한 건축개요를 설계 스토어에 저장 → 설계 스튜디오(CAD/BIM)가 동일 개요로 생성(정합) ──
      // 층수는 용적률/건폐율로 추정(far/bcr). 면적은 정밀화 모달에서 확정한 연면적 사용.
      const ord = ctxStore.siteAnalysis?.ordinance;
      const bcr = ord?.effectiveBcr ?? ord?.nationalBcr ?? null;
      const far = ord?.effectiveFar ?? ord?.nationalFar ?? null;
      const floors = far && bcr ? Math.max(1, Math.round(far / bcr)) : null;
      ctxStore.updateDesignData({
        totalGfaSqm: refined.total_gfa_sqm || selectedModel.total_gfa_sqm || null,
        floorCount: floors,
        buildingType: selectedModel.type_name,
        bcr,
        far,
      });
      ctxStore.markStageComplete("design");

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
      {/* ── Header (체험/모달 모드) ── */}
      {!embedded && (
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
      )}

      {/* ── Embedded 모드: store 기반 분석 대상 요약 바 ── */}
      {embedded && (
        <div className="flex flex-wrap items-center gap-4 rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-strong)] px-5 py-4 shadow-[var(--shadow-md)]">
          <div className="flex items-center gap-3 flex-1 min-w-0">
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-[var(--accent-soft)] text-[var(--accent-strong)]">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M20 10c0 4.993-5.539 10.193-7.399 11.799a1 1 0 0 1-1.202 0C9.539 20.193 4 14.993 4 10a8 8 0 0 1 16 0"/><circle cx="12" cy="10" r="3"/></svg>
            </span>
            <div className="min-w-0">
              <p className="text-[10px] font-[900] uppercase tracking-[0.2em] text-[var(--text-hint)]">분석 대상</p>
              <p className="text-sm font-bold text-[var(--text-primary)] truncate">{address || "주소 정보 없음"}</p>
            </div>
          </div>
          <div className="flex items-center gap-5 text-xs">
            <div>
              <p className="text-[10px] font-bold text-[var(--text-hint)] tracking-wider">지역</p>
              <p className="font-bold text-[var(--text-primary)]">{region}</p>
            </div>
            <div>
              <p className="text-[10px] font-bold text-[var(--text-hint)] tracking-wider">대지면적</p>
              <p className="font-bold text-[var(--text-primary)] tabular-nums">{landArea ? `${Number(landArea).toLocaleString()} m²` : "—"}</p>
            </div>
          </div>
          <button
            onClick={handleAnalyze}
            disabled={isLoading || !address.trim()}
            className="h-9 px-4 rounded-lg border border-[var(--line-strong)] text-xs font-bold text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--surface-soft)] transition-all disabled:opacity-50 disabled:cursor-not-allowed shrink-0"
          >
            {isLoading ? "추천 분석 중..." : "다시 추천"}
          </button>
        </div>
      )}

      {/* ── Input Form (체험/모달 모드) ── */}
      {!embedded && (
      <div className="rounded-[var(--radius-lg)] border border-[var(--line-strong)] bg-[var(--surface-strong)] p-8 shadow-[var(--shadow-xl)]">
        <div className="flex flex-col gap-6">
          {/* Row 1: Address + Region */}
          <div className="flex flex-col gap-4 lg:flex-row">
            <div className="flex-1">
              <label className="mb-2 block text-[10px] font-[900] uppercase tracking-[0.3em] text-[var(--text-hint)]">
                주소 입력
              </label>
              {/* 주소 검색 (GlobalAddressSearch — 단일/다필지·엑셀 지원) */}
              <GlobalAddressSearch
                writeToContext={false}
                onChange={(entries) => {
                  if (entries.length > 0) {
                    const next = entries[0].jibunAddress || entries[0].fullAddress;
                    // 새 주소 입력 시 이전 추천결과 무효화(stale 표시 방지 — SSOT 정합).
                    if (next && next !== address) {
                      setTopModels([]); setAllModels([]); setAiInterpretation(null); setError(null);
                    }
                    setAddress(next);
                    // 시도 자동 설정
                    if (entries[0].sido) {
                      const matchedRegion = REGIONS.find((r) => entries[0].sido.includes(r) || r.includes(entries[0].sido));
                      if (matchedRegion) setRegion(matchedRegion);
                    }
                  }
                  setParcels(entries.map((e) => e.jibunAddress || e.fullAddress || e.roadAddress).filter(Boolean));
                }}
                placeholder="주소 검색 · 다필지는 엑셀로 일괄 등록"
              />
            </div>
            <div className="w-full lg:w-56">
              <label className="mb-2 block text-[10px] font-[900] uppercase tracking-[0.3em] text-[var(--text-hint)]">
                지역 선택
              </label>
              <select
                value={region}
                onChange={(e) => setRegion(e.target.value as typeof REGIONS[number])}
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
              <NumberInput
                allowDecimal
                value={landArea === "" ? null : Number(landArea)}
                onChange={(n) => setLandArea(n != null ? String(n) : "")}
                placeholder="1,500"
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

          {/* 다필지(2필지↑) 통합 개발방식 분석 — 검색·엑셀 등록 시 자동 노출 */}
          {parcels.length > 1 && (
            <div className="mt-4">
              <DevelopmentScenarioCard address={address} parcels={parcels} />
            </div>
          )}

        </div>
      </div>
      )}

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
        {/* ★P3: 가정치 폴백 정직 고지 — 백엔드가 disclosure를 보낸 경우에만 노출(무목업). */}
        {topModels.length > 0 && disclosures.length > 0 && (
          <div className="rounded-2xl border border-[var(--status-warning)]/40 bg-[var(--status-warning)]/10 px-5 py-4">
            <div className="flex items-start gap-3">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-[var(--status-warning)]" />
              <div className="space-y-1">
                {disclosures.map((d) => (
                  <p key={d} className="text-xs leading-5 text-[var(--text-secondary)] break-keep">{d}</p>
                ))}
              </div>
            </div>
          </div>
        )}

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
                  className="rounded-[var(--radius-xl)]"
                >
                  <motion.div
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.1 * (idx + 1) }}
                    className={`relative flex flex-col gap-6 rounded-[var(--radius-xl)] border-2 ${style.border} ${style.bg} p-8 backdrop-blur-xl shadow-[var(--shadow-xl)] h-full`}
                  >
                    {/* Rank Badge */}
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        <span className="text-2xl">{style.emoji}</span>
                        <span className={`label-caps ${style.accent}`}>
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

      {/* ── ★P1 미래속성: 종상향 잠재(현행 추천과 분리·예상치) ── */}
      {upzoning?.potential_far_range && (upzoning.potential_far_range.max_pct ?? 0) > (upzoning.current_far_pct ?? 0) && (
        <div className="rounded-[var(--radius-lg)] border border-amber-500/30 bg-amber-500/5 p-6">
          <div className="mb-2 flex items-center gap-2">
            <TrendingUp className="size-5 text-amber-400" aria-hidden />
            <h3 className="text-base font-black text-[var(--text-primary)]">미래 토지속성 — 종상향 잠재(예상치)</h3>
          </div>
          <p className="text-sm text-[var(--text-secondary)]">
            현행 실효 용적률 <b className="text-[var(--text-primary)]">{upzoning.current_far_pct}%</b> 기준 추천입니다.
            종상향(역세권·지구단위 등) 시 잠재 용적률은{" "}
            <b className="text-amber-400">
              {upzoning.potential_far_range.min_pct === upzoning.potential_far_range.max_pct
                ? `${upzoning.potential_far_range.max_pct}%`
                : `${upzoning.potential_far_range.min_pct}~${upzoning.potential_far_range.max_pct}%`}
            </b>
            까지 가능하며, 이 경우 더 고밀·고수익 건축유형이 추천될 수 있습니다.
          </p>
          {upzoning.summary && (
            <p className="mt-1.5 text-xs leading-relaxed text-[var(--text-tertiary)]">{upzoning.summary}</p>
          )}
          {upzoning.disclaimer && (
            <p className="mt-1.5 text-[11px] leading-relaxed text-[var(--text-hint)]">{upzoning.disclaimer}</p>
          )}
        </div>
      )}

      {/* ★100% 완성: 종상향이 '실제 추천 사업방식'으로 랭킹 반영(IntegratedRecommender 2축의 종상향 후보).
          ★배너(upzoning_potential)와 독립 — 두 엔진(calc_upzoning vs IntegratedRecommender) 판정이 달라도 노출. */}
      {upzoningRanked.length > 0 && (
        <div className="rounded-[var(--radius-lg)] border border-amber-500/30 bg-amber-500/5 p-6">
          <div className="mb-2 flex items-center gap-2">
            <TrendingUp className="size-5 text-amber-400" aria-hidden />
            <h3 className="text-base font-black text-[var(--text-primary)]">종상향 시 추천 사업방식(수익순·잠재)</h3>
          </div>
          <div className="space-y-1.5">
            {upzoningRanked.map((c) => (
              <div key={`${c.method ?? ""}-${c.target_zone ?? ""}-${c.applied_far_pct ?? ""}`} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-[var(--line)] bg-[var(--surface-strong)] px-3 py-2">
                <span className="flex items-center gap-2">
                  <span className="text-[10px] font-bold text-amber-400">종상향</span>
                  <span className="text-[12px] font-bold text-[var(--text-primary)]">{c.type_name || c.method}</span>
                  {c.applied_far_pct != null && (
                    <span className="text-[10px] text-[var(--text-tertiary)]">용적 {c.applied_far_pct}%</span>
                  )}
                </span>
                <span className="flex items-center gap-2 text-[10px]">
                  {c.profit_rate_pct != null && (
                    <span className="font-bold text-[var(--accent-strong)]">수익률 {c.profit_rate_pct.toFixed(1)}%</span>
                  )}
                  {c.composite != null && <span className="text-[var(--text-tertiary)]">종합 {c.composite.toFixed(1)}</span>}
                </span>
              </div>
            ))}
          </div>
          <p className="mt-1.5 text-[10px] text-[var(--text-hint)]">
            종상향 후보는 고시·심의 통과를 전제로 한 조건부 시나리오입니다(확정 아님). 수익성은 동일 면적 상대비교.
          </p>
        </div>
      )}

      {/* ── LLM(Claude) 사업성 종합 해석 ── */}
      {aiInterpretation && (
        <div className="rounded-[var(--radius-lg)] border border-blue-500/30 bg-blue-500/5 p-6 shadow-[var(--shadow-lg)]">
          <div className="flex items-center gap-2 mb-4">
            <Brain className="size-5 text-blue-400" aria-hidden />
            <h3 className="text-base font-black text-[var(--text-primary)]">
              AI 사업성 종합 해석
            </h3>
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            <FeasAiSection icon={CheckCircle2} title="종합 추천" text={aiInterpretation.overall_recommendation} emphasis />
            <FeasAiSection icon={AlertTriangle} title="리스크 평가" text={aiInterpretation.risk_assessment} />
            <FeasAiSection icon={Wallet} title="수익 극대화" text={aiInterpretation.profit_optimization} />
            <FeasAiSection icon={TrendingUp} title="시장 타이밍" text={aiInterpretation.market_timing} />
            <FeasAiSection icon={Landmark} title="자금조달 제안" text={aiInterpretation.financing_advice} />
          </div>
        </div>
      )}

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
            equity={100}
            onConfirm={handleRefineConfirm}
            onClose={() => setShowRefineModal(false)}
          />
        )}
      </AnimatePresence>
    </div>
  );
}

/* LLM 사업성 해석 섹션 카드 (종합추천은 emphasis로 강조, 전폭) */
function FeasAiSection({
  icon: Icon,
  title,
  text,
  emphasis = false,
}: {
  icon: LucideIcon;
  title: string;
  text?: string;
  emphasis?: boolean;
}) {
  if (!text) return null;
  return (
    <div
      className={`rounded-xl p-4 ${
        emphasis
          ? "md:col-span-2 bg-blue-500/10 border border-blue-500/30"
          : "bg-[var(--surface-muted)]/40 border border-[var(--line)]"
      }`}
    >
      <div className="flex items-center gap-1.5 mb-1.5">
        <Icon className="size-4 shrink-0" aria-hidden />
        <span
          className={`text-xs font-bold ${
            emphasis ? "text-blue-300" : "text-[var(--text-primary)]"
          }`}
        >
          {title}
        </span>
      </div>
      <p className="text-[11px] text-[var(--text-secondary)] leading-relaxed whitespace-pre-line">
        {text}
      </p>
    </div>
  );
}
