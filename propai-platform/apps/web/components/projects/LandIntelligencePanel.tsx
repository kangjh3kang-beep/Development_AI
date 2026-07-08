"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { AlertTriangle } from "lucide-react";
import { useAIAnalyze, useAIReady } from "@/lib/ai-analyze-client";
import { analyzeLocally } from "@/lib/kr-building-regulations";
import { apiClient } from "@/lib/api-client";
import { getCachedAnalysis, setCachedAnalysis, TTL_30D, TTL_7D, TTL_3D } from "@/lib/analysis-fetch-cache";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import {
  DEVELOPABILITY_LABEL,
  resolveFarPct,
  resolveBcrPct,
  specialFactorLabels,
  preconditionFactors,
  type SpecialFactorRich,
} from "@/lib/zoning-ssot";
import { EvidencePanel, type EvidenceItem } from "@/components/common/EvidencePanel";
import { LegalRefChip } from "@/components/common/LegalRefChip";
import {
  SpecialParcelLegalPrelim,
  type SpecialParcelFactorLike,
} from "@/components/projects/SpecialParcelLegalPrelim";
import { UseLlmToggle } from "@/components/common/UseLlmToggle";
import type { BackendLegalRef } from "@/lib/evidence/adaptEvidence";

// ── Icons ──
const Icons = {
  Sparkles: () => <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m12 3 1.912 5.813a2 2 0 0 0 1.275 1.275L21 12l-5.813 1.912a2 2 0 0 0-1.275 1.275L12 21l-1.912-5.813a2 2 0 0 0-1.275-1.275L3 12l5.813-1.912a2 2 0 0 0 1.275-1.275L12 3Z"/><path d="M5 3v4"/><path d="M19 17v4"/><path d="M3 5h4"/><path d="M17 19h4"/></svg>,
  TrendingUp: () => <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/><polyline points="16 7 22 7 22 13"/></svg>,
  ArrowRight: () => <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12h14"/><path d="m12 5 7 7-7 7"/></svg>,
  Map: () => <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M14.106 5.553a2 2 0 0 0 1.788 0l3.659-1.83A1 1 0 0 1 21 4.619v12.764a1 1 0 0 1-.553.894l-4.553 2.277a2 2 0 0 1-1.788 0l-4.212-2.106a2 2 0 0 0-1.788 0l-3.659 1.83A1 1 0 0 1 3 19.381V6.618a1 1 0 0 1 .553-.894l4.553-2.277a2 2 0 0 1 1.788 0z"/><path d="M15 5.764v15"/><path d="M9 3.236v15"/></svg>,
  Layers: () => <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m12.83 2.18a2 2 0 0 0-1.66 0L2.6 6.08a1 1 0 0 0 0 1.83l8.58 3.91a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.83Z"/><path d="m22.54 12.43-1.42-.65-8.28 3.78a2 2 0 0 1-1.66 0l-8.29-3.78-1.42.65a1 1 0 0 0 0 1.84l8.58 3.91a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.85Z"/><path d="m22.54 16.43-1.42-.65-8.28 3.78a2 2 0 0 1-1.66 0l-8.29-3.78-1.42.65a1 1 0 0 0 0 1.84l8.58 3.91a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.85Z"/></svg>,
  Building: () => <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect width="16" height="20" x="4" y="2" rx="2" ry="2"/><path d="M9 22v-4h6v4"/><path d="M8 6h.01"/><path d="M16 6h.01"/><path d="M12 6h.01"/><path d="M12 10h.01"/><path d="M12 14h.01"/><path d="M16 10h.01"/><path d="M16 14h.01"/><path d="M8 10h.01"/><path d="M8 14h.01"/></svg>,
  Check: () => <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M20 6 9 17l-5-5"/></svg>,
  AlertCircle: () => <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" x2="12" y1="8" y2="12"/><line x1="12" x2="12.01" y1="16" y2="16"/></svg>,
  Loader: () => <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="animate-spin"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>,
};

// ── Types ──
type SiteAnalysisResult = {
  zoning?: { current?: string; target?: string; probability?: number; reason?: string };
  characteristics?: Array<{ label: string; value: string; status: string }>;
  scenarios?: Array<{ title: string; score: number; reason: string }>;
  summary?: string;
};

type ZoningAnalysisResponse = {
  address: string;
  pnu: string | null;
  zone_type: string | null;
  zone_limits: {
    max_bcr_pct: number;
    max_far_pct: number;
    max_height_m: number | null;
    zone_key: string;
    legal_basis: string;
  } | null;
  land_area_sqm: number | null;
  land_category: string | null;
  official_price_per_sqm: number | null;
  special_districts: Array<{ name: string; bonus_far: number | null }>;
  warnings: string[];
  // 실효용적률 계층(가산·옵셔널) — 법정상한을 실효처럼 표시하지 않도록 분리 제공.
  effective_far?: {
    national_bcr_pct?: number | null;
    national_far_pct?: number | null;
    effective_bcr_pct?: number | null;
    effective_far_pct?: number | null;
    far_basis?: string | null;
  } | null;
  // 특이부지 게이트(가산·옵셔널) — is_special일 때만 게이트 카드 렌더(무목업).
  special_parcel?: {
    is_special?: boolean | null;
    developability?: string | null;
    resolvable?: string | null;
    severity_label?: string | null;
    // ★factor는 문자열 또는 rich dict(category·developability·implications[]·legal_basis[]·legal_refs[]).
    //   개발행위허가 게이트(§56/§58) implications 상세 렌더(SpecialFactorRich)와
    //   법규 예비판정(additive·옵셔널 — 임야/농지 요인에만 백엔드가 주입:
    //   forest_facts(DEM 경사도·입목축적) / preliminary_assessment(경사도·입목축적
    //   3단 예비판정 — 확정 아님) / charge_notice(전용 부담금 산식·추정액 고지);
    //   SpecialParcelFactorLike가 흡수, SpecialParcelLegalPrelim이 소비)을
    //   모두 지원하도록 교차 타입으로 받는다.
    factors?: Array<(SpecialFactorRich & SpecialParcelFactorLike) | string> | null;
    honest_disclosure?: string | null;
  } | null;
};

// 다필지 통합분석 응답(POST /api/v1/zoning/integrated-analysis) — 면적가중 건폐/용적·통합GFA·
//   인접성·통합 시나리오를 한 번에 제공. 중첩/배열은 부분응답 가능성에 대비해 전부 옵셔널(런타임 가드 일치).
type IntegratedAnalysisResponse = {
  parcel_count?: number | null;
  zone_mix?: Array<{
    zone?: string | null;
    area_sqm?: number | null;
    share_pct?: number | null;
    bcr_legal?: number | null;
    far_legal?: number | null;
    bcr_eff?: number | null;
    far_eff?: number | null;
  }> | null;
  dominant_zone?: string | null;
  dominant_basis?: string | null; // 'area_share' | 'mixed_review_required' 등
  integrated?: {
    total_area_sqm?: number | null;
    blended_bcr_eff_pct?: number | null;
    blended_far_eff_pct?: number | null;
    blended_bcr_legal_pct?: number | null;
    blended_far_legal_pct?: number | null;
    far_basis_note?: string | null;
    integrated_gfa_sqm?: number | null;
    integrated_footprint_sqm?: number | null;
    gfa_basis?: string | null;
  } | null;
  adjacency?: {
    contiguous?: boolean | null;
    components?: number | null;
    note?: string | null;
  } | null;
  developability?: string | null;
  resolvable?: string | null;
  blocking_parcels?: unknown[] | null;
  honest_disclosure?: string | null;
  scenario?: {
    status?: "computed" | "tentative" | "blocked" | string | null;
    disclosure?: string | null;
    [key: string]: unknown;
  } | null;
  // 필지별 상세(백엔드 router per_parcel) — 통합 산출근거 추적용. 중첩/결측 대비 전부 옵셔널.
  per_parcel?: Array<{
    pnu?: string | null;
    address?: string | null;
    area_sqm?: number | null;
    zone_type?: string | null;
    bcr_eff_pct?: number | null;
    far_eff_pct?: number | null;
    bcr_legal_pct?: number | null;
    far_legal_pct?: number | null;
    far_basis?: string | null;
    special_parcel?: { is_special?: boolean | null; developability?: string | null } | null;
    status?: string | null;
    reason?: string | null;
    [key: string]: unknown;
  }> | null;
  warnings?: string[] | null;
};

type TransactionItem = {
  deal_amount?: string;
  deal_year?: string;
  deal_month?: string;
  deal_day?: string;
  area_sqm?: number;
  floor?: number;
  apt_name?: string;
  dong?: string;
  [key: string]: unknown;
};

type TransactionsResponse = {
  items?: TransactionItem[];
  total_count?: number;
};

type RecommendedModel = {
  rank: number;
  type_code: string;
  type_name: string;
  // 무목업: 부분 응답 시 가짜 0/—을 실분석결과처럼 렌더하지 않도록 nullable 유지.
  profit_rate_pct: number | null;
  roi_pct: number | null;
  grade: string | null;
  permit_ease: string;
  total_revenue_won: number | null;
  net_profit_won: number | null;
  project_months: number;
  total_gfa_sqm: number | null;
  total_households: number | null;
  avg_sale_price_per_pyeong: number | null;
  composite_score: number | null;
  ai_summary: string;
  // 특이부지 잠정 강등(도로·학교·맹지 등 선행절차형) — true면 확신 % 대신 '선행절차 전제 잠정' 표기.
  tentative: boolean;
  tentative_reason: string | null;
};

// 백엔드 실제 응답 타입 — 중첩 객체는 에러/부분 응답 시 누락될 수 있어 옵셔널로 선언(런타임 가드와 일치).
type BackendRecommendItem = {
  development_type?: string;
  type_name?: string;
  feasibility?: { total_revenue_won?: number; net_profit_won?: number; profit_rate_pct?: number; roi_pct?: number; grade?: string };
  permit?: { complexity_label?: string; reason?: string };
  unit_summary?: { total_gfa_sqm?: number; total_households?: number; avg_area_pyeong?: number };
  composite_score?: number;
  input_used?: { project_months?: number; avg_sale_price_per_pyeong?: number };
  // 백엔드 잠정 강등 플래그(특이부지 PRECONDITION/CONDITIONAL).
  tentative?: boolean;
  tentative_reason?: string;
};

type AutoRecommendApiResponse = {
  recommendations: BackendRecommendItem[];
  all_results: BackendRecommendItem[];
  total_types_analyzed: number;
  // "tentative"면 전 후보가 선행절차 전제 잠정치(확정 아님). 확신 % 렌더 억제 신호.
  scenario_status?: string;
  honest_disclosure?: string;
  special_parcel?: { developability?: string | null; honest_disclosure?: string | null } | null;
};

