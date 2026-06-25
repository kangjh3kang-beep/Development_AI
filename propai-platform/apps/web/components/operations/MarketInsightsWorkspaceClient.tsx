"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Bot, Building, Compass, Download, Files, Lock, PenLine, Target, Users, Wallet } from "lucide-react";
import { Card, CardContent } from "@propai/ui";
import { apiClient, ApiClientError } from "@/lib/api-client";
import { ProjectAddressInput } from "@/components/common/ProjectAddressInput";
import { dynamicMap } from "@/components/common/MapShell";
import type {
  NearbyTransactionsMap as NearbyTransactionsMapType,
  NearbyMapPayload,
} from "@/components/map/NearbyTransactionsMap";
import type { ParcelBoundaryMap as ParcelBoundaryMapType } from "@/components/map/ParcelBoundaryMap";
import type { PopulationDensityMap as PopulationDensityMapType } from "@/components/map/PopulationDensityMap";
import { ExpertPanelCard } from "@/components/common/ExpertPanelCard";
import { SeniorVerdictCard, type SeniorConsultation } from "@/components/analysis/SeniorVerdictCard";

// 지도는 SSR 없이 동적 로드(SSR throw 차단 + 로딩 스켈레톤). 동작·props 불변.
const NearbyTransactionsMap = dynamicMap<React.ComponentProps<typeof NearbyTransactionsMapType>>(
  () => import("@/components/map/NearbyTransactionsMap"),
  { pick: "NearbyTransactionsMap", height: 440, loadingMessage: "주변 실거래 지도 로딩…" },
);
const ParcelBoundaryMap = dynamicMap<React.ComponentProps<typeof ParcelBoundaryMapType>>(
  () => import("@/components/map/ParcelBoundaryMap"),
  { pick: "ParcelBoundaryMap", height: 360, loadingMessage: "필지 구획도 로딩…" },
);
const PopulationDensityMap = dynamicMap<React.ComponentProps<typeof PopulationDensityMapType>>(
  () => import("@/components/map/PopulationDensityMap"),
  { pick: "PopulationDensityMap", height: 360, loadingMessage: "인구밀도 지도 로딩…" },
);
import { VerificationBadge } from "@/components/common/VerificationBadge";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { FeasibilityDashboard } from "@/components/feasibility/FeasibilityDashboard";
import { AnalysisModuleSelector, type AnalysisModuleOption } from "@/components/common/AnalysisModuleSelector";
import { DemographicPanel } from "@/components/operations/market/DemographicPanel";
import { PricingBandPanel } from "@/components/operations/market/PricingBandPanel";
import { RawDataTables, type RawData } from "@/components/operations/market/RawDataTables";
// B3 채택(additive·무회귀): 오케스트레이션 레지스트리 구동 셀렉터/실행 컨테이너.
// 기존 도메인 셀렉터(SGIS/KOSIS market 서브모듈)·buildOptionsPayload·/market/report 흐름은 불변.
// 이 패널은 별도 store(propai-orchestration)·별도 실행경로라 기존 과금/실행과 결선되지 않는다.
import { OrchestratorPanel } from "@/components/orchestration/OrchestratorPanel";

// PDF/PPTX 바이너리 다운로드용 API 베이스 (api-client 로직 미러)
function marketApiBase(): string {
  if (typeof window !== "undefined") {
    const h = window.location.hostname;
    if (h === "4t8t.net" || h === "www.4t8t.net" || h.endsWith(".pages.dev") || h === "propai.kr") {
      return "https://api.4t8t.net/api/v1";
    }
  }
  return "/api/proxy";
}

/* ------------------------------------------------------------------ */
/*  Types                                                             */
/* ------------------------------------------------------------------ */

type AvmSummary = {
  estimated_price: number; // 원
  price_per_sqm: number;   // 원/㎡
  confidence_score: number;
  comparable_count: number;
};

type TxItem = {
  deal_amount?: number; // 만원
  deal_year?: string; deal_month?: string; deal_day?: string;
  area_sqm?: number; floor?: number | string; apt_name?: string; distance_m?: number;
};

type RadiusBucket = { label: string; count: number; avgPrice: number /* 만원 */ };

type MarketResults = {
  avm: AvmSummary | null;
  totalCount: number;
  avgPrice: number; // 만원
  radiusGroups: RadiusBucket[];
  transactions: TxItem[];
  months: number;
  radius: number;
  searchAddress: string;
};

/* ------------------------------------------------------------------ */
/*  Helpers                                                           */
/* ------------------------------------------------------------------ */

const PYEONG = 3.305785;

function formatPrice(man: number): string {
  if (!man || man <= 0) return "-";
  if (man >= 10000) {
    const uk = Math.floor(man / 10000);
    const rest = man % 10000;
    return rest > 0 ? `${uk}억 ${rest.toLocaleString()}만원` : `${uk}억원`;
  }
  return `${man.toLocaleString()}만원`;
}

function formatCurrency(won: number): string {
  return new Intl.NumberFormat("ko-KR", { style: "currency", currency: "KRW", maximumFractionDigits: 0 }).format(won);
}

function distanceM(aLat: number, aLon: number, bLat: number, bLon: number): number {
  const R = 6371000, toRad = (d: number) => (d * Math.PI) / 180;
  const dLat = toRad(bLat - aLat), dLon = toRad(bLon - aLon);
  const s = Math.sin(dLat / 2) ** 2 + Math.cos(toRad(aLat)) * Math.cos(toRad(bLat)) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(s));
}

function parseDealDate(s?: string): { deal_year?: string; deal_month?: string; deal_day?: string } {
  if (!s) return {};
  const m = s.match(/(\d{4})\D+(\d{1,2})(?:\D+(\d{1,2}))?/);
  if (!m) return {};
  return { deal_year: m[1], deal_month: m[2], deal_day: m[3] };
}

