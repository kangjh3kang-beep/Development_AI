"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Lock } from "lucide-react";
import { useParams, usePathname, useRouter } from "next/navigation";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { effectiveLandAreaSqm } from "@/lib/site-area";
import { appendLedger } from "@/lib/analysis-ledger";
import { currentUserId } from "@/lib/projectSync";
import { useProjectStore as useProjectListStore } from "@/store/useProjectStore";
import { useUiReset } from "@/store/useUiReset";
import { apiClient } from "@/lib/api-client";
import { parcelDataToRows, shouldSendParcels } from "@/lib/parcel-rows";
import { GlobalAddressSearch, type AddressEntry } from "@/components/common/GlobalAddressSearch";
import { PipelineResultDetail } from "./PipelineResultDetail";
import { ProjectCompareView } from "./ProjectCompareView";
import { SiteAnalysisDetail } from "./SiteAnalysisDetail";
import { writePreCheckHandoff } from "@/components/precheck/handoff";

// 대시보드(비프로젝트) 체험 모드에서 노출/실행 가능한 단계 — 부지분석 + 약식 수지만.
// 나머지(설계·공사비·세무·ESG·보고서)는 잠금 → 프로젝트 생성 시 제공(구독 전환 관문).
const TEASER_STAGES = new Set(["site_analysis", "feasibility"]);

/* ── Types ── */

interface PipelineStageStatus {
  stage: string;
  status: "pending" | "running" | "completed" | "failed" | "skipped";
  duration_ms: number | null;
  data: Record<string, unknown>;
  error: string | null;
}

interface PipelineRunResponse {
  pipeline_id: string;
  project_id: string;
  status: string;
  stages: PipelineStageStatus[];
  summary: Record<string, Record<string, unknown>>;
}

/* ── History entry stored in localStorage ── */

interface HistoryEntry {
  id: string;
  address: string;
  completedAt: string;
  result: PipelineRunResponse;
  addresses?: string[];  // 다필지 주소 — 재진입 시 필지 구획도/지도 재조회용(개별 좌표는 라이브 재조회)
  projectId?: string;   // 프로젝트별 이력 격리(프로젝트 모드에서만 태깅)
  mode?: "quick" | "project";  // 실행 모드 — 대시보드(quick) vs 프로젝트(project). 이력 분류 기준.
}

const HISTORY_KEY = "propai_pipeline_history";
const MAX_HISTORY = 20;   // 전역 보관 확대(프로젝트별 필터링 후 표시)

// ★분석이력은 계정별로 분리한다(propai_pipeline_history__{userId}). 단일 공유키였을 때
//  로그아웃 와이프로 본인 이력이 사라지고 다른 계정에 노출되던 문제를 근본 차단.
//  키 자체가 격리되므로 와이프 없이도 본인 이력은 영구 보존되고 삭제는 본인만 영향.
export function pipelineHistoryKey(): string {
  return `${HISTORY_KEY}__${currentUserId()}`;
}

function loadHistory(): HistoryEntry[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(pipelineHistoryKey());
    return raw ? (JSON.parse(raw) as HistoryEntry[]) : [];
  } catch {
    return [];
  }
}

// 무거운 분석결과(몬테카를로 샘플·현금흐름·민감도·실거래 수백건)는 localStorage 용량을 폭증시켜
// 저장 실패→이력 재진입 시 사업개요 상세가 사라지는 원인. 표시에 불필요한 대용량 필드만 솎아낸다.
function trimEntry(entry: HistoryEntry): HistoryEntry {
  try {
    const r = JSON.parse(JSON.stringify(entry.result)) as PipelineRunResponse;
    for (const s of r.stages ?? []) {
      const d = s.data as Record<string, unknown> | undefined;
      if (!d) continue;
      delete d.monte_carlo; delete d.cashflow; delete d.sensitivity;  // 복합객체(표시 안 함)
      const pricing = d.pricing as Record<string, unknown> | undefined;
      if (pricing && Array.isArray(pricing.nearby_transactions)) {
        pricing.nearby_transactions = (pricing.nearby_transactions as unknown[]).slice(0, 8); // 실거래 8건만
      }
      if (Array.isArray(d.nearby_amenities)) d.nearby_amenities = (d.nearby_amenities as unknown[]).slice(0, 12);
    }
    return { ...entry, result: r };
  } catch {
    return entry;
  }
}

function saveHistory(entries: HistoryEntry[]) {
  if (typeof window === "undefined") return;
  const key = pipelineHistoryKey();
  // 최신 우선 보존 + 무거운 필드 솎기 + 용량 초과 시 오래된 항목부터 제거하며 재시도(저장 실패=상세 유실 방지).
  let list = entries.slice(0, MAX_HISTORY).map(trimEntry);
  for (let i = 0; i < MAX_HISTORY; i++) {
    try {
      localStorage.setItem(key, JSON.stringify(list));
      return;
    } catch {
      if (list.length > 1) { list = list.slice(0, list.length - 1); continue; }
      return; // 1개도 못 넣으면 포기(드문 경우)
    }
  }
}

/* ── 비회원(미로그인) 브라우저 기반 무료 1회 게이트 ── */
const GUEST_KEY = "propai_guest_analysis_count";
const GUEST_FREE_QUOTA = 1;

function isGuest(): boolean {
  // 로그인 토큰이 없으면 비회원으로 간주
  if (typeof window === "undefined") return false;
  return !(localStorage.getItem("propai_access_token") || "").trim();
}
function guestUsed(): number {
  if (typeof window === "undefined") return 0;
  return Number(localStorage.getItem(GUEST_KEY) || 0);
}
function bumpGuest() {
  if (typeof window === "undefined") return;
  localStorage.setItem(GUEST_KEY, String(guestUsed() + 1));
}

/* ── Constants ── */

const STAGE_LABELS: Record<string, string> = {
  site_analysis: "부지분석",
  design: "건축설계",
  cost: "공사비",
  feasibility: "수지분석",
  tax: "세금계산",
  esg: "ESG/탄소",
  report: "통합보고서",
};

const STAGE_NUMBERS: Record<string, string> = {
  site_analysis: "\u2460",
  design: "\u2461",
  cost: "\u2462",
  feasibility: "\u2463",
  tax: "\u2464",
  esg: "\u2465",
  report: "\u2466",
};

const FIELD_LABELS: Record<string, string> = {
  // site_analysis
  zone_type: "용도지역",
  land_area_sqm: "대지면적(m²)",
  max_bcr: "법정 최대 건폐율(%)",
  max_far: "법정 최대 용적률(%)",
  official_land_price: "공시지가(원)",
  pnu_codes: "PNU 코드",
  address: "주소",
  estimated_value: "추정가치(원)",
  building_info: "기존 건축물 정보",
  coordinates: "좌표",

  // design
  building_type: "건축물 용도",
  total_gfa_sqm: "연면적(m²)",
  building_area_sqm: "건축면적(m²)",
  floor_count_above: "지상 층수",
  floor_count_below: "지하 층수",
  unit_count: "세대수",
  bcr: "적용 건폐율(%)",
  far: "적용 용적률(%)",
  bcr_used_pct: "적용 건폐율(%)",
  far_used_pct: "적용 용적률(%)",
  compliance: "법규검토결과",
  floor_count: "총 층수",

  // cost
  total_construction_cost: "총공사비",
  direct_cost: "직접공사비",
  indirect_cost: "간접공사비",
  cost_per_sqm: "평당공사비",
  duration_months: "예상 공기(개월)",

  // feasibility (약식 수지분석)
  land_cost: "토지비",
  land_cost_source: "토지비 산정근거",
  construction_cost: "직접공사비",
  general_expense_won: "일반사업비(소프트코스트)",
  finance_cost_won: "금융비",
  breakeven_sale_rate_pct: "손익분기 분양률(%)",
  roe_pct: "자기자본수익률 ROE(%)",
  project_months: "사업기간(개월)",
  total_project_cost: "총 사업비",
  total_revenue: "총 분양수입",
  net_profit: "순이익",
  avg_sale_price_per_pyeong: "평당 분양가",
  sale_price_source: "분양가 산정근거",
  sale_price_confidence: "분양가 신뢰도(%)",
  total_revenue_won: "총 예상 분양수입",
  total_cost_won: "총 투자비용",
  net_profit_won: "순이익(원)",
  profit_rate_pct: "예상 수익률(%)",
  npv: "순현재가치(NPV)",
  irr: "내부수익률(IRR)",
  grade: "사업성 등급",

  // tax
  acquisition_tax: "취득세",
  property_tax: "재산세",
  comprehensive_real_estate_tax: "종합부동산세",
  corporate_tax: "법인세",
  total_tax: "총 납부세액",

  // esg
  embodied_carbon: "내재탄소 상세 분석",
  operational_carbon: "운영탄소 상세 분석",
  lifecycle_total: "전과정 총 탄소 배출 시나리오",
  low_carbon_scenario: "저탄소 대안 시나리오",
  gseed_prediction: "녹색건축인증(G-SEED) 예측",
  gresb: "GRESB 평가 지표",
  embodied_carbon_kg: "내재탄소량(kg)",
  operational_carbon_kg: "운영탄소량(kg)",
  operational_carbon_30yr_kg: "30년 운영탄소량(kg)",
  total_lifecycle_carbon_kg: "전과정 총 탄소량(kg)",
  carbon_per_sqm_kg: "단위면적당 탄소(kg/m²)",
  total_carbon_per_sqm: "단위면적당 탄소(kg/m²)",
  esg_score: "ESG 종합 점수",
  certification_level: "친환경 인증 등급",

  // report
  report_url: "보고서 다운로드 링크",
  generated_at: "보고서 생성 일시",
  sections_included: "포함된 분석 섹션",
};

