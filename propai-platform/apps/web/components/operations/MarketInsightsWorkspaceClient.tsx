"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Building, Compass, Files, MapPin, PenLine, Target, Users, Wallet } from "lucide-react";
import { Card, CardContent } from "@propai/ui";
import { apiClient, ApiClientError } from "@/lib/api-client";
import {
  submitMarketReportJob,
  readActiveMarketReportJob,
  resumeMarketReportJob,
} from "@/lib/market-report-job";
import { AnalysisHistoryCard } from "@/components/common/AnalysisHistoryCard";
import { optionsSummary } from "@/lib/use-analysis-history";
import { formatCurrencyKRW, formatManwon as formatPrice, formatYm } from "@/lib/formatters";
import { effectiveLandAreaSqm } from "@/lib/site-area";
import { dynamicMap } from "@/components/common/MapShell";
import type {
  NearbyTransactionsMap as NearbyTransactionsMapType,
  NearbyMapPayload,
} from "@/components/map/NearbyTransactionsMap";
import type { ParcelBoundaryMap as ParcelBoundaryMapType } from "@/components/map/ParcelBoundaryMap";
import type { PopulationDensityMap as PopulationDensityMapType } from "@/components/map/PopulationDensityMap";
import type { MigrationRegionMap as MigrationRegionMapType } from "@/components/map/MigrationRegionMap";
import { SeniorVerdictCard, type SeniorConsultation } from "@/components/analysis/SeniorVerdictCard";
import { ExpertPanelCard } from "@/components/common/ExpertPanelCard";
import dynamic from "next/dynamic";
const SatongMapShellDynamic = dynamic(
  () => import("@/components/precheck/SatongMapShell").then((m) => m.SatongMapShell),
  { ssr: false },
);

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
const MigrationRegionMap = dynamicMap<React.ComponentProps<typeof MigrationRegionMapType>>(
  () => import("@/components/map/MigrationRegionMap"),
  { pick: "MigrationRegionMap", height: 360, loadingMessage: "권역 순이동 지도 로딩…" },
);
import { VerificationBadge } from "@/components/common/VerificationBadge";
import { ContextHeader } from "@/components/common/ContextHeader";
import { deriveMarketPipelineSteps } from "@/lib/context-header";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { FeasibilityDashboard } from "@/components/feasibility/FeasibilityDashboard";
import { IntegratedParcelsBadge, type IntegratedMeta } from "@/components/common/IntegratedParcelsBadge";
import { parcelDataToRows, shouldSendParcels } from "@/lib/parcel-rows";
import { UseLlmToggle } from "@/components/common/UseLlmToggle";
import { AnalysisModuleSelector, type AnalysisModuleOption } from "@/components/common/AnalysisModuleSelector";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import { DemographicPanel } from "@/components/operations/market/DemographicPanel";
import { PricingBandPanel } from "@/components/operations/market/PricingBandPanel";
import { RawDataTables, type RawData } from "@/components/operations/market/RawDataTables";
import { DataSourceBadge } from "@/components/operations/market/DataSourceBadge";
import type { MarketReport, SeniorInsight, TargetProfile, MarketNarrative } from "@/components/operations/market/marketTypes";
import {
  buildTrendLightPath,
  mapLightTrend,
  mapReportTrendSeries,
  selectTrendChartPoints,
  trendStatusMessage,
  type MarketTrendLightResponse,
  type TrendPeriodMonths,
} from "@/lib/market-trend-light";

// /market/report 응답 계약 — marketTypes.MarketReport에 이 화면이 소비하는 부가 필드 2종을 더한 것.
// (raw_data/integrated 는 각 소비 컴포넌트의 export 타입이 정본이라 여기서 교차만 한다.)
type MarketReportResponse = MarketReport & {
  raw_data?: RawData | null;
  integrated?: IntegratedMeta | null;
};
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
  sample_count: number;     // 신뢰도(CV) 산출에 실제 사용된 개별 거래 표본 수
  price_cv_percent: number; // 표본 가격 변동계수(CV, %) — 낮을수록 가격이 고르게 형성됨
};

type TxItem = {
  deal_amount?: number; // 만원
  deal_year?: string; deal_month?: string; deal_day?: string;
  area_sqm?: number; floor?: number | string; apt_name?: string; distance_m?: number;
};

type RadiusBucket = { label: string; count: number; avgPrice: number /* 만원 — 아파트 매매 기준(P2b) */ };

/** ★유형별 분리 집계(P2b — 분석품질 레인G): 토지·상업용·아파트는 단가 스케일이 달라
 *  섞으면 "평균가"가 무의미해진다(deriveResults 주석 참조). 유형별 독립 평균. */
type TradeTypeBreakdown = { key: string; label: string; count: number; avgPrice: number /* 만원 */ };

type MarketResults = {
  avm: AvmSummary | null;
  totalCount: number;
  avgPrice: number; // 만원 — 아파트 매매 기준(P2b, AVM과 동일 축)
  radiusGroups: RadiusBucket[];
  byType: TradeTypeBreakdown[];
  transactions: TxItem[];
  months: number;
  radius: number;
  searchAddress: string;
};