/** nearby-map 단일 데이터원 → 실거래 현황 + AI 시세(실거래 비교 기반). */
function deriveResults(payload: NearbyMapPayload | null, fallbackAddr: string): MarketResults | null {
  if (!payload) return null;
  const center = payload.center;
  const cats = payload.categories || {};
  const tradeEntries = Object.entries(cats).filter(([k]) => k.endsWith("_trade"));

  const totalCount = tradeEntries.reduce((a, [, c]) => a + (c.count || 0), 0);

  const buckets = [
    { label: "반경 500m", max: 500, count: 0, pSum: 0, pN: 0 },
    { label: "반경 1km", max: 1000, count: 0, pSum: 0, pN: 0 },
    { label: "반경 3km", max: 3000, count: 0, pSum: 0, pN: 0 },
    { label: "반경 5km+", max: Infinity, count: 0, pSum: 0, pN: 0 },
  ];
  const transactions: TxItem[] = [];
  let allPSum = 0, allPN = 0;

  for (const [, c] of tradeEntries) {
    for (const g of c.groups || []) {
      const dist = center?.lat && g.lat ? distanceM(center.lat, center.lon as number, g.lat, g.lon) : 1000;
      const cnt = g.count || 0;
      if (g.avg_price_10k) { allPSum += g.avg_price_10k * (cnt || 1); allPN += cnt || 1; }
      for (const b of buckets) {
        if (dist <= b.max) {
          b.count += cnt;
          if (g.avg_price_10k) { b.pSum += g.avg_price_10k * (cnt || 1); b.pN += cnt || 1; }
          break;
        }
      }
      for (const d of g.deals || []) {
        transactions.push({
          deal_amount: d.price_10k_won, area_sqm: d.area_m2, floor: d.floor,
          apt_name: g.name, distance_m: Math.round(dist), ...parseDealDate(d.deal_date),
        });
      }
    }
  }

  const radiusGroups: RadiusBucket[] = buckets
    .filter((b) => b.count > 0)
    .map((b) => ({ label: b.label, count: b.count, avgPrice: b.pN ? Math.round(b.pSum / b.pN) : 0 }));

  // AI 시세: 아파트 매매 실거래 평당가 가중평균 → 84㎡ 기준 추정
  const apt = cats["apt_trade"];
  let avm: AvmSummary | null = null;
  if (apt?.groups?.length) {
    let ppSum = 0, ppN = 0;
    for (const g of apt.groups) {
      if (g.avg_price_10k && g.avg_area_m2 > 0) {
        const perPyeong = g.avg_price_10k / (g.avg_area_m2 / PYEONG);
        ppSum += perPyeong * (g.count || 1); ppN += g.count || 1;
      }
    }
    if (ppN > 0) {
      const perPyeong = ppSum / ppN;        // 만원/평
      const perM2man = perPyeong / PYEONG;  // 만원/㎡
      avm = {
        estimated_price: Math.round(perM2man * 84 * 10000),
        price_per_sqm: Math.round(perM2man * 10000),
        confidence_score: Math.min(0.95, 0.5 + Math.log10((apt.count || 0) + 1) / 4),
        comparable_count: apt.count || 0,
      };
    }
  }

  return {
    avm, totalCount,
    avgPrice: allPN ? Math.round(allPSum / allPN) : 0,
    radiusGroups, transactions,
    months: payload.months?.length || 3,
    radius: payload.radius_m || 1000,
    searchAddress: center?.address || fallbackAddr,
  };
}

type Balance = {
  tier_label: string;
  monthly_base_remaining: number;
  topup_remaining: number;
  markup_pct: number;
  unlimited?: boolean; // 비과금 등급(super_admin 등) — 코인 게이트 면제
  // 관리자가 설정한 분석 모듈 사용료 맵(미설정 시 빈 dict = 전부 무료).
  module_fees?: Record<string, number>;
};

const won = (n: number) => (n ?? 0).toLocaleString("ko-KR") + "원";

/* ── 데이터 인텔리전스 metric 타일 ──
   핵심 수치는 mono·tabular-nums로 자릿수 정렬(sa-di-tile). accent=true는 핵심 KPI 1개에만. */
function MetricTile({ label, value, accent = false }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className={`sa-di-tile${accent ? " sa-di-tile--accent" : ""}`}>
      <span className="sa-di-tile__label">{label}</span>
      <span className="sa-di-tile__value">{value || "-"}</span>
    </div>
  );
}

/* ── 섹션 구분 헤더 ──
   보고서를 "실데이터(RAW) → 분석(ANALYSIS)" 두 구간으로 시각 분리한다.
   토큰 색만 사용한 단순 divider + eyebrow 라벨(과한 장식 금지). */