// 약식 그리드에서 숨길 필드: 보고서 호환 중복 alias + 복합객체(상세는 정식 분석에서).
const HIDDEN_GRID_FIELDS = new Set<string>([
  "total_cost_won", "total_revenue_won", "net_profit_won",  // *_won = 본필드 중복 alias
  "monte_carlo", "cashflow", "sensitivity", "market_revaluation",  // 복합객체(원시 JSON 방지)
  "cost_breakdown",  // 라인아이템 총사업비 — 별도 표로 렌더(아래)
  "pnu_codes", "coordinates", "building_info", "category_totals",
]);

// 총사업비 라인아이템 표시 순서(실무 수지 검토용)
const COST_BREAKDOWN_ORDER = [
  "토지비", "직접공사비", "설계·감리비", "인허가·분담금", "분양경비",
  "일반관리비", "예비비", "금융비", "제세공과(취득세 등)",
];

// 수지 필드별 산정근거(주석) — 실제 백엔드 계산식과 동일. 화면에 작은 회색 글씨로 표시.
const FIELD_BASIS: Record<string, string> = {
  construction_cost: "공사비 분석 단계 산출(지상+지하 직접공사비)",
  general_expense_won: "분양경비(매출×4%)+일반관리비((토지+공사)×3%)+예비비(공사×5%)",
  finance_cost_won: "(토지비+직접공사비)×50% 차입 × 연 6.5% × 사업기간",
  breakeven_sale_rate_pct: "총사업비 ÷ 총분양수입 × 100 (이 분양률에서 손익분기)",
  roe_pct: "순이익 ÷ 자기자본(총사업비의 30%) × 100",
  project_months: "공사비 분석의 추정 공기(미산출 시 기본 30개월)",
  total_project_cost: "9개 라인아이템 합산(토지+공사+설계+인허가+분양경비+관리비+예비비+금융+제세)",
  total_revenue: "평당 분양가 × 분양면적(전용/공용 효율 반영)",
  net_profit: "총 분양수입 − 총 사업비",
  profit_rate_pct: "순이익 ÷ 총 사업비 × 100",
  grade: "예상 수익률 구간별 등급(A 우수 ~ D 주의)",
};

// 총사업비 라인아이템별 산정근거(주석)
const COST_BASIS: Record<string, string> = {
  "토지비": "공시지가×1.3 또는 주변 실거래시세",
  "직접공사비": "공사비 분석(지상+지하)",
  "설계·감리비": "직접공사비 × 5%",
  "인허가·분담금": "직접공사비 × 3%",
  "분양경비": "총 분양수입 × 4%",
  "일반관리비": "(토지비+직접공사비) × 3%",
  "예비비": "직접공사비 × 5%",
  "금융비": "(토지+공사)×50% × 연6.5% × 사업기간",
  "제세공과(취득세 등)": "토지비 × 4.6%",
};

// 분양가 산정근거 코드 → 한글
const SALE_SOURCE_LABEL: Record<string, string> = {
  market_blended: "시장 블렌딩(실거래+표준)",
  regional_market_table: "지역 시장 표준단가",
  molit_realtx: "국토부 실거래",
  nearby_map: "주변 실거래",
  avm: "AI 추정시세",
  cost_based_fallback: "공사비 기반(폴백)",
  user: "사용자 입력",
};

/** 약식 분석 필드 값 표시 — 객체 JSON 덤프 금지, 코드값은 한글 매핑. */
function displayFieldValue(key: string, value: unknown): string {
  if (value == null) return "-";
  if (key === "sale_price_source" && typeof value === "string") {
    return SALE_SOURCE_LABEL[value] || value;
  }
  if (typeof value === "object") return "—"; // 복합객체는 그리드에 표시하지 않음(숨김 대상)
  return formatNumber(value as number | string);
}

// 백엔드 PipelineStage enum과 동일한 단계 순서(SSOT). rerun-stage 라우터의 valid_stages·
// skip_stages 계산과 일치해야 한다 — 다단계 오버라이드 중 "파이프라인상 최초 단계"를 산출하는 기준.
const STAGE_ORDER = [
  "site_analysis",
  "design",
  "cost",
  "feasibility",
  "tax",
  "esg",
  "report",
] as const;

const DEFAULT_STAGES: PipelineStageStatus[] = STAGE_ORDER.map((s) => ({
  stage: s,
  status: "pending",
  duration_ms: null,
  data: {},
  error: null,
}));

/* ── Helpers ── */

function statusIcon(status: PipelineStageStatus["status"]) {
  switch (status) {
    case "completed":
      return (
        <span className="flex h-6 w-6 items-center justify-center rounded-full bg-emerald-500/20 text-emerald-400 text-xs font-bold">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><path d="M20 6 9 17l-5-5" /></svg>
        </span>
      );
    case "running":
      return (
        <span className="flex h-6 w-6 items-center justify-center rounded-full bg-[var(--accent-strong)]/20 text-[var(--accent-strong)]">
          <svg className="animate-spin" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><path d="M21 12a9 9 0 1 1-6.219-8.56" /></svg>
        </span>
      );
    case "failed":
      return (
        <span className="flex h-6 w-6 items-center justify-center rounded-full bg-red-500/20 text-red-400 text-xs font-bold">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><path d="M18 6 6 18" /><path d="m6 6 12 12" /></svg>
        </span>
      );
    case "skipped":
      return (
        <span className="flex h-6 w-6 items-center justify-center rounded-full bg-yellow-500/20 text-yellow-400 text-[10px] font-bold">
          -
        </span>
      );
    default:
      return (
        <span className="flex h-6 w-6 items-center justify-center rounded-full bg-[var(--surface-strong)] text-[var(--text-tertiary)] text-[10px]">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><circle cx="12" cy="12" r="10" /><path d="M12 6v6l4 2" /></svg>
        </span>
      );
  }
}

function statusLabel(status: PipelineStageStatus["status"]) {
  switch (status) {
    case "completed":
      return "완료";
    case "running":
      return "진행 중...";
    case "failed":
      return "실패";
    case "skipped":
      return "건너뜀";
    default:
      return "대기";
  }
}

function formatDuration(ms: number | null) {
  if (ms == null) return "";
  return `(${(ms / 1000).toFixed(1)}s)`;
}

function formatNumber(value: unknown): string {
  if (typeof value === "number") {
    if (Math.abs(value) >= 1e8) {
      return `${(value / 1e8).toFixed(1)}억`;
    }
    if (Math.abs(value) >= 1e4) {
      return `${(value / 1e4).toFixed(0)}만`;
    }
    return value.toLocaleString("ko-KR");
  }
  return String(value ?? "-");
}

/* ── Summary card specs ── */

interface SummaryCard {
  label: string;
  key: string;
  unit: string;
  source: string;
  format?: (v: unknown) => string;
}

const SUMMARY_CARDS: SummaryCard[] = [
  { label: "토지면적", key: "land_area_sqm", unit: "m\u00B2", source: "site_analysis", format: (v) => (typeof v === "number" ? `${v.toLocaleString("ko-KR")}` : "-") },
  { label: "총공사비", key: "total_construction_cost", unit: "", source: "cost", format: (v) => formatNumber(v) },
  { label: "수익률", key: "profit_rate_pct", unit: "%", source: "feasibility", format: (v) => (typeof v === "number" ? v.toFixed(1) : "-") },
  { label: "탄소배출", key: "carbon_per_sqm_kg", unit: "kgCO\u2082/m\u00B2", source: "esg", format: (v) => (typeof v === "number" ? v.toFixed(1) : "-") },
];

/* ── View Mode ── */

type ViewMode = "pipeline" | "detail" | "compare";

/* ── Component ── */

/** 단계별 워크플로우 상태 */
type WorkflowPhase =
  | "input"           // 주소 입력 단계
  | "site_review"     // 부지분석 결과 확인 단계
  | "remaining"       // 나머지 단계 진행 중
  | "done";           // 전체 완료

/**
 * @param projectMode  프로젝트 상세 허브에서 사용. 주소 입력을 숨기고 store의 부지정보를 사용한다.
 * @param autoStart    projectMode에서 마운트 시 부지분석을 자동 실행한다.
 * @param onSiteAnalysisComplete  부지분석 완료 후 "사업모델 추천 보기" CTA에서 호출 (통합 흐름 연결점).
 */
interface ProjectPipelinePanelProps {
  projectMode?: boolean;
  autoStart?: boolean;
  onSiteAnalysisComplete?: () => void;
}