function mapBackendToModel(item: BackendRecommendItem, rank: number): RecommendedModel {
  // 백엔드 응답의 중첩 객체(feasibility/unit_summary/permit)가 누락된 경우에도
  // 렌더 경로에서 동기 throw(→ 전체 페이지 에러바운더리 크래시)가 나지 않도록 옵셔널/폴백 처리.
  const fs = item.feasibility ?? {};
  const us = item.unit_summary ?? {};
  const pm = item.permit ?? {};
  const typeName = item.type_name ?? item.development_type ?? "개발 유형";
  return {
    rank,
    type_code: item.development_type ?? "",
    type_name: typeName,
    // 무목업: 폴백을 0/—으로 강제하지 않고 null 유지 → 렌더부에서 "분석 데이터 없음"/"—" 빈상태 분기.
    profit_rate_pct: fs.profit_rate_pct ?? null,
    roi_pct: fs.roi_pct ?? null,
    grade: fs.grade ?? null,
    permit_ease: pm.complexity_label ?? "—",
    total_revenue_won: fs.total_revenue_won ?? null,
    net_profit_won: fs.net_profit_won ?? null,
    project_months: item.input_used?.project_months ?? 36,
    total_gfa_sqm: us.total_gfa_sqm ?? null,
    total_households: us.total_households ?? null,
    avg_sale_price_per_pyeong: item.input_used?.avg_sale_price_per_pyeong ?? null,
    composite_score: item.composite_score ?? null,
    ai_summary: `${typeName}: ${pm.reason ?? "분석 결과"}`,
    // 특이부지 잠정 강등 — 백엔드 후보 플래그(없으면 false). 렌더에서 확신 % 억제·잠정 배지.
    tentative: item.tentative === true,
    tentative_reason: item.tentative_reason ?? null,
  };
}

// 무목업: 수익률/등급이 누락(null)이면 가짜 "0.0%·—등급" 대신 빈상태 라벨로 정직 표기.
function recommendReason(r: RecommendedModel): string {
  const parts: string[] = [];
  if (r.profit_rate_pct != null) parts.push(`수익률 ${r.profit_rate_pct.toFixed(1)}%`);
  if (r.grade != null) parts.push(`${r.grade}등급`);
  const summary = r.ai_summary?.slice(0, 40);
  if (summary) parts.push(summary);
  return parts.length > 0 ? parts.join(" · ") : "분석 데이터 없음";
}

interface LandIntelligencePanelProps {
  projectId: string;
  data: Record<string, string | undefined>;
}

// ── Status badge colors ──
const statusColors: Record<string, string> = {
  safe: "text-emerald-400 bg-emerald-500/10 border-emerald-500/20",
  warning: "text-amber-400 bg-amber-500/10 border-amber-500/20",
  danger: "text-red-400 bg-red-500/10 border-red-500/20",
};

// ── Bottom Tab Pages ──
type BottomTab = "pnu" | "price" | "transaction" | "gis";

// ── Helper: extract lawd_cd from address ──
function extractLawdCd(address: string): string | null {
  // Seoul district mapping (simplified)
  const districtMap: Record<string, string> = {
    "강남": "11680", "서초": "11650", "송파": "11710", "강동": "11740",
    "마포": "11440", "용산": "11170", "성동": "11200", "광진": "11215",
    "동대문": "11230", "중랑": "11260", "성북": "11290", "강북": "11305",
    "도봉": "11320", "노원": "11350", "은평": "11380", "서대문": "11410",
    "종로": "11110", "중구": "11140", "동작": "11590", "관악": "11620",
    "영등포": "11560", "금천": "11545", "구로": "11530", "양천": "11500",
    "강서": "11500",
  };
  for (const [district, code] of Object.entries(districtMap)) {
    if (address.includes(district)) return code;
  }
  // Default to Gangnam if address contains 서울
  if (address.includes("서울")) return "11680";
  return null;
}

// ── Helper: format price in 억/만 ──
function formatPrice(amountStr: string | undefined): string {
  if (!amountStr) return "—";
  const amount = parseInt(amountStr.replace(/,/g, ""), 10);
  if (isNaN(amount)) return amountStr;
  if (amount >= 10000) {
    const eok = Math.floor(amount / 10000);
    const remain = amount % 10000;
    return remain > 0 ? `${eok}억 ${remain.toLocaleString()}만` : `${eok}억`;
  }
  return `${amount.toLocaleString()}만`;
}