function SectionDivider({ kr, en }: { kr: string; en: string }) {
  return (
    <div className="mt-2 flex items-center gap-3">
      <div className="flex flex-col">
        <span className="sa-di-eyebrow">{en}</span>
        <span className="text-base font-black text-[var(--text-primary)]">{kr}</span>
      </div>
      <div className="h-px flex-1 bg-[var(--line)]" aria-hidden />
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Component                                                         */
/* ------------------------------------------------------------------ */

export function MarketInsightsWorkspaceClient() {
  // 활성 프로젝트(projectId)가 있을 때만 컨텍스트를 사용 — 약식 검색이 타 페이지로 새지 않도록.
  const projectId = useProjectContextStore((s) => s.projectId);
  const rawSite = useProjectContextStore((s) => s.siteAnalysis);
  const siteAnalysis = projectId ? rawSite : null;
  const [searchAddr, setSearchAddr] = useState("");
  // 명시실행: 주소 입력만으로는 분석하지 않고, "분석 실행" 클릭 시에만 runAddress를 확정한다.
  const [runAddress, setRunAddress] = useState("");
  const [mapPayload, setMapPayload] = useState<NearbyMapPayload | null>(null);
  const [mapLoading, setMapLoading] = useState(false);
  const [report, setReport] = useState<any | null>(null);
  const [genState, setGenState] = useState<"" | "report" | "pdf" | "pptx" | "docx">("");
  const [useLlm, setUseLlm] = useState(true);
  // 선택 상태(말단 항목 기준 평탄 boolean 맵). 분류 sgis/kosis는 자식들에서 파생해 전송한다.
  //   population(인구/가구) 자식: pop_age / pop_household / pop_migration
  //   income(거시 소득) 자식: income_avg / income_basis
  //   katlas: 마이크로 타겟팅(프리미엄)
  const [analysisOptions, setAnalysisOptions] = useState<Record<string, boolean>>({
    pop_age: false,
    pop_household: false,
    pop_migration: false,
    income_avg: false,
    income_basis: false,
    katlas: false,
  });
  const [error, setError] = useState("");
  const [balance, setBalance] = useState<Balance | null>(null);

  // 입력 후보 주소(실행 전): 검색 → 없으면 활성 프로젝트 주소.
  const inputAddress = searchAddr || siteAnalysis?.address || "";
  // 실제 분석 대상 주소 — 버튼 클릭으로 확정된 값만 지도/산출에 전달.
  const address = runAddress;
  // 지도/보고서용 pnu: GlobalAddressSearch가 현재 검색의 pnu를 store에 기록 → 현재 검색분 사용
  const mapPnu = (rawSite?.pnu as string) || "";
  // P4-B 인구밀도: bcode(법정동 10자리) = PNU 앞 10자리. 동시표시 토글(지연로드).
  const mapBcode = mapPnu.slice(0, 10);
  const [showDensity, setShowDensity] = useState(false);
  const results = useMemo(() => deriveResults(mapPayload, address), [mapPayload, address]);

  const totalRemaining = balance
    ? (balance.monthly_base_remaining || 0) + (balance.topup_remaining || 0)
    : null;
  // 무제한 등급(관리자 등)은 코인 게이트 면제 — 잔액 0이어도 막지 않는다.
  const insufficient = !balance?.unlimited && totalRemaining !== null && totalRemaining <= 0;
  
  // 엔터프라이즈/PRO 등급 등 프리미엄 권한 체크 (마이크로 타겟팅 분석 열람용)
  const isPremiumUser = balance?.unlimited || 
    ["엔터프라이즈", "ENTERPRISE", "PRO", "프리미엄"].some(tier => 
      (balance?.tier_label || "").toUpperCase().includes(tier)
    );

  // ── 선택형 분석 모듈 카탈로그(공용 AnalysisModuleSelector 주입용) ──
  // 사용자 핵심지침 "선택형 상세분석을 전 시스템 기본으로" — 필요한 모듈만 체크→선택분만 실행·과금.
  // coinCost/estimatedSeconds는 선택 수→예상 코인·시간 실시간 표시에 사용(안내용 추정치).
  //   각 항목 coinCost는 하드코딩 금지 → 관리자 설정값(balance.module_fees)에서 채운다.
  //   관리자 미설정 시 0 → 셀렉터가 "추가 비용 없음"으로 표기(허위 표시값 제거).
  const fee = useCallback((k: string) => balance?.module_fees?.[k] ?? 0, [balance]);
  const analysisModules: AnalysisModuleOption[] = useMemo(() => [
    { key: "base", label: "기본 부동산 분석", description: "주변 실거래·AI 시세·입지 인프라", required: true, estimatedSeconds: 8, icon: Building },
    {
      key: "population", label: "인구/가구 분석", description: "유입 인구와 가구 구성을 분석", icon: Users,
      children: [
        { key: "pop_age", label: "연령·인구 분포", description: "연령대별 인구 구성비", coinCost: fee("pop_age"), estimatedSeconds: 3 },
        { key: "pop_household", label: "가구원수·가구 구성", description: "1~4인+ 가구 구성비", coinCost: fee("pop_household"), estimatedSeconds: 3 },
        { key: "pop_migration", label: "전입·전출·순이동", description: "지역 인구 유입세(순이동)", coinCost: fee("pop_migration"), estimatedSeconds: 4 },
      ],
    },
    {
      key: "income", label: "거시 소득 지표", description: "지역 소득 수준으로 지불여력 추정", icon: Wallet,
      children: [
        { key: "income_avg", label: "평균 연소득", description: "시군구 평균 연소득", coinCost: fee("income_avg"), estimatedSeconds: 3 },
        { key: "income_basis", label: "산출근거(인원·총급여)", description: "근로소득 인원·총급여 원천", coinCost: fee("income_basis"), estimatedSeconds: 2 },
      ],
    },
    { key: "katlas", label: "마이크로 타겟팅", description: "초정밀 금융·소비 데이터 (K-Atlas)", locked: !isPremiumUser, coinCost: fee("katlas"), estimatedSeconds: 6, lockedCtaLabel: "프리미엄 전용", icon: Target },
  ], [isPremiumUser, fee]);

  // 선택 변경 — 공용 컴포넌트의 selected 맵을 그대로 반영(말단 항목 평탄 맵).
  const onModulesChange = useCallback((next: Record<string, boolean>) => {
    setAnalysisOptions({
      pop_age: !!next.pop_age,
      pop_household: !!next.pop_household,
      pop_migration: !!next.pop_migration,
      income_avg: !!next.income_avg,
      income_basis: !!next.income_basis,
      katlas: !!next.katlas,
    });
  }, []);
  // 전체 자동분석 — 가능한 항목 전부 선택(잠금 모듈은 프리미엄일 때만).
  const onSelectAll = useCallback(() => {
    setAnalysisOptions({
      pop_age: true,
      pop_household: true,
      pop_migration: true,
      income_avg: true,
      income_basis: true,
      katlas: isPremiumUser,
    });
  }, [isPremiumUser]);

  // 백엔드 build_report 전송용 옵션 payload — 하위호환 sgis/kosis(분류 단위) + 신규 detail(세부).
  //   sgis = 인구/가구 분류 중 하나라도 켜짐, kosis = 소득 분류 중 하나라도 켜짐.
  //   기존 백엔드 분기(sgis/kosis boolean)는 그대로 동작하고, detail은 추가 정보로 전달한다.
  const buildOptionsPayload = useCallback(() => {
    const o = analysisOptions;
    const sgis = !!(o.pop_age || o.pop_household || o.pop_migration);
    const kosis = !!(o.income_avg || o.income_basis);
    return {
      sgis,
      kosis,
      katlas: !!o.katlas,
      detail: {
        pop_age: !!o.pop_age,
        pop_household: !!o.pop_household,
        pop_migration: !!o.pop_migration,
        income_avg: !!o.income_avg,
        income_basis: !!o.income_basis,
      },
    };
  }, [analysisOptions]);

  // 코인 잔액(월기본+충전) 안내용 — 차감은 백엔드(BaseInterpreter)가 LLM 호출 시 자동 처리.
  useEffect(() => {
    apiClient.get<Balance>("/billing/balance", { useMock: false })
      .then(setBalance)
      .catch((e) => { if (!(e instanceof ApiClientError)) setBalance(null); });
  }, []);

  // 주소 변경 → 입력 후보만 갱신(자동 분석/조회 없음). 전역 store에는 기록하지 않음.
  const onAddress = useCallback((addr: string) => {
    setSearchAddr(addr);
  }, []);

  // 명시 실행: 버튼 클릭 시에만 분석 대상 주소를 확정하고 지도/산출을 트리거한다.
  const runAnalysis = useCallback(() => {
    if (!inputAddress) return;
    setError("");
    setReport(null);
    setMapPayload(null);
    setRunAddress(inputAddress);
    // 실행 후 잔액 갱신(차감 반영) — 약간 지연 후 재조회.
    setTimeout(() => {
      apiClient.get<Balance>("/billing/balance", { useMock: false }).then(setBalance).catch(() => { /* noop */ });
    }, 1500);
  }, [inputAddress]);

  // 시장조사보고서: 구조화 미리보기
  const generateReport = useCallback(async () => {
    if (!address) return;
    setGenState("report");
    try {
      const r = await apiClient.post<any>("/market/report", {
        body: { address, pnu: siteAnalysis?.pnu || undefined, use_llm: useLlm, options: buildOptionsPayload() },
        useMock: false, timeoutMs: 120000,
      });
      setReport(r);
      // LLM 분석 후 코인 차감 반영 — 잔액 재조회.
      if (useLlm) {
        apiClient.get<Balance>("/billing/balance", { useMock: false }).then(setBalance).catch(() => { /* noop */ });
      }
    } catch {
      setError("보고서 생성에 실패했습니다.");
    } finally {
      setGenState("");
    }
  }, [address, siteAnalysis?.pnu, useLlm, buildOptionsPayload]);

  // PDF/PPTX 다운로드(바이너리)
  const downloadReport = useCallback(async (fmt: "pdf" | "pptx" | "docx") => {
    if (!address) return;
    setGenState(fmt);
    try {
      const token = (typeof window !== "undefined" && localStorage.getItem("propai_access_token")) || "";
      const res = await fetch(`${marketApiBase()}/market/report/${fmt}`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        // ★다운로드도 options를 포함해야 PDF/PPTX에 인구·소득 데이터가 누락되지 않는다(미리보기와 동일 payload).
        body: JSON.stringify({ address, pnu: siteAnalysis?.pnu || undefined, use_llm: useLlm, options: buildOptionsPayload() }),
      });
      if (!res.ok) throw new Error(String(res.status));
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `시장조사보고서_${address}.${fmt}`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      setError(`${fmt.toUpperCase()} 다운로드에 실패했습니다.`);
    } finally {
      setGenState("");
    }
  }, [address, siteAnalysis?.pnu, useLlm, buildOptionsPayload]);

  return (
    <section className="grid grid-cols-1 gap-6 min-w-0">
      {/* 헤더 — 시장 인텔리전스 관제 콘솔 */}
      <div>
        <div className="flex items-center gap-3">
          <span className="cc-meta">MARKET · TRANSACTION INTEL</span>
          <span className="cc-live"><i />LIVE</span>
        </div>
        <h2 className="mt-2 text-2xl font-black text-[var(--text-primary)]">시장·시세 분석</h2>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">
          주소를 입력하고 <b className="text-[var(--text-primary)]">「분석 시작」</b> 버튼을 누르면 주변 실거래가·시세 추이·시장 동향을 분석합니다.
        </p>
      </div>

      {/* 검색입력(카카오) — 직접입력 → 주소 검색으로 보강 */}
      <ProjectAddressInput
        value={searchAddr}
        onChange={onAddress}
        label="시장 분석 주소"
        placeholder="주소를 검색하세요 (예: 서울 강남구 역삼동)"
      />

      {/* P3 Zone B — 분석 후 지도를 주소 바로 아래(최상단)에 크게 노출해 스크롤 없이 즉시 보이게.
          실거래+분양 통합 오버레이 지도 → 필지 구획도 순. 분석 전(address 없음)엔 숨겨 셀렉터가 상단. */}
      {address && (
        <div className="grid gap-4">
          <NearbyTransactionsMap address={address} pnu={mapPnu} onPayload={setMapPayload} onLoading={setMapLoading} />
          <ParcelBoundaryMap parcels={[address]} />
          {/* P4-B 인구밀도 코로플레스 — 지연로드 토글(SGIS 호출 비용 절약). */}
          <div className="rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-soft)] p-3">
            <button
              type="button"
              onClick={() => setShowDensity((v) => !v)}
              className="flex w-full items-center justify-between gap-2 text-left text-sm font-bold text-[var(--text-primary)]"
            >
              <span className="inline-flex items-center gap-1.5"><Users className="size-4" aria-hidden />인구밀도 (행정동) <span className="ml-1 text-xs font-normal text-[var(--text-hint)]">SGIS 경계+인구 코로플레스</span></span>
              <span className="text-[var(--accent-strong)]">{showDensity ? "▾ 닫기" : "▸ 보기"}</span>
            </button>
            {showDensity && (
              <div className="mt-3">
                <PopulationDensityMap address={address} bcode={mapBcode} />
              </div>
            )}
          </div>
        </div>
      )}

      {/* 선택형 분석 모듈 — 공용 AnalysisModuleSelector(선택형이 기본 진입). 선택분만 실행·과금. */}
      <AnalysisModuleSelector
        modules={analysisModules}
        selected={analysisOptions}
        onChange={onModulesChange}
        onSelectAll={onSelectAll}
        unlimited={!!balance?.unlimited}
        subtitle="필요한 분석만 선택하세요. 선택한 항목만 실행·과금됩니다. (전체 자동분석은 우측 버튼)"
      />

      {/* B3 채택(additive): 오케스트레이션 노드 기반 분석 실행 — 분양성·분양가(sales) 스코프.
          기존 시장보고서 흐름과 별개 경로(별도 store). nodesToOptions가 레지스트리에서 옵션을 자동 생성하고,
          폐포(상류 의존)·신선스킵·과금합계를 선표시한 뒤 동의 실행한다. balance.module_fees(미설정 0=무료) 재사용. */}
      <OrchestratorPanel
        scopeNodes={["sales"]}
        balance={balance}
        runDisabled={!inputAddress || insufficient}
        title="통합 분석(베타)"
        subtitle="분양성·분양가 분석을 레지스트리 기반으로 실행합니다. 상류(부지·설계) 의존은 자동 포함됩니다."
      />

      {/* 명시 실행 패널 — 자동 실행 제거. 코인 차감 안내 + 잔액 부족 시 충전 유도. */}
      <Card className="rounded-[var(--radius-2xl)] shadow-[var(--shadow-md)]">
        <CardContent className="p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="min-w-0">
              <p className="text-sm font-bold text-[var(--text-primary)]">분석 시작</p>
              <p className="mt-0.5 text-xs text-[var(--text-secondary)]">
                분석 시 사용한 LLM 사용량만큼 코인이 자동 차감됩니다
                {balance?.unlimited ? (
                  <> · <b className="text-[var(--text-primary)]">무제한(관리자)</b></>
                ) : totalRemaining !== null && (
                  <> · 코인 잔여 <b className="text-[var(--text-primary)]">{won(totalRemaining)}</b></>
                )}
              </p>
            </div>
            <button
              onClick={runAnalysis}
              disabled={!inputAddress || insufficient}
              className="whitespace-nowrap rounded-xl bg-[var(--accent-strong)] px-5 py-2.5 text-sm font-black text-white hover:opacity-90 disabled:opacity-50"
            >
              분석 시작
            </button>
          </div>
          {insufficient && (
            <p className="mt-2 text-xs font-bold text-[var(--status-warning)]">
              코인 잔액이 부족합니다. 좌측 코인 미터의 「추가결제」로 충전 후 다시 실행해 주세요.
            </p>
          )}
          {!inputAddress && (
            <p className="mt-2 text-xs text-[var(--text-hint)]">먼저 위에서 분석할 주소를 입력하세요.</p>
          )}
          {address && (
            <p className="mt-2 text-xs text-[var(--text-hint)]">
              분석 대상: <b className="text-[var(--text-secondary)]">{address}</b> · 실행 후 사용량은 설정 &gt; AI 사용량에서 확인할 수 있습니다.
            </p>
          )}
        </CardContent>
      </Card>

      {/* (지도는 위 Zone B로 이동 — 분석 후 상단 노출) */}

      {/* 시장조사보고서 생성 트리거 (미리보기/PDF/PPT) — 분석 실행 버튼(기능 영역) */}
      {address && (
        <Card className="rounded-[var(--radius-2xl)] shadow-[var(--shadow-md)]">
          <CardContent className="p-6">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="inline-flex items-center gap-1.5 text-sm font-bold text-[var(--text-primary)]"><Files className="size-4" aria-hidden />시장조사보고서</p>
                <p className="mt-0.5 text-xs text-[var(--text-secondary)]">주변 실거래·시세·입지를 통합한 심층 보고서를 PDF/PPT로 생성합니다.</p>
                <label className="mt-2 inline-flex cursor-pointer items-center gap-2 text-xs font-semibold text-[var(--text-secondary)]">
                  <input type="checkbox" checked={useLlm} onChange={(e) => setUseLlm(e.target.checked)}
                    className="h-4 w-4 accent-[var(--accent-strong)]" disabled={!!genState} />
                  <span className="inline-flex items-center gap-1.5"><Bot className="size-4" aria-hidden />AI 분석 포함</span> <span className="font-normal text-[var(--text-tertiary)]">(LLM이 시장요약·기회·리스크·가격동향을 작성)</span>
                </label>
              </div>
              <div className="flex flex-wrap gap-2">
                <button onClick={generateReport} disabled={!!genState}
                  className="whitespace-nowrap rounded-xl border border-[var(--line-strong)] px-4 py-2 text-xs font-bold text-[var(--text-secondary)] hover:border-[var(--accent-strong)] disabled:opacity-50">
                  {genState === "report" ? "생성 중…" : "미리보기 생성"}
                </button>
                <button onClick={() => downloadReport("pdf")} disabled={!!genState}
                  className="whitespace-nowrap rounded-xl bg-[var(--accent-strong)] px-4 py-2 text-xs font-black text-white hover:opacity-90 disabled:opacity-50">
                  {genState === "pdf" ? "PDF 생성 중…" : "PDF 다운로드"}
                </button>
                <button onClick={() => downloadReport("pptx")} disabled={!!genState}
                  className="whitespace-nowrap rounded-xl bg-gradient-to-r from-[var(--accent-strong)] to-[var(--data-accent)] px-4 py-2 text-xs font-black text-white hover:opacity-90 disabled:opacity-50">
                  {genState === "pptx" ? "PPT 생성 중…" : "PPT 다운로드"}
                </button>
                <button onClick={() => downloadReport("docx")} disabled={!!genState}
                  className="whitespace-nowrap rounded-xl border border-[var(--line-strong)] px-4 py-2 text-xs font-bold text-[var(--text-secondary)] hover:border-[var(--accent-strong)] disabled:opacity-50">
                  {genState === "docx" ? "DOCX 생성 중…" : "DOCX 다운로드"}
                </button>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* 에러 */}
      {error && (
        <div className="rounded-[var(--radius-xl)] border border-[var(--status-warning)]/30 bg-[color-mix(in_srgb,var(--status-warning)_8%,transparent)] p-5 text-sm leading-7 text-[var(--status-warning)]">
          {error}
        </div>
      )}

      {/* ================================================================ */}
      {/*  [실데이터 · RAW DATA] — 가공 전 원천 데이터를 먼저 나열한다.       */}
      {/*  사용자 핵심지침: "실데이터 표 먼저 → 분석은 그 다음".            */}
      {/* ================================================================ */}
      <SectionDivider kr="실데이터" en="RAW DATA · 원천 데이터" />

      {/* 주변 실거래 현황 — 반경별 거래량·평균가를 데이터 인텔리전스로 */}
      <div className="sa-di-block">
        <header className="sa-di-block__head" style={{ cursor: "default" }}>
          <span className="sa-di-block__icon" aria-hidden>◎</span>
          <span className="sa-di-block__title">주변 실거래 현황</span>
          <span className="cc-live"><i />LIVE</span>
        </header>
        <div className="sa-di-block__body">
          {mapLoading || (address && !mapPayload) ? (
            <p className="sa-di-empty">주변 실거래를 수집하는 중…</p>
          ) : results ? (
            <>
              {/* 요약 통계 줄 — 기간/거래건수/평균가 */}
              <div className="sa-di-stats">
                <div className="sa-di-stat">
                  <span className="sa-di-stat__label">조회 기간</span>
                  <span className="sa-di-stat__value">{results.months}개월</span>
                </div>
                <div className="sa-di-stat">
                  <span className="sa-di-stat__label">총 거래</span>
                  <span className="sa-di-stat__value" style={{ color: "var(--data-accent)" }}>{results.totalCount.toLocaleString()}건</span>
                </div>
                <div className="sa-di-stat">
                  <span className="sa-di-stat__label">매매 평균가</span>
                  <span className="sa-di-stat__value">{results.avgPrice > 0 ? formatPrice(results.avgPrice) : "-"}</span>
                </div>
                <div className="sa-di-stat">
                  <span className="sa-di-stat__label">분석 반경</span>
                  <span className="sa-di-stat__value">{(results.radius / 1000).toLocaleString()}km</span>
                </div>
              </div>

              {results.radiusGroups?.length > 0 && (
                <div className="sa-di-sub mt-3">
                  <p className="sa-di-eyebrow mb-2.5">반경별 거래량 · 평균가</p>
                  <div className="sa-di-tiles sa-di-tiles--4">
                    {(results.radiusGroups ?? []).map((group) => (
                      <div key={group.label} className="sa-di-tile">
                        <span className="sa-di-tile__label">{group.label}</span>
                        <span className="sa-di-tile__value">{group.count.toLocaleString()}건</span>
                        <span className="sa-di-tile__label" style={{ marginTop: "0.125rem" }}>평균 {formatPrice(group.avgPrice)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {results.totalCount === 0 && (
                <p className="sa-di-empty">조건에 맞는 실거래 데이터가 없습니다.</p>
              )}
            </>
          ) : (
            <p className="sa-di-empty">주소 입력 후 「분석 시작」을 누르면 주변 실거래 현황이 표시됩니다.</p>
          )}
        </div>
      </div>

      {/* 실거래 상세 내역 — 헤어라인 정밀 데이터 테이블(숫자 우측 mono 정렬) */}
      {results && results.transactions?.length > 0 && (
        <div className="sa-di-block">
          <header className="sa-di-block__head" style={{ cursor: "default" }}>
            <span className="sa-di-block__icon" aria-hidden>≣</span>
            <span className="sa-di-block__title">실거래 상세 내역</span>
            <span className="sa-di-eyebrow">{results.totalCount.toLocaleString()} DEALS</span>
          </header>
          <div className="sa-di-block__body">
            <div className="overflow-x-auto">
              <table className="sa-di-table">
                <thead>
                  <tr>
                    <th>거래일</th>
                    <th>단지명</th>
                    <th className="sa-di-num">면적</th>
                    <th className="sa-di-num">층</th>
                    <th className="sa-di-num">거래가</th>
                  </tr>
                </thead>
                <tbody>
                  {results.transactions.slice(0, 50).map((tx, idx) => (
                    <tr key={idx}>
                      <td className="sa-di-num" style={{ textAlign: "left", color: "var(--text-secondary)" }}>
                        {tx.deal_year ?? ""}{tx.deal_month ? `.${tx.deal_month}` : ""}{tx.deal_day ? `.${tx.deal_day}` : ""}
                      </td>
                      <td style={{ fontWeight: 600 }}>{tx.apt_name ?? "-"}</td>
                      <td className="sa-di-num" style={{ color: "var(--text-secondary)" }}>{tx.area_sqm != null ? `${tx.area_sqm}㎡` : "-"}</td>
                      <td className="sa-di-num" style={{ color: "var(--text-secondary)" }}>{tx.floor != null ? `${tx.floor}층` : "-"}</td>
                      <td className="sa-di-num">{tx.deal_amount != null ? formatPrice(tx.deal_amount) : "-"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {results.transactions?.length > 50 && (
                <p className="mt-3 text-xs text-[var(--text-tertiary)]">상위 50건만 표시 (표본 {results.transactions?.length}건 · 전체 {results.totalCount.toLocaleString()}건)</p>
              )}
            </div>
          </div>
        </div>
      )}

      {/* 보고서 원천 데이터 표 — 백엔드 report.raw_data(P2 신설)를 표로 먼저 나열.
          유형별 매매·전월세·시세추이 + (선택 시) 인구·소득. provider 미제공 값은 "-"·"데이터 없음"으로 정직 표기. */}
      {report && <RawDataTables raw={report.raw_data as RawData | undefined} />}

      {/* ================================================================ */}
      {/*  [분석 · ANALYSIS] — 위 실데이터를 해석한 결과를 그 다음에 둔다.    */}
      {/* ================================================================ */}
      <SectionDivider kr="분석" en="ANALYSIS · 해석·전망" />

      {/* AI 시세 추정 — 데이터 인텔리전스 metric 블록(실거래 기반 해석값이므로 분석으로 재배치) */}
      <div className="sa-di-block">
        <header className="sa-di-block__head" style={{ cursor: "default" }}>
          <span className="sa-di-block__icon" aria-hidden>₩</span>
          <span className="sa-di-block__title">AI 시세 추정</span>
          <span className="sa-di-eyebrow">AVM · ESTIMATE</span>
        </header>
        <div className="sa-di-block__body">
          {results?.avm ? (
            <>
              <div className="sa-di-tiles sa-di-tiles--4">
                {/* 추정 시세만 accent — 핵심 KPI 1개 강조 */}
                <MetricTile label="추정 시세 (84㎡)" value={formatCurrency(results.avm.estimated_price)} accent />
                <MetricTile label="㎡당 시세" value={formatCurrency(results.avm.price_per_sqm)} />
                <MetricTile label="신뢰도" value={`${(results.avm.confidence_score * 100).toFixed(0)}%`} />
                <MetricTile label="비교 사례" value={`${results.avm.comparable_count.toLocaleString()}건`} />
              </div>
              <p className="mt-3 text-[11px] text-[var(--text-hint)]">※ 주변 아파트 실거래 평당가 가중평균을 84㎡ 기준으로 환산한 참고 추정치입니다.</p>
            </>
          ) : mapLoading || (address && !mapPayload) ? (
            <p className="sa-di-empty">주변 실거래를 수집해 시세를 추정하는 중…</p>
          ) : (
            <p className="sa-di-empty">
              {address ? "주변 아파트 실거래가 없어 시세를 추정할 수 없습니다." : "주소 입력 후 「분석 시작」을 누르면 AI 시세가 표시됩니다."}
            </p>
          )}
        </div>
      </div>

      {/* 시장조사보고서 미리보기 — LLM 내러티브(요약/기회/리스크/가격동향/타겟). 보고서 생성 시에만. */}
      {report && (
        <div className="sa-di-block">
          <header className="sa-di-block__head" style={{ cursor: "default" }}>
            <span className="sa-di-block__icon" aria-hidden><PenLine className="size-4" /></span>
            <span className="sa-di-block__title">시장조사보고서 미리보기</span>
            <span className="sa-di-eyebrow">AI NARRATIVE</span>
          </header>
          <div className="sa-di-block__body space-y-4">
            <div>
              <p className="sa-di-eyebrow">MARKET SUMMARY · 시장 요약</p>
              <p className="mt-1.5 text-sm leading-relaxed text-[var(--text-secondary)]">{report.narrative?.summary || "-"}</p>
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <p className="sa-di-eyebrow">OPPORTUNITIES · 기회 요인</p>
                <ul className="mt-1.5 space-y-0.5 text-xs text-[var(--text-secondary)]">
                  {(report.narrative?.opportunities || []).map((o: string, i: number) => <li key={i}>· {o}</li>)}
                </ul>
              </div>
              <div>
                <p className="sa-di-eyebrow" style={{ color: "var(--status-warning)" }}>RISKS · 리스크 요인</p>
                <ul className="mt-1.5 space-y-0.5 text-xs text-[var(--text-secondary)]">
                  {(report.narrative?.risks || []).map((r: string, i: number) => <li key={i}>· {r}</li>)}
                </ul>
              </div>
            </div>
            {report.narrative?.price_trend && (
              <div>
                <p className="sa-di-eyebrow">PRICE TREND · 가격 동향</p>
                <p className="mt-1.5 text-sm leading-relaxed text-[var(--text-secondary)]">{report.narrative.price_trend}</p>
              </div>
            )}
            {report.narrative?.target_persona && (
              <div className="rounded-xl border border-[var(--accent-strong)]/30 bg-[var(--accent-strong)]/5 p-4">
                <p className="sa-di-eyebrow text-[var(--accent-strong)]">TARGET PERSONA · 추천 타겟 고객층</p>
                <p className="mt-1 text-sm font-bold leading-relaxed text-[var(--text-primary)]">{report.narrative.target_persona}</p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── Phase 3: AI 사업 타당성 엔진 (Feasibility, 공급측) ── */}
      {report?.feasibility_analysis && (
        <FeasibilityDashboard
          data={report.feasibility_analysis}
          zoneType={report.zone_type}
        />
      )}

      {/* 시니어 금융전문가 자문 — 백엔드 senior_consultation 소비. ★정직: 시장보고서 경로는
          총사업비만 전달(NOI·DSCR·자기자본 미합성)이라 통상 프레임워크·근거 중심(정량 verdict는
          입력 충족 시에만). 제목을 실제 산출에 맞춰 과장하지 않는다. */}
      {report && (
        <SeniorVerdictCard
          consultation={(report as { senior_consultation?: SeniorConsultation }).senior_consultation}
          title="시니어 금융 자문(프레임워크·근거)"
        />
      )}

      {/* ── M3: 적정 분양가 밴드 (수요측 지불여력 — 공급측 타당성과 결합) ── */}
      {report?.pricing_band && <PricingBandPanel data={report.pricing_band} />}

      {/* 인구·가구·소득 시각화(Recharts) — 분석 보조로 재배치(원천 표는 RAW에 별도). 데이터 출처 정직 배지 */}
      {report?.demographics && <DemographicPanel data={report.demographics} unitMix={report.unit_mix_recommendation} />}

      {/* 인구 이동(OD) — 현재 SGIS 미제공·행안부/KOSIS OD 미연동이라 정직하게 안내(가짜 Top3 금지) */}
      {report?.demographics?.migration && (
        (report.demographics.migration.top_inflow_regions?.length ?? 0) > 0 ? (
          <div className="sa-di-block">
            <header className="sa-di-block__head" style={{ cursor: "default" }}>
              <span className="sa-di-block__icon" aria-hidden><Compass className="size-3.5" /></span>
              <span className="sa-di-block__title">인구 이동망 (유입 Top)</span>
              <span className="sa-di-eyebrow">MIGRATION</span>
            </header>
            <div className="sa-di-block__body">
              <ul className="space-y-1.5 text-sm text-[var(--text-secondary)]">
                {report.demographics.migration.top_inflow_regions.map((reg: any, i: number) => (
                  <li key={i} className="flex justify-between border-b border-[var(--line-light)] pb-1.5">
                    <span>{reg.name}</span>
                    <span className="font-bold">{reg.ratio}% ({(reg.count ?? 0).toLocaleString()}명)</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        ) : (
          <div className="sa-di-block">
            <header className="sa-di-block__head" style={{ cursor: "default" }}>
              <span className="sa-di-block__icon" aria-hidden><Compass className="size-3.5" /></span>
              <span className="sa-di-block__title">인구 이동망 (전입·전출)</span>
              <span className="rounded-full px-2 py-0.5 text-[10px] font-bold" style={{ color: "var(--text-tertiary)", backgroundColor: "var(--surface-muted)" }}>데이터 없음</span>
            </header>
            <div className="sa-di-block__body">
              <p className="sa-di-empty">인구이동(OD) 데이터는 행정안전부/KOSIS 연동 예정입니다. (SGIS 미제공 — 가짜 수치 대신 정직 표기)</p>
            </div>
          </div>
        )
      )}

      {/* 초정밀 타겟 분석 (Phase 2 - Premium) */}
      {report?.demographics && (
        <div className="sa-di-block relative overflow-hidden">
          <header className={`sa-di-block__head ${!isPremiumUser ? "opacity-50" : ""}`} style={{ cursor: "default" }}>
            <span className="sa-di-block__icon" aria-hidden><Target className="size-3.5" /></span>
            <span className="sa-di-block__title">마이크로 타겟팅 분석</span>
            <span className="sa-di-eyebrow text-[var(--accent-strong)]">PREMIUM DATA</span>
          </header>
          <div className={`sa-di-block__body ${!isPremiumUser ? "opacity-30 blur-[2px] pointer-events-none" : ""}`}>
            {/* G7: 하드코딩 더미수치 제거 — 실데이터(K-Atlas) 미연동 상태를 정직하게 표기(가짜값 금지). */}
            {report?.demographics?.micro_finance ? (
              <div className="sa-di-tiles sa-di-tiles--4">
                <MetricTile label="평균 월소득 (avgInc)" value={report.demographics.micro_finance.avgInc != null ? `${report.demographics.micro_finance.avgInc}만원` : "-"} />
                <MetricTile label="급여소득자 수 (cntCustEmp)" value={report.demographics.micro_finance.cntCustEmp != null ? `${report.demographics.micro_finance.cntCustEmp.toLocaleString()}명` : "-"} />
                <MetricTile label="평균 신용평점 (avrCreditscore)" value={report.demographics.micro_finance.avrCreditscore != null ? `${report.demographics.micro_finance.avrCreditscore}점` : "-"} />
                <MetricTile label="주택보유자 수 (cntCustHOwn)" value={report.demographics.micro_finance.cntCustHOwn != null ? `${report.demographics.micro_finance.cntCustHOwn.toLocaleString()}명` : "-"} />
              </div>
            ) : (
              <p className="sa-di-empty">K-Atlas 초정밀 금융·소비 데이터는 제휴 연동 후 제공됩니다. (현재 미연동 — 표본 수치 비표시)</p>
            )}
          </div>
          
          {/* 권한 미달 시 잠금 오버레이 */}
          {!isPremiumUser && (
            <div className="absolute inset-0 z-10 flex flex-col items-center justify-center bg-gradient-to-t from-[var(--bg-primary)] via-[var(--bg-primary)]/80 to-transparent pt-12">
              <div className="flex flex-col items-center justify-center rounded-2xl border border-[var(--accent-strong)]/30 bg-[var(--surface-card)]/95 px-8 py-6 text-center shadow-xl backdrop-blur-md">
                <span className="mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-[var(--accent-strong)]/10 text-[var(--accent-strong)]"><Lock className="size-6" aria-hidden /></span>
                <h4 className="text-lg font-black text-[var(--text-primary)]">K-Atlas 금융 데이터 프리미엄 연동</h4>
                <p className="mt-2 max-w-sm text-sm leading-relaxed text-[var(--text-secondary)]">
                  해당 기능은 관리자가 승인한 <b>엔터프라이즈 및 PRO 등급</b> 전용입니다.<br />
                  (현재 등급: {balance?.tier_label || "미지정"})
                </p>
                <button className="mt-5 rounded-xl bg-gradient-to-r from-[var(--text-primary)] to-[var(--text-secondary)] px-6 py-2.5 text-sm font-bold text-[var(--bg-primary)] transition-transform hover:scale-105 shadow-lg">
                  등급 업그레이드 문의
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* AI 검증 + 전문가 패널 (보고서 생성 시) — 분석 신뢰성 검증 */}
      {report && <VerificationBadge analysisType="market" context={report as unknown as Record<string, unknown>} />}
      {report && (
        <ExpertPanelCard analysisType="market" address={address} context={report as unknown as Record<string, unknown>} />
      )}

      {/* 보고서 다운로드 — ANALYSIS 말미(P4에서 DOCX 버튼 추가 예정이라 구조 유지). 보고서 생성 시에만. */}
      {report && (
        <Card className="rounded-[var(--radius-2xl)] shadow-[var(--shadow-md)]">
          <CardContent className="p-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="inline-flex items-center gap-1.5 text-sm font-bold text-[var(--text-primary)]"><Download className="size-4" aria-hidden />보고서 다운로드</p>
                <p className="mt-0.5 text-xs text-[var(--text-secondary)]">위 분석 결과를 PDF/PPT 문서로 저장합니다.</p>
              </div>
              <div className="flex flex-wrap gap-2">
                <button onClick={() => downloadReport("pdf")} disabled={!!genState}
                  className="whitespace-nowrap rounded-xl bg-[var(--accent-strong)] px-4 py-2 text-xs font-black text-white hover:opacity-90 disabled:opacity-50">
                  {genState === "pdf" ? "PDF 생성 중…" : "PDF 다운로드"}
                </button>
                <button onClick={() => downloadReport("pptx")} disabled={!!genState}
                  className="whitespace-nowrap rounded-xl bg-gradient-to-r from-[var(--accent-strong)] to-[var(--data-accent)] px-4 py-2 text-xs font-black text-white hover:opacity-90 disabled:opacity-50">
                  {genState === "pptx" ? "PPT 생성 중…" : "PPT 다운로드"}
                </button>
                <button onClick={() => downloadReport("docx")} disabled={!!genState}
                  className="whitespace-nowrap rounded-xl border border-[var(--line-strong)] px-4 py-2 text-xs font-bold text-[var(--text-secondary)] hover:border-[var(--accent-strong)] disabled:opacity-50">
                  {genState === "docx" ? "DOCX 생성 중…" : "DOCX 다운로드"}
                </button>
              </div>
            </div>
          </CardContent>
        </Card>
      )}
    </section>
  );
}