export function ProjectPipelinePanel({
  projectMode = false,
  autoStart = false,
  onSiteAnalysisComplete,
}: ProjectPipelinePanelProps = {}) {
  const [address, setAddress] = useState("");
  const [allAddresses, setAllAddresses] = useState<AddressEntry[]>([]);
  const [stages, setStages] = useState<PipelineStageStatus[]>(DEFAULT_STAGES);
  const [summary, setSummary] = useState<Record<string, Record<string, unknown>>>({});
  const [isRunning, setIsRunning] = useState(false);
  const [expandedStage, setExpandedStage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [guestGateOpen, setGuestGateOpen] = useState(false);  // 비회원 무료소진 게이트
  const { locale } = (useParams() as { locale?: string }) || {};
  const pathname = usePathname();
  const router = useRouter();

  // 단계별 워크플로우
  const [workflowPhase, setWorkflowPhase] = useState<WorkflowPhase>("input");

  // Phase 3: view mode, history, compare
  const [viewMode, setViewMode] = useState<ViewMode>("pipeline");
  const [lastResult, setLastResult] = useState<PipelineRunResponse | null>(null);
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [compareSelection, setCompareSelection] = useState<Set<string>>(new Set());

  // Load history on mount + 프로젝트 목록 백엔드 동기화(드롭다운/프로젝트관리 단일출처 일치)
  useEffect(() => {
    setHistory(loadHistory());
    void useProjectListStore.getState().syncFromBackend();
  }, []);

  // ★홈/중앙분석센터 클릭 시(같은 라우트라 리마운트 없음) 분석뷰→입력(랜딩)으로 리셋.
  //  새로고침해야만 홈으로 가던 문제 해결. 프로젝트 허브(projectMode)에선 적용 안 함.
  const homeNonce = useUiReset((s) => s.homeNonce);
  const homeNonceInit = useRef(true);
  useEffect(() => {
    if (homeNonceInit.current) { homeNonceInit.current = false; return; }
    if (projectMode) return;
    setWorkflowPhase("input");
    setStages(DEFAULT_STAGES);
    setSummary({});
    setLastResult(null);
    setError(null);
    setExpandedStage(null);
    setViewMode("pipeline");
    setAddress("");
    setAllAddresses([]);
    if (typeof window !== "undefined") window.scrollTo({ top: 0, behavior: "smooth" });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [homeNonce]);

  // 경로 변경(대시보드 복귀/프로젝트 전환) 시 항상 첫 단계(진행 단계 뷰)로 리셋.
  // (이전: detail/compare 뷰가 남아 재진입 시 다른 분석 상세가 그대로 표시됨)
  useEffect(() => {
    setViewMode("pipeline");
    setCompareSelection(new Set());
  }, [pathname]);

  const projectId = useProjectContextStore((s) => s.projectId);
  const siteAnalysis = useProjectContextStore((s) => s.siteAnalysis);
  const completedStages = useProjectContextStore((s) => s.completedStages);
  const storeAddress = useProjectContextStore((s) => s.siteAnalysis?.address ?? "");
  const autoStartedRef = useRef(false);
  // 부지분석 단독 실행이 남긴 "임시 이력"의 id. 이어서 전체 분석이 끝나면 이 항목을 교체(supersede)해
  // "1회 분석 = 이력 2개(부지만/전체)" 중복을 방지한다.
  const siteOnlyEntryIdRef = useRef<string | null>(null);
  const updateSiteAnalysis = useProjectContextStore((s) => s.updateSiteAnalysis);
  const updateDesignData = useProjectContextStore((s) => s.updateDesignData);
  const updateFeasibilityData = useProjectContextStore((s) => s.updateFeasibilityData);
  const updateEsgData = useProjectContextStore((s) => s.updateEsgData);
  const updateCostData = useProjectContextStore((s) => s.updateCostData);
  const updateComplianceData = useProjectContextStore((s) => s.updateComplianceData);
  const addAnalysisResult = useProjectContextStore((s) => s.addAnalysisResult);
  const markStageComplete = useProjectContextStore((s) => s.markStageComplete);

  const saveToStore = useCallback(
    (result: PipelineRunResponse, addr?: string) => {
      const effectiveAddr = addr ?? address;
      // site_analysis — summary 우선, 없으면 stages[0].data에서 직접 추출
      // partial merge로 기존 데이터 유지하면서 새 값만 덮어쓰기
      const site = result.summary?.site_analysis;
      const siteStageData = result.stages?.find((s) => s.stage === "site_analysis")?.data as Record<string, unknown> | undefined;
      const basic = (siteStageData?.basic ?? {}) as Record<string, unknown>;
      if (site || siteStageData) {
        const newLandArea = (site?.land_area_sqm as number) ?? (basic.land_area_sqm as number) ?? (siteStageData?.land_area_sqm as number);
        const newZoneCode = (site?.zone_code as string) ?? (basic.zone_type as string) ?? (siteStageData?.zone_type as string);
        const newPnu = (site?.pnu as string) ?? (basic.pnu as string);
        const newEstValue = site?.estimated_value as number | undefined;

        // E7: 사이트 결과가 외부 데이터 미확보로 기본 가정값을 채운 경우(data_quality==="assumed_defaults"),
        //  해당 가정 필드(assumed_fields)를 SSOT 시드에서 제외한다. 가정값이 자동 환류로 store에 박히면
        //  staleness/다운스트림이 "근거 있는 값"으로 오인 → 정직성 위반·재분석 왜곡. (zone_type→zoneCode,
        //  land_area_sqm→landAreaSqm 매핑으로 store 필드명에 대응)
        const dataQuality = (site?.data_quality as string | undefined) ?? (siteStageData?.data_quality as string | undefined);
        const assumedFields = new Set<string>(
          dataQuality === "assumed_defaults"
            ? (((site?.assumed_fields as string[] | undefined) ?? (siteStageData?.assumed_fields as string[] | undefined)) ?? [])
            : [],
        );
        const seedLandArea = !assumedFields.has("land_area_sqm");
        const seedZone = !assumedFields.has("zone_type");

        updateSiteAnalysis({
          ...(newEstValue != null ? { estimatedValue: newEstValue } : {}),
          ...(seedLandArea && newLandArea != null && newLandArea > 0 ? { landAreaSqm: newLandArea } : {}),
          ...(seedZone && newZoneCode ? { zoneCode: newZoneCode } : {}),
          ...(effectiveAddr ? { address: effectiveAddr } : {}),
          ...(newPnu ? { pnu: newPnu } : {}),
        });
        markStageComplete("site-analysis");
      }

      // design
      const design = result.summary?.design;
      if (design) {
        // 세대 구성·전용률 환류 — 도면/유닛믹스/수지 다운스트림의 "데이터 없음" 해소(SSOT 연결).
        //  unit_types는 백엔드가 객체 배열([{type,...}])로 산출 → 평형 라벨 문자열 배열로 정규화.
        const unitTypesRaw = design.unit_types;
        const unitTypes: string[] | null = Array.isArray(unitTypesRaw)
          ? unitTypesRaw
              .map((u) =>
                typeof u === "string"
                  ? u
                  : ((u as Record<string, unknown> | null)?.type as string | undefined)
                    ?? ((u as Record<string, unknown> | null)?.name as string | undefined),
              )
              .filter((v): v is string => typeof v === "string" && v.length > 0)
          : null;
        const efficiencyPct = (design.sellable_efficiency_pct as number) ?? null;
        const unitCount = (design.unit_count as number | undefined) ?? null;
        updateDesignData({
          totalGfaSqm: (design.total_gfa_sqm as number) ?? null,
          floorCount: (design.floor_count as number) ?? null,
          buildingType: (design.building_type as string) ?? null,
          bcr: (design.bcr as number) ?? null,
          far: (design.far as number) ?? null,
          // 세대수·평형·전용률은 summary에 실제 값이 있을 때만 환류 — 부재 시 기존 SSOT값 보존
          ...(unitCount != null ? { unitCount } : {}),
          ...(unitTypes && unitTypes.length > 0 ? { unitTypes } : {}),
          ...(efficiencyPct != null ? { efficiencyPct } : {}),
        });
        markStageComplete("design");

        // 법규검토(BL-001 건폐율 / BL-002 용적률 / BL-003 높이) → ComplianceData 환류.
        //  설계 단계가 BuildingCodeRuleEngine으로 산출한 results를 SSOT로 연결해 "법규" 단계를 완료 처리한다.
        //  status는 ComplianceStatus enum값(pass/fail/warning/n/a) — pass만 적합, n/a(높이제한 없음)는
        //  "위반 아님"으로 null 유지(거짓 적합/위반 표기 방지).
        const complianceResults = (design.compliance as Record<string, unknown> | undefined)?.results;
        if (Array.isArray(complianceResults) && complianceResults.length > 0) {
          const byRule = new Map<string, string>();
          const violations: string[] = [];
          for (const r of complianceResults) {
            const rule = (r as Record<string, unknown>)?.rule_id as string | undefined;
            const status = (r as Record<string, unknown>)?.status as string | undefined;
            if (rule && status) byRule.set(rule, status);
            if (status === "fail") {
              const msg =
                ((r as Record<string, unknown>)?.message as string | undefined) ??
                ((r as Record<string, unknown>)?.rule_name as string | undefined) ??
                rule;
              if (msg) violations.push(msg);
            }
          }
          // pass → true / fail → false / 미검(n/a·부재) → null("데이터 없음" 정직 표기)
          const verdict = (rule: string): boolean | null => {
            const s = byRule.get(rule);
            if (s === "pass") return true;
            if (s === "fail") return false;
            return null;
          };
          updateComplianceData({
            bcrCompliant: verdict("BL-001"),
            farCompliant: verdict("BL-002"),
            heightCompliant: verdict("BL-003"),
            violations,
          });
          markStageComplete("legal");
        }
      }

      // cost — 공사비 분석 결과를 SSOT(CostData)에 환류(auto). 수지·사업성 단일 데이터원 연결,
      //  staleness 캐스케이드 트리거. 백엔드 미산출 필드는 정직하게 null 유지(가짜값 금지).
      const cost = result.summary?.cost;
      if (cost) {
        updateCostData({
          totalConstructionCostWon: (cost.total_construction_cost as number) ?? null,
          perSqmWon: (cost.cost_per_sqm as number) ?? null,
          perPyeongWon: (cost.cost_per_pyeong as number) ?? null,
          abovegroundWon: (cost.aboveground_cost as number) ?? null,
          undergroundWon: (cost.underground_cost as number) ?? null,
          landscapeWon: (cost.landscape_cost as number) ?? null,
          directWon: (cost.direct_cost as number) ?? null,
          indirectWon: (cost.indirect_cost as number) ?? null,
          rangeMinWon: (cost.range_min as number) ?? null,
          rangeMaxWon: (cost.range_max as number) ?? null,
          source: "overview",
        });
        markStageComplete("construction");
      }

      // feasibility
      const feas = result.summary?.feasibility;
      if (feas) {
        updateFeasibilityData({
          totalCostWon: (feas.total_cost_won as number) ?? null,
          totalRevenueWon: (feas.total_revenue_won as number) ?? null,
          profitRatePct: (feas.profit_rate_pct as number) ?? null,
          grade: (feas.grade as string) ?? null,
        });
        markStageComplete("feasibility");
      }

      // esg
      const esg = result.summary?.esg_carbon;
      if (esg) {
        updateEsgData({
          embodiedCarbonKg: (esg.embodied_carbon_kg as number) ?? null,
          operationalCarbonKg: (esg.operational_carbon_kg as number) ?? null,
          totalCarbonPerSqm: (esg.total_carbon_per_sqm as number) ?? null,
        });
        markStageComplete("esg");
      }

      // analysis results for each completed stage
      for (const stage of result.stages) {
        if (stage.status === "completed") {
          addAnalysisResult({
            module: stage.stage,
            completedAt: new Date().toISOString(),
            summary: stage.data,
          });
        }
      }
    },
    [address, updateSiteAnalysis, updateDesignData, updateFeasibilityData, updateEsgData, updateCostData, updateComplianceData, addAnalysisResult, markStageComplete],
  );

  const addToHistory = useCallback(
    (result: PipelineRunResponse, addr: string, supersedeId?: string | null) => {
      const entry: HistoryEntry = {
        id: result.pipeline_id,
        address: addr,
        completedAt: new Date().toISOString(),
        result,
        addresses: allAddresses.length > 0 ? allAddresses.map((a) => a.fullAddress) : [addr],
        // ★대시보드(quick)는 projectId 태깅 금지 — store에 묻은 stale projectId로 태깅돼
        //  무태깅 필터에서 본인 이력이 전부 숨겨지던 근본원인 차단. 프로젝트 모드만 태깅.
        projectId: projectMode ? (projectId || undefined) : undefined,
        mode: projectMode ? "project" : "quick",
      };
      // entry.id 중복 제거 + (있으면) 부지분석 단독 임시이력(supersedeId)도 함께 제거 → 전체분석이 대체
      const updated = [
        entry,
        ...history.filter((h) => h.id !== entry.id && (!supersedeId || h.id !== supersedeId)),
      ].slice(0, MAX_HISTORY);
      setHistory(updated);
      saveHistory(updated);
      // 분석 원장 write-through(서버 영속·기기간 공유·무결성). best-effort.
      const r = result as unknown as { summary?: Record<string, any>; stages?: Array<{ stage: string; data?: any }> };
      const pnu = r.summary?.site_analysis?.pnu
        || r.stages?.find((s) => s.stage === "site_analysis")?.data?.basic?.pnu
        || undefined;
      void appendLedger(
        "pipeline",
        { summary: result.summary, stages: result.stages, pipeline_id: result.pipeline_id },
        { pnu, address: addr, projectId: projectId || undefined },
        projectMode ? "project" : "quick",
      );
    },
    [history, projectId, projectMode, allAddresses],
  );

  // 이력 삭제
  const removeFromHistory = useCallback(
    (id: string) => {
      const updated = history.filter((h) => h.id !== id);
      setHistory(updated);
      saveHistory(updated);
      setCompareSelection((prev) => {
        const next = new Set(prev);
        next.delete(id);
        return next;
      });
    },
    [history],
  );

  // 이력 클릭 → 읽기전용 상세 뷰어. 로컬 상태만 갱신하고 전역 프로젝트 컨텍스트는 건드리지 않는다.
  // (이전 버그: 대시보드 이력 클릭이 saveToStore로 "현재 projectId" 슬롯을 오염 주입 →
  //  "신봉동 선택인데 중곡동 헤더" 발생). 프로젝트 컨텍스트 변경은 projectMode에서만 허용.
  const openHistory = useCallback((entry: HistoryEntry) => {
    // 대시보드(전역)에서 이력 선택 → 인라인 상세로 머무르지 않고 해당 프로젝트의
    // 입지분석 보고서 페이지로 이동(상단 진입). 대시보드는 항상 깨끗하게 유지된다.
    if (!projectMode && entry.projectId && locale) {
      router.push(`/${locale}/projects/${entry.projectId}/site-analysis`);
      return;
    }
    setLastResult(entry.result);
    setAddress(entry.address);
    // 다필지 주소 복원 — 사업개요의 필지 구획도/지도가 재진입 시에도 표시되도록(좌표는 라이브 재조회)
    setAllAddresses(
      (entry.addresses && entry.addresses.length > 0 ? entry.addresses : [entry.address])
        .map((a) => ({ fullAddress: a } as AddressEntry)),
    );
    setStages(entry.result.stages);
    setSummary(entry.result.summary ?? {});
    setViewMode("detail");
    // projectMode(프로젝트 상세 허브)에서만 스냅샷에 복원. 대시보드(전역)는 읽기전용.
    if (projectMode) saveToStore(entry.result, entry.address);
  }, [saveToStore, projectMode, locale, router]);

  // 주소 검색 콜백 (다필지 지원)
  const handleAddressChange = useCallback((entries: AddressEntry[]) => {
    setAllAddresses(entries);
    if (entries.length > 0) {
      // 대표 주소 설정 (첫 번째 필지)
      setAddress(entries[0]!.fullAddress);
    } else {
      setAddress("");
    }
  }, []);

  // STEP 1: 부지분석 — GlobalAddressSearch가 이미 수집한 데이터 활용
  const runSiteAnalysis = useCallback(async () => {
    if (!address.trim()) return;

    // 비회원 무료 1회 게이트: 소진 시 분석 차단 + 가입/구독 유도
    if (isGuest() && guestUsed() >= GUEST_FREE_QUOTA) {
      setGuestGateOpen(true);
      return;
    }

    setError(null);
    setStages(DEFAULT_STAGES.map((s) => ({ ...s })));
    setSummary({});
    setExpandedStage(null);
    setViewMode("pipeline");
    setLastResult(null);

    // 항상 백엔드 진행 단계 API를 호출하여 실제 데이터를 수집
    // (siteAnalysis 캐시는 불완전할 수 있으므로 신뢰하지 않음)
    setIsRunning(true);
    setWorkflowPhase("input");

    try {
      const updatedStages = DEFAULT_STAGES.map((s) => ({ ...s }));
      updatedStages[0]!.status = "running";
      setStages([...updatedStages]);

      // 프론트에서 수집한 siteAnalysis가 있으면 항상 백엔드에 전달
      // null/0은 undefined로 변환하여 백엔드가 "미제공"으로 인식
      const siteDataForBackend = siteAnalysis ? {
        zone_type: siteAnalysis.zoneCode || undefined,
        // ★다필지면 통합 면적을 백엔드에 보낸다(대표값 전송 시 수지·법규가 과소산출).
        land_area_sqm: effectiveLandAreaSqm(siteAnalysis) || undefined,
        max_bcr: siteAnalysis.ordinance?.effectiveBcr || siteAnalysis.ordinance?.nationalBcr || undefined,
        max_far: siteAnalysis.ordinance?.effectiveFar || siteAnalysis.ordinance?.nationalFar || undefined,
        official_land_price: siteAnalysis.officialPrices?.[0]?.pricePerSqm || undefined,
        pnu_codes: siteAnalysis.pnu ? [siteAnalysis.pnu] : [],
        coordinates: siteAnalysis.coordinates ?? null,
        ordinance_source: siteAnalysis.ordinance?.source || undefined,
        building_info: siteAnalysis.buildingInfo ?? null,
        land_use_districts: siteAnalysis.landUseDistricts ?? [],
      } : undefined;

      // ★다필지 통합(RC#2): store 다필지(2필지↑)면 파이프라인에 필지목록 전송 → site stage가
      //   통합면적 기준으로 산출(대표 1필지 763㎡ 축소 버그 제거). 1필지·미보유는 미전송(무회귀).
      const parcelRowsForBackend = parcelDataToRows(siteAnalysis?.parcels);

      // 백엔드 진행 단계 호출 (부지분석만)
      const result = await apiClient.postV2<PipelineRunResponse>("/pipeline/run", {
        body: {
          address: address.trim(),
          project_id: projectId,
          options: {
            stop_after: "site_analysis",
            site_data: siteDataForBackend,  // 항상 전달 (null이어도 백엔드가 폴백 처리)
          },
          ...(shouldSendParcels(parcelRowsForBackend) ? { parcels: parcelRowsForBackend } : {}),
        },
        useMock: false,
        timeoutMs: 170000,  // 부지분석은 데이터수집+LLM으로 ~60초 소요 → 넉넉히
      });

      setStages(result.stages);
      setSummary(result.summary ?? {});
      setLastResult(result);

      const siteStage = (result.stages ?? []).find((s) => s.stage === "site_analysis");
      if (siteStage?.status === "completed") {
        setWorkflowPhase("site_review");
        setExpandedStage("site_analysis");
        saveToStore(result);
        addToHistory(result, address.trim());  // 부지분석 단독 실행도 이력 저장
        // 이 임시 이력 id를 기억 → 이어서 전체 분석이 끝나면 교체(중복 방지)
        siteOnlyEntryIdRef.current = result.pipeline_id;
        if (isGuest()) bumpGuest();  // 비회원 무료 사용 횟수 증가
      } else {
        setError("부지분석에 실패했습니다. 주소를 확인해주세요.");
      }
    } catch (err) {
      let msg = err instanceof Error ? err.message : "알 수 없는 오류가 발생했습니다.";
      if (/fetch|network|timeout|시간|abort|load failed/i.test(msg)) {
        msg = "부지분석 연결이 지연되거나 중단되었습니다(분석은 다소 시간이 걸립니다). '부지 분석 다시'를 눌러 다시 시도해 주세요.";
      }
      setError(msg);
      // 멈춤 방지: 진행 중이던 단계를 '실패'로 되돌려 무한 '진행 중' 표시를 해소
      setStages((prev) => prev.map((s, i) => (i === 0 ? { ...s, status: "failed" } : s)));
    } finally {
      setIsRunning(false);
    }
  }, [address, projectId, siteAnalysis, saveToStore, addToHistory]);

  // STEP 2: 나머지 단계 진행 (부지분석 결과 확인 후)
  const runRemainingStages = useCallback(async () => {
    if (!address.trim()) return;

    setIsRunning(true);
    setError(null);
    setWorkflowPhase("remaining");

    try {
      // siteAnalysis 데이터를 백엔드에 전달하여 외부 API 재호출 방지
      // null/0은 undefined로 변환하여 백엔드가 "미제공"으로 인식
      const siteDataForBackend = siteAnalysis ? {
        zone_type: siteAnalysis.zoneCode || undefined,
        // ★다필지면 통합 면적을 백엔드에 보낸다(대표값 전송 시 수지·법규가 과소산출).
        land_area_sqm: effectiveLandAreaSqm(siteAnalysis) || undefined,
        max_bcr: siteAnalysis.ordinance?.effectiveBcr || undefined,
        max_far: siteAnalysis.ordinance?.effectiveFar || undefined,
        official_land_price: siteAnalysis.officialPrices?.[0]?.pricePerSqm || undefined,
        pnu_codes: siteAnalysis.pnu ? [siteAnalysis.pnu] : [],
        coordinates: siteAnalysis.coordinates ?? null,
      } : undefined;

      // ★다필지 통합(RC#2): 전체 파이프라인에도 필지목록 전송 → 설계·수지·보고서까지 통합면적 기준.
      const parcelRowsForFull = parcelDataToRows(siteAnalysis?.parcels);

      const result = await apiClient.postV2<PipelineRunResponse>("/pipeline/run", {
        body: {
          address: address.trim(),
          project_id: projectId,
          options: { site_data: siteDataForBackend },
          ...(shouldSendParcels(parcelRowsForFull) ? { parcels: parcelRowsForFull } : {}),
        },
        useMock: false,
        // 전체 7단계 동기 실행은 부지분석 재수집(~40s)+설계~보고서를 포함해 가장 무거운 호출이다.
        // 기본 120s로는 콜드 캐시/프록시 지연 시 중도 abort → "공사비 이후 정지"처럼 보이므로
        // runSiteAnalysis와 동일하게 넉넉히 잡아 끝까지 응답을 받도록 한다.
        timeoutMs: 170000,
      });

      setStages(result.stages);
      setSummary(result.summary ?? {});
      setLastResult(result);
      setWorkflowPhase("done");

      saveToStore(result);
      // 전체 분석 완료 → 직전 부지분석 단독 임시이력을 교체(supersede)해 중복 이력 방지
      addToHistory(result, address.trim(), siteOnlyEntryIdRef.current);
      siteOnlyEntryIdRef.current = null;
    } catch (err) {
      let msg = err instanceof Error ? err.message : "알 수 없는 오류가 발생했습니다.";
      if (/fetch|network|timeout|시간|abort|load failed/i.test(msg)) {
        msg = "전체 분석 연결이 지연되거나 중단되었습니다(분석은 다소 시간이 걸립니다). '전체 7단계 분석 계속'을 다시 눌러 재시도해 주세요.";
      }
      setError(msg);
      // 스톨 방지: 미완료(대기/진행 중) 단계를 '실패'로 되돌려 "공사비 이후 정지"처럼
      // 멈춘 듯 보이는 상태를 해소한다(부지분석 등 이미 완료된 단계는 보존).
      setStages((prev) =>
        prev.map((s) =>
          s.status === "completed" || s.status === "skipped" ? s : { ...s, status: "failed" },
        ),
      );
    } finally {
      setIsRunning(false);
    }
  }, [address, projectId, siteAnalysis, saveToStore, addToHistory]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    runSiteAnalysis();
  };

  // projectMode: store 주소를 입력값으로 동기화 (persist 하이드레이션 대응)
  useEffect(() => {
    if (projectMode && storeAddress && storeAddress !== address) {
      setAddress(storeAddress);
    }
  }, [projectMode, storeAddress]); // eslint-disable-line react-hooks/exhaustive-deps

  // projectMode + autoStart: 마운트 후 주소가 준비되면 부지분석 1회 자동 실행
  useEffect(() => {
    if (!projectMode || !autoStart) return;
    if (autoStartedRef.current) return;
    if (!address.trim()) return;
    if (isRunning || workflowPhase !== "input") return;
    // 이미 부지분석이 끝난 프로젝트라면 결과 확인 단계로 자동 전환
    if (completedStages.includes("site-analysis")) {
      autoStartedRef.current = true;
      setWorkflowPhase("site_review");
      return;
    }
    autoStartedRef.current = true;
    runSiteAnalysis();
  }, [projectMode, autoStart, address, isRunning, workflowPhase, completedStages, runSiteAnalysis]);

  // ③ 체험 → 프로젝트 승격: 대시보드 체험분석의 주소·부지결과를 핸드오프로 넘겨 프로젝트
  // 생성 화면(전체 전주기 분석)으로 이동시킨다. 체험 이력은 대시보드에만 남고, 프로젝트화하면
  // 전체 분석이 프로젝트 이력으로 축적된다(구독 전환 관문).
  const promoteToProject = useCallback(() => {
    const addr = (address || storeAddress || "").trim();
    if (!addr) return;
    writePreCheckHandoff({
      address: addr,
      zoneType: siteAnalysis?.zoneCode ?? null,
      areaSqm: effectiveLandAreaSqm(siteAnalysis),
      pnu: siteAnalysis?.pnu ?? null,
      bestMethod: null,
      bestMethodName: null,
    });
    router.push(`/${locale ?? "ko"}/projects/new`);
  }, [address, storeAddress, siteAnalysis, router, locale]);

  // 단계 행 ref — 펼침 시 상단(긴 지도) 접힘에 따른 레이아웃 점프를 막고 클릭 단계로 재고정.
  const stageRowRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const toggleStage = (stageKey: string) => {
    setExpandedStage((prev) => {
      const next = prev === stageKey ? null : stageKey;
      if (next) {
        requestAnimationFrame(() => {
          stageRowRefs.current[stageKey]?.scrollIntoView({ behavior: "smooth", block: "nearest" });
        });
      }
      return next;
    });
  };

  const handleRerun = useCallback(
    async (stageName: string, overrides: Record<string, unknown>) => {
      if (!lastResult) return;
      setIsRunning(true);
      setError(null);
      setViewMode("pipeline");

      try {
        // PipelineResultDetail의 onRerun 계약은 flat "{stage}.{field}" 오버라이드(불변).
        //  이를 단계별 맵(stage_overrides)으로 파싱하고, STAGE_ORDER상 "최초로 오버라이드된 단계"를
        //  재실행 진입점(stage)으로 산출한다 — 그 이전 단계는 previous_result로 복원·스킵되어
        //  기본값(500/60/200) 왜곡 없이 수정 지점부터 정확히 재계산된다. (/pipeline/rerun-stage 전환)
        const stageOverrides: Record<string, Record<string, unknown>> = {};
        for (const [flatKey, value] of Object.entries(overrides)) {
          const dot = flatKey.indexOf(".");
          // 점이 없는 키(드묾)는 호출자가 지정한 stageName으로 귀속(하위호환).
          const stage = dot >= 0 ? flatKey.slice(0, dot) : stageName;
          const field = dot >= 0 ? flatKey.slice(dot + 1) : flatKey;
          if (!field) continue;
          (stageOverrides[stage] ??= {})[field] = value;
        }

        // 파이프라인 순서상 최초 오버라이드 단계 산출(미상 단계는 무시). 없으면 호출자 stageName 폴백.
        let earliest = stageName;
        let earliestIdx = Number.POSITIVE_INFINITY;
        for (const stage of Object.keys(stageOverrides)) {
          const idx = STAGE_ORDER.indexOf(stage as (typeof STAGE_ORDER)[number]);
          if (idx >= 0 && idx < earliestIdx) {
            earliestIdx = idx;
            earliest = stage;
          }
        }

        const result = await apiClient.postV2<PipelineRunResponse>("/pipeline/rerun-stage", {
          body: {
            address: address.trim(),
            project_id: projectId,
            stage: earliest,
            stage_overrides: stageOverrides,
            // 이전 결과 동봉 → 백엔드가 skip 단계 data + 단계간 payload 복원(정확 재계산).
            previous_result: { stages: lastResult.stages },
          },
          useMock: false,
          timeoutMs: 170000,
        });

        setStages(result.stages);
        setSummary(result.summary ?? {});
        setLastResult(result);
        saveToStore(result);
        addToHistory(result, address.trim());
      } catch (err) {
        const msg = err instanceof Error ? err.message : "알 수 없는 오류가 발생했습니다.";
        setError(msg);
      } finally {
        setIsRunning(false);
      }
    },
    [lastResult, address, projectId, saveToStore, addToHistory],
  );

  const toggleCompareSelect = (id: string) => {
    setCompareSelection((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else if (next.size < 3) {
        next.add(id);
      }
      return next;
    });
  };

  const startCompare = () => {
    if (compareSelection.size >= 2) {
      setViewMode("compare");
    }
  };

  // 이력 격리(차별화): 대시보드(체험) 모드는 프로젝트 미소속(무태깅) 체험 이력만 노출 →
  // 프로젝트 생성으로 분석한 건(projectId 태깅)은 대시보드 이력에서 제외(중복 해소).
  // 프로젝트 모드는 현재 projectId 이력만(레거시 무태깅은 주소매칭 폴백).
  const visibleHistory = (() => {
    // 대시보드(체험): 프로젝트 모드로 실행한 이력만 제외하고 모두 노출.
    //  (mode 기준 — 레거시 무mode 항목은 stale projectId로 잘못 태깅됐어도 여기서 복구됨.)
    if (!projectMode) return history.filter((h) => h.mode !== "project");
    if (!projectId) return history;
    const norm = (s: string) => (s || "").replace(/\s+/g, "");
    const projAddr = norm(storeAddress);
    return history.filter((h) =>
      h.projectId === projectId ||
      // 레거시(무projectId) 또는 quick으로 잘못 남은 동일주소 건은 주소매칭 폴백.
      ((!h.projectId || h.mode === "quick") && projAddr && h.address &&
        (norm(h.address) === projAddr || norm(h.address).includes(projAddr) || projAddr.includes(norm(h.address)))),
    );
  })();

  const compareResults = visibleHistory
    .filter((h) => compareSelection.has(h.id))
    .map((h) => h.result);

  const pipelineCompleted = stages.every((s) => s.status === "completed" || s.status === "skipped");
  const hasSummary = Object.keys(summary).length > 0;

  /* ── Detail View ── */
  if (viewMode === "detail" && lastResult) {
    return (
      <div className="space-y-4">
        <button
          type="button"
          onClick={() => setViewMode("pipeline")}
          className="flex items-center gap-2 text-sm font-bold text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="m15 18-6-6 6-6" />
          </svg>
          진행 단계으로 돌아가기
        </button>
        <PipelineResultDetail result={lastResult} onRerun={handleRerun} addresses={allAddresses.map((a) => a.fullAddress)} />
      </div>
    );
  }

  /* ── Compare View ── */
  if (viewMode === "compare" && compareResults.length >= 2) {
    return (
      <div className="space-y-4">
        <button
          type="button"
          onClick={() => {
            setViewMode("pipeline");
            setCompareSelection(new Set());
          }}
          className="flex items-center gap-2 text-sm font-bold text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="m15 18-6-6 6-6" />
          </svg>
          진행 단계으로 돌아가기
        </button>
        <ProjectCompareView results={compareResults} />
      </div>
    );
  }

  /* ── Pipeline View (default) ── */
  return (
    <section className="rounded-2xl sm:rounded-[2rem] border border-[var(--line-strong)] bg-[var(--surface-soft)] shadow-[var(--shadow-xl)] overflow-hidden transition-all relative">
      <div className="absolute inset-0 bg-[url('https://www.transparenttextures.com/patterns/cubes.png')] opacity-[0.02] pointer-events-none" />

      {/* ── Header ── */}
      <div className="px-6 py-5 sm:px-8 sm:py-6 border-b border-[var(--line)] bg-gradient-to-r from-[var(--accent-strong)]/5 to-transparent">
        <div className="flex items-center gap-3 mb-1">
          <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-[var(--accent-soft)] border border-[var(--accent-strong)]/20">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--accent-strong)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 3v18h18" /><path d="m19 9-5 5-4-4-3 3" /></svg>
          </div>
          <h2 className="text-lg sm:text-xl font-[800] tracking-tight text-[var(--text-primary)]">
            프로젝트 자동 분석 진행 단계
          </h2>
        </div>
        <p className="text-sm font-medium text-[var(--text-secondary)] tracking-tight ml-11">
          {projectMode
            ? "프로젝트 주소로 부지분석을 자동 수행합니다. 완료 후 사업모델 추천으로 이어집니다."
            : "주소를 검색하면 부지분석 → 결과 확인 → 나머지 6단계를 순차 수행합니다"}
        </p>
      </div>

      {/* ── Address Search Input (GlobalAddressSearch) — 대시보드 체험 모드 ── */}
      {!projectMode && (
        <div className="px-6 py-4 sm:px-8 border-b border-[var(--line)]">
          <div className="flex flex-col sm:flex-row gap-3">
            <div className="flex-1">
              <GlobalAddressSearch
                single={false}
                onChange={handleAddressChange}
                placeholder="주소를 검색하세요 (예: 서울 강남구 역삼동)"
                disabled={isRunning}
                writeToContext={false}
              />
            </div>
            <button
              type="button"
              onClick={runSiteAnalysis}
              disabled={isRunning || !address.trim()}
              className="h-12 px-6 sm:px-8 rounded-xl bg-gradient-to-br from-[var(--accent-strong)] to-[var(--accent)] text-white text-sm font-bold tracking-wide shadow-[var(--shadow-glow)] transition-all hover:scale-[1.03] active:scale-[0.97] disabled:opacity-50 disabled:hover:scale-100 disabled:cursor-not-allowed whitespace-nowrap flex items-center justify-center gap-2 shrink-0"
            >
              {isRunning && workflowPhase === "input" ? (
                <>
                  <svg className="animate-spin" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><path d="M21 12a9 9 0 1 1-6.219-8.56" /></svg>
                  부지분석 중...
                </>
              ) : (
                <>
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M20 10c0 4.993-5.539 10.193-7.399 11.799a1 1 0 0 1-1.202 0C9.539 20.193 4 14.993 4 10a8 8 0 0 1 16 0" /><circle cx="12" cy="10" r="3" /></svg>
                  부지분석 시작
                </>
              )}
            </button>
          </div>
          {allAddresses.length > 0 && (
            <div className="mt-2 text-xs font-medium text-[var(--text-secondary)]">
              {allAddresses.length === 1 ? (
                <p>선택된 주소: <span className="text-[var(--accent-strong)]">{address}</span></p>
              ) : (
                // 대량 필지: 전체 주소를 콤마로 나열하지 않고 대표 + "외 N필지"로 간결 표기(가독성).
                <p>선택된 필지: <span className="text-[var(--accent-strong)]">{allAddresses.length}개</span> — {(allAddresses[0]?.jibunAddress || allAddresses[0]?.fullAddress || address)}{allAddresses.length > 1 ? ` 외 ${allAddresses.length - 1}필지` : ""}</p>
              )}
            </div>
          )}
        </div>
      )}

      {/* ── Project Mode: 읽기 전용 주소 바 + 재분석 ── */}
      {projectMode && (
        <div className="px-6 py-4 sm:px-8 border-b border-[var(--line)] flex flex-wrap items-center gap-3">
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[var(--accent-soft)] text-[var(--accent-strong)]">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M20 10c0 4.993-5.539 10.193-7.399 11.799a1 1 0 0 1-1.202 0C9.539 20.193 4 14.993 4 10a8 8 0 0 1 16 0" /><circle cx="12" cy="10" r="3" /></svg>
          </span>
          <div className="flex-1 min-w-0">
            <p className="text-[11px] font-semibold tracking-normal text-[var(--text-hint)]">분석 대상 주소</p>
            <p className="text-sm font-bold text-[var(--text-primary)] truncate">{address || "주소 정보 없음"}</p>
          </div>
          <button
            type="button"
            onClick={runSiteAnalysis}
            disabled={isRunning || !address.trim()}
            className="h-9 px-4 rounded-lg border border-[var(--line-strong)] text-xs font-bold text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--surface-strong)] transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2 shrink-0"
          >
            {isRunning && workflowPhase === "input" ? (
              <>
                <svg className="animate-spin" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><path d="M21 12a9 9 0 1 1-6.219-8.56" /></svg>
                부지분석 중...
              </>
            ) : (
              "부지 분석 다시"
            )}
          </button>
        </div>
      )}

      {/* ── Site Analysis Review Banner ── */}
      {workflowPhase === "site_review" && (
        <div className="mx-6 sm:mx-8 mt-4 rounded-xl border border-[var(--accent-strong)]/30 bg-[var(--accent-strong)]/5 px-5 py-4">
          <div className="flex items-start gap-3">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[var(--accent-strong)]/20 text-[var(--accent-strong)]">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M20 6 9 17l-5-5" /></svg>
            </div>
            <div className="flex-1">
              <h4 className="text-sm font-bold text-[var(--text-primary)]">부지분석 완료 — 결과를 확인하세요</h4>
              <p className="text-xs text-[var(--text-secondary)] mt-1">
                {projectMode
                  ? "아래 부지분석 결과를 확인한 후, “사업모델 추천 보기”를 눌러 이 부지에 최적인 사업모델 Top 3를 추천받으세요."
                  : "아래 부지분석 결과를 확인한 후, 만족스러우면 “다음 단계 진행”을 눌러 설계→공사비→수지분석을 이어서 실행합니다."}
              </p>
              <div className="flex flex-wrap gap-3 mt-3">
                {projectMode ? (
                  <>
                    <button
                      type="button"
                      onClick={() => onSiteAnalysisComplete?.()}
                      className="h-10 px-6 rounded-xl bg-gradient-to-br from-[var(--accent-strong)] to-[var(--accent)] text-white text-sm font-bold shadow-[var(--shadow-glow)] hover:scale-[1.03] active:scale-[0.97] transition-all flex items-center gap-2"
                    >
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="m22 12-4-4v3H3v2h15v3z" /></svg>
                      사업모델 추천 보기
                    </button>
                    <button
                      type="button"
                      onClick={runRemainingStages}
                      disabled={isRunning}
                      className="h-10 px-4 rounded-xl border border-[var(--line-strong)] text-sm font-bold text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--surface-strong)] transition-all disabled:opacity-50 flex items-center gap-2"
                    >
                      {isRunning ? (
                        <>
                          <svg className="animate-spin" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><path d="M21 12a9 9 0 1 1-6.219-8.56" /></svg>
                          전체 분석 진행 중...
                        </>
                      ) : (
                        "전체 7단계 분석 계속"
                      )}
                    </button>
                  </>
                ) : (
                  <>
                    <button
                      type="button"
                      onClick={runRemainingStages}
                      disabled={isRunning}
                      className="h-10 px-6 rounded-xl bg-gradient-to-br from-[var(--accent-strong)] to-[var(--accent)] text-white text-sm font-bold shadow-[var(--shadow-glow)] hover:scale-[1.03] active:scale-[0.97] transition-all disabled:opacity-50 flex items-center gap-2"
                    >
                      {isRunning ? (
                        <>
                          <svg className="animate-spin" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><path d="M21 12a9 9 0 1 1-6.219-8.56" /></svg>
                          약식 수지분석 중...
                        </>
                      ) : (
                        <>
                          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><polygon points="6 3 20 12 6 21 6 3" /></svg>
                          약식 수지분석 체험 (시장표준)
                        </>
                      )}
                    </button>
                    <button
                      type="button"
                      onClick={promoteToProject}
                      className="h-10 px-5 rounded-xl border border-[var(--accent-strong)]/50 bg-[var(--accent-strong)]/10 text-sm font-bold text-[var(--accent-strong)] hover:bg-[var(--accent-strong)]/20 transition-all flex items-center gap-2"
                    >
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12h14" /><path d="m12 5 7 7-7 7" /></svg>
                      프로젝트로 저장 · 전체 분석
                    </button>
                    <button
                      type="button"
                      onClick={() => { setWorkflowPhase("input"); setStages(DEFAULT_STAGES.map((s) => ({ ...s }))); }}
                      className="h-10 px-4 rounded-xl border border-[var(--line-strong)] text-sm font-bold text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--surface-strong)] transition-all"
                    >
                      다른 주소 분석
                    </button>
                  </>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── Error Banner ── */}
      {error && (
        <div className="mx-6 sm:mx-8 mt-4 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm font-medium text-red-400">
          {error}
        </div>
      )}

      {/* ── Stage List ── */}
      <div className="px-6 py-4 sm:px-8 space-y-1">
        {stages.map((stage) => {
          const isExpanded = expandedStage === stage.stage;
          const hasData = Object.keys(stage.data).length > 0;

          // ② 대시보드(체험) 모드: 부지·약식수지 외 단계는 잠금 행으로 표시(상세 비노출) →
          //    프로젝트 생성 시 제공. 구독 전환 관문(차별화).
          const dashboardLocked = !projectMode && !TEASER_STAGES.has(stage.stage);
          if (dashboardLocked) {
            return (
              <div
                key={stage.stage}
                className="rounded-xl border border-dashed border-[var(--line)] overflow-hidden opacity-80"
              >
                <button
                  type="button"
                  onClick={promoteToProject}
                  className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-[var(--surface-strong)] transition-colors"
                >
                  <span className="text-sm font-bold text-[var(--text-tertiary)] w-5 shrink-0">
                    {STAGE_NUMBERS[stage.stage] ?? ""}
                  </span>
                  <span className="flex h-6 w-6 items-center justify-center rounded-full bg-[var(--surface-strong)] text-[var(--text-hint)]">
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect width="18" height="11" x="3" y="11" rx="2" ry="2" /><path d="M7 11V7a5 5 0 0 1 10 0v4" /></svg>
                  </span>
                  <span className="flex-1 text-sm font-bold tracking-tight text-[var(--text-tertiary)]">
                    {STAGE_LABELS[stage.stage] ?? stage.stage}
                  </span>
                  <span className="text-[11px] font-bold text-[var(--accent-strong)] whitespace-nowrap">
                    프로젝트 생성 시 제공 →
                  </span>
                </button>
              </div>
            );
          }

          return (
            <div
              key={stage.stage}
              ref={(el) => { stageRowRefs.current[stage.stage] = el; }}
              className="rounded-xl border border-[var(--line)] overflow-hidden transition-all scroll-mt-24"
            >
              {/* Stage Row */}
              <button
                type="button"
                onClick={() => hasData && toggleStage(stage.stage)}
                className={`w-full flex items-center gap-3 px-4 py-3 text-left transition-colors ${hasData ? "cursor-pointer hover:bg-[var(--surface-strong)]" : "cursor-default"
                  } ${stage.status === "running" ? "bg-[var(--accent-strong)]/5" : "bg-transparent"}`}
              >
                {/* Number */}
                <span className="text-sm font-bold text-[var(--text-tertiary)] w-5 shrink-0">
                  {STAGE_NUMBERS[stage.stage] ?? ""}
                </span>

                {/* Icon */}
                {statusIcon(stage.status)}

                {/* Label */}
                <span className={`flex-1 text-sm font-bold tracking-tight ${stage.status === "completed" ? "text-[var(--text-primary)]" :
                    stage.status === "running" ? "text-[var(--accent-strong)]" :
                      stage.status === "failed" ? "text-red-400" :
                        "text-[var(--text-tertiary)]"
                  }`}>
                  {STAGE_LABELS[stage.stage] ?? stage.stage}
                </span>

                {/* Status */}
                <span className={`text-xs font-medium ${stage.status === "completed" ? "text-emerald-400" :
                    stage.status === "running" ? "text-[var(--accent-strong)]" :
                      stage.status === "failed" ? "text-red-400" :
                        "text-[var(--text-hint)]"
                  }`}>
                  {statusLabel(stage.status)} {formatDuration(stage.duration_ms)}
                </span>

                {/* Expand arrow */}
                {hasData && (
                  <svg
                    width="14"
                    height="14"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="var(--text-tertiary)"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    className={`shrink-0 transition-transform duration-200 ${isExpanded ? "rotate-180" : ""}`}
                  >
                    <path d="m6 9 6 6 6-6" />
                  </svg>
                )}
              </button>

              {/* Expanded Detail */}
              {isExpanded && hasData && (
                <div className="px-4 pb-4 pt-1 border-t border-[var(--line)] bg-[var(--surface-strong)]/50">
                  {stage.error && (
                    <p className="text-xs text-red-400 mb-2">{stage.error}</p>
                  )}
                  {stage.stage === "site_analysis" ? (
                    <SiteAnalysisDetail data={stage.data} parcels={allAddresses.map((a) => a.fullAddress)} />
                  ) : (
                    <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                      {Object.entries(stage.data)
                        .filter(([key, value]) => !HIDDEN_GRID_FIELDS.has(key) && !(value && typeof value === "object"))
                        .map(([key, value]) => (
                          <div key={key} className="rounded-lg bg-[var(--surface)] border border-[var(--line)] px-3 py-2">
                            <p className="text-[10px] font-bold text-[var(--text-hint)] tracking-wider mb-0.5">
                              {FIELD_LABELS[key] || key.replace(/_/g, " ")}
                            </p>
                            <p className="text-xs font-bold text-[var(--text-primary)] truncate">
                              {displayFieldValue(key, value)}
                            </p>
                            {stage.stage === "feasibility" && FIELD_BASIS[key] && (
                              <p className="mt-0.5 text-[9px] leading-tight text-[var(--text-hint)]">
                                {FIELD_BASIS[key]}
                              </p>
                            )}
                          </div>
                        ))}
                    </div>
                  )}
                  {/* 총사업비 라인아이템(실무 수지) — feasibility 단계에만 */}
                  {stage.stage === "feasibility" && stage.data.cost_breakdown != null
                    && typeof stage.data.cost_breakdown === "object" && (
                    <div className="mt-3 overflow-hidden rounded-lg border border-[var(--line)]">
                      <div className="bg-[var(--surface-muted)] px-3 py-1.5 text-[10px] font-black tracking-wider text-[var(--text-secondary)]">
                        총사업비 구성 (실무 라인아이템)
                      </div>
                      <table className="w-full text-[11px]">
                        <tbody>
                          {COST_BREAKDOWN_ORDER
                            .filter((k) => (stage.data.cost_breakdown as Record<string, number>)[k] != null)
                            .map((k) => {
                              const v = (stage.data.cost_breakdown as Record<string, number>)[k];
                              return (
                                <tr key={k} className="border-t border-[var(--line)]">
                                  <td className="px-3 py-1 text-[var(--text-secondary)]">
                                    {k}
                                    {COST_BASIS[k] && (
                                      <span className="block text-[9px] leading-tight text-[var(--text-hint)]">{COST_BASIS[k]}</span>
                                    )}
                                  </td>
                                  <td className="px-3 py-1 text-right font-bold text-[var(--text-primary)] align-top">
                                    {(v / 1e8).toLocaleString(undefined, { maximumFractionDigits: 1 })}억
                                  </td>
                                </tr>
                              );
                            })}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* ── 대시보드(체험) 약식 분석 안내 — 상세는 프로젝트 생성 후 ── */}
      {!projectMode && (
        <div className="mx-6 sm:mx-8 mb-5 rounded-xl border border-[var(--accent-strong)]/25 bg-[var(--accent-strong)]/5 px-4 py-3">
          <div className="flex items-start gap-2.5">
            <span className="mt-0.5 text-[var(--accent-strong)]">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10" /><path d="M12 16v-4" /><path d="M12 8h.01" /></svg>
            </span>
            <div className="flex-1 min-w-0">
              <p className="text-xs font-bold text-[var(--text-primary)]">
                본 대시보드는 <span className="text-[var(--accent-strong)]">부지분석·약식 수지분석(시장표준 기반)</span> 체험을 제공합니다.
              </p>
              <p className="mt-0.5 text-[11px] leading-5 text-[var(--text-secondary)]">
                설계·공사비·금융·ESG·인허가·보고서 등 <b>상세 전주기 분석은 프로젝트를 생성</b>하면 단계별 데이터가 누적·고도화되어 제공됩니다.
              </p>
              <button
                type="button"
                onClick={promoteToProject}
                className="mt-2 inline-flex items-center gap-1.5 rounded-lg bg-[var(--accent-strong)] px-3.5 py-1.5 text-[11px] font-black text-white hover:opacity-90 transition-all"
              >
                프로젝트 생성하고 전체 분석 시작
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12h14" /><path d="m12 5 7 7-7 7" /></svg>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Summary Cards + Detail Button ── */}
      {pipelineCompleted && hasSummary && (
        <div className="px-6 pb-6 sm:px-8 sm:pb-8">
          <div className="rounded-xl border border-[var(--accent-strong)]/20 bg-gradient-to-br from-[var(--accent-soft)]/30 to-transparent p-4 sm:p-6">
            <h3 className="text-sm font-bold text-[var(--text-primary)] tracking-[0.1em] mb-4 flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-[var(--accent-strong)] animate-pulse" />
              핵심 지표 요약
            </h3>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {SUMMARY_CARDS.filter((card) => projectMode || TEASER_STAGES.has(card.source)).map((card) => {
                const stageData = summary[card.source];
                const rawValue = stageData?.[card.key];
                const displayValue = card.format ? card.format(rawValue) : formatNumber(rawValue);

                return (
                  <div
                    key={card.key}
                    className="rounded-xl bg-[var(--surface)] border border-[var(--line-strong)] p-4 text-center shadow-sm hover:shadow-[var(--shadow-glow)] hover:border-[var(--accent)] hover:-translate-y-0.5 transition-all duration-300"
                  >
                    <p className="text-[10px] font-bold text-[var(--text-hint)] tracking-[0.15em] uppercase mb-2">
                      {card.label}
                    </p>
                    <p className="text-xl sm:text-2xl font-[900] text-[var(--text-primary)] tracking-tight leading-none">
                      {displayValue}
                    </p>
                    {card.unit && (
                      <p className="text-[10px] font-medium text-[var(--text-tertiary)] mt-1">{card.unit}</p>
                    )}
                  </div>
                );
              })}
            </div>

            {/* Detail Report Button */}
            {lastResult && projectMode && (
              <div className="mt-4 flex justify-center">
                <button
                  type="button"
                  onClick={() => setViewMode("detail")}
                  className="h-10 px-6 rounded-xl bg-gradient-to-br from-[var(--accent-strong)] to-[var(--accent)] text-white text-sm font-bold shadow-[var(--shadow-glow)] hover:scale-[1.03] active:scale-[0.97] transition-all flex items-center gap-2"
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z" />
                    <path d="M14 2v6h6" />
                    <path d="M16 13H8" />
                    <path d="M16 17H8" />
                    <path d="M10 9H8" />
                  </svg>
                  상세 보고서 보기
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── Analysis History (프로젝트별 격리) ── */}
      {visibleHistory.length > 0 && (
        <div className="px-6 pb-6 sm:px-8 sm:pb-8">
          <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-strong)]/30 p-4 sm:p-5">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-bold text-[var(--text-primary)] tracking-[0.08em] flex items-center gap-2">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--text-secondary)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="12" cy="12" r="10" />
                  <polyline points="12 6 12 12 16 14" />
                </svg>
                분석 이력
              </h3>
              {compareSelection.size >= 2 && (
                <button
                  type="button"
                  onClick={startCompare}
                  className="h-8 px-4 rounded-lg bg-gradient-to-br from-[var(--accent-strong)] to-[var(--accent)] text-white text-xs font-bold shadow-[var(--shadow-glow)] hover:scale-[1.03] active:scale-[0.97] transition-all flex items-center gap-1.5"
                >
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M16 3h5v5" />
                    <path d="M8 3H3v5" />
                    <path d="M12 22v-8.3a4 4 0 0 0-1.172-2.872L3 3" />
                    <path d="m15 9 6-6" />
                  </svg>
                  비교 분석 ({compareSelection.size}개)
                </button>
              )}
            </div>
            <div className="space-y-1.5">
              {visibleHistory.map((entry) => {
                const isSelected = compareSelection.has(entry.id);
                const profitRate = entry.result.summary?.feasibility?.profit_rate_pct;
                const date = new Date(entry.completedAt);
                const dateStr = `${date.getMonth() + 1}/${date.getDate()} ${date.getHours().toString().padStart(2, "0")}:${date.getMinutes().toString().padStart(2, "0")}`;

                return (
                  <div
                    key={entry.id}
                    className={`flex items-center gap-3 rounded-xl border px-4 py-2.5 transition-all ${isSelected
                        ? "border-[var(--accent-strong)]/50 bg-[var(--accent-strong)]/5 ring-1 ring-[var(--accent-strong)]/20"
                        : "border-[var(--line)] bg-[var(--surface)] hover:bg-[var(--surface-strong)]"
                      }`}
                  >
                    {/* Compare checkbox */}
                    <button
                      type="button"
                      onClick={() => toggleCompareSelect(entry.id)}
                      className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-md border-2 transition-all ${isSelected
                          ? "border-[var(--accent-strong)] bg-[var(--accent-strong)] text-white"
                          : "border-[var(--line-strong)] bg-transparent hover:border-[var(--accent-strong)]/50"
                        }`}
                      title="비교 대상 선택"
                    >
                      {isSelected && (
                        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M20 6 9 17l-5-5" />
                        </svg>
                      )}
                    </button>

                    {/* Address — 클릭 시 이전 분석 재조회 */}
                    <button
                      type="button"
                      onClick={() => openHistory(entry)}
                      className="flex-1 min-w-0 text-left cursor-pointer group/hist"
                      title="클릭하여 이 분석 결과 다시 보기"
                    >
                      <p className="text-xs font-bold text-[var(--text-primary)] truncate group-hover/hist:text-[var(--accent-strong)] transition-colors">
                        {entry.address}
                      </p>
                      <p className="text-[10px] text-[var(--text-hint)]">{dateStr}</p>
                    </button>

                    {/* Profit rate badge */}
                    {typeof profitRate === "number" && (
                      <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 shrink-0">
                        {profitRate.toFixed(1)}%
                      </span>
                    )}

                    {/* View detail button */}
                    <button
                      type="button"
                      onClick={() => openHistory(entry)}
                      className="text-[10px] font-bold text-[var(--text-secondary)] hover:text-[var(--accent-strong)] transition-colors shrink-0 cursor-pointer"
                    >
                      상세
                    </button>

                    {/* Delete button */}
                    <button
                      type="button"
                      onClick={() => removeFromHistory(entry.id)}
                      className="shrink-0 rounded-md p-1 text-[var(--text-hint)] hover:text-red-500 hover:bg-red-500/10 transition-colors cursor-pointer"
                      title="이력 삭제"
                      aria-label="이력 삭제"
                    >
                      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M3 6h18" /><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                      </svg>
                    </button>
                  </div>
                );
              })}
            </div>
            {compareSelection.size > 0 && compareSelection.size < 2 && (
              <p className="text-[10px] text-[var(--text-hint)] mt-2 text-center">
                비교하려면 2개 이상 선택하세요 (최대 3개)
              </p>
            )}
          </div>
        </div>
      )}

      {/* 비회원 무료 1회 소진 — 가입/구독 유도 모달 */}
      {guestGateOpen && (
        <div className="fixed inset-0 z-[1000] flex items-center justify-center bg-black/50 backdrop-blur-sm p-4" onClick={() => setGuestGateOpen(false)}>
          <div className="w-full max-w-sm rounded-2xl border border-[var(--line-strong)] bg-[var(--surface)] p-6 shadow-2xl text-center" onClick={(e) => e.stopPropagation()}>
            <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-[var(--accent-soft)] text-[var(--accent-strong)]"><Lock className="size-6" aria-hidden /></div>
            <h3 className="text-lg font-bold text-[var(--text-primary)]">무료 체험을 모두 사용했어요</h3>
            <p className="mt-2 text-sm leading-relaxed text-[var(--text-secondary)]">
              비회원은 토지분석을 <b>1회</b> 무료로 이용할 수 있습니다.<br />
              가입하면 추가로 무료 분석을, 구독하면 제한 없이 이용할 수 있습니다.
            </p>
            <div className="mt-5 flex flex-col gap-2">
              <a href={`/${locale || "ko"}/login`}
                className="rounded-xl bg-gradient-to-r from-[var(--accent-strong)] to-[#085d73] py-3 text-sm font-black text-white">
                로그인 / 회원가입
              </a>
              <button onClick={() => setGuestGateOpen(false)}
                className="rounded-xl border border-[var(--line-strong)] py-2.5 text-sm font-bold text-[var(--text-secondary)]">
                닫기
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