/* ------------------------------------------------------------------ */
/*  Helpers                                                           */
/* ------------------------------------------------------------------ */

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
  // ★유형별 분리 집계(P2b — 분석품질 레인G): 종전엔 `_trade`로 끝나는 전 카테고리(아파트·
  //   연립다세대·단독다가구·오피스텔·토지·상업업무용)의 avg_price_10k를 한 통에 섞어
  //   가중평균했다 — 아파트(㎡당 수백만원)와 토지·상업용(단가 스케일 자체가 상이)이 뒤섞여
  //   "평균 실거래가"가 무의미해지는 결함이었다(값의 계산은 맞지만 비교불가 단위 혼합).
  //   헤드라인 평균·반경버킷 평균은 apt_trade만 사용(AVM·avm 필드와 동일 축으로 정합),
  //   그 외 유형은 byType에서 유형별 독립 평균으로 분리해 보존한다(무손실 — 값 자체는 유지).
  let aptPSum = 0, aptPN = 0;
  const byType: TradeTypeBreakdown[] = [];

  for (const [, c] of tradeEntries) {
    const isApt = c.type === "apt";
    let typePSum = 0, typePN = 0;
    for (const g of c.groups || []) {
      const dist = center?.lat && g.lat ? distanceM(center.lat, center.lon as number, g.lat, g.lon) : 1000;
      const cnt = g.count || 0;
      if (g.avg_price_10k) {
        typePSum += g.avg_price_10k * (cnt || 1);
        typePN += cnt || 1;
        if (isApt) { aptPSum += g.avg_price_10k * (cnt || 1); aptPN += cnt || 1; }
      }
      for (const b of buckets) {
        if (dist <= b.max) {
          // 건수는 유형 무관 커먼저러블(합산 문제 없음) — 가격만 apt로 한정(단위 혼합 방지).
          b.count += cnt;
          if (isApt && g.avg_price_10k) { b.pSum += g.avg_price_10k * (cnt || 1); b.pN += cnt || 1; }
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
    if (c.count) {
      byType.push({
        key: c.type || "",
        label: c.label || c.type || "",
        count: c.count,
        avgPrice: typePN ? Math.round(typePSum / typePN) : 0,
      });
    }
  }
  byType.sort((a, b) => b.count - a.count);

  // 거래일 desc 정렬(최신 거래가 먼저) — 연/월/일을 zero-pad한 문자열 비교로 결측(day 없음)도 안전.
  transactions.sort((a, b) => {
    const key = (t: TxItem) =>
      `${t.deal_year ?? ""}${(t.deal_month ?? "").padStart(2, "0")}${(t.deal_day ?? "").padStart(2, "0")}`;
    return key(b).localeCompare(key(a));
  });

  const radiusGroups: RadiusBucket[] = buckets
    .filter((b) => b.count > 0)
    .map((b) => ({ label: b.label, count: b.count, avgPrice: b.pN ? Math.round(b.pSum / b.pN) : 0 }));

  // AI 시세(AVM) — SSOT 일원화(PropAI 아이디어#3): 종전엔 여기서 apt_trade 그룹을 다시
  //   순회해 평당가 가중평균+CV 신뢰도를 재계산했으나, 백엔드(nearby_map_service
  //   ._compute_avm_summary)가 동일 로직으로 이미 계산해 payload.avm에 실어보낸다 —
  //   프론트는 그 값을 그대로 소비한다(계산 위치만 이동, 값·표기는 불변). 비교 표본
  //   0건이면 백엔드가 null을 보낸다(무날조) — "일시 미제공" graceful 표기로 소비.
  const avm: AvmSummary | null = payload.avm ?? null;

  return {
    avm, totalCount,
    avgPrice: aptPN ? Math.round(aptPSum / aptPN) : 0,
    radiusGroups, byType, transactions,
    months: payload.months?.length || 3,
    radius: payload.radius_m || 1000,
    searchAddress: center?.address || fallbackAddr,
  };
}

type Balance = {
  tier_label: string;
  monthly_base_remaining: number;
  topup_remaining: number;
  unlimited?: boolean; // 비과금 등급(super_admin 등) — 코인 게이트 면제
  // 관리자가 설정한 분석 모듈 사용료 맵(미설정 시 빈 dict = 전부 무료).
  module_fees?: Record<string, number>;
};

const won = (n: number) => (n ?? 0).toLocaleString("ko-KR") + "원";

/* ── 데이터 인텔리전스 metric 타일 ──
   핵심 수치는 mono·tabular-nums로 자릿수 정렬(sa-di-tile). accent=true는 핵심 KPI 1개에만. */
function MetricTile({ label, value, accent = false, detail }: { label: string; value: string; accent?: boolean; detail?: string }) {
  return (
    <div className={`sa-di-tile${accent ? " sa-di-tile--accent" : ""}`}>
      <span className="sa-di-tile__label">{label}</span>
      <span className="sa-di-tile__value">{value || "-"}</span>
      {detail ? <span className="sa-di-tile__label" style={{ marginTop: "0.125rem" }}>{detail}</span> : null}
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

/* ── 원자료 표 펼치기 컨테이너(로컬) ──
   차트·요약을 기본으로 두고, 동일 데이터의 세부 표(RawDataTables)는 접힘 '원자료'로 강등해
   표↔차트 이원화를 없앤다(한 곳에만). 헤더 클릭으로 펼침/접힘. */
function CollapsibleRaw({ title, children }: { title: string; children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)]">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center justify-between gap-2 px-5 py-3 text-left"
      >
        <span className="text-xs font-bold text-[var(--text-secondary)]">{title}</span>
        <span className="text-xs text-[var(--accent-strong)]">{open ? "▾ 닫기" : "▸ 원자료 보기"}</span>
      </button>
      {open && <div className="border-t border-[var(--line)] px-5 pb-5 pt-4">{children}</div>}
    </div>
  );
}

/* ── 보고서 액션 바(로컬·단일화) ──
   PDF/PPT/DOCX 다운로드 버튼이 '생성 트리거 카드'와 '하단 다운로드 카드'에 완전 중복이던 것을
   한 곳(보고서 그룹)으로 통합. 미리보기 생성 + AI 사용 토글 + 3개 문서 버튼(기존 콜백 재사용, 로직 0신규). */
/**
 * 오류 사유 보존 — ApiClientError.payload(백엔드 {detail}/{message}) 우선, 없으면 상태코드.
 * (인허가/적산 클라이언트의 관례와 동일 패턴 — catch{}로 사유를 삼키지 않는다.)
 */
function errorMessage(e: unknown, fallback: string): string {
  if (e instanceof ApiClientError) {
    const payload = e.payload as { detail?: string; message?: string } | null;
    return payload?.detail || payload?.message || `${fallback} (HTTP ${e.status})`;
  }
  // 다운로드(PDF/PPT/DOCX) 경로는 apiClient가 아닌 raw fetch()를 쓰므로 lib/api-client.ts의
  //   네트워크 오류 래핑을 타지 않는다 — 여기서도 브라우저 원시 예외("Failed to fetch" 등)를
  //   그대로 노출하지 않고 한국어로 정규화한다.
  if (e instanceof TypeError || (e instanceof DOMException && e.name !== "AbortError")) {
    return "네트워크 오류 — 연결이 지연되거나 끊겼습니다. 다시 시도해 주세요.";
  }
  return e instanceof Error && e.message ? e.message : fallback;
}

function ReportActionsBar({
  genState,
  useLlm,
  onUseLlmChange,
  onGenerate,
  onDownload,
}: {
  genState: "" | "report" | "pdf" | "pptx" | "docx";
  useLlm: boolean;
  onUseLlmChange: (v: boolean) => void;
  onGenerate: () => void;
  onDownload: (fmt: "pdf" | "pptx" | "docx") => void;
}) {
  return (
    <Card className="rounded-[var(--radius-2xl)] shadow-[var(--shadow-md)]">
      <CardContent className="p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="inline-flex items-center gap-1.5 text-sm font-bold text-[var(--text-primary)]"><Files className="size-4" aria-hidden />시장조사보고서</p>
            <p className="mt-0.5 text-xs text-[var(--text-secondary)]">위 분석(실거래·시세·입지·인구)을 통합한 심층 보고서를 PDF/PPT/DOCX로 저장합니다.</p>
            {/* use_llm 옵트인 — 공용 UseLlmToggle(중복 제거, 시각 동일). */}
            <UseLlmToggle
              className="mt-2"
              checked={useLlm}
              onChange={onUseLlmChange}
              disabled={!!genState}
              hint="LLM이 시장요약·기회·리스크·가격동향을 작성"
            />
          </div>
          <div className="flex flex-wrap gap-2">
            <button onClick={onGenerate} disabled={!!genState}
              className="whitespace-nowrap rounded-xl border border-[var(--line-strong)] px-4 py-2 text-xs font-bold text-[var(--text-secondary)] hover:border-[var(--accent-strong)] disabled:opacity-50">
              {genState === "report" ? "생성 중…" : "미리보기 생성"}
            </button>
            <button onClick={() => onDownload("pdf")} disabled={!!genState}
              className="whitespace-nowrap rounded-xl bg-[var(--accent-strong)] px-4 py-2 text-xs font-black text-white hover:opacity-90 disabled:opacity-50">
              {genState === "pdf" ? "PDF 생성 중…" : "PDF 다운로드"}
            </button>
            <button onClick={() => onDownload("pptx")} disabled={!!genState}
              className="whitespace-nowrap rounded-xl bg-gradient-to-r from-[var(--accent-strong)] to-[var(--data-accent)] px-4 py-2 text-xs font-black text-white hover:opacity-90 disabled:opacity-50">
              {genState === "pptx" ? "PPT 생성 중…" : "PPT 다운로드"}
            </button>
            <button onClick={() => onDownload("docx")} disabled={!!genState}
              className="whitespace-nowrap rounded-xl border border-[var(--line-strong)] px-4 py-2 text-xs font-bold text-[var(--text-secondary)] hover:border-[var(--accent-strong)] disabled:opacity-50">
              {genState === "docx" ? "DOCX 생성 중…" : "DOCX 다운로드"}
            </button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

/* ------------------------------------------------------------------ */
/*  Component                                                         */
/* ------------------------------------------------------------------ */

export function MarketInsightsWorkspaceClient() {
  // 활성 프로젝트(projectId)가 있을 때만 컨텍스트를 사용 — 약식 검색이 타 페이지로 새지 않도록.
  const projectId = useProjectContextStore((s) => s.projectId);
  const projectName = useProjectContextStore((s) => s.projectName);
  const rawSite = useProjectContextStore((s) => s.siteAnalysis);
  const siteAnalysis = projectId ? rawSite : null;
  // 유효 대지면적(다필지=통합) — 렌더에서 재호출하지 않도록 1회 파생.
  const effAreaSqm = effectiveLandAreaSqm(siteAnalysis);
  // 명시실행: 주소 입력만으로는 분석하지 않고, "분석 실행" 클릭 시에만 runAddress를 확정한다.
  const [runAddress, setRunAddress] = useState("");
  // store 폴백 다필지(인테이크/프로젝트가 store에 쓴 것)도 실행 시점에 스냅샷으로 고정 — 피커와 동일하게
  //   '미리보기=다운로드' 불변식이 이후 store 변경(다탭 등)에 흔들리지 않게 한다.
  const [runStoreParcels, setRunStoreParcels] = useState<
    Array<{ address?: string; areaSqm?: number | null; zoneCode?: string | null; pnu?: string | null }>
  >([]);
  // 일괄분석(P2): 「분석 시작」 클릭 시 지도뿐 아니라 시장보고서까지 한 번에 생성하기 위한 대기 플래그.
  const [pendingReport, setPendingReport] = useState(false);
  const [mapPayload, setMapPayload] = useState<NearbyMapPayload | null>(null);
  const [mapLoading, setMapLoading] = useState(false);
  const [report, setReport] = useState<MarketReportResponse | null>(null);
  const [genState, setGenState] = useState<"" | "report" | "pdf" | "pptx" | "docx">("");
  const [useLlm, setUseLlm] = useState(true);
  // 히스토리 카드 재조회 신호 — 새 보고서 생성/복원 완료 시 증가시켜 AnalysisHistoryCard가
  //   언마운트 없이 목록을 다시 불러오게 한다.
  const [historyRefreshTick, setHistoryRefreshTick] = useState(0);
  // 선택 상태(말단 항목 기준 평탄 boolean 맵). 분류 sgis/kosis는 자식들에서 파생해 전송한다.
  //   population(인구/가구) 자식: pop_age / pop_household / pop_migration
  //   income(거시 소득) 자식: income_avg / income_basis
  //   katlas: 마이크로 타겟팅(프리미엄)
  const [analysisOptions, setAnalysisOptions] = useState<Record<string, boolean>>({
    pop_age: true,
    pop_household: true,
    pop_migration: true,
    income_avg: true,
    income_basis: true,
    katlas: false,
  });
  const [error, setError] = useState("");
  const [balance, setBalance] = useState<Balance | null>(null);
  // 시세추이 경량 조회(GET /market/trend) — 기간 칩(3/12/24개월). 3=report.trend_series
  //   그대로(무변경 기본, 아래 상태들 미사용). 12/24 선택 시에만 별도 GET을 쏜다(보고서 재생성 없음).
  const [trendMonths, setTrendMonths] = useState<TrendPeriodMonths>(3);
  const [trendLight, setTrendLight] = useState<MarketTrendLightResponse | null>(null);
  const [trendLightLoading, setTrendLightLoading] = useState(false);
  const [trendLightError, setTrendLightError] = useState("");

  // 입력 후보 주소(실행 전): 활성 프로젝트 주소(SSOT).
  const inputAddress = siteAnalysis?.address || "";
  // 실제 분석 대상 주소 — 버튼 클릭으로 확정된 값만 지도/산출에 전달.
  const address = runAddress;
  // ── 다필지 SSOT 파생 ──
  const mapPnu = runStoreParcels.length > 0
    ? ((runStoreParcels[0]?.pnu as string) || "")
    : ((siteAnalysis?.pnu as string) || "");
  // 등록된 전 필지 주소(구획도 통합 경계용).
  const runParcelAddrs = useMemo(
    () => runStoreParcels.map((p) => p.address ?? "").filter(Boolean),
    [runStoreParcels],
  );
  // 백엔드 통합집계 입력행(면적가중) — comprehensive_analysis 계약과 동일 키. 면적>0만.
  const runParcelRows = useMemo(
    () => parcelDataToRows(runStoreParcels),
    [runStoreParcels],
  );
  // P4-B 인구밀도: bcode(법정동 10자리) = PNU 앞 10자리. 동시표시 토글(지연로드).
  const mapBcode = mapPnu.slice(0, 10);
  const [showDensity, setShowDensity] = useState(false);
  // 권역 순이동 코로플레스(시군구 발산 지도) 지연로드 토글 — 인구이동망 패널 하단.
  const [showMigrationMap, setShowMigrationMap] = useState(false);
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

  // ── 분석 모듈 카탈로그(공용 AnalysisModuleSelector 주입용) ──
  // 선택형 기본(★선택형 분석 기본 지침): 셀렉터에서 체크한 항목만 analysisOptions에 반영되고
  //   buildOptionsPayload가 그대로 전송한다(체크→선택분만 실행·과금).
  //   (+katlas는 프리미엄 여부 연동 effect로 기본값 결정 — 비프리미엄은 잠금이라 토글 불가.)
  // coinCost/estimatedSeconds는 예상 코인·시간 안내 표시에 사용(안내용 추정치).
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

  // 히스토리 변동감지 시그니처 파트 — 백엔드 계약과 동일 순서
  //   [address, pnu||"", parcelCount, useLlm, options요약].
  //   parcelCount는 실행 바디(generateReport의 body.parcels)와 동일 출처·동일 폴백으로 맞춘다
  //   — runStoreParcels(store 원본)가 아니라 실제로 전송되는 runParcelRows 기준, 백엔드
  //   `len(req.parcels or []) or 1`을 그대로 미러(`|| 1`). options는 optionsSummary()로
  //   백엔드 _options_summary()와 canonical 일치시킨다(JSON.stringify는 키 순서에 민감해 폐기).
  const historySignatureParts = useMemo(
    () => [address, mapPnu || "", String(runParcelRows.length || 1), String(useLlm), optionsSummary(buildOptionsPayload())],
    [address, mapPnu, runParcelRows.length, useLlm, buildOptionsPayload],
  );

  useEffect(() => {
    apiClient.get<Balance>("/billing/balance", { useMock: false })
      .then(setBalance)
      .catch((e) => { if (!(e instanceof ApiClientError)) setBalance(null); });
  }, []);

  // 프리미엄 권한 변경 시 K-Atlas 마이크로 타겟팅 분석 기본값 연동
  useEffect(() => {
    setAnalysisOptions(prev => ({
      ...prev,
      katlas: !!isPremiumUser,
    }));
  }, [isPremiumUser]);

  // 주소 변경 감시 → 새 대상 선택 시 기존 결과 비움(stale 차단)
  useEffect(() => {
    if (inputAddress && inputAddress !== runAddress) {
      setMapPayload(null);
      setReport(null);
      setError("");
      // 시세추이 경량 조회도 대상 전환 시 초기화(다른 지역의 12/24개월 추이가 남아있으면 오염).
      setTrendMonths(3);
      setTrendLight(null);
      setTrendLightError("");
    }
  }, [inputAddress, runAddress]);

  // 명시 실행: 버튼 클릭 시에만 분석 대상 주소를 확정하고 지도/산출을 트리거한다.
  const runAnalysis = useCallback(() => {
    if (!inputAddress) return;
    setError("");
    setReport(null);
    setMapPayload(null);
    setRunAddress(inputAddress);
    // 오직 store parcels만 스냅샷으로 캡처
    setRunStoreParcels(siteAnalysis?.parcels ?? []);
    // P2 일괄분석: 지도와 함께 시장보고서까지 한 번에 생성(아래 effect가 address 확정 후 트리거).
    setPendingReport(true);
    // 실행 후 잔액 갱신(차감 반영) — 약간 지연 후 재조회.
    setTimeout(() => {
      apiClient.get<Balance>("/billing/balance", { useMock: false }).then(setBalance).catch(() => { /* noop */ });
    }, 1500);
  }, [inputAddress, siteAnalysis?.parcels]);

  // 시장조사보고서: 구조화 미리보기 — ★로드맵(잡 제출+폴링, 등기 권리분석 패턴 재사용).
  //   /market/report/jobs 가 아직 배포되지 않은 환경(404)에서는 기존 동기 POST로 폴백해
  //   백엔드·프론트 병렬 배포 순서와 무관하게 동작한다.
  const generateReport = useCallback(async () => {
    if (!address) return;
    setGenState("report");
    setError("");
    // 새 보고서 = 새 3개월 추이(SSOT) — 이전 보고서에서 조회했던 12/24개월 경량 결과는 폐기.
    setTrendMonths(3);
    setTrendLight(null);
    setTrendLightError("");
    try {
      // pnu·parcels 모두 SSOT(현재 피커 선택)에서: 단일필지 고착·엉뚱지역 표시 동시 해소.
      const body = {
        address, pnu: mapPnu || undefined, use_llm: useLlm, options: buildOptionsPayload(),
        ...(shouldSendParcels(runParcelRows) ? { parcels: runParcelRows } : {}),
      };
      let r: MarketReportResponse;
      try {
        r = await submitMarketReportJob<MarketReportResponse>(body);
      } catch (jobErr) {
        if (jobErr instanceof ApiClientError && jobErr.status === 404) {
          // 잡 엔드포인트 미배포 — 기존 동기 POST 폴백(순서 독립 배포).
          r = await apiClient.post<MarketReportResponse>("/market/report", {
            body, useMock: false, timeoutMs: 120000,
          });
        } else {
          throw jobErr;
        }
      }
      setReport(r);
      setHistoryRefreshTick((t) => t + 1);
      // LLM 분석 후 코인 차감 반영 — 잔액 재조회.
      if (useLlm) {
        apiClient.get<Balance>("/billing/balance", { useMock: false }).then(setBalance).catch(() => { /* noop */ });
      }
    } catch (e) {
      // 오류 사유 보존(catch{} 삼킴 금지) — 401/402/충전필요 등 실제 원인을 사용자에게 표기.
      setError(errorMessage(e, "보고서 생성에 실패했습니다."));
    } finally {
      setGenState("");
    }
  }, [address, mapPnu, runParcelRows, useLlm, buildOptionsPayload]);

  // 12/24 칩 연타·응답 재정렬 시 느린 선행 응답이 최신 선택을 덮는 레이스 방지(#385 패턴).
  //   요청마다 시퀀스를 증가시키고, 응답이 최신 시퀀스일 때만 반영한다.
  const trendSeqRef = useRef(0);

  // 시세추이 경량 조회(GET /market/trend) — 12/24개월 칩 선택 시에만 호출. 보고서 전체
  //   재생성(MOLIT 6유형+SGIS+KOSIS+LLM) 없이 아파트 매매 월별 평당가만 가져온다.
  const fetchTrendLight = useCallback(async (months: 12 | 24) => {
    if (!address) return;
    const seq = ++trendSeqRef.current;
    setTrendLightLoading(true);
    setTrendLightError("");
    try {
      const r = await apiClient.get<MarketTrendLightResponse>(
        buildTrendLightPath({ address, pnu: mapPnu || undefined, months }),
        { useMock: false, timeoutMs: 30000 },
      );
      if (seq !== trendSeqRef.current) return; // stale 응답 — 이후 칩 선택이 이미 발화됨
      setTrendLight(r);
    } catch (e) {
      if (seq !== trendSeqRef.current) return;
      // 오류 사유 보존(catch{} 삼킴 금지) — 정직 실패 문구를 그대로 카드에 노출.
      setTrendLightError(errorMessage(e, "시세 추이 조회에 실패했습니다."));
      setTrendLight(null);
    } finally {
      if (seq === trendSeqRef.current) setTrendLightLoading(false);
    }
  }, [address, mapPnu]);

  // 기간 칩 전환 — 3개월은 이미 보유한 report.trend_series를 그대로 쓰므로 재요청 없음(무변경 기본).
  const handleTrendMonthsChange = useCallback((months: TrendPeriodMonths) => {
    setTrendMonths(months);
    if (months === 3) return;
    void fetchTrendLight(months);
  }, [fetchTrendLight]);

  // 리로드·재진입 복원 — 진행 중이던 보고서 잡을 sessionStorage에서 찾아 이어서 폴링한다
  //   (design-audit DesignAuditWorkspace.tsx:284-322 패턴, 마운트 1회만).
  useEffect(() => {
    const active = readActiveMarketReportJob();
    if (!active) return;
    let cancelled = false;
    setGenState("report");
    setError("");
    // stale 가드 — 저장된 잡의 address와 현재 SSOT 주소(inputAddress)가 다르면 폴링 없이
    //   스킵하고 흔적만 제거한다(다른 프로젝트로 전환된 사이 남은 잡이 엉뚱하게 표시되는 사고 방지).
    resumeMarketReportJob<MarketReportResponse>(active.jobId, inputAddress || undefined)
      .then((r) => {
        if (cancelled || !r) return;
        setReport(r);
        setHistoryRefreshTick((t) => t + 1);
      })
      .catch((e) => {
        if (!cancelled) setError(errorMessage(e, "보고서 생성에 실패했습니다."));
      })
      .finally(() => {
        if (!cancelled) setGenState("");
      });
    return () => {
      cancelled = true;
    };
    // 마운트 1회만(리로드 복원) — inputAddress는 최초 렌더 시점 값으로 충분(가드는 "그 사이
    //   바뀌었는가"만 확인하면 되고, 이후 주소 변경까지 추적할 필요는 없다).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // PDF/PPTX 다운로드(바이너리)
  const downloadReport = useCallback(async (fmt: "pdf" | "pptx" | "docx") => {
    if (!address) return;
    setGenState(fmt);
    try {
      const token = (typeof window !== "undefined" && localStorage.getItem("propai_access_token")) || "";
      const res = await fetch(`${marketApiBase()}/market/report/${fmt}`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        // ★다운로드도 미리보기와 동일 payload(options+pnu+parcels) — PDF/PPTX에 인구·소득·통합면적이 누락되지 않게.
        body: JSON.stringify({
          address, pnu: mapPnu || undefined, use_llm: useLlm, options: buildOptionsPayload(),
          ...(shouldSendParcels(runParcelRows) ? { parcels: runParcelRows } : {}),
        }),
      });
      if (!res.ok) {
        // 오류 사유 보존 — 스트리밍 에러 본문({detail})을 읽어 실제 원인을 표기(삼킴 금지).
        let detail = "";
        try {
          const body = (await res.json()) as { detail?: string; message?: string };
          detail = body?.detail || body?.message || "";
        } catch { /* 본문이 JSON이 아니면 상태코드만 */ }
        throw new Error(detail || `${fmt.toUpperCase()} 다운로드 실패 (HTTP ${res.status})`);
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      // 다필지 대표주소에 / : 등 OS 금칙문자가 있으면 파일명이 깨지므로 치환.
      const safeName = address.replace(/[\\/:*?"<>|]/g, "_");
      a.download = `시장조사보고서_${safeName}.${fmt}`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(errorMessage(e, `${fmt.toUpperCase()} 다운로드에 실패했습니다.`));
    } finally {
      setGenState("");
    }
  }, [address, mapPnu, runParcelRows, useLlm, buildOptionsPayload]);

  // P2 일괄분석: 「분석 시작」이 address를 확정하면(pendingReport=true) 시장보고서를 자동 1회 생성한다.
  //   (지도+보고서를 한 번의 클릭으로 — 사용자 요청 "사업지 입력 후 분석 누르면 일괄분석".)
  useEffect(() => {
    if (pendingReport && address) {
      setPendingReport(false);
      void generateReport();
    }
  }, [pendingReport, address, generateReport]);

  // OrchestratorPanel 접기/펼치기 토글 — 베타 패널을 핵심 흐름에서 격리하기 위한 presentational 상태.
  // 분석/과금/실행 동작에 영향 0. OrchestratorPanel의 props·scopeNodes·balance는 불변.
  const [showOrchestrator, setShowOrchestrator] = useState(false);

  return (
    <section className="grid grid-cols-1 gap-6 min-w-0">

      {/* 생성허브 공용 대상 컨텍스트 헤더(additive) — 어느 프로젝트·토지 대상 시장분석인지 상시
          표시 + 이 산출물의 실제 분석 3단계(수집=실거래 데이터, 검증=정직 idle 고정(교차검증
          트레이스 미보유), 전문가=LLM 시장해설 narrative). */}
      <ContextHeader
        pipeline={deriveMarketPipelineSteps({ genState, report, useLlm })}
      />

      {/* 사통팔땅 전역 싱글 통합지도 워크스페이스 (대시보드와 100% 동일한 필지 입력 + 멀티지도 엔진) */}
      <SatongMapShellDynamic locale="ko" />

      {/* 분석 대상 요약 카드 */}
      <div className="rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)]/50 p-4 flex flex-wrap items-center justify-between gap-4">
        <div>
          <span className="text-[10px] font-bold uppercase tracking-wider text-[var(--text-tertiary)]">시장 분석 대상</span>
          <h3 className="text-sm font-black text-[var(--text-primary)] mt-0.5">
            {inputAddress ? (
              <span className="inline-flex items-center gap-1.5">
                <MapPin className="size-4 text-[var(--accent-strong)]" />
                {inputAddress}
                {projectName ? (
                  <span className="text-xs font-semibold text-[var(--text-secondary)]">({projectName})</span>
                ) : null}
              </span>
            ) : (
              <span className="text-[var(--text-hint)]">상단 통합 지도에서 분석 대상을 선택해 주세요.</span>
            )}
          </h3>
        </div>
        {/* ★면적은 effectiveLandAreaSqm(SSOT) — raw landAreaSqm 금지(바로 옆 필지 수와 축이 어긋난다). */}
        {effAreaSqm ? (
          <div className="flex gap-4 text-xs font-bold text-[var(--text-secondary)]">
            <span>대지면적: <b className="text-[var(--text-primary)]">{effAreaSqm.toLocaleString()}㎡</b></span>
            {siteAnalysis?.parcelCount ? (
              <span>필지 수: <b className="text-[var(--text-primary)]">{siteAnalysis.parcelCount}필지</b></span>
            ) : null}
          </div>
        ) : null}
      </div>

      {/* 분석 설정 + 실행 — 모듈 선택과 실행 버튼을 하나의 카드로 묶어 "설정→실행" 흐름을 일원화. */}
      <Card className="rounded-[var(--radius-2xl)] shadow-[var(--shadow-md)]">
        <CardContent className="p-5 space-y-4">
          {/* 분석 대상 항목 선택(선택형 기본) — 체크한 항목만 실행·과금. 아래 「분석 시작」이 실행. */}
          <AnalysisModuleSelector
            modules={analysisModules}
            selected={analysisOptions}
            onChange={setAnalysisOptions}
            unlimited={!!balance?.unlimited}
          />

          {/* 구분선 */}
          <div className="h-px bg-[var(--line)]" aria-hidden />

          {/* 실행 버튼 행 */}
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
            <p className="text-xs font-bold text-[var(--status-warning)]">
              코인 잔액이 부족합니다. 좌측 코인 미터의 「추가결제」로 충전 후 다시 실행해 주세요.
            </p>
          )}
          {!inputAddress && (
            <p className="text-xs text-[var(--text-hint)]">먼저 위에서 분석할 주소를 입력하세요.</p>
          )}
          {address && (
            <p className="text-xs text-[var(--text-hint)]">
              분석 대상: <b className="text-[var(--text-secondary)]">{address}</b> · 실행 후 사용량은 설정 &gt; AI 사용량에서 확인할 수 있습니다.
            </p>
          )}
        </CardContent>
      </Card>

      {/* ── ZONE A-ALT: 대안/고급 분석(베타) — 접기 토글로 핵심 흐름과 격리 ── */}
      {/* B3 채택(additive): 오케스트레이션 노드 기반 분석 실행 — 분양성·분양가(sales) 스코프.
          기존 시장보고서 흐름과 별개 경로(별도 store). balance.module_fees(미설정 0=무료) 재사용. */}
      <div className="rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)]">
        <button
          type="button"
          onClick={() => setShowOrchestrator((v) => !v)}
          className="flex w-full items-center justify-between gap-2 px-5 py-3 text-left"
          aria-expanded={showOrchestrator}
        >
          <div className="flex items-center gap-2">
            <span className="text-xs font-bold text-[var(--text-secondary)]">통합 분석(베타)</span>
            <span className="rounded-full border border-[var(--line-strong)] px-2 py-0.5 text-[10px] font-bold text-[var(--text-tertiary)]">고급 · 분양성·분양가</span>
          </div>
          <span className="text-xs text-[var(--accent-strong)]">{showOrchestrator ? "▾ 닫기" : "▸ 펼치기"}</span>
        </button>
        {showOrchestrator && (
          <div className="border-t border-[var(--line)] px-5 pb-5 pt-4">
            <OrchestratorPanel
              scopeNodes={["sales"]}
              balance={balance}
              runDisabled={!inputAddress || insufficient}
              title="통합 분석(베타)"
              subtitle="분양성·분양가 분석을 레지스트리 기반으로 실행합니다. 상류(부지·설계) 의존은 자동 포함됩니다."
            />
          </div>
        )}
      </div>

      {/* ── ZONE B: 지도 — 분석 후 주소 아래 즉시 노출 ─────────────────── */}
      {/* P3 Zone B: 실거래+분양 통합 오버레이 지도 → 필지 구획도 순. 분석 전엔 숨겨 셀렉터가 상단. */}
      {address && (
        <div className="grid gap-4">
          <NearbyTransactionsMap address={address} pnu={mapPnu} onPayload={setMapPayload} onLoading={setMapLoading} />
          {/* 구획도: 등록된 전 필지(다필지 통합 경계) — 비면 대표주소 단독. */}
          <ParcelBoundaryMap parcels={runParcelAddrs.length > 0 ? runParcelAddrs : [address]} />
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

      {/* 에러 */}
      {error && (
        <div className="rounded-[var(--radius-xl)] border border-[var(--status-warning)]/30 bg-[color-mix(in_srgb,var(--status-warning)_8%,transparent)] p-5 text-sm leading-7 text-[var(--status-warning)]">
          <p>{error}</p>
          {address && (
            <button
              type="button"
              onClick={() => { setError(""); void generateReport(); }}
              disabled={genState === "report"}
              className="mt-3 rounded-lg border border-[var(--status-warning)]/40 bg-[var(--surface)] px-3 py-1.5 text-xs font-bold text-[var(--status-warning)] hover:bg-[color-mix(in_srgb,var(--status-warning)_10%,transparent)] disabled:opacity-50"
            >
              {genState === "report" ? "재시도 중…" : "다시 시도"}
            </button>
          )}
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
                  {/* ★P2b(레인G) 교정: 종전 "매매 평균가"는 아파트·연립·단독·오피스텔·토지·
                      상업업무용 단가를 한 통에 섞은 값이라 무의미했다 — 아파트(AVM과 동일 축)
                      기준으로 좁히고 라벨을 정직화, 유형별 값은 아래 "유형별 거래량 · 평균가"로 분리. */}
                  <span className="sa-di-stat__label">아파트 매매 평균가</span>
                  <span className="sa-di-stat__value">{results.avgPrice > 0 ? formatPrice(results.avgPrice) : "-"}</span>
                </div>
                <div className="sa-di-stat">
                  <span className="sa-di-stat__label">분석 반경</span>
                  <span className="sa-di-stat__value">{(results.radius / 1000).toLocaleString()}km</span>
                </div>
              </div>

              {results.byType?.length > 0 && (
                <div className="sa-di-sub mt-3">
                  <p className="sa-di-eyebrow mb-2.5">유형별 거래량 · 평균가</p>
                  <div className="sa-di-tiles sa-di-tiles--4">
                    {results.byType.map((t) => (
                      <div key={t.key} className="sa-di-tile">
                        <span className="sa-di-tile__label">{t.label}</span>
                        <span className="sa-di-tile__value">{t.count.toLocaleString()}건</span>
                        <span className="sa-di-tile__label" style={{ marginTop: "0.125rem" }}>{t.avgPrice > 0 ? `평균 ${formatPrice(t.avgPrice)}` : "평균가 미상"}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {results.radiusGroups?.length > 0 && (
                <div className="sa-di-sub mt-3">
                  <p className="sa-di-eyebrow mb-2.5">반경별 거래량 · 평균가(아파트 매매 기준)</p>
                  <div className="sa-di-tiles sa-di-tiles--4">
                    {(results.radiusGroups ?? []).map((group) => (
                      <div key={group.label} className="sa-di-tile">
                        <span className="sa-di-tile__label">{group.label}</span>
                        <span className="sa-di-tile__value">{group.count.toLocaleString()}건</span>
                        <span className="sa-di-tile__label" style={{ marginTop: "0.125rem" }}>{group.avgPrice > 0 ? `평균 ${formatPrice(group.avgPrice)}` : "평균가 미상"}</span>
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
            <span className="sa-di-eyebrow">표본 {Math.min(50, results.transactions.length).toLocaleString()} / 전체 {results.totalCount.toLocaleString()} DEALS</span>
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

      {/* ================================================================ */}
      {/*  [분석 · ANALYSIS] — 위 실데이터(RAW)를 해석한 결과.                 */}
      {/*  결론(시니어 통합 인사이트)을 최상단에 두고 근거→리스크→권고로 위계를  */}
      {/*  세운다. 6개 논리 그룹으로 스토리라인을 구성(SectionDivider 재사용):  */}
      {/*  [시니어]→[수요·인구]→[가격·시세]→[공급 타당성]→[검증]→[보고서].     */}
      {/*  원자료 표(RawDataTables)는 각 그룹 안에 '펼치기 원자료'로 흡수한다.    */}
      {/* ================================================================ */}

      {/* ── 그룹1 [시니어 통합 인사이트] · 결론 우선 ── */}
      <SectionDivider kr="시니어 통합 인사이트" en="ANALYSIS · 결론 우선 해석" />

      {/* 시니어 통합 인사이트 카드 — MarketInterpreter 6키 정밀 내러티브를
          핵심결론(investment_insight)·근거(comparable_analysis·market_overview)·
          리스크(risk_factors)·권고(timing_recommendation)로 구조화(문단 덤프 금지).
          헤더 아래 AI 검증 배지를 인라인 배치해 '결론+검증'을 함께 노출한다.
          senior_insight 부재(use_llm off/미생성) 시 기존 narrative 폴백(무목업). */}
      {report && (() => {
        const si = (report.senior_insight ?? null) as SeniorInsight | null;
        const nar = (report.narrative ?? null) as MarketNarrative | null;
        const hasSenior = !!si && !!(
          si.investment_insight || si.comparable_analysis || si.risk_factors ||
          si.timing_recommendation || si.market_overview || si.price_trend_analysis
        );
        return (
          <div className="sa-di-block">
            <header className="sa-di-block__head" style={{ cursor: "default" }}>
              <span className="sa-di-block__icon" aria-hidden><PenLine className="size-4" /></span>
              <span className="sa-di-block__title">시니어 통합 인사이트</span>
              <span className="sa-di-eyebrow text-[var(--accent-strong)]">SENIOR ANALYSIS</span>
            </header>
            <div className="sa-di-block__body space-y-4">
              {/* 헤더 인라인 AI 검증 — 결론과 함께 검증 verdict를 노출(하단 매몰 방지). */}
              <VerificationBadge
                analysisType="market"
                context={report as unknown as Record<string, unknown>}
                ledgerHash={(report as { ledger_hash?: string })?.ledger_hash}
              />

              {hasSenior && si ? (
                <>
                  {/* 핵심 결론(투자 시사점) — accent 박스로 최상단 강조 */}
                  {si.investment_insight && (
                    <div className="rounded-xl border border-[var(--accent-strong)]/30 bg-[var(--accent-strong)]/5 p-4">
                      <p className="sa-di-eyebrow text-[var(--accent-strong)]">KEY CONCLUSION · 핵심 결론(투자 시사점)</p>
                      <p className="mt-1.5 text-sm font-bold leading-relaxed text-[var(--text-primary)]">{si.investment_insight}</p>
                    </div>
                  )}
                  {/* 근거 | 리스크 2열 */}
                  <div className="grid gap-4 sm:grid-cols-2">
                    {si.comparable_analysis && (
                      <div>
                        <p className="sa-di-eyebrow">EVIDENCE · 근거(실데이터 비교)</p>
                        <p className="mt-1.5 text-sm leading-relaxed text-[var(--text-secondary)]">{si.comparable_analysis}</p>
                      </div>
                    )}
                    {si.risk_factors && (
                      <div>
                        <p className="sa-di-eyebrow" style={{ color: "var(--status-warning)" }}>RISK · 리스크 요인</p>
                        <p className="mt-1.5 text-sm leading-relaxed text-[var(--text-secondary)]">{si.risk_factors}</p>
                      </div>
                    )}
                  </div>
                  {/* 시장 개요 + 가격 추이 — 부연 근거 */}
                  {(si.market_overview || si.price_trend_analysis) && (
                    <div className="grid gap-4 sm:grid-cols-2">
                      {si.market_overview && (
                        <div>
                          <p className="sa-di-eyebrow">MARKET · 시장 개요</p>
                          <p className="mt-1.5 text-sm leading-relaxed text-[var(--text-secondary)]">{si.market_overview}</p>
                        </div>
                      )}
                      {si.price_trend_analysis && (
                        <div>
                          <p className="sa-di-eyebrow">PRICE TREND · 가격 추이</p>
                          <p className="mt-1.5 text-sm leading-relaxed text-[var(--text-secondary)]">{si.price_trend_analysis}</p>
                        </div>
                      )}
                    </div>
                  )}
                  {/* 권고(매수·개발 적기) — accent 박스 */}
                  {si.timing_recommendation && (
                    <div className="rounded-xl border border-[var(--line-strong)] bg-[var(--surface-soft)] p-4">
                      <p className="sa-di-eyebrow">RECOMMENDATION · 매수·개발 권고(적기)</p>
                      <p className="mt-1.5 text-sm leading-relaxed text-[var(--text-primary)]">{si.timing_recommendation}</p>
                    </div>
                  )}
                </>
              ) : (
                /* 폴백: 기존 AI 내러티브(요약/기회/리스크/가격동향/타겟) — senior_insight 미생성 시(무목업). */
                <>
                  <div>
                    <p className="sa-di-eyebrow">MARKET SUMMARY · 시장 요약</p>
                    <p className="mt-1.5 text-sm leading-relaxed text-[var(--text-secondary)]">{nar?.summary || "-"}</p>
                  </div>
                  <div className="grid gap-4 sm:grid-cols-2">
                    <div>
                      <p className="sa-di-eyebrow">OPPORTUNITIES · 기회 요인</p>
                      <ul className="mt-1.5 space-y-0.5 text-xs text-[var(--text-secondary)]">
                        {(nar?.opportunities || []).map((o: string, i: number) => <li key={i}>· {o}</li>)}
                      </ul>
                    </div>
                    <div>
                      <p className="sa-di-eyebrow" style={{ color: "var(--status-warning)" }}>RISKS · 리스크 요인</p>
                      <ul className="mt-1.5 space-y-0.5 text-xs text-[var(--text-secondary)]">
                        {(nar?.risks || []).map((r: string, i: number) => <li key={i}>· {r}</li>)}
                      </ul>
                    </div>
                  </div>
                  {nar?.price_trend && (
                    <div>
                      <p className="sa-di-eyebrow">PRICE TREND · 가격 동향</p>
                      <p className="mt-1.5 text-sm leading-relaxed text-[var(--text-secondary)]">{nar.price_trend}</p>
                    </div>
                  )}
                  {nar?.target_persona && (
                    <div className="rounded-xl border border-[var(--accent-strong)]/30 bg-[var(--accent-strong)]/5 p-4">
                      <p className="sa-di-eyebrow text-[var(--accent-strong)]">TARGET PERSONA · 추천 타겟 고객층</p>
                      <p className="mt-1 text-sm font-bold leading-relaxed text-[var(--text-primary)]">{nar.target_persona}</p>
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        );
      })()}

      {/* 시니어 금융전문가 자문 — 백엔드 senior_consultation 소비(다도메인 verdict·근거). ★정직:
          시장보고서 경로는 총사업비만 전달(NOI·DSCR·자기자본 미합성)이라 통상 프레임워크·근거 중심.
          자문 없으면 미렌더(본 분석을 가리지 않음). */}
      {report && (
        <SeniorVerdictCard
          consultation={(report as { senior_consultation?: SeniorConsultation }).senior_consultation}
          title="시니어 금융 자문(프레임워크·근거)"
        />
      )}

      {/* ── 그룹2 [수요·인구] · 인구·가구·소득 차트 + 인구이동망 + 타겟 프로파일 ── */}
      {report?.demographics && (
        <>
          <SectionDivider kr="수요·인구" en="DEMAND · 인구·가구·소득" />

          {/* 인구·가구·소득 시각화(Recharts, 차트=기본). 동일 데이터의 세부 표는 아래 '원자료 표'로 강등(이원화 제거). */}
          <DemographicPanel data={report.demographics} unitMix={report.unit_mix_recommendation} />

          {/* 인구 이동망 — KOSIS「시군구별 이동자수」로 대상 권역의 총전입·총전출·순이동(유입세)을 표시.
              ★배선 수정(정본·보존): 실데이터(data_source==='live')면 전입/전출/순이동을 표시하고 분석범위(권역)를
              라벨한다. OD 출발지 Top(권역 흐름도)은 KOSIS 단일분류표에 미제공이라 옵션(있을 때만)으로 두고,
              없으면 행안부 OD 연동 예정을 정직하게 안내한다(가짜 금지). RawData(표)의 순이동 타일 중복은 제거. */}
          {report.demographics.migration && (() => {
            const mig = report.demographics.migration;
            const inflow = mig.total_inflow ?? 0;
            const outflow = mig.total_outflow ?? 0;
            const net = mig.net_migration ?? 0;
            const hasFlow = mig.data_source === "live" && (inflow > 0 || outflow > 0);
            const hasOD = (mig.top_inflow_regions?.length ?? 0) > 0;
            const scopeRegion = mig.region_name || report?.address?.split(" ").find((t: string) => /(구|시|군)$/.test(t)) || null;
            return (
              <div className="sa-di-block">
                <header className="sa-di-block__head" style={{ cursor: "default" }}>
                  <span className="sa-di-block__icon" aria-hidden><Compass className="size-3.5" /></span>
                  <span className="sa-di-block__title">인구 이동망 (전입·전출)</span>
                  {hasFlow ? (
                    <span className="sa-di-eyebrow">MIGRATION</span>
                  ) : (
                    <DataSourceBadge source="unavailable" />
                  )}
                </header>
                <div className="sa-di-block__body">
                  {/* 이동망 분석범위(권역) — 대상 시군구·기준연도·데이터 출처 정직 표기 */}
                  {(scopeRegion || hasFlow) && (
                    <p className="mb-2 text-xs text-[var(--text-tertiary)]">
                      분석범위(권역): <strong className="text-[var(--text-secondary)]">{scopeRegion ?? "—"}</strong>
                      {mig.year ? ` · ${mig.year}년 기준` : ""} · 출처 KOSIS 시군구별 이동자수
                    </p>
                  )}
                  {hasFlow ? (
                    <>
                      <div className="sa-di-tiles sa-di-tiles--3">
                        <div className="sa-di-tile">
                          <span className="sa-di-tile__label">전입</span>
                          <span className="sa-di-tile__value">{inflow.toLocaleString()}명</span>
                        </div>
                        <div className="sa-di-tile">
                          <span className="sa-di-tile__label">전출</span>
                          <span className="sa-di-tile__value">{outflow.toLocaleString()}명</span>
                        </div>
                        <div className="sa-di-tile">
                          <span className="sa-di-tile__label">순이동</span>
                          <span
                            className="sa-di-tile__value"
                            style={{ color: net > 0 ? "var(--status-success)" : net < 0 ? "var(--status-error)" : undefined }}
                          >
                            {net > 0 ? "+" : ""}{net.toLocaleString()}명
                          </span>
                        </div>
                      </div>
                      {hasOD ? (
                        <ul className="mt-3 space-y-1.5 text-sm text-[var(--text-secondary)]">
                          {mig.top_inflow_regions!.map((reg: { name?: string; ratio?: number; count?: number }, i: number) => (
                            <li key={i} className="flex justify-between border-b border-[var(--line-subtle)] pb-1.5">
                              <span>{reg.name}</span>
                              <span className="font-bold">{reg.ratio}% ({(reg.count ?? 0).toLocaleString()}명)</span>
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <p className="sa-di-empty mt-2">전출지별 유입 Top(OD 출발지)·권역 흐름도는 KOSIS 시군구 이동표에 미제공 — 행정안전부 OD 마이크로데이터 연동 시 표시됩니다(현재 순이동세만 실데이터).</p>
                      )}
                      {/* 권역도(순이동 코로플레스) — 대상 시군구+주변 시군구(같은 시도)의 순이동을 발산색 지도로.
                          방향 화살표(OD)는 불가하나, 권역 전체의 순유입/순유출 분포를 시각화한다. 지연로드 토글. */}
                      <div className="mt-3 rounded-xl border border-[var(--line)] bg-[var(--surface)] p-3">
                        <button
                          type="button"
                          onClick={() => setShowMigrationMap((v) => !v)}
                          className="flex w-full items-center justify-between gap-2 text-left text-sm font-bold text-[var(--text-primary)]"
                        >
                          <span className="inline-flex items-center gap-1.5"><Compass className="size-4" aria-hidden />권역 순이동 지도 <span className="ml-1 text-xs font-normal text-[var(--text-hint)]">시군구 발산 코로플레스</span></span>
                          <span className="text-[var(--accent-strong)]">{showMigrationMap ? "▾ 닫기" : "▸ 보기"}</span>
                        </button>
                        {showMigrationMap && (
                          <div className="mt-3">
                            <MigrationRegionMap address={address} bcode={mapBcode} />
                          </div>
                        )}
                      </div>
                    </>
                  ) : (
                    <p className="sa-di-empty">인구이동(OD) 데이터는 행정안전부/KOSIS 연동 예정입니다. (SGIS 미제공·KOSIS 키/시군구 미확정 — 가짜 수치 대신 정직 표기)</p>
                  )}
                </div>
              </div>
            );
          })()}

          {/* 실데이터 타겟 고객층 프로파일(5축) — 마이크로 타겟팅(K-Atlas 잠금 데드섹션)을 대체.
              주력 연령·가구·소득분위·상권특성·입지를 인구·소득 실데이터에서 도출해 타일로 표시.
              신용·카드소비 등 초정밀 금융은 잠금 오버레이 없이 'PREMIUM 제휴 예정' 1줄로 강등(정직·무목업). */}
          {(() => {
            const tp = (report.target_profile ?? null) as TargetProfile | null;
            const tpRec = tp as Record<string, unknown> | null;
            // 알려진 축 키 → 한국어 라벨(백엔드 키 변형 허용, 미지정 키는 키 그대로 노출).
            const AXIS_LABELS: Record<string, string> = {
              primary_age: "주력 연령", age: "주력 연령",
              primary_household: "주력 가구", household: "주력 가구",
              income_level: "소득 분위", income_tier: "소득 분위", income_quintile: "소득 분위", income: "소득 분위",
              commercial: "상권 특성", commercial_type: "상권 특성",
              location: "입지", location_type: "입지",
            };
            // 각 축은 문자열 또는 {label,value,detail,data_source} 객체 — 둘 다 방어적으로 정규화한다.
            //   축별 data_source도 함께 캡처해 배지를 실제 출처로 계산한다(가짜 'live' 오표시 방지).
            const axes = tpRec
              ? Object.entries(tpRec)
                  .filter(([k]) => k !== "summary" && k !== "data_source" && k !== "premium")
                  .map(([k, v]) => {
                    const label = AXIS_LABELS[k] || k;
                    if (typeof v === "string") return { key: k, label, value: v, detail: undefined as string | undefined, src: undefined as string | undefined, tooltip: undefined as string | undefined };
                    const o = (v && typeof v === "object" ? v : {}) as {
                      label?: string; value?: string; detail?: string; data_source?: string;
                      // 상권(E) 축 전용 — 백엔드가 추가 배선 중인 옵셔널 필드(부재 시 미표기).
                      vitality_score?: number; grade_legend?: string;
                    };
                    // 상권 특성 축은 활력점수(vitality_score)를 detail에 부연하고, 등급 범례
                    //   (grade_legend)를 툴팁(title)으로 노출한다 — 둘 다 옵셔널 소비(부재해도 정상 렌더).
                    let detail = o.detail;
                    let tooltip: string | undefined;
                    if (k === "commercial") {
                      const scoreText = typeof o.vitality_score === "number" ? `활력점수 ${o.vitality_score}` : undefined;
                      detail = [o.detail, scoreText].filter(Boolean).join(" · ") || o.detail;
                      tooltip = o.grade_legend;
                    }
                    return { key: k, label: o.label || label, value: o.value, detail, src: o.data_source, tooltip };
                  })
                  .filter((a) => !!a.value)
              : [];
            const hasAxes = axes.length > 0;
            // 배지 출처: 렌더되는 축들의 data_source 중 가장 보수적인 값(하나라도 fallback이면 fallback).
            //   ★백엔드 target_profile엔 최상위 data_source가 없으므로 tp.data_source(undefined)를
            //   'live'로 폴백하면 mock/fallback도 초록으로 오표시된다 → 축별 출처로 정직 계산.
            const badgeSrc = !hasAxes
              ? "unavailable"
              : axes.some((a) => a.src === "fallback") ? "fallback"
              : axes.every((a) => a.src === "live" || a.src == null) ? "live"
              : "fallback";
            return (
              <div className="sa-di-block">
                <header className="sa-di-block__head" style={{ cursor: "default" }}>
                  <span className="sa-di-block__icon" aria-hidden><Target className="size-3.5" /></span>
                  <span className="sa-di-block__title">타겟 고객층 프로파일</span>
                  <DataSourceBadge source={badgeSrc} />
                </header>
                <div className="sa-di-block__body">
                  {hasAxes ? (
                    <>
                      <div className={`sa-di-tiles${axes.length >= 4 ? " sa-di-tiles--4" : axes.length === 3 ? " sa-di-tiles--3" : axes.length === 2 ? " sa-di-tiles--2" : ""}`}>
                        {axes.map((a) => (
                          <div key={a.key} className="sa-di-tile" title={a.tooltip}>
                            <span className="sa-di-tile__label">{a.label}</span>
                            <span className="sa-di-tile__value">{a.value}</span>
                            {a.detail ? (
                              <span className="sa-di-tile__label" style={{ marginTop: "0.125rem" }}>{a.detail}</span>
                            ) : null}
                          </div>
                        ))}
                      </div>
                      {tp?.summary ? (
                        <p className="mt-3 text-sm leading-relaxed text-[var(--text-secondary)]">{tp.summary}</p>
                      ) : null}
                    </>
                  ) : (
                    <p className="sa-di-empty">인구·가구·소득 실데이터로 주력 수요층(연령·가구·소득분위·상권·입지)을 산출합니다. 현재 산출된 프로파일이 없습니다(인구/소득 분석 선택 시 표시).</p>
                  )}
                  <p className="mt-3 text-[11px] text-[var(--text-hint)]">※ 신용점수·카드소비 등 초정밀 금융 데이터(K-Atlas)는 PREMIUM 제휴 연동 예정입니다.</p>
                </div>
              </div>
            );
          })()}

          {/* 인구·소득 원자료 표(펼치기) — 위 차트와 동일 데이터의 세부 표를 한 곳에만(이원화 제거). */}
          {(report.raw_data?.population || report.raw_data?.income) ? (
            <CollapsibleRaw title="인구·소득 원자료 표 (세부)">
              <RawDataTables raw={report.raw_data as RawData | undefined} section="demand" />
            </CollapsibleRaw>
          ) : null}
        </>
      )}

      {/* ── 그룹3 [가격·시세] · AI 시세 + 적정 분양가 + 매매 원자료(인접 배치) ── */}
      {address && (
        <>
          <SectionDivider kr="가격·시세" en="PRICE · 시세·분양가" />

          {/* AI 시세 추정 — 실거래 평당가 가중평균 → 84㎡ 기준 추정(해석값). */}
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
                    <MetricTile label="추정 시세 (84㎡)" value={formatCurrencyKRW(results.avm.estimated_price)} accent />
                    <MetricTile label="㎡당 시세" value={formatCurrencyKRW(results.avm.price_per_sqm)} />
                    <MetricTile
                      label="표본 신뢰도(표본수·분산 기반)"
                      value={`${(results.avm.confidence_score * 100).toFixed(0)}%`}
                      detail={`표본 ${results.avm.sample_count.toLocaleString()}건 · 가격변동계수 ${results.avm.price_cv_percent}%`}
                    />
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

          {/* 적정 분양가 밴드(M3) — 수요측 지불여력을 공급측 타당성과 결합. */}
          {report?.pricing_band && <PricingBandPanel data={report.pricing_band} />}

          {/* 시세 추이 — 아파트 평당가 월별 추이(실거래·전월대비). recharts LineChart(DemographicPanel과 동일 라이브러리).
              기간 칩(3/12/24개월): 3=report.trend_series 그대로(무변경 기본), 12/24=경량 GET /market/trend
              (보고서 전체 재생성 없이 아파트 매매 월별 평당가만 조회 — lib/market-trend-light.ts 순수 헬퍼). */}
          {report && (() => {
            const baseTrend = mapReportTrendSeries(report.raw_data?.real_estate?.trend_series);
            const lightTrend = mapLightTrend(trendLight?.trend);
            const trend = selectTrendChartPoints(trendMonths, baseTrend, lightTrend);
            const statusMsg = trendStatusMessage({
              months: trendMonths, loading: trendLightLoading, error: trendLightError, pointsCount: trend.length,
            });
            const last = trend[trend.length - 1];
            // Y축 범위 — recharts 기본(auto)은 0부터 시작해 실측 변동폭이 작아 보일 수 있다.
            //   실측 최소~최대에 10% 여백만 둬 "데이터가 주인공"이 되도록(dataviz 원칙).
            const values = trend.map((t) => t.perPyeong);
            const minV = values.length ? Math.min(...values) : 0;
            const maxV = values.length ? Math.max(...values) : 0;
            const pad = Math.max(1, (maxV - minV) * 0.1);
            const yDomain: [number, number] = [Math.max(0, Math.floor(minV - pad)), Math.ceil(maxV + pad)];
            return (
              <div className="sa-di-block">
                <header className="sa-di-block__head" style={{ cursor: "default" }}>
                  <span className="sa-di-block__icon" aria-hidden>₩</span>
                  <span className="sa-di-block__title">시세 추이 (아파트 평당가)</span>
                  <span className="sa-di-eyebrow">TREND · 월별</span>
                </header>
                <div className="sa-di-block__body">
                  <div className="sa-seg mb-3 w-fit" role="tablist" aria-label="시세추이 조회 기간">
                    {([3, 12, 24] as const).map((m) => (
                      <button
                        key={m}
                        type="button"
                        role="tab"
                        aria-selected={trendMonths === m}
                        data-active={trendMonths === m}
                        onClick={() => handleTrendMonthsChange(m)}
                        className="sa-seg__item"
                      >
                        {m}개월
                      </button>
                    ))}
                  </div>
                  {statusMsg ? (
                    <p className={trendMonths !== 3 && trendLightError ? "text-sm font-semibold text-[var(--status-error)]" : "sa-di-empty"}>
                      {statusMsg}
                    </p>
                  ) : (
                    <>
                      <ResponsiveContainer width="100%" height={200}>
                        <LineChart data={trend} margin={{ left: 8, right: 16, top: 8, bottom: 4 }}>
                          <CartesianGrid stroke="var(--line-subtle)" strokeDasharray="3 3" vertical={false} />
                          <XAxis dataKey="ym" tickFormatter={(v) => formatYm(String(v))} tick={{ fontSize: 11 }} />
                          <YAxis domain={yDomain} tick={{ fontSize: 11 }} width={64} />
                          <Tooltip formatter={(v) => [`${Number(v).toLocaleString()}만원/평`, "평당가(전용)"]} labelFormatter={(v) => formatYm(String(v))} />
                          <Line type="monotone" dataKey="perPyeong" stroke="var(--accent-strong)" strokeWidth={2} dot />
                        </LineChart>
                      </ResponsiveContainer>
                      <p className="mt-2 text-[11px] text-[var(--text-hint)]">
                        ※ 국토부 아파트 실거래 평당가(전용 기준) 월별 추이({trendMonths}개월{trendMonths !== 3 ? (trendLight?.cached ? " · 캐시" : "") : ""}).
                        최근 {formatYm(last.ym)} 평당 {last.perPyeong.toLocaleString()}만원
                        {typeof last.mom === "number" ? ` (전월대비 ${last.mom > 0 ? "+" : ""}${last.mom}%)` : ""}.
                      </p>
                    </>
                  )}
                </div>
              </div>
            );
          })()}

          {/* 경쟁 단지 비교 — 주변 아파트 실거래를 단지명별 집계(거래건수 상위 8). 빈 배열이면 정직 표기. */}
          {report?.raw_data?.real_estate && (() => {
            const comps = (report.raw_data.real_estate.competitor_complexes ?? []) as Array<{
              name?: string; deal_count?: number; avg_per_pyeong_manwon?: number | null;
              price_basis?: string; recent_deal_ym?: string | null; build_year?: number | null;
            }>;
            return (
              <div className="sa-di-block">
                <header className="sa-di-block__head" style={{ cursor: "default" }}>
                  <span className="sa-di-block__icon" aria-hidden>▦</span>
                  <span className="sa-di-block__title">경쟁 단지 비교</span>
                  <span className="sa-di-eyebrow">COMPETITORS · 실거래 집계</span>
                </header>
                <div className="sa-di-block__body">
                  {comps.length > 0 ? (
                    <>
                      <div className="overflow-x-auto">
                        <table className="sa-di-table">
                          <thead>
                            <tr>
                              <th>단지명</th>
                              <th className="sa-di-num">거래건수</th>
                              <th className="sa-di-num">평당가(전용)</th>
                              <th className="sa-di-num">최근 거래월</th>
                              <th className="sa-di-num">준공</th>
                            </tr>
                          </thead>
                          <tbody>
                            {comps.map((c, i) => (
                              <tr key={`${c.name ?? ""}-${i}`}>
                                <td style={{ fontWeight: 600 }}>{c.name || "—"}</td>
                                <td className="sa-di-num" style={{ color: "var(--text-secondary)" }}>{(c.deal_count ?? 0).toLocaleString()}건</td>
                                <td className="sa-di-num">{typeof c.avg_per_pyeong_manwon === "number" ? `${c.avg_per_pyeong_manwon.toLocaleString()}만원/평` : "—"}</td>
                                <td className="sa-di-num" style={{ color: "var(--text-secondary)" }}>{c.recent_deal_ym || "—"}</td>
                                <td className="sa-di-num" style={{ color: "var(--text-secondary)" }}>{c.build_year ? `${c.build_year}년` : "—"}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                      <p className="mt-2 text-[11px] text-[var(--text-hint)]">
                        ※ 주변 아파트 실거래를 단지명별로 집계한 경쟁 단지(거래건수 상위 {comps.length}개). 평당가는 전용면적 기준 거래액가중 평균입니다.
                      </p>
                    </>
                  ) : (
                    <p className="sa-di-empty">비교 가능한 경쟁 단지 실거래가 없습니다.</p>
                  )}
                </div>
              </div>
            );
          })()}

          {/* 분양 전략 요약 — result에 실재하는 신호(시세방향·경쟁밀도·수요유입·가격수용성·상품전략)만
              결정론적으로 조합(신규 LLM 호출 없음·날조 없음). 신호가 2개 미만이면 미렌더(정직). */}
          {(() => {
            const re = report?.raw_data?.real_estate;
            const signals: Array<{ label: string; value: string; detail?: string }> = [];

            // ① 시세 방향 — 추이 마지막 전월대비(mom_pct) 부호.
            const trendPts = ((re?.trend_series ?? []) as Array<{ mom_pct?: number | null }>)
              .filter((t) => typeof t.mom_pct === "number");
            if (trendPts.length > 0) {
              const mom = trendPts[trendPts.length - 1].mom_pct as number;
              signals.push({
                label: "시세 방향",
                value: mom > 0 ? "상승세" : mom < 0 ? "조정세" : "보합",
                detail: `최근 전월대비 ${mom > 0 ? "+" : ""}${mom}%`,
              });
            }

            // ② 경쟁 밀도 — 경쟁 단지 수·총 거래건수.
            const comps = (re?.competitor_complexes ?? []) as Array<{ deal_count?: number }>;
            if (comps.length > 0) {
              const totalDeals = comps.reduce((a, c) => a + (c.deal_count ?? 0), 0);
              signals.push({
                label: "경쟁 밀도",
                value: comps.length >= 5 ? "경쟁 밀집" : comps.length >= 2 ? "경쟁 보통" : "경쟁 희박",
                detail: `${comps.length}개 단지·실거래 ${totalDeals.toLocaleString()}건`,
              });
            }

            // ③ 수요 유입 — 순이동(전입-전출). 미확보(unavailable/mock)는 제외(정직).
            const mig = report?.demographics?.migration as
              | { net_migration?: number | null; data_source?: string | null } | undefined;
            const migSrc = String(mig?.data_source ?? "").toLowerCase();
            if (mig && typeof mig.net_migration === "number" && migSrc !== "" && migSrc !== "unavailable" && migSrc !== "mock") {
              const net = mig.net_migration;
              signals.push({
                label: "수요 유입",
                value: net > 0 ? "순유입(수요 유입)" : net < 0 ? "순유출(수요 유출)" : "유입·유출 균형",
                detail: `순이동 ${net > 0 ? "+" : ""}${net.toLocaleString()}명`,
              });
            }

            // ④ 가격 수용성 — 적정분양가 지불여력 판정.
            const verdict = report?.pricing_band?.affordability_verdict as string | undefined;
            const verdictLabel: Record<string, string> = {
              within_conservative: "가격 수용성 높음(보수 밴드 내)",
              within_optimistic: "가격 수용성 보통(낙관 밴드 내)",
              over_band: "가격 부담(미분양 위험 주의)",
            };
            if (verdict && verdict !== "unavailable" && verdictLabel[verdict]) {
              signals.push({ label: "가격 수용성", value: verdictLabel[verdict] });
            }

            // ⑤ 상품 전략 — 수요기반 권장 주력 평형.
            const um = report?.unit_mix_recommendation as
              | { dominant_band?: string; data_source?: string | null } | undefined;
            const umSrc = String(um?.data_source ?? "").toLowerCase();
            if (um?.dominant_band && umSrc !== "" && umSrc !== "unavailable" && umSrc !== "mock") {
              signals.push({ label: "상품 전략", value: `주력 ${um.dominant_band} 권장`, detail: "수요(가구원수) 기반" });
            }

            if (signals.length < 2) return null; // 신호 부족 시 미렌더(무목업 — 억지 요약 금지).
            return (
              <div className="sa-di-block">
                <header className="sa-di-block__head" style={{ cursor: "default" }}>
                  <span className="sa-di-block__icon" aria-hidden>◆</span>
                  <span className="sa-di-block__title">분양 전략 요약</span>
                  <span className="sa-di-eyebrow">STRATEGY · 실데이터 신호</span>
                </header>
                <div className="sa-di-block__body">
                  <ul className="flex flex-col gap-2">
                    {signals.map((s) => (
                      <li key={s.label} className="flex flex-wrap items-baseline gap-2 text-sm">
                        <span className="min-w-[72px] font-bold text-[var(--text-tertiary)]">{s.label}</span>
                        <span className="font-black text-[var(--text-primary)]">{s.value}</span>
                        {s.detail ? <span className="text-[11px] text-[var(--text-hint)]">{s.detail}</span> : null}
                      </li>
                    ))}
                  </ul>
                  <p className="mt-3 text-[11px] text-[var(--text-hint)]">※ 수집된 실데이터 신호만 결정론적으로 요약한 것으로, AI 서술이 아닙니다. 상세 전략 서술은 위 시니어 인사이트를 참고하세요.</p>
                </div>
              </div>
            );
          })()}

          {/* 유형별 매매·전월세·시세추이 원자료 표(펼치기) — 가격 근거 데이터를 한 곳에 인접 배치. */}
          {report?.raw_data?.real_estate ? (
            <CollapsibleRaw title="유형별 매매·전월세·시세추이 원자료 표">
              <RawDataTables raw={report.raw_data as RawData | undefined} section="real_estate" />
            </CollapsibleRaw>
          ) : null}
        </>
      )}

      {/* ── 그룹4 [공급 타당성] · 통합면적 고지 + AI 사업 타당성 엔진(Feasibility) ── */}
      {(report?.feasibility_analysis || report?.integrated) && (
        <>
          <SectionDivider kr="공급 타당성" en="SUPPLY · 사업 타당성" />
          {/* 다필지 통합 고지 — 보고서/타당성이 N필지 통합면적 기준임을 명시(근거·투명성). */}
          {report?.integrated && <IntegratedParcelsBadge integrated={report.integrated} />}
          {report?.feasibility_analysis && (
            <FeasibilityDashboard
              data={report.feasibility_analysis}
              zoneType={report.zone_type ?? undefined}
            />
          )}
        </>
      )}

      {/* ── 그룹5 [검증] · 전문가 패널 심화 검증(자동 AI 검증 배지는 결론 카드에 인라인) ── */}
      {report && (
        <>
          <SectionDivider kr="검증" en="VERIFY · 전문가 패널" />
          <ExpertPanelCard analysisType="market" address={address} context={report as unknown as Record<string, unknown>} />
        </>
      )}

      {/* ── 그룹6 [보고서] · 단일 다운로드 바(미리보기+AI토글+PDF/PPT/DOCX 통합) ── */}
      {address && (
        <>
          <SectionDivider kr="보고서" en="REPORT · 다운로드" />
          <ReportActionsBar
            genState={genState}
            useLlm={useLlm}
            onUseLlmChange={setUseLlm}
            onGenerate={generateReport}
            onDownload={downloadReport}
          />
        </>
      )}
      {/* 분석 히스토리 — 원장 조회(옵셔널 소비). 입력변동 감지 시 재분석 제안(자동실행 없음).
          ★실행 확정 주소(runAddress)가 아니라 입력 후보(SSOT inputAddress)까지 폴백한다 —
          명시실행 계약상 리로드 직후 runAddress 는 비어 있는데, 그때야말로 사용자가
          "이전 분석"을 보러 온 순간이기 때문(W5 실동선 검증에서 적발된 소실 결함).
          재분석은 명시실행 계약을 그대로 태운다: runAddress 미확정이면 pendingReport
          플래그로 기존 일괄분석 플로우를 재사용(자동 아님 — 버튼 클릭에만 반응). */}
      {(address || inputAddress) && (
        <AnalysisHistoryCard
          analysisType="market_report"
          address={address || inputAddress}
          pnu={mapPnu || null}
          currentSignatureParts={historySignatureParts}
          onReanalyze={() => {
            if (!address && inputAddress) {
              setRunAddress(inputAddress);
              setPendingReport(true);
              return;
            }
            void generateReport();
          }}
          reanalyzing={genState === "report"}
          refreshSignal={historyRefreshTick}
        />
      )}
    </section>
  );
}