export function LandIntelligencePanel({ projectId, data }: LandIntelligencePanelProps) {
  const displayAddress = data?.address || "분석 대상 주소를 입력하세요";
  const displayPnu = data?.pnu || "—";
  const { isReady } = useAIReady();
  const { mutate: runAnalysis, data: aiResult, isPending: isAnalyzing, error: aiError } = useAIAnalyze<SiteAnalysisResult>();
  const [activeTab, setActiveTab] = useState<BottomTab>("pnu");

  // ── Project context store ──
  const siteAnalysis = useProjectContextStore((s) => s.siteAnalysis);
  const updateSiteAnalysis = useProjectContextStore((s) => s.updateSiteAnalysis);

  // ── Zoning API state ──
  const [zoningData, setZoningData] = useState<ZoningAnalysisResponse | null>(null);
  const [zoningLoading, setZoningLoading] = useState(false);
  const [zoningError, setZoningError] = useState<string | null>(null);

  // ── Transaction API state ──
  const [txData, setTxData] = useState<TransactionsResponse | null>(null);
  const [txLoading, setTxLoading] = useState(false);
  const [txError, setTxError] = useState<string | null>(null);

  // ── Auto-recommend (scenarios) API state ──
  // scenarioStatus="tentative"면 특이부지(도로·학교·맹지 등)로 전 후보가 선행절차 전제 잠정치.
  const [scenarioData, setScenarioData] = useState<{ recommendations: RecommendedModel[]; all_models: RecommendedModel[]; analysis_count: number; scenarioStatus: string; honest: string | null } | null>(null);
  const [scenarioLoading, setScenarioLoading] = useState(false);
  const [scenarioError, setScenarioError] = useState<string | null>(null);
  // AI 내러티브(수지 해석) 옵트인 — 자동 추천(3)·심층 분석 버튼(triggerDeepAnalysis) 양쪽이 공유.
  // 종전엔 use_llm 미전송이라 백엔드 기본값(true)에 암묵 의존해 항상 ON이었다. 기본 true로 유지해
  // 기존 동작을 보존하면서, 끄면 결정론 추천만(무과금) 받을 수 있게 한다(D1).
  const [useLlm, setUseLlm] = useState(true);

  // ── 다필지 통합분석(/zoning/integrated-analysis) API state ──
  //   parcelCount>1 && parcels.length>1일 때만 호출. 결과는 '읽기 소비'(SSOT 재기록 금지) — 로컬 state.
  const [integratedData, setIntegratedData] = useState<IntegratedAnalysisResponse | null>(null);
  const [integratedLoading, setIntegratedLoading] = useState(false);
  const [integratedError, setIntegratedError] = useState<string | null>(null);
  // 필지별 상세(per_parcel) 토글 — 기본 접힘(통합 요약 우선, 필요 시 펼쳐 산출근거 추적).
  const [perParcelOpen, setPerParcelOpen] = useState(false);

  // ── GIS layer toggles ──
  const [gisLayers, setGisLayers] = useState<Record<string, boolean>>({
    "용도지역": true,
    "도로망": true,
    "지적도": false,
    "항공사진": false,
    "등고선": false,
  });

  // ── AI deep analysis state ──
  const [deepAnalysisLoading, setDeepAnalysisLoading] = useState(false);
  const [deepAnalysisResult, setDeepAnalysisResult] = useState<{ recommendations: RecommendedModel[]; all_models: RecommendedModel[]; analysis_count: number; scenarioStatus: string; honest: string | null } | null>(null);
  const [deepAnalysisError, setDeepAnalysisError] = useState<string | null>(null);

  // ── 1) Fetch zoning data from /zoning/analyze ──
  useEffect(() => {
    if (!data?.address || data.address.trim().length < 3) {
      setZoningData(null);
      return;
    }

    const zAddr = data.address.trim();
    // 캐시 우선 — 한번 분석한 용도지역은 재진입 시 즉시 사용(재분석 방지).
    const zCached = getCachedAnalysis<ZoningAnalysisResponse>(`zoning:${zAddr}`, TTL_30D);
    if (zCached) { setZoningData(zCached); setZoningLoading(false); return; }

    let cancelled = false;
    async function fetchZoning() {
      setZoningLoading(true);
      setZoningError(null);
      try {
        const res = await apiClient.post<ZoningAnalysisResponse>("/zoning/analyze", {
          useMock: false,
          body: { address: data!.address!.trim() },
        });
        if (!cancelled) {
          setZoningData(res);
          setCachedAnalysis(`zoning:${zAddr}`, res);
          // Update project context store
          // ★다필지 통합면적 보존 가드(AutoZoningBadge와 동일 계약): 이 /zoning/analyze는
          //   단일 PNU(대표 1필지) 분석이라 res.land_area_sqm은 대표 면적이다. 현재 SSOT가
          //   이미 다필지 통합(parcelCount>1 && landAreaSqmTotal>0)이면 landAreaSqm 키를 빼서
          //   통합 면적/메타를 보존한다(대표값이 통합값을 덮어쓰는 회귀 차단). 라이브 SSOT 사용.
          const cur = useProjectContextStore.getState().siteAnalysis;
          const isMultiParcel =
            (cur?.parcelCount ?? 1) > 1 &&
            typeof cur?.landAreaSqmTotal === "number" &&
            cur.landAreaSqmTotal > 0;
          // ★#185 무한렌더 가드: SSOT address는 '입력 정체성'이므로 분석 결과(res.address·백엔드
          //   정규화)로 덮어쓰지 않는다. 덮어쓰면 res.address≠입력일 때 이 effect(deps=[data?.address])가
          //   재발화→재분석→재기록 순환으로 렌더가 폭주한다(Minified React #185·부지분석 첫진입 크래시).
          //   분석은 zoneCode/pnu만 enrich하고 address는 SSOT(사용자 입력)를 보존한다.
          const zPayload = {
            estimatedValue: cur?.estimatedValue ?? null,
            zoneCode: res.zone_limits?.zone_key ?? res.zone_type ?? null,
            pnu: res.pnu ?? cur?.pnu ?? null,
          };
          updateSiteAnalysis(
            isMultiParcel
              ? zPayload // 다필지: landAreaSqm 미포함 → 통합 면적 보존
              : {
                  ...zPayload,
                  landAreaSqm: res.land_area_sqm ?? cur?.landAreaSqm ?? null,
                },
          );
        }
      } catch (err) {
        if (!cancelled) {
          setZoningError(err instanceof Error ? err.message : "용도지역 조회 실패");
        }
      } finally {
        if (!cancelled) setZoningLoading(false);
      }
    }

    const timer = setTimeout(fetchZoning, 600);
    return () => { cancelled = true; clearTimeout(timer); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data?.address]);

  // ── 2) Fetch transaction data ──
  useEffect(() => {
    if (!data?.address) {
      setTxData(null);
      return;
    }

    const lawdCd = extractLawdCd(data.address);
    if (!lawdCd) {
      setTxData(null);
      return;
    }

    const now = new Date();
    const dealYm = `${now.getFullYear()}${String(now.getMonth() + 1).padStart(2, "0")}`;
    const txCached = getCachedAnalysis<TransactionsResponse>(`tx:${lawdCd}:${dealYm}`, TTL_3D);
    if (txCached) { setTxData(txCached); setTxLoading(false); return; }

    let cancelled = false;
    async function fetchTransactions() {
      setTxLoading(true);
      setTxError(null);
      try {
        const res = await apiClient.get<TransactionsResponse>(
          `/external/transactions/apt?lawd_cd=${lawdCd}&deal_ym=${dealYm}`,
          { useMock: false },
        );
        if (!cancelled) { setTxData(res); setCachedAnalysis(`tx:${lawdCd}:${dealYm}`, res); }
      } catch (err) {
        if (!cancelled) {
          setTxError(err instanceof Error ? err.message : "실거래 데이터 조회 실패");
        }
      } finally {
        if (!cancelled) setTxLoading(false);
      }
    }

    const timer = setTimeout(fetchTransactions, 800);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [data?.address]);

  // ── 3) Fetch auto-recommend scenarios ──
  useEffect(() => {
    if (!data?.address || data.address.trim().length < 3) {
      setScenarioData(null);
      return;
    }

    const sAddr = data.address.trim();
    const sKey = `scenario:${sAddr}:${zoningData?.land_area_sqm ?? ""}:${useLlm ? "L" : "D"}`;
    const sCached = getCachedAnalysis<{ recommendations: RecommendedModel[]; all_models: RecommendedModel[]; analysis_count: number; scenarioStatus: string; honest: string | null }>(sKey, TTL_7D);
    if (sCached) { setScenarioData(sCached); setScenarioLoading(false); return; }

    let cancelled = false;
    async function fetchScenarios() {
      setScenarioLoading(true);
      setScenarioError(null);
      try {
        const raw = await apiClient.postV2<AutoRecommendApiResponse>("/feasibility/auto-recommend", {
          body: {
            address: data!.address!.trim(),
            land_area_sqm: zoningData?.land_area_sqm ?? undefined,
            region: data?.address?.includes("서울") ? "서울특별시" : "경기도",
            use_llm: useLlm,
          },
        });
        // 백엔드 응답을 프론트엔드 타입으로 변환 (부분응답에서 recommendations 누락 시 빈배열 폴백)
        const recs = raw.recommendations ?? [];
        const mapped = {
          recommendations: recs.map((item, i) => mapBackendToModel(item, i + 1)),
          all_models: (raw.all_results ?? recs).map((item, i) => mapBackendToModel(item, i + 1)),
          analysis_count: raw.total_types_analyzed ?? recs.length,
          // 특이부지 잠정 상태 — "tentative"면 전 후보가 선행절차 전제 잠정치(확신 % 억제).
          scenarioStatus: raw.scenario_status ?? "actual",
          honest: raw.honest_disclosure ?? raw.special_parcel?.honest_disclosure ?? null,
        };
        if (!cancelled) { setScenarioData(mapped); setCachedAnalysis(sKey, mapped); }
      } catch (err) {
        if (!cancelled) {
          setScenarioError(err instanceof Error ? err.message : "시나리오 분석 실패");
        }
      } finally {
        if (!cancelled) setScenarioLoading(false);
      }
    }

    // Delay slightly after zoning to allow land_area_sqm
    const timer = setTimeout(fetchScenarios, 1200);
    return () => { cancelled = true; clearTimeout(timer); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data?.address, zoningData?.land_area_sqm, useLlm]);

  // ── 다필지 여부(SSOT 기준) — parcelCount>1 && 실제 필지목록>1일 때만 통합분석 경로 진입 ──
  //   (단일/유효<2는 위 단일 경로(/zoning/analyze·/feasibility/auto-recommend)를 그대로 사용)
  const ssotParcels = siteAnalysis?.parcels ?? null;
  const isMultiParcel =
    (siteAnalysis?.parcelCount ?? 1) > 1 && (ssotParcels?.length ?? 0) > 1;
  // 통합분석 페이로드/캐시 키에 쓸 필지 시그니처(목록이 바뀌면 재호출). pnu 순서 무관하게 안정화.
  const parcelsSig = useMemo(() => {
    if (!isMultiParcel || !ssotParcels) return "";
    return ssotParcels
      .map((p) => `${p.pnu}:${p.areaSqm ?? ""}`)
      .sort()
      .join("|");
  }, [isMultiParcel, ssotParcels]);

  // ── 다필지 통합분석 fetch — 면적가중 건폐/용적·통합GFA·인접성·통합 시나리오를 한 번에 소비. ──
  //   ★읽기 소비 원칙: 결과는 로컬 state로만 보관(updateSiteAnalysis로 SSOT 재기록 금지).
  //   projectId 캡처→응답 시 재확인 가드(분석 중 프로젝트 전환 시 stale 결과 반영 차단).
  useEffect(() => {
    if (!isMultiParcel || !ssotParcels || ssotParcels.length < 2) {
      setIntegratedData(null);
      setIntegratedError(null);
      return;
    }

    // 캐싱 키에 parcelCount + 필지 시그니처 포함(필지목록 변경 시 자동 무효화).
    const iKey = `integrated:${ssotParcels.length}:${parcelsSig}`;
    const iCached = getCachedAnalysis<IntegratedAnalysisResponse>(iKey, TTL_7D);
    if (iCached) { setIntegratedData(iCached); setIntegratedLoading(false); return; }

    let cancelled = false;
    // 응답 시 프로젝트 전환 여부를 재확인하기 위한 캡처(계정/프로젝트 격리 — 기존 패턴).
    const triggeredProjectId = useProjectContextStore.getState().projectId;
    async function fetchIntegrated() {
      setIntegratedLoading(true);
      setIntegratedError(null);
      try {
        const res = await apiClient.post<IntegratedAnalysisResponse>("/zoning/integrated-analysis", {
          useMock: false,
          body: {
            parcels: (ssotParcels ?? []).map((p) => ({
              pnu: p.pnu,
              address: p.address,
              area_sqm: p.areaSqm,
              land_category: p.landCategory,
            })),
            // 자동 통합 fetch는 시나리오 자동 경로와 동일하게 LLM 미사용(심층 분석은 별도 버튼 경로).
            use_llm: false,
          },
        });
        // 응답 도착 시 활성 프로젝트가 바뀌었으면(전환 race) 반영 중단 — stale 결과 차단.
        if (cancelled) return;
        if (useProjectContextStore.getState().projectId !== triggeredProjectId) return;
        setIntegratedData(res);
        setCachedAnalysis(iKey, res);
      } catch (err) {
        if (!cancelled) {
          setIntegratedError(err instanceof Error ? err.message : "다필지 통합분석 실패");
        }
      } finally {
        if (!cancelled) setIntegratedLoading(false);
      }
    }

    const timer = setTimeout(fetchIntegrated, 900);
    return () => { cancelled = true; clearTimeout(timer); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isMultiParcel, parcelsSig]);

  // ── Local calculation engine (fallback) ──
  const localResult = useMemo(() => {
    if (!data?.address) return null;
    return analyzeLocally(data.address, data.pnu);
  }, [data?.address, data?.pnu]);

  // ── AI analysis trigger (deep analysis via backend) ──
  const triggerDeepAnalysis = useCallback(async () => {
    if (!data?.address) return;

    setDeepAnalysisLoading(true);
    setDeepAnalysisError(null);
    setDeepAnalysisResult(null);

    try {
      // Try backend auto-recommend as the deep analysis endpoint
      const raw = await apiClient.postV2<AutoRecommendApiResponse>("/feasibility/auto-recommend", {
        body: {
          address: data.address.trim(),
          land_area_sqm: zoningData?.land_area_sqm ?? undefined,
          region: data.address.includes("서울") ? "서울특별시" : "경기도",
          equity_won: 15_000_000_000,
          use_llm: useLlm,
        },
      });
      const recs = raw.recommendations ?? [];
      const mapped = {
        recommendations: recs.map((item, i) => mapBackendToModel(item, i + 1)),
        all_models: (raw.all_results ?? recs).map((item, i) => mapBackendToModel(item, i + 1)),
        analysis_count: raw.total_types_analyzed ?? recs.length,
        scenarioStatus: raw.scenario_status ?? "actual",
        honest: raw.honest_disclosure ?? raw.special_parcel?.honest_disclosure ?? null,
      };
      setDeepAnalysisResult(mapped);
    } catch {
      // AI 분석 실패 시 사용자 친화적 안내
      setDeepAnalysisError("AI 심층 분석을 사용하려면 관리자 설정에서 AI API 키를 등록하세요. (설정 → API 키 관리)");
    } finally {
      setDeepAnalysisLoading(false);
    }
  }, [data?.address, data?.pnu, isReady, projectId, runAnalysis, zoningData?.land_area_sqm, useLlm]);

  // ── Data Integration: zoning API > local calc > defaults ──
  const aiData = aiResult?.data;

  // Determine data source for characteristics
  const zoningCharacteristics = useMemo(() => {
    if (!zoningData) return null;
    const chars: Array<{ label: string; value: string; status: "safe" | "warning" | "danger" }> = [];

    if (zoningData.land_category) {
      chars.push({ label: "지목", value: zoningData.land_category, status: "safe" });
    }
    if (zoningData.zone_type) {
      chars.push({ label: "용도지역", value: zoningData.zone_type, status: "safe" });
    }
    if (zoningData.land_area_sqm != null) {
      chars.push({
        label: "면적",
        value: `${zoningData.land_area_sqm.toLocaleString()}m²`,
        status: zoningData.land_area_sqm >= 200 ? "safe" : "warning",
      });
    }
    if (zoningData.zone_limits?.max_height_m != null) {
      chars.push({
        label: "높이 제한",
        value: `${zoningData.zone_limits.max_height_m}m`,
        status: zoningData.zone_limits.max_height_m >= 20 ? "safe" : "warning",
      });
    } else {
      chars.push({ label: "높이 제한", value: "별도 제한 없음", status: "safe" });
    }
    // Fill up to 4 items with special district info
    // (백엔드 부분응답·404 프로젝트에서 배열 필드가 누락될 수 있어 무가드 .length 크래시 방지)
    const specialDistricts = zoningData.special_districts ?? [];
    const zoningWarnings = zoningData.warnings ?? [];
    if (chars.length < 4 && specialDistricts.length > 0) {
      chars.push({
        label: "특별구역",
        value: specialDistricts.map(d => d.name).join(", "),
        status: "warning",
      });
    }
    // Pad with warnings from zoning data
    if (chars.length < 4 && zoningWarnings.length > 0) {
      chars.push({
        label: "주의사항",
        value: zoningWarnings[0].slice(0, 30),
        status: "danger",
      });
    }
    return chars.length > 0 ? chars : null;
  }, [zoningData]);

  // Determine data source for scenarios
  // 각 시나리오에 tentative(선행절차 전제 잠정)·tentativeReason을 전파해, 렌더에서 확신 % 대신
  //   '잠정' 배지로 표기한다(도로·학교·맹지 등 특이부지 할루시네이션 차단).
  const scenarioItems = useMemo(() => {
    // Priority 1: deep analysis result
    if (deepAnalysisResult?.recommendations?.length) {
      return deepAnalysisResult.recommendations.slice(0, 3).map(r => ({
        title: r.type_name,
        score: r.composite_score != null ? Math.round(r.composite_score) : 0,
        reason: recommendReason(r),
        isReal: true,
        tentative: r.tentative,
        tentativeReason: r.tentative_reason,
      }));
    }
    // Priority 2: auto-recommend API
    if (scenarioData?.recommendations?.length) {
      return scenarioData.recommendations.slice(0, 3).map(r => ({
        title: r.type_name,
        score: r.composite_score != null ? Math.round(r.composite_score) : 0,
        reason: recommendReason(r),
        isReal: true,
        tentative: r.tentative,
        tentativeReason: r.tentative_reason,
      }));
    }
    // Priority 3: AI analyze client result
    if (aiData?.scenarios?.length) {
      return (aiData.scenarios ?? []).map(s => ({ ...s, isReal: true, tentative: false, tentativeReason: null as string | null }));
    }
    // Priority 4: local fallback
    if (localResult?.scenarios?.length) {
      return (localResult.scenarios ?? []).map(s => ({ ...s, isReal: false, tentative: false, tentativeReason: null as string | null }));
    }
    return [];
  }, [deepAnalysisResult, scenarioData, aiData, localResult]);

  const isScenarioReal = scenarioItems.length > 0 && scenarioItems[0].isReal;
  // ── 특이부지 게이트 신호(2차 방어선) — /zoning/analyze(data.address 기준) 또는 store가 준 ──
  //   special_parcel.developability가 '개발 가능(POSSIBLE)'이 아니면(=선행절차/조건부/제한/불가)
  //   시나리오 % 를 확정처럼 노출하지 않는다. 시나리오 API가 (대표 재조준 전 등으로) tentative를
  //   못 채웠어도, 이 게이트만으로 잠정 렌더(배지·점선·배너)를 강제한다 → "도로 타운하우스 88%
  //   확정" 할루시네이션을 이중으로 차단. (POSSIBLE이면 일반 부지로 간주해 확정% 무회귀 유지.)
  const specialGateTentative = useMemo(() => {
    // 소스 합류(우선순위 무관·하나라도 비-POSSIBLE이면 잠정): ①/zoning/analyze special_parcel
    //   ②다필지 통합 developability(integrated-analysis) ③store specialParcel.
    const candidates: Array<string | null> = [
      (zoningData?.special_parcel?.is_special === true)
        ? (zoningData.special_parcel.developability ?? null)
        : null,
      integratedData?.developability ?? null,
      (siteAnalysis?.specialParcel?.isSpecial ? (siteAnalysis.specialParcel.developability ?? null) : null),
    ];
    const devs = candidates.filter((d): d is string => d != null);
    if (devs.length === 0) return false;
    // POSSIBLE 외 모든 게이트는 잠정 처리 — 하나라도 비-POSSIBLE이면 잠정.
    return devs.some((d) => String(d).toUpperCase() !== "POSSIBLE");
  }, [zoningData?.special_parcel, integratedData?.developability, siteAnalysis?.specialParcel]);
  // 시나리오 전체가 선행절차 전제 잠정치인지 — 백엔드 scenario_status·후보 tentative·특이부지 게이트.
  const isScenarioTentative = useMemo(() => {
    const status = deepAnalysisResult?.scenarioStatus ?? scenarioData?.scenarioStatus;
    if (status === "tentative") return true;
    if (specialGateTentative) return true;
    // 다필지 통합 시나리오 status가 'computed'가 아니면(tentative/blocked) 확정% 억제.
    const iStatus = integratedData?.scenario?.status;
    if (iStatus != null && iStatus !== "computed") return true;
    return scenarioItems.some((s) => "tentative" in s && s.tentative === true);
  }, [deepAnalysisResult?.scenarioStatus, scenarioData?.scenarioStatus, specialGateTentative, integratedData?.scenario?.status, scenarioItems]);
  // 잠정 사유(첫 후보 우선) + 정직고지 — 잠정 안내 배너 표시용. 특이부지 honest_disclosure도 표면화.
  const tentativeDisclosure = useMemo(() => {
    const fromItem = scenarioItems.find((s) => "tentativeReason" in s && s.tentativeReason)?.tentativeReason as string | undefined;
    const specialHonest = (zoningData?.special_parcel?.is_special === true)
      ? (zoningData.special_parcel.honest_disclosure ?? null)
      : (siteAnalysis?.specialParcel?.isSpecial ? (siteAnalysis.specialParcel.honest ?? null) : null);
    // 다필지 통합분석의 정직고지(scenario.disclosure 우선, 없으면 honest_disclosure)도 표면화.
    const integratedHonest = integratedData
      ? ((integratedData.scenario?.disclosure ?? null) ?? (integratedData.honest_disclosure ?? null))
      : null;
    return fromItem ?? deepAnalysisResult?.honest ?? scenarioData?.honest ?? integratedHonest ?? specialHonest ?? null;
  }, [scenarioItems, deepAnalysisResult?.honest, scenarioData?.honest, integratedData, zoningData?.special_parcel, siteAnalysis?.specialParcel]);

  // ── 다필지 통합 산출근거(EvidencePanel) — 백엔드가 반환한 실값으로만 산식 트레이스 구성. ──
  //   가짜값/가짜URL 0: 응답에 없는 값(null)은 항목 자체를 만들지 않는다(가짜0 금지·정직 미표시).
  //   통합GFA=Σ(필지면적×실효용적률), 건폐면적=Σ(필지면적×실효건폐율), 면적가중 실효 건폐/용적의
  //   근거(gfa_basis·far_basis_note)를 그대로 인용한다(백엔드 산식 미접촉).
  const integratedEvidenceItems = useMemo<EvidenceItem[]>(() => {
    const ig = integratedData?.integrated;
    if (!ig) return [];
    const items: EvidenceItem[] = [];
    // 통합 대지면적(Σ 필지면적)
    if (ig.total_area_sqm != null) {
      items.push({
        label: "통합 대지면적",
        value: `${Math.round(ig.total_area_sqm).toLocaleString()}㎡`,
        basis: `${integratedData?.parcel_count ?? (ssotParcels?.length ?? 0)}개 필지 면적 합계(Σ)`,
      });
    }
    // 통합 GFA — gfa_basis 근거가 있으면 그대로 인용(예: per_parcel_effective_sum).
    if (ig.integrated_gfa_sqm != null) {
      items.push({
        label: "통합 연면적(GFA)",
        value: `${Math.round(ig.integrated_gfa_sqm).toLocaleString()}㎡`,
        basis: ig.gfa_basis
          ? `Σ(필지면적 × 실효용적률) · ${ig.gfa_basis}`
          : "Σ(필지면적 × 실효용적률)",
      });
    }
    // 통합 건폐면적 — Σ(필지면적×실효건폐율)
    if (ig.integrated_footprint_sqm != null) {
      items.push({
        label: "통합 건폐면적",
        value: `${Math.round(ig.integrated_footprint_sqm).toLocaleString()}㎡`,
        basis: "Σ(필지면적 × 실효건폐율)",
      });
    }
    // 면적가중 실효 건폐율 — far_basis_note 근거 인용(있을 때).
    if (ig.blended_bcr_eff_pct != null) {
      items.push({
        label: "면적가중 실효 건폐율",
        value: `${ig.blended_bcr_eff_pct}%`,
        basis: ig.far_basis_note ?? "필지별 실효 건폐율의 면적가중 평균",
      });
    }
    // 면적가중 실효 용적률 — far_basis_note 근거 인용(있을 때).
    if (ig.blended_far_eff_pct != null) {
      items.push({
        label: "면적가중 실효 용적률",
        value: `${ig.blended_far_eff_pct}%`,
        basis: ig.far_basis_note ?? "필지별 실효 용적률의 면적가중 평균",
      });
    }
    return items;
  }, [integratedData?.integrated, integratedData?.parcel_count, ssotParcels?.length]);

  const analysis = {
    zoning: {
      current: zoningData?.zone_type || aiData?.zoning?.current || localResult?.zoningName || "용도지역 분석 대기",
      target: aiData?.zoning?.target || (localResult ? `${localResult.zoningCategory}지역 상위 변경` : "—"),
      possibility: aiData?.zoning?.probability ?? (localResult ? 35 : 0),
      reason: zoningData?.zone_limits?.legal_basis || aiData?.zoning?.reason || localResult?.summary || "주소를 입력하세요",
    },
    characteristics: aiData?.characteristics?.map(c => ({
      label: c.label,
      value: c.value,
      status: c.status as "safe" | "warning" | "danger",
    })) || zoningCharacteristics || localResult?.characteristics || [
      { label: "경사도", value: "—", status: "safe" as const },
      { label: "접도 상태", value: "—", status: "safe" as const },
      { label: "지형", value: "—", status: "safe" as const },
      { label: "높이 제한", value: "—", status: "warning" as const },
    ],
    summary: aiData?.summary || localResult?.summary || null,
    // ── 용적/건폐 한도: 실효 우선(법정상한을 실효처럼 표시하던 결함 교정) ──
    //   1순위 실효(effective_far 자체 API 응답), 2순위 SSOT 헬퍼(통합>실효>법정), 없으면 zone_limits/로컬.
    //   ★SSOT 읽기 통일: 종전 siteAnalysis?.effectiveBcrPct/FarPct 직접읽기 대신 resolveBcrPct/FarPct
    //   (통합 > 실효 > 법정)로 교체 — 다필지에서 대표 1필지 값 누락/오염 차단. 자체 API 응답이 있으면
    //   그것이 우선(자체 패치가 SSOT 폴백보다 fresher할 수 있으므로 우선순위 그대로 유지·무회귀).
    buildingCoverageMax:
      zoningData?.effective_far?.effective_bcr_pct ??
      resolveBcrPct(siteAnalysis) ??
      zoningData?.zone_limits?.max_bcr_pct ??
      localResult?.buildingCoverageMax ?? 0,
    floorAreaRatioMax:
      zoningData?.effective_far?.effective_far_pct ??
      resolveFarPct(siteAnalysis) ??
      zoningData?.zone_limits?.max_far_pct ??
      localResult?.floorAreaRatioMax ?? 0,
    isEffectiveBcr:
      zoningData?.effective_far?.effective_bcr_pct != null ||
      resolveBcrPct(siteAnalysis) != null,
    isEffectiveFar:
      zoningData?.effective_far?.effective_far_pct != null ||
      resolveFarPct(siteAnalysis) != null,
    legalBcrMax:
      zoningData?.effective_far?.national_bcr_pct ??
      siteAnalysis?.nationalBcrPct ??
      zoningData?.zone_limits?.max_bcr_pct ?? null,
    legalFarMax:
      zoningData?.effective_far?.national_far_pct ??
      siteAnalysis?.nationalFarPct ??
      zoningData?.zone_limits?.max_far_pct ?? null,
    heightLimit: zoningData?.zone_limits?.max_height_m ?? localResult?.heightLimit,
    officialPricePerSqm: zoningData?.official_price_per_sqm ?? null,
    landAreaSqm: zoningData?.land_area_sqm ?? null,
  };

  // ── 특이부지 게이트 — API 응답 우선, 없으면 store(specialParcel) 폴백. is_special일 때만 카드 렌더. ──
  // DEVELOPABILITY_LABEL은 zoning-ssot.ts 공용 상수 사용.
  const specialParcel = useMemo(() => {
    const api = zoningData?.special_parcel;
    if (api?.is_special === true) {
      // ★공용 specialFactorLabels로 category 추출(dict factor "[object Object]" 오렌더 방지·전역 일관).
      const factors = specialFactorLabels(api.factors);
      // 개발행위허가 등 선행요건 상세(implications+§56/§58)를 가진 factor만 별도 상세 렌더.
      const precondFactors = preconditionFactors(api.factors);
      // verified 법령링크(요인별 legal_refs 병합·중복 제거) — 죽은 링크 금지(verified만).
      const seen = new Set<string>();
      const legalRefs: BackendLegalRef[] = [];
      for (const f of api.factors ?? []) {
        if (typeof f === "string" || !f) continue;
        for (const r of f.legal_refs ?? []) {
          if (!r || (r.url_status || "").trim() !== "verified" || !(r.url || "").trim()) continue;
          const k = r.key || r.url || "";
          if (k && !seen.has(k)) {
            seen.add(k);
            legalRefs.push(r);
          }
        }
      }
      return {
        developability: api.developability ?? api.severity_label ?? null,
        factors,
        precondFactors,
        honest: api.honest_disclosure ?? null,
        legalRefs,
        // 법규 예비판정/부담금 고지용 원본 factors(객체형) — SpecialParcelLegalPrelim이
        //   forest_facts·preliminary_assessment·charge_notice를 소비(없으면 섹션 미표시).
        rawFactors: (api.factors ?? []).filter(
          (f): f is SpecialParcelFactorLike => !!f && typeof f !== "string",
        ),
      };
    }
    // store 폴백(mapZoningRich가 기록): isSpecial true일 때만. (store엔 legal_refs 미보존 → 빈 링크)
    const st = siteAnalysis?.specialParcel;
    if (st?.isSpecial) {
      return {
        developability: st.developability,
        factors: st.factors ?? [],
        precondFactors: [] as SpecialFactorRich[],
        honest: st.honest,
        legalRefs: [] as BackendLegalRef[],
        // store엔 예비판정 원본 미보존 → 빈 배열(섹션 미표시 — 무날조).
        rawFactors: [] as SpecialParcelFactorLike[],
      };
    }
    return null;
  }, [zoningData?.special_parcel, siteAnalysis?.specialParcel]);

  const hasData = !!localResult || !!zoningData;
  const hasZoningApi = !!zoningData;

  // ── Data source label ──
  const dataSourceLabel = useMemo(() => {
    if (isAnalyzing || deepAnalysisLoading) return { dot: "bg-amber-400 animate-pulse", text: "AI 분석 중...", color: "text-amber-400" };
    if (deepAnalysisResult || aiData) return { dot: "bg-emerald-400", text: "AI 분석 완료", color: "text-emerald-400" };
    if (hasZoningApi) return { dot: "bg-teal-400", text: "실시간 API 연동 완료", color: "text-teal-400" };
    if (zoningError || txError || scenarioError) return { dot: "bg-amber-400", text: "API 연결 실패 — 로컬 추정 표시 중", color: "text-amber-400" };
    if (localResult) return { dot: "bg-blue-400", text: "로컬 추정값 (백엔드 연결 필요)", color: "text-blue-400" };
    return { dot: "bg-slate-400", text: "대기 중", color: "text-[var(--accent-strong)]" };
  }, [isAnalyzing, deepAnalysisLoading, deepAnalysisResult, aiData, hasZoningApi, localResult]);

  return (
    <div className="relative w-full rounded-[3rem] border border-[var(--line)] bg-[var(--surface-strong)] shadow-[var(--shadow-xl)] overflow-hidden">
      {/* ── Background Decorations (pointer-events-none) ── */}
      <div className="absolute inset-0 pointer-events-none">
        <div className="absolute inset-0 opacity-40 bg-gradient-to-br from-blue-900/20 via-slate-800/30 to-emerald-900/20" />
        <div className="absolute inset-0 bg-[linear-gradient(var(--line)_1px,transparent_1px),linear-gradient(90deg,var(--line)_1px,transparent_1px)] bg-[size:40px_40px] opacity-10 dark:opacity-30" />
      </div>

      {/* ── MAIN CONTENT GRID (2-col on lg/md, 1-col on mobile) ── */}
      <div className="relative z-10 grid grid-cols-1 md:grid-cols-2 gap-4 md:gap-5 lg:gap-6 p-4 md:p-6 lg:p-8">

        {/* === LEFT PANEL: Analysis === */}
        <div className="space-y-5">
          <motion.div
            initial={{ x: -20, opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            className="glass rounded-[2rem] p-5 md:p-6 lg:p-7 border border-[var(--line-strong)] shadow-[var(--shadow-xl)]"
          >
            {/* Header */}
            <div className="flex items-center gap-3 mb-5">
              <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-[var(--accent-soft)] text-[var(--accent-strong)]">
                <Icons.Sparkles />
              </div>
              <div>
                <h4 className="text-lg font-black text-[var(--text-primary)] tracking-tight">지능형 입지 분석</h4>
                <p className="text-[10px] font-black uppercase tracking-[0.2em] flex items-center gap-1">
                  <span className={`inline-block h-1.5 w-1.5 rounded-full ${dataSourceLabel.dot}`} />
                  <span className={dataSourceLabel.color}>{dataSourceLabel.text}</span>
                </p>
              </div>
            </div>

            {/* AI 내러티브 옵트인(기본 on — 기존 동작 보존) — 자동 추천·심층 분석 버튼이 공유. */}
            <UseLlmToggle
              checked={useLlm}
              onChange={setUseLlm}
              label="AI 내러티브 포함"
              hint="자동 추천·심층 분석에도 적용됩니다(끄면 결정론 추천만·무과금)"
              className="mb-4 flex w-fit cursor-pointer items-center gap-2 text-[11px] text-[var(--text-secondary)]"
            />

            {/* Zoning & Regulation KPI */}
            <div className="space-y-4">
              {/* Building Coverage & FAR */}
              {hasData && (
                <div className="grid grid-cols-2 gap-3">
                  <div className="rounded-xl bg-[var(--surface-muted)] p-4 border border-[var(--line)] text-center">
                    {/* 실효 우선 — 라벨로 실효/법정상한을 구분(법정상한을 실효처럼 오인하던 결함 교정) */}
                    <p className="text-[9px] font-black text-blue-400 uppercase tracking-widest mb-1">
                      건폐율 {analysis.isEffectiveBcr ? "(실효)" : "(법정상한)"}
                    </p>
                    <p className="text-2xl font-black text-[var(--text-primary)]">
                      {analysis.buildingCoverageMax}<span className="text-xs ml-0.5">%</span>
                    </p>
                    {/* 실효<법정일 때만 법정상한 보조 병기 */}
                    {analysis.isEffectiveBcr && analysis.legalBcrMax != null && analysis.legalBcrMax > analysis.buildingCoverageMax && (
                      <span className="text-[8px] text-[var(--text-hint)]">법정상한 {analysis.legalBcrMax}%</span>
                    )}
                    {zoningLoading && <span className="text-[8px] text-[var(--text-hint)]">조회 중...</span>}
                  </div>
                  <div className="rounded-xl bg-[var(--surface-muted)] p-4 border border-[var(--line)] text-center">
                    <p className="text-[9px] font-black text-emerald-400 uppercase tracking-widest mb-1">
                      용적률 {analysis.isEffectiveFar ? "(실효)" : "(법정상한)"}
                    </p>
                    <p className="text-2xl font-black text-[var(--text-primary)]">
                      {analysis.floorAreaRatioMax}<span className="text-xs ml-0.5">%</span>
                    </p>
                    {analysis.isEffectiveFar && analysis.legalFarMax != null && analysis.legalFarMax > analysis.floorAreaRatioMax && (
                      <span className="text-[8px] text-[var(--text-hint)]">법정상한 {analysis.legalFarMax}%</span>
                    )}
                    {zoningLoading && <span className="text-[8px] text-[var(--text-hint)]">조회 중...</span>}
                  </div>
                </div>
              )}

              {/* ── 다필지 통합분석 카드 — parcelCount>1일 때만 렌더(읽기 소비, SSOT 미기록). ──
                  대표 단일필지가 아닌, 면적가중 건폐/용적·통합GFA·용도혼재·인접성을 종합 표시한다.
                  무목업: integratedData 미확보(로딩/실패)면 정직표기, 확보 시에만 수치 노출. */}
              {isMultiParcel && (
                <div className="rounded-xl border border-[var(--line-strong)] bg-[var(--surface-muted)] p-4">
                  <p className="text-[10px] font-black text-[var(--accent-strong)] uppercase tracking-widest mb-2 flex items-center gap-1.5">
                    <Icons.Layers />
                    다필지 통합분석
                    <span className="normal-case tracking-normal text-[var(--text-hint)]">
                      · {integratedData?.parcel_count ?? siteAnalysis?.parcelCount ?? (ssotParcels?.length ?? 0)}필지
                    </span>
                  </p>
                  {integratedLoading && !integratedData ? (
                    <div className="flex items-center gap-2 py-1">
                      <Icons.Loader />
                      <span className="text-xs text-[var(--text-secondary)]">통합분석 조회 중...</span>
                    </div>
                  ) : integratedData ? (
                    <div className="space-y-3">
                      {/* 대표 용도지역(혼재 배지) */}
                      <div className="flex flex-wrap items-center gap-2">
                        {integratedData.dominant_zone && (
                          <span className="rounded-full bg-[var(--accent-soft)] px-3 py-1 text-xs font-black text-[var(--accent-strong)]">
                            {integratedData.dominant_zone}
                          </span>
                        )}
                        {integratedData.dominant_basis === "mixed_review_required" && (
                          <span className="rounded-full border border-[color-mix(in_srgb,var(--status-warning)_36%,transparent)] bg-[color-mix(in_srgb,var(--status-warning)_10%,transparent)] px-2.5 py-1 text-[10px] font-black text-[var(--status-warning)]">
                            혼재 · 분리검토
                          </span>
                        )}
                      </div>

                      {/* 면적가중 실효 건폐/용적 + 통합 GFA (실효 우선·법정상한 보조병기 — 실효>법정 모순 방지) */}
                      <div className="grid grid-cols-3 gap-2">
                        <div className="rounded-lg bg-[var(--surface-soft)] p-2.5 text-center border border-[var(--line)]">
                          <p className="text-[8px] font-black text-blue-400 uppercase tracking-widest mb-0.5">건폐율(통합실효)</p>
                          <p className="text-base font-black text-[var(--text-primary)]">
                            {integratedData.integrated?.blended_bcr_eff_pct != null
                              ? `${integratedData.integrated.blended_bcr_eff_pct}%`
                              : "—"}
                          </p>
                          {/* 실효 < 법정상한일 때만 법정 보조병기(가짜0 금지 — legal이 실제로 존재하고 더 클 때만) */}
                          {integratedData.integrated?.blended_bcr_eff_pct != null &&
                            integratedData.integrated?.blended_bcr_legal_pct != null &&
                            integratedData.integrated.blended_bcr_legal_pct > integratedData.integrated.blended_bcr_eff_pct && (
                              <span className="block text-[8px] text-[var(--text-hint)]">법정상한 {integratedData.integrated.blended_bcr_legal_pct}%</span>
                            )}
                        </div>
                        <div className="rounded-lg bg-[var(--surface-soft)] p-2.5 text-center border border-[var(--line)]">
                          <p className="text-[8px] font-black text-emerald-400 uppercase tracking-widest mb-0.5">용적률(통합실효)</p>
                          <p className="text-base font-black text-[var(--text-primary)]">
                            {integratedData.integrated?.blended_far_eff_pct != null
                              ? `${integratedData.integrated.blended_far_eff_pct}%`
                              : "—"}
                          </p>
                          {integratedData.integrated?.blended_far_eff_pct != null &&
                            integratedData.integrated?.blended_far_legal_pct != null &&
                            integratedData.integrated.blended_far_legal_pct > integratedData.integrated.blended_far_eff_pct && (
                              <span className="block text-[8px] text-[var(--text-hint)]">법정상한 {integratedData.integrated.blended_far_legal_pct}%</span>
                            )}
                        </div>
                        <div className="rounded-lg bg-[var(--surface-soft)] p-2.5 text-center border border-[var(--line)]">
                          <p className="text-[8px] font-black text-teal-400 uppercase tracking-widest mb-0.5">통합 GFA</p>
                          <p className="text-base font-black text-[var(--text-primary)]">
                            {integratedData.integrated?.integrated_gfa_sqm != null
                              ? `${Math.round(integratedData.integrated.integrated_gfa_sqm).toLocaleString()}㎡`
                              : "—"}
                          </p>
                        </div>
                      </div>

                      {/* 통합 대지면적·건폐면적 — 대지/GFA/건폐면적 3요소 규모 파악(있는 값만 정직표기) */}
                      {(integratedData.integrated?.total_area_sqm != null ||
                        integratedData.integrated?.integrated_footprint_sqm != null) && (
                        <div className="grid grid-cols-2 gap-2">
                          {integratedData.integrated?.total_area_sqm != null && (
                            <div className="rounded-lg bg-[var(--surface-soft)] p-2.5 text-center border border-[var(--line)]">
                              <p className="text-[8px] font-black text-[var(--text-hint)] uppercase tracking-widest mb-0.5">통합 대지면적</p>
                              <p className="text-sm font-black text-[var(--text-primary)]">
                                {Math.round(integratedData.integrated.total_area_sqm).toLocaleString()}㎡
                              </p>
                            </div>
                          )}
                          {integratedData.integrated?.integrated_footprint_sqm != null && (
                            <div className="rounded-lg bg-[var(--surface-soft)] p-2.5 text-center border border-[var(--line)]">
                              <p className="text-[8px] font-black text-[var(--text-hint)] uppercase tracking-widest mb-0.5">통합 건폐면적</p>
                              <p className="text-sm font-black text-[var(--text-primary)]">
                                {Math.round(integratedData.integrated.integrated_footprint_sqm).toLocaleString()}㎡
                              </p>
                            </div>
                          )}
                        </div>
                      )}
                      {integratedData.integrated?.far_basis_note && (
                        <p className="text-[9px] text-[var(--text-hint)] leading-relaxed">{integratedData.integrated.far_basis_note}</p>
                      )}

                      {/* 통합 산출근거(EvidencePanel) — 응답 실값으로만 산식 트레이스(가짜값/가짜URL 0) */}
                      {integratedEvidenceItems.length > 0 && (
                        <EvidencePanel items={integratedEvidenceItems} title="통합분석 산출 근거" defaultOpen={false} />
                      )}

                      {/* 용도별 면적/비율 + 용도별 규제한도(zone_mix) — 혼재 부지의 용도별 분포·실효/법정 한도 정직표기.
                          ★null 가드: 조례 미확보 등으로 *_eff/*_legal이 null이면 해당 한도는 미표시(가짜0 금지). */}
                      {(integratedData.zone_mix?.length ?? 0) > 0 && (
                        <div className="space-y-1.5">
                          <p className="text-[9px] font-black text-[var(--text-hint)] uppercase tracking-widest">용도별 구성 · 규제한도</p>
                          {(integratedData.zone_mix ?? []).map((z, i) => {
                            // 건폐/용적을 실효(법정상한) 한 줄로 병기 — 실효 우선, 법정은 보조.
                            const bcrTxt =
                              z.bcr_eff != null
                                ? `건폐 ${z.bcr_eff}%${z.bcr_legal != null && z.bcr_legal > z.bcr_eff ? `(법정 ${z.bcr_legal}%)` : ""}`
                                : z.bcr_legal != null
                                ? `건폐 법정 ${z.bcr_legal}%`
                                : null;
                            const farTxt =
                              z.far_eff != null
                                ? `용적 ${z.far_eff}%${z.far_legal != null && z.far_legal > z.far_eff ? `(법정 ${z.far_legal}%)` : ""}`
                                : z.far_legal != null
                                ? `용적 법정 ${z.far_legal}%`
                                : null;
                            const limitParts = [bcrTxt, farTxt].filter((t): t is string => !!t);
                            return (
                              <div key={`zmix-${i}`} className="rounded-lg bg-[var(--surface-soft)] px-2.5 py-1.5 border border-[var(--line)]">
                                <div className="flex items-center justify-between text-[10px]">
                                  <span className="font-bold text-[var(--text-secondary)]">{z.zone ?? "—"}</span>
                                  <span className="text-[var(--text-hint)]">
                                    {z.area_sqm != null ? `${Math.round(z.area_sqm).toLocaleString()}㎡` : "—"}
                                    {z.share_pct != null ? ` · ${z.share_pct}%` : ""}
                                  </span>
                                </div>
                                {limitParts.length > 0 && (
                                  <p className="mt-0.5 text-[9px] text-[var(--text-tertiary)]">{limitParts.join(" · ")}</p>
                                )}
                              </div>
                            );
                          })}
                        </div>
                      )}

                      {/* 인접성 안내(통합개발 가능여부 신호) — 연담여부·단편수 구조화 병기.
                          ★null 가드: contiguous=null(형상 미확보)은 '아니오'가 아닌 '미확정'으로(오도 방지). */}
                      {(integratedData.adjacency?.note ||
                        integratedData.adjacency?.contiguous != null ||
                        integratedData.adjacency?.components != null) && (
                        <div className="text-[10px] text-[var(--text-secondary)] leading-relaxed">
                          <span className="font-black text-[var(--accent-strong)]">인접성</span>
                          {integratedData.adjacency?.contiguous != null && (
                            <span
                              className={`ml-1.5 rounded-full px-2 py-0.5 text-[9px] font-black ${
                                integratedData.adjacency.contiguous
                                  ? "bg-[color-mix(in_srgb,var(--status-success)_12%,transparent)] text-[var(--status-success)]"
                                  : "bg-[color-mix(in_srgb,var(--status-warning)_12%,transparent)] text-[var(--status-warning)]"
                              }`}
                            >
                              연담 {integratedData.adjacency.contiguous ? "예" : "아니오"}
                            </span>
                          )}
                          {integratedData.adjacency?.contiguous == null && (
                            <span className="ml-1.5 rounded-full bg-[var(--surface-soft)] px-2 py-0.5 text-[9px] font-black text-[var(--text-hint)]">
                              연담 미확정
                            </span>
                          )}
                          {integratedData.adjacency?.components != null && (
                            <span className="ml-1.5 text-[var(--text-hint)]">· 단편 {integratedData.adjacency.components}개</span>
                          )}
                          {integratedData.adjacency?.note && (
                            <span className="ml-1"> · {integratedData.adjacency.note}</span>
                          )}
                        </div>
                      )}

                      {/* 시나리오 status 분기: computed=확정, tentative/blocked=잠정 배너(확정% 억제) */}
                      {integratedData.scenario?.status && integratedData.scenario.status !== "computed" && (
                        <div className="rounded-lg border border-dashed border-[color-mix(in_srgb,var(--status-warning)_36%,transparent)] bg-[color-mix(in_srgb,var(--status-warning)_10%,transparent)] p-2.5">
                          <p className="text-[10px] font-black text-[var(--status-warning)] uppercase tracking-widest mb-1 flex items-center gap-1.5">
                            <Icons.AlertCircle />
                            {integratedData.scenario.status === "blocked" ? "개발 제한 · 통합 시나리오 보류" : "선행절차 전제 · 잠정 (확정 아님)"}
                          </p>
                          {(integratedData.scenario.disclosure || integratedData.honest_disclosure) && (
                            <p className="text-[10px] leading-relaxed text-[var(--text-secondary)] font-medium">
                              {integratedData.scenario.disclosure || integratedData.honest_disclosure}
                            </p>
                          )}
                        </div>
                      )}

                      {/* 통합분석 경고(warnings) — 혼재·조례결측·형상미확보·위임실패 등 정직표기(무목업).
                          백엔드가 실제 축적한 string[]만 노출(가짜 경고 생성 금지). */}
                      {(integratedData.warnings?.length ?? 0) > 0 && (
                        <div className="rounded-lg border border-[color-mix(in_srgb,var(--status-warning)_30%,transparent)] bg-[color-mix(in_srgb,var(--status-warning)_8%,transparent)] p-2.5">
                          <p className="text-[10px] font-black text-[var(--status-warning)] uppercase tracking-widest mb-1 flex items-center gap-1.5">
                            <Icons.AlertCircle />검토 경고 · {integratedData.warnings?.length}건
                          </p>
                          <ul className="space-y-0.5">
                            {(integratedData.warnings ?? []).map((w, i) => (
                              <li key={`iwarn-${i}`} className="text-[10px] leading-relaxed text-[var(--text-secondary)]">· {w}</li>
                            ))}
                          </ul>
                        </div>
                      )}

                      {/* 필지별 상세(per_parcel) — 통합 산출근거 추적용. 토글(기본 접힘). 실효(법정)·특이·상태 정직표기. */}
                      {(integratedData.per_parcel?.length ?? 0) > 0 && (
                        <div className="rounded-lg border border-[var(--line)] bg-[var(--surface-soft)]">
                          <button
                            type="button"
                            onClick={() => setPerParcelOpen((v) => !v)}
                            aria-expanded={perParcelOpen}
                            className="flex w-full items-center justify-between px-3 py-2 text-left"
                          >
                            <span className="text-[10px] font-black text-[var(--text-secondary)] uppercase tracking-widest">
                              필지별 상세 · {integratedData.per_parcel?.length}필지
                            </span>
                            <span className="text-[10px] font-semibold text-[var(--accent-strong)]">{perParcelOpen ? "접기" : "펼치기"}</span>
                          </button>
                          {perParcelOpen && (
                            <div className="space-y-1.5 border-t border-[var(--line)] px-3 py-2">
                              {(integratedData.per_parcel ?? []).map((p, i) => {
                                // 건폐/용적 실효(법정) 한 줄 — null은 미표시(가짜0 금지).
                                const bcr = p.bcr_eff_pct != null
                                  ? `건폐 ${p.bcr_eff_pct}%${p.bcr_legal_pct != null && p.bcr_legal_pct > p.bcr_eff_pct ? `(법정 ${p.bcr_legal_pct}%)` : ""}`
                                  : null;
                                const far = p.far_eff_pct != null
                                  ? `용적 ${p.far_eff_pct}%${p.far_legal_pct != null && p.far_legal_pct > p.far_eff_pct ? `(법정 ${p.far_legal_pct}%)` : ""}`
                                  : null;
                                const metrics = [bcr, far].filter((t): t is string => !!t);
                                const isSpecial = p.special_parcel?.is_special === true;
                                return (
                                  <div key={`pp-${i}`} className="rounded-md bg-[var(--surface-muted)] px-2.5 py-1.5 border border-[var(--line)]">
                                    <div className="flex items-center justify-between gap-2 text-[10px]">
                                      <span className="font-bold text-[var(--text-secondary)] truncate">
                                        {p.address ?? p.pnu ?? `필지 ${i + 1}`}
                                      </span>
                                      <span className="shrink-0 text-[var(--text-hint)]">
                                        {p.area_sqm != null ? `${Math.round(p.area_sqm).toLocaleString()}㎡` : "—"}
                                      </span>
                                    </div>
                                    <div className="mt-0.5 flex flex-wrap items-center gap-x-1.5 gap-y-0.5 text-[9px] text-[var(--text-tertiary)]">
                                      {p.zone_type && <span className="font-semibold text-[var(--text-secondary)]">{p.zone_type}</span>}
                                      {metrics.length > 0 && <span>{metrics.join(" · ")}</span>}
                                      {isSpecial && p.special_parcel?.developability && (
                                        <span className="rounded-full bg-[color-mix(in_srgb,var(--status-warning)_12%,transparent)] px-1.5 py-0.5 font-black text-[var(--status-warning)]">
                                          특이 · {DEVELOPABILITY_LABEL[p.special_parcel.developability] ?? p.special_parcel.developability}
                                        </span>
                                      )}
                                      {p.status && p.status !== "ok" && (
                                        <span className="rounded-full bg-[var(--surface-soft)] px-1.5 py-0.5 font-black text-[var(--text-hint)]">{p.status}</span>
                                      )}
                                    </div>
                                    {p.reason && (
                                      <p className="mt-0.5 text-[9px] leading-relaxed text-[var(--text-hint)]">{p.reason}</p>
                                    )}
                                  </div>
                                );
                              })}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  ) : (
                    <p className="text-[10px] text-[var(--text-hint)] leading-relaxed">
                      {integratedError
                        ? `통합분석을 불러오지 못했습니다 — ${integratedError}`
                        : "필지 보강 완료 후 자동으로 통합분석이 표시됩니다."}
                    </p>
                  )}
                </div>
              )}

              {/* 특이부지 게이트 카드 — is_special일 때만. 임야·학교용지·GB·맹지 등은 법정/실효 한도가
                  그대로 실현되지 않으므로 개발가능성·정직고지를 표시(무목업: 특이 없으면 미표시). */}
              {specialParcel && (
                <div className="rounded-xl border border-[color-mix(in_srgb,var(--status-warning)_36%,transparent)] bg-[color-mix(in_srgb,var(--status-warning)_10%,transparent)] p-4">
                  <p className="text-[10px] font-black text-[var(--status-warning)] uppercase tracking-widest mb-1.5 flex items-center gap-1.5">
                    <Icons.AlertCircle />
                    특이부지{specialParcel.factors.length > 0 ? ` · ${specialParcel.factors.join(" · ")}` : ""}
                    {specialParcel.developability && (
                      <span className="normal-case tracking-normal"> — {DEVELOPABILITY_LABEL[specialParcel.developability] ?? specialParcel.developability}</span>
                    )}
                  </p>
                  {specialParcel.honest && (
                    <p className="text-[10px] leading-relaxed text-[var(--text-secondary)] font-medium">
                      {specialParcel.honest}
                    </p>
                  )}
                  {/* 개발행위허가 선행요건 상세 — CONDITIONAL/PRECONDITION factor의 implications(상세 문구).
                      도시지역 내 녹지 등은 밀도한도(용적/건폐) 충족만으로 개발 확정이 아니라 개발행위허가
                      (§56)·형질변경이 선행/병행돼야 함을 화면에 노출한다(category만이 아닌 상세·정직 고지). */}
                  {specialParcel.precondFactors.map((f, fi) => {
                    const impl = (f.implications ?? []).filter(
                      (s) => typeof s === "string" && s.trim().length > 0,
                    );
                    if (impl.length === 0) return null;
                    return (
                      <div key={`precond-${fi}`} className="mt-2">
                        <p className="text-[9px] font-black text-[var(--status-warning)] uppercase tracking-widest mb-1">
                          {(f.category ?? "개발행위허가 선행요건").toString().trim()} · 선행요건 상세
                        </p>
                        <ul className="list-disc space-y-1 pl-4">
                          {impl.map((s, si) => (
                            <li key={`impl-${si}`} className="text-[10px] leading-5 text-[var(--text-secondary)]">
                              {s}
                            </li>
                          ))}
                        </ul>
                      </div>
                    );
                  })}
                  {/* 법규 예비판정(경사도·입목축적·부담금) — 백엔드 예비판정/부담금 고지가 있을
                      때만 표시(additive·무목업). '확정 아님·공식조사 필요' 정직 라벨 동반. */}
                  <SpecialParcelLegalPrelim factors={specialParcel.rawFactors} />
                  {/* 근거법령 — verified면 클릭 가능한 law.go.kr 딥링크 칩(미verified는 미표시·죽은 링크 금지) */}
                  {specialParcel.legalRefs.length > 0 && (
                    <div className="mt-2 flex flex-wrap items-center gap-1.5">
                      <span className="text-[9px] font-bold text-[var(--text-hint)]">근거법령:</span>
                      {specialParcel.legalRefs.map((r, i) => (
                        <LegalRefChip
                          key={`${r.key || r.law_name || "ref"}-${i}`}
                          lawName={r.law_name || ""}
                          article={r.article}
                          title={r.title}
                          url={r.url}
                        />
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* Zoning */}
              <div className="rounded-xl bg-[var(--surface-muted)] p-4 border border-[var(--line)]">
                <p className="text-[9px] font-black text-[var(--accent-strong)] mb-2 uppercase tracking-widest flex items-center gap-1.5">
                  <Icons.TrendingUp />용도지역
                </p>
                {zoningLoading ? (
                  <div className="flex items-center gap-2">
                    <Icons.Loader />
                    <span className="text-xs text-[var(--text-secondary)]">용도지역 조회 중...</span>
                  </div>
                ) : (
                  <>
                    <p className="text-lg font-black text-[var(--text-primary)] mb-1">{analysis.zoning.current}</p>
                    <p className="text-[10px] text-[var(--text-secondary)] font-medium leading-relaxed">{analysis.zoning.reason}</p>
                  </>
                )}
              </div>

              {/* Land Characteristics */}
              <div className="rounded-xl bg-[var(--surface-muted)] p-4 border border-[var(--line)]">
                <p className="text-[9px] font-black text-blue-400 mb-3 uppercase tracking-widest flex items-center gap-1.5">
                  토지 형질 분석
                  {!hasZoningApi && hasData && (
                    <span className="text-[8px] font-medium text-[var(--text-hint)] normal-case tracking-normal">(로컬 추정)</span>
                  )}
                </p>
                {zoningLoading ? (
                  <div className="flex items-center gap-2 py-2">
                    <Icons.Loader />
                    <span className="text-xs text-[var(--text-secondary)]">필지 정보 조회 중...</span>
                  </div>
                ) : (
                  <div className="grid grid-cols-2 gap-2">
                    {analysis.characteristics.slice(0, 4).map((c, i) => (
                      <div key={i} className={`flex flex-col gap-1 rounded-lg border p-2 ${statusColors[c.status] || statusColors.safe}`}>
                        <span className="text-[9px] font-black uppercase tracking-tighter opacity-80">{c.label}</span>
                        <span className="text-xs font-bold">{c.value}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>

            {/* Zoning API Error */}
            {zoningError && (
              <div className="mt-3 rounded-xl bg-amber-500/10 border border-amber-500/20 p-3">
                <p className="text-xs text-amber-400 font-medium flex items-center gap-1.5">
                  <Icons.AlertCircle />{zoningError}
                </p>
              </div>
            )}

            {/* AI/Deep Analysis Error */}
            {(aiError || deepAnalysisError) && (
              <div className="mt-3 rounded-xl bg-red-500/10 border border-red-500/20 p-3">
                <p className="text-xs text-red-400 font-medium">{aiError?.message || deepAnalysisError}</p>
              </div>
            )}

            {/* AI Summary */}
            {(aiData?.summary || deepAnalysisResult) && (
              <div className="mt-3 rounded-xl bg-emerald-500/10 border border-emerald-500/20 p-3">
                <p className="text-[9px] font-black text-emerald-400 mb-1 uppercase tracking-widest">AI 종합 분석</p>
                <p className="text-xs text-[var(--text-secondary)] leading-relaxed">
                  {aiData?.summary || (deepAnalysisResult?.recommendations?.[0]
                    ? (() => {
                        const top = deepAnalysisResult.recommendations[0];
                        const metrics = recommendReason(top);
                        return `최적 사업모델: ${top.type_name}${metrics !== "분석 데이터 없음" ? ` (${metrics})` : ""}`;
                      })()
                    : ""
                  )}
                </p>
              </div>
            )}

            {/* AI Deep Analysis Button */}
            <button
              onClick={triggerDeepAnalysis}
              disabled={deepAnalysisLoading || isAnalyzing || !data?.address}
              className="mt-4 flex w-full items-center justify-center gap-2 rounded-2xl bg-teal-500 py-3.5 text-sm font-black text-[#0a0f14] shadow-[0_0_30px_rgba(45,212,191,0.3)] transition-all hover:scale-[1.02] hover:brightness-110 active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {deepAnalysisLoading || isAnalyzing ? "심층 분석 중..." : "심층 분석"}
              <Icons.ArrowRight />
            </button>
          </motion.div>
        </div>

        {/* === RIGHT PANEL: Scenarios + Parcel Info === */}
        <div className="flex flex-col gap-5">
          {/* Scenarios Card */}
          <motion.div
            initial={{ x: 20, opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            transition={{ delay: 0.15 }}
            className="glass rounded-[2rem] p-5 md:p-6 lg:p-7 border border-[var(--line-strong)] shadow-[var(--shadow-xl)]"
          >
            <div className="flex items-center justify-between mb-6">
              <h4 className="text-lg font-black text-[var(--text-primary)] tracking-tight">
                {scenarioLoading ? "시나리오 분석 중..." :
                 isScenarioReal && isScenarioTentative ? "선행절차 전제 잠정 시나리오" :
                 isScenarioReal ? "실제 분석 기반 시나리오" : "법규 기반 개발 시나리오"}
              </h4>
              <div className={`h-2 w-2 rounded-full ${
                scenarioLoading ? "bg-amber-500 animate-pulse" :
                isScenarioReal && isScenarioTentative ? "bg-amber-500 shadow-[0_0_10px_rgba(245,158,11,0.9)]" :
                isScenarioReal ? "bg-emerald-500 shadow-[0_0_10px_rgba(16,185,129,1)]" :
                hasData ? "bg-blue-500" : "bg-slate-500"
              } animate-pulse`} />
            </div>

            {/* 잠정 안내 배너 — 특이부지(도로·학교·맹지 등)로 전 후보가 선행절차 전제 잠정치일 때만.
                확신 % 를 그대로 노출하지 않고, 확정 아님·선행절차 전제임을 명시(할루시네이션 차단). */}
            {!scenarioLoading && isScenarioReal && isScenarioTentative && (
              <div className="mb-4 rounded-xl border border-[color-mix(in_srgb,var(--status-warning)_36%,transparent)] bg-[color-mix(in_srgb,var(--status-warning)_10%,transparent)] p-3">
                <p className="text-[10px] font-black text-[var(--status-warning)] uppercase tracking-widest mb-1 flex items-center gap-1.5">
                  <Icons.AlertCircle />선행절차 전제 · 잠정 (확정 아님)
                </p>
                <p className="text-[10px] leading-relaxed text-[var(--text-secondary)] font-medium">
                  {tentativeDisclosure ??
                    "이 부지는 도로·학교·맹지 등 선행절차형 특이부지로, 아래 시나리오는 폐도·용도폐지·도시계획변경 등 선행절차 통과를 전제로 한 잠정치입니다."}
                </p>
              </div>
            )}

            {scenarioLoading ? (
              <div className="flex flex-col items-center gap-3 py-8">
                <Icons.Loader />
                <p className="text-xs text-[var(--text-hint)]">수익성 기반 시나리오 분석 중...</p>
              </div>
            ) : (
              <div className="space-y-5">
                {scenarioItems.length > 0 ? scenarioItems.map((s, i) => {
                  // 후보별 tentative 또는 부지 전체 잠정(scenario_status·특이부지 게이트) 중 하나라도면 잠정 렌더.
                  //   → 시나리오 API가 후보 플래그를 못 채웠어도 게이트만으로 모든 항목의 확정% 막대를 억제(일관성).
                  const itemTentative = (isScenarioReal && isScenarioTentative) || ("tentative" in s && s.tentative === true);
                  return (
                  <div key={i} className="group relative">
                    <div className="flex items-start justify-between mb-2">
                      <div className="flex flex-col gap-1 flex-1 mr-3">
                        <span className="text-base font-[900] text-[var(--text-primary)] group-hover:text-[var(--accent-strong)] transition-colors">
                          {s.title}
                          {!s.isReal && <span className="ml-1.5 text-[9px] font-medium text-[var(--text-hint)]">(로컬 추정)</span>}
                          {itemTentative && <span className="ml-1.5 text-[9px] font-black text-[var(--status-warning)]">(선행절차 전제·잠정)</span>}
                        </span>
                        <span className="text-[10px] text-[var(--text-hint)] font-medium leading-snug">{s.reason}</span>
                      </div>
                      {/* 잠정 후보는 확신 % 대신 '잠정' 배지 — 확정치처럼 보이는 % 노출을 억제. */}
                      {itemTentative ? (
                        <span className="text-[10px] font-black text-[var(--status-warning)] whitespace-nowrap rounded-md border border-[color-mix(in_srgb,var(--status-warning)_36%,transparent)] bg-[color-mix(in_srgb,var(--status-warning)_10%,transparent)] px-2 py-1">
                          잠정
                        </span>
                      ) : (
                        <span className={`text-2xl font-black ${s.score >= 80 ? "text-emerald-400" : s.score >= 50 ? "text-amber-400" : "text-red-400"}`}>
                          {s.score}%
                        </span>
                      )}
                    </div>
                    {/* 잠정 후보는 진행바도 점선·억제 — 확정 점수 막대 미표시. */}
                    {itemTentative ? (
                      <div className="h-1.5 w-full rounded-full border border-dashed border-[color-mix(in_srgb,var(--status-warning)_30%,transparent)]" />
                    ) : (
                      <div className="h-1.5 w-full rounded-full bg-[var(--line)] overflow-hidden">
                        <motion.div
                          initial={{ width: 0 }}
                          animate={{ width: `${s.score}%` }}
                          transition={{ duration: 1.2, delay: 0.3 + i * 0.15 }}
                          className={`h-full rounded-full ${s.score >= 80 ? "bg-gradient-to-r from-emerald-500 to-teal-400" : s.score >= 50 ? "bg-gradient-to-r from-amber-500 to-orange-400" : "bg-gradient-to-r from-red-500 to-pink-400"}`}
                        />
                      </div>
                    )}
                  </div>
                  );
                }) : (
                  <p className="text-sm text-[var(--text-hint)] text-center py-6">주소를 입력하면 자동 분석됩니다</p>
                )}

                {scenarioError && (
                  <p className="text-[10px] text-amber-400 text-center mt-2 flex items-center justify-center gap-1">
                    <Icons.AlertCircle />API 시나리오 조회 실패 — 로컬 추정값 표시 중
                  </p>
                )}
              </div>
            )}
          </motion.div>

          {/* Parcel Info Card */}
          <motion.div
            initial={{ y: 20, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            transition={{ delay: 0.3 }}
            className="glass rounded-[2rem] p-5 border border-[var(--line)] bg-[var(--surface-muted)]"
          >
            <div className="flex items-center gap-3 mb-3">
              <div className="h-8 w-8 flex items-center justify-center rounded-lg bg-[var(--line)] text-[var(--text-tertiary)]">
                <Icons.Map />
              </div>
              <span className="text-[10px] font-black text-[var(--text-hint)] uppercase tracking-widest">
                {zoningData?.pnu ? `PNU: ${zoningData.pnu}` : displayPnu !== "—" ? `PNU: ${displayPnu}` : "PNU: 주소 입력 시 자동 매핑"}
              </span>
            </div>
            <div className="px-2">
              <p className="text-sm font-bold text-[var(--text-secondary)]">{displayAddress}</p>
              {hasData && (
                <p className="text-[10px] text-emerald-400 mt-1 font-bold">
                  {analysis.zoning.current} · 건폐율 {analysis.buildingCoverageMax}%{analysis.isEffectiveBcr ? "(실효)" : "(법정상한)"} · 용적률 {analysis.floorAreaRatioMax}%{analysis.isEffectiveFar ? "(실효)" : "(법정상한)"}
                  {analysis.landAreaSqm != null && ` · ${analysis.landAreaSqm.toLocaleString()}m²`}
                  {specialParcel && <span className="inline-flex items-center gap-1 text-[var(--status-warning)]"> · <AlertTriangle className="size-3" aria-hidden />특이부지</span>}
                </p>
              )}
            </div>
          </motion.div>
        </div>
      </div>

      {/* ── BOTTOM TABS (below the grid) ── */}
      <div className="relative z-10 px-4 md:px-6 lg:px-8 pb-4 md:pb-6">
        {/* Tab Bar */}
        <div className="flex flex-wrap justify-center gap-1 rounded-2xl bg-[var(--background)]/80 backdrop-blur-xl border border-[var(--line-strong)] p-1.5 shadow-[var(--shadow-xl)] mb-3 w-fit mx-auto">
          {([
            { key: "pnu" as const, label: "상세 지적(PNU)" },
            { key: "price" as const, label: "공시지가" },
            { key: "transaction" as const, label: "인근 실거래가" },
          ]).map(tab => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`rounded-xl px-3 md:px-4 py-2 text-xs font-black transition-all whitespace-nowrap ${
                activeTab === tab.key
                  ? "text-white bg-[var(--accent-strong)] shadow-md"
                  : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
              }`}
            >
              {tab.label}
            </button>
          ))}
          <div className="w-px h-4 bg-[var(--line-strong)] mx-2 self-center" />
          <button
            onClick={() => setActiveTab("gis")}
            className={`flex items-center gap-2 rounded-xl px-3 md:px-4 py-2 text-xs font-black whitespace-nowrap ${
              activeTab === "gis"
                ? "text-white bg-[var(--accent-strong)] shadow-md"
                : "text-[var(--accent-strong)]"
            }`}
          >
            <Icons.Layers /> GIS layers
          </button>
        </div>

        {/* Tab Content */}
        {hasData && (
          <motion.div
            initial={{ y: 10, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            className="glass rounded-2xl p-4 border border-[var(--line)]"
          >
            {/* PNU Tab */}
            {activeTab === "pnu" && (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
                <div>
                  <p className="text-[9px] font-black text-[var(--text-hint)] uppercase">용도지역</p>
                  <p className="font-bold text-[var(--text-primary)] mt-1">{analysis.zoning.current}</p>
                </div>
                <div>
                  <p className="text-[9px] font-black text-[var(--text-hint)] uppercase">건폐율 {analysis.isEffectiveBcr ? "(실효)" : "(법정상한)"}</p>
                  <p className="font-bold text-[var(--text-primary)] mt-1">{analysis.buildingCoverageMax}%</p>
                </div>
                <div>
                  <p className="text-[9px] font-black text-[var(--text-hint)] uppercase">용적률 {analysis.isEffectiveFar ? "(실효)" : "(법정상한)"}</p>
                  <p className="font-bold text-[var(--text-primary)] mt-1">{analysis.floorAreaRatioMax}%</p>
                </div>
                <div>
                  <p className="text-[9px] font-black text-[var(--text-hint)] uppercase">높이제한</p>
                  <p className="font-bold text-[var(--text-primary)] mt-1">{analysis.heightLimit ? `${analysis.heightLimit}m` : "없음"}</p>
                </div>
              </div>
            )}

            {/* Official Land Price Tab */}
            {activeTab === "price" && (
              <div className="text-xs text-[var(--text-secondary)]">
                {zoningLoading ? (
                  <div className="flex items-center gap-2 py-4 justify-center">
                    <Icons.Loader />
                    <span>공시지가 조회 중...</span>
                  </div>
                ) : analysis.officialPricePerSqm != null ? (
                  <div className="flex flex-col items-center gap-3">
                    <p className="text-[9px] font-black text-teal-400 uppercase tracking-widest">현재 공시지가 (실시간 조회)</p>
                    <div className="flex items-baseline gap-2">
                      <span className="text-3xl font-black text-[var(--text-primary)]">
                        {analysis.officialPricePerSqm.toLocaleString()}
                      </span>
                      <span className="text-sm text-[var(--text-secondary)]">원/m²</span>
                    </div>
                    {analysis.landAreaSqm != null && (
                      <p className="text-[10px] text-[var(--text-hint)]">
                        추정 토지가액: {(analysis.officialPricePerSqm * analysis.landAreaSqm).toLocaleString()}원
                        ({analysis.landAreaSqm.toLocaleString()}m² 기준)
                      </p>
                    )}
                  </div>
                ) : (
                  <div className="flex flex-col items-center gap-2 py-3">
                    <Icons.AlertCircle />
                    <p className="text-[10px] text-[var(--text-hint)] text-center">
                      공시지가 데이터를 불러올 수 없습니다.<br />
                      용도지역 분석 완료 후 자동으로 표시됩니다.
                    </p>
                  </div>
                )}
              </div>
            )}

            {/* Transaction Tab — 지도 기반 패널로 승격됨. 여기선 진입 CTA만 제공(중복 제거) */}
            {activeTab === "transaction" && (
              <div className="flex flex-col items-center gap-3 py-5 text-center">
                <p className="text-[11px] font-bold text-[var(--text-secondary)] leading-relaxed max-w-sm">
                  인근 실거래가는 아래 <span className="text-[var(--accent-strong)] font-black">&ldquo;주변 실거래 지도&rdquo;</span> 패널에서
                  반경·매매/전월세·부동산 유형별로 지도와 함께 확인할 수 있습니다.
                </p>
                <button
                  type="button"
                  onClick={() => {
                    if (typeof document !== "undefined") {
                      document
                        .getElementById("nearby-transactions-map")
                        ?.scrollIntoView({ behavior: "smooth", block: "start" });
                    }
                  }}
                  className="inline-flex items-center gap-2 rounded-xl bg-[var(--accent-strong)] px-5 py-2 text-xs font-black text-white whitespace-nowrap transition-all hover:brightness-110 active:scale-95"
                >
                  지도에서 보기
                  <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><polyline points="6 9 12 15 18 9" /></svg>
                </button>
              </div>
            )}

            {/* GIS Layers Tab */}
            {activeTab === "gis" && (
              <div className="space-y-2">
                <div className="flex flex-wrap items-center gap-4 text-xs">
                  {Object.entries(gisLayers).map(([label, checked]) => (
                    <label
                      key={label}
                      className="flex items-center gap-1.5 cursor-pointer select-none"
                      onClick={() => setGisLayers(prev => ({ ...prev, [label]: !prev[label] }))}
                    >
                      <div className={`h-4 w-4 rounded border flex items-center justify-center transition-colors ${
                        checked ? "bg-teal-500 border-teal-500 text-white" : "border-[var(--line-strong)] hover:border-teal-400"
                      }`}>
                        {checked && <Icons.Check />}
                      </div>
                      <span className="text-[var(--text-secondary)] font-bold">{label}</span>
                    </label>
                  ))}
                </div>
                <p className="text-[9px] text-[var(--text-hint)] text-center mt-1">
                  지도 연동은 추후 업데이트 예정입니다. 레이어 선택 상태는 저장됩니다.
                </p>
              </div>
            )}
          </motion.div>
        )}
      </div>
    </div>
  );
}
