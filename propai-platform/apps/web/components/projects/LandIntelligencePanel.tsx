"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { useAIAnalyze, useAIReady } from "@/lib/ai-analyze-client";
import { analyzeLocally } from "@/lib/kr-building-regulations";
import { apiClient } from "@/lib/api-client";
import { useProjectContextStore } from "@/store/useProjectContextStore";

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
};

type AutoRecommendResponse = {
  recommendations: RecommendedModel[];
  all_models: RecommendedModel[];
  analysis_count: number;
};

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
  const [scenarioData, setScenarioData] = useState<AutoRecommendResponse | null>(null);
  const [scenarioLoading, setScenarioLoading] = useState(false);
  const [scenarioError, setScenarioError] = useState<string | null>(null);

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
  const [deepAnalysisResult, setDeepAnalysisResult] = useState<AutoRecommendResponse | null>(null);
  const [deepAnalysisError, setDeepAnalysisError] = useState<string | null>(null);

  // ── 1) Fetch zoning data from /zoning/analyze ──
  useEffect(() => {
    if (!data?.address || data.address.trim().length < 3) {
      setZoningData(null);
      return;
    }

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
          // Update project context store
          updateSiteAnalysis({
            estimatedValue: siteAnalysis?.estimatedValue ?? null,
            landAreaSqm: res.land_area_sqm ?? siteAnalysis?.landAreaSqm ?? null,
            zoneCode: res.zone_limits?.zone_key ?? res.zone_type ?? null,
            address: res.address,
            pnu: res.pnu ?? siteAnalysis?.pnu ?? null,
          });
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

    let cancelled = false;
    async function fetchTransactions() {
      setTxLoading(true);
      setTxError(null);
      try {
        const now = new Date();
        const dealYm = `${now.getFullYear()}${String(now.getMonth() + 1).padStart(2, "0")}`;
        const res = await apiClient.get<TransactionsResponse>(
          `/external/transactions/apt?lawd_cd=${lawdCd}&deal_ym=${dealYm}`,
          { useMock: false },
        );
        if (!cancelled) setTxData(res);
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

    let cancelled = false;
    async function fetchScenarios() {
      setScenarioLoading(true);
      setScenarioError(null);
      try {
        const res = await apiClient.postV2<AutoRecommendResponse>("/feasibility/auto-recommend", {
          body: {
            address: data!.address!.trim(),
            land_area_sqm: zoningData?.land_area_sqm ?? undefined,
            region: data?.address?.includes("서울") ? "서울특별시" : "경기도",
          },
        });
        if (!cancelled) setScenarioData(res);
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
  }, [data?.address, zoningData?.land_area_sqm]);

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
      const res = await apiClient.postV2<AutoRecommendResponse>("/feasibility/auto-recommend", {
        body: {
          address: data.address.trim(),
          land_area_sqm: zoningData?.land_area_sqm ?? undefined,
          region: data.address.includes("서울") ? "서울특별시" : "경기도",
          equity_won: 15_000_000_000,
        },
      });
      setDeepAnalysisResult(res);
    } catch {
      // Fallback: try AI analyze client if backend fails
      if (isReady) {
        runAnalysis({
          domain: "site-analysis",
          context: { address: data.address, pnu: data.pnu || "", projectId },
        });
      } else {
        setDeepAnalysisError("백엔드 분석 서비스에 연결할 수 없습니다. 잠시 후 다시 시도해주세요.");
      }
    } finally {
      setDeepAnalysisLoading(false);
    }
  }, [data?.address, data?.pnu, isReady, projectId, runAnalysis, zoningData?.land_area_sqm]);

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
    if (chars.length < 4 && zoningData.special_districts.length > 0) {
      chars.push({
        label: "특별구역",
        value: zoningData.special_districts.map(d => d.name).join(", "),
        status: "warning",
      });
    }
    // Pad with warnings from zoning data
    if (chars.length < 4 && zoningData.warnings.length > 0) {
      chars.push({
        label: "주의사항",
        value: zoningData.warnings[0].slice(0, 30),
        status: "danger",
      });
    }
    return chars.length > 0 ? chars : null;
  }, [zoningData]);

  // Determine data source for scenarios
  const scenarioItems = useMemo(() => {
    // Priority 1: deep analysis result
    if (deepAnalysisResult?.recommendations?.length) {
      return deepAnalysisResult.recommendations.slice(0, 3).map(r => ({
        title: r.type_name,
        score: Math.round(r.composite_score),
        reason: `수익률 ${r.profit_rate_pct.toFixed(1)}% · ${r.grade}등급 · ${r.ai_summary.slice(0, 40)}`,
        isReal: true,
      }));
    }
    // Priority 2: auto-recommend API
    if (scenarioData?.recommendations?.length) {
      return scenarioData.recommendations.slice(0, 3).map(r => ({
        title: r.type_name,
        score: Math.round(r.composite_score),
        reason: `수익률 ${r.profit_rate_pct.toFixed(1)}% · ${r.grade}등급 · ${r.ai_summary.slice(0, 40)}`,
        isReal: true,
      }));
    }
    // Priority 3: AI analyze client result
    if (aiData?.scenarios?.length) {
      return aiData.scenarios.map(s => ({ ...s, isReal: true }));
    }
    // Priority 4: local fallback
    if (localResult?.scenarios?.length) {
      return localResult.scenarios.map(s => ({ ...s, isReal: false }));
    }
    return [];
  }, [deepAnalysisResult, scenarioData, aiData, localResult]);

  const isScenarioReal = scenarioItems.length > 0 && scenarioItems[0].isReal;

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
    buildingCoverageMax: zoningData?.zone_limits?.max_bcr_pct ?? localResult?.buildingCoverageMax ?? 0,
    floorAreaRatioMax: zoningData?.zone_limits?.max_far_pct ?? localResult?.floorAreaRatioMax ?? 0,
    heightLimit: zoningData?.zone_limits?.max_height_m ?? localResult?.heightLimit,
    officialPricePerSqm: zoningData?.official_price_per_sqm ?? null,
    landAreaSqm: zoningData?.land_area_sqm ?? null,
  };

  const hasData = !!localResult || !!zoningData;
  const hasZoningApi = !!zoningData;

  // ── Data source label ──
  const dataSourceLabel = useMemo(() => {
    if (isAnalyzing || deepAnalysisLoading) return { dot: "bg-amber-400 animate-pulse", text: "AI 분석 중...", color: "text-amber-400" };
    if (deepAnalysisResult || aiData) return { dot: "bg-emerald-400", text: "AI 분석 완료", color: "text-emerald-400" };
    if (hasZoningApi) return { dot: "bg-teal-400", text: "실시간 API 분석 완료", color: "text-teal-400" };
    if (localResult) return { dot: "bg-blue-400", text: "법규 기반 분석 완료", color: "text-blue-400" };
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

            {/* Zoning & Regulation KPI */}
            <div className="space-y-4">
              {/* Building Coverage & FAR */}
              {hasData && (
                <div className="grid grid-cols-2 gap-3">
                  <div className="rounded-xl bg-[var(--surface-muted)] p-4 border border-[var(--line)] text-center">
                    <p className="text-[9px] font-black text-blue-400 uppercase tracking-widest mb-1">건폐율 한도</p>
                    <p className="text-2xl font-black text-[var(--text-primary)]">
                      {analysis.buildingCoverageMax}<span className="text-xs ml-0.5">%</span>
                    </p>
                    {zoningLoading && <span className="text-[8px] text-[var(--text-hint)]">조회 중...</span>}
                  </div>
                  <div className="rounded-xl bg-[var(--surface-muted)] p-4 border border-[var(--line)] text-center">
                    <p className="text-[9px] font-black text-emerald-400 uppercase tracking-widest mb-1">용적률 한도</p>
                    <p className="text-2xl font-black text-[var(--text-primary)]">
                      {analysis.floorAreaRatioMax}<span className="text-xs ml-0.5">%</span>
                    </p>
                    {zoningLoading && <span className="text-[8px] text-[var(--text-hint)]">조회 중...</span>}
                  </div>
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
                    ? `최적 사업모델: ${deepAnalysisResult.recommendations[0].type_name} (수익률 ${deepAnalysisResult.recommendations[0].profit_rate_pct.toFixed(1)}%, ${deepAnalysisResult.recommendations[0].grade}등급)`
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
              {deepAnalysisLoading || isAnalyzing ? "AI 심층 분석 중..." : "AI 심층 분석 실행"}
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
                {isScenarioReal ? "실제 분석 기반 시나리오" : scenarioLoading ? "시나리오 분석 중..." : "법규 기반 개발 시나리오"}
              </h4>
              <div className={`h-2 w-2 rounded-full ${
                scenarioLoading ? "bg-amber-500 animate-pulse" :
                isScenarioReal ? "bg-emerald-500 shadow-[0_0_10px_rgba(16,185,129,1)]" :
                hasData ? "bg-blue-500" : "bg-slate-500"
              } animate-pulse`} />
            </div>

            {scenarioLoading ? (
              <div className="flex flex-col items-center gap-3 py-8">
                <Icons.Loader />
                <p className="text-xs text-[var(--text-hint)]">수익성 기반 시나리오 분석 중...</p>
              </div>
            ) : (
              <div className="space-y-5">
                {scenarioItems.length > 0 ? scenarioItems.map((s, i) => (
                  <div key={i} className="group relative">
                    <div className="flex items-start justify-between mb-2">
                      <div className="flex flex-col gap-1 flex-1 mr-3">
                        <span className="text-base font-[900] text-[var(--text-primary)] group-hover:text-[var(--accent-strong)] transition-colors">
                          {s.title}
                          {!s.isReal && <span className="ml-1.5 text-[9px] font-medium text-[var(--text-hint)]">(로컬 추정)</span>}
                        </span>
                        <span className="text-[10px] text-[var(--text-hint)] font-medium leading-snug">{s.reason}</span>
                      </div>
                      <span className={`text-2xl font-black ${s.score >= 80 ? "text-emerald-400" : s.score >= 50 ? "text-amber-400" : "text-red-400"}`}>
                        {s.score}%
                      </span>
                    </div>
                    <div className="h-1.5 w-full rounded-full bg-[var(--line)] overflow-hidden">
                      <motion.div
                        initial={{ width: 0 }}
                        animate={{ width: `${s.score}%` }}
                        transition={{ duration: 1.2, delay: 0.3 + i * 0.15 }}
                        className={`h-full rounded-full ${s.score >= 80 ? "bg-gradient-to-r from-emerald-500 to-teal-400" : s.score >= 50 ? "bg-gradient-to-r from-amber-500 to-orange-400" : "bg-gradient-to-r from-red-500 to-pink-400"}`}
                      />
                    </div>
                  </div>
                )) : (
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
                  {analysis.zoning.current} · 건폐율 {analysis.buildingCoverageMax}% · 용적률 {analysis.floorAreaRatioMax}%
                  {analysis.landAreaSqm != null && ` · ${analysis.landAreaSqm.toLocaleString()}m²`}
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
                  <p className="text-[9px] font-black text-[var(--text-hint)] uppercase">건폐율</p>
                  <p className="font-bold text-[var(--text-primary)] mt-1">{analysis.buildingCoverageMax}%</p>
                </div>
                <div>
                  <p className="text-[9px] font-black text-[var(--text-hint)] uppercase">용적률</p>
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

            {/* Transaction Tab */}
            {activeTab === "transaction" && (
              <div className="text-xs">
                {txLoading ? (
                  <div className="flex items-center gap-2 py-4 justify-center">
                    <Icons.Loader />
                    <span className="text-[var(--text-secondary)]">실거래 데이터 조회 중...</span>
                  </div>
                ) : txError ? (
                  <div className="flex flex-col items-center gap-2 py-3">
                    <Icons.AlertCircle />
                    <p className="text-[10px] text-[var(--text-hint)] text-center">
                      {txError}<br />
                      부지분석 워크스페이스에서 AVM 분석을 실행하세요.
                    </p>
                  </div>
                ) : txData?.items && txData.items.length > 0 ? (
                  <>
                    <p className="text-[9px] font-black text-teal-400 uppercase mb-2">
                      인근 실거래가 (실시간 조회 · {txData.total_count ?? txData.items.length}건)
                    </p>
                    <div className="space-y-1.5">
                      {txData.items.slice(0, 5).map((t, i) => (
                        <div key={i} className="flex items-center justify-between text-[var(--text-secondary)] bg-[var(--surface-muted)] rounded-lg px-3 py-1.5">
                          <span>{t.deal_year}.{t.deal_month?.padStart(2, "0")}</span>
                          <span className="text-[var(--text-hint)]">
                            {t.apt_name || t.dong || "—"} · {t.area_sqm ? `${t.area_sqm}m²` : "—"}
                          </span>
                          <span className="font-bold text-[var(--text-primary)]">{formatPrice(t.deal_amount)}</span>
                        </div>
                      ))}
                    </div>
                  </>
                ) : (
                  <div className="flex flex-col items-center gap-2 py-3">
                    <p className="text-[10px] text-[var(--text-hint)] text-center">
                      실거래 데이터를 조회하려면 부지분석 워크스페이스에서 AVM 분석을 실행하세요.
                    </p>
                  </div>
                )}
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
