import { create } from "zustand";
import { persist } from "zustand/middleware";
import { createDebouncedStorage } from "@/lib/debounced-storage";
import { effectiveLandAreaSqm } from "@/lib/site-area";
import { resolveEquityWon, DEFAULT_EQUITY_RATIO_PCT } from "@/lib/finance/leverage";
import type { DecisionBrief } from "@/components/projects/decision-brief-types";
import type { DesignCompliance } from "@/lib/design-contract";

/* ── Types ── */

interface AnalysisResult {
  module: string;
  completedAt: string;
  summary: Record<string, unknown>;
}

/** 개별 필지 정보 */
interface ParcelData {
  pnu: string;
  address: string;
  areaSqm: number;
  landCategory: string; // 지목
  ownerType: string;
  zoneCode?: string | null; // 용도지역 — 다필지 통합 시 면적가중 우세용도 산정에 사용(없으면 면적만 통합)
  // ── 지도 복원용(옵션B, additive·persist 왕복 무손상) — 필지별 좌표·경계·속성을 SSOT에 영속해
  //    precheck 재진입 시 지도 오버레이·POI·개발계획 레이어를 필지별로 정밀 복원한다. 미확보는 생략(무날조).
  lat?: number | null;
  lon?: number | null;
  geometry?: unknown; // GeoJSON geometry(필지 경계) — 있으면 재조회 없이 즉시 폴리곤 렌더
  officialPricePerSqm?: number | null; // 개별공시지가(원/㎡)
  builtYear?: number | null;
  buildingAgeYears?: number | null;
}

/** 토지이용계획 규제 항목 */
interface LandUseDistrict {
  districtName: string;
  districtCode: string;
  conflictStatus: string;
}

/** 지자체 조례 정보 */
interface OrdinanceData {
  sido: string;
  sigungu: string | null;
  // 무목업: 미해결 한도를 0%로 강제하지 않고 null 유지(표시단 "—").
  nationalBcr: number | null;
  nationalFar: number | null;
  ordinanceBcr: number | null;
  ordinanceFar: number | null;
  effectiveBcr: number | null;
  effectiveFar: number | null;
  source: string; // "법제처API" | "캐시DB" | "법정상한"
  legalBasis: string;
  // 실효값이 아직 '법정상한 시드'(조례/계획 승격 전 잠정값)인지 표기.
  // true면 하류·표시단이 effectiveBcr/Far를 '확정 실효'가 아닌 '잠정 법정상한'으로 구분해야 한다.
  // calc_effective_far 실값 승격(zoning/comprehensive) 시 false 또는 미설정으로 갱신.
  seededFromLegal?: boolean;
}

/** 건축물대장 정보 */
interface BuildingInfo {
  buildingName: string;
  mainPurpose: string;
  totalAreaSqm: number;
  groundFloors: number;
  structure: string;
  useApprovalDate: string;
}

/** 공시지가 정보 */
interface OfficialPriceData {
  pnu: string;
  year: number;
  pricePerSqm: number;
}

/** 종상향/종변경 잠재 시나리오(미래 토지특성 SSOT) — /zoning/comprehensive 산출 보존(additive).
 *  배경: comprehensive 응답의 풍부한 per-scenario(경로·목표용도·예상용적·가능성·법령근거)는 그동안
 *  로컬 state(L3)에만 머물러 하류(추천·설계·수지)가 읽지 못했다. 이를 SSOT에 보존해 토지특성
 *  foundation(Stage B 미래)이 단일 진실원에서 소비되게 한다(U2). 무목업: 미해소 필드는 null. */
export interface UpzoningScenarioData {
  /** 경로명(예: "준주거 → 일반상업"). 없으면 null. */
  path: string | null;
  /** 목표 용도지역(없으면 null). */
  targetZone: string | null;
  /** 가능성 등급('상'|'중'|'하'). 미해소 null. */
  feasibility: string | null;
  /** 예상 재산정 용적률 하단(%) — 없으면 null. */
  expectedFarLowPct: number | null;
  /** 예상 재산정 용적률 상단(%) — 없으면 null. */
  expectedFarHighPct: number | null;
  /** 근거 법령(없으면 null). */
  legalBasis: string | null;
  /** 도출 이유(feasibility_reason 등). 없으면 null. */
  rationale: string | null;
}

/** 기초 데이터 파이프라인 — 모든 모듈의 근간 */
interface SiteAnalysisData {
  // 기본 정보
  estimatedValue: number | null;
  // ★다필지면 통합 합계가 들어온다(대표 1필지 아님). 하류(수지·설계·공사비)는 이 값을 부지면적으로 본다.
  landAreaSqm: number | null;
  zoneCode: string | null;
  address: string | null;
  pnu: string | null;

  // ── 다필지 통합 면적 메타(additive·하위호환) — 단일필지면 미기록(아래 전부 부재) ──
  // 통합 합계 면적(㎡): landAreaSqm와 동일값을 별도로 명시 보관(통합인지 명확히 구분용).
  landAreaSqmTotal?: number | null;
  // 대표 1필지 면적(㎡): 통합 전 "첫 필지" 면적(참고·비교용).
  repLandAreaSqm?: number | null;
  // 유효 필지 수(면적>0·status ok만 집계).
  parcelCount?: number | null;
  // 용도지역이 2종 이상 섞였는지(혼합지). 하류가 단일 용도 가정을 피하도록 신호.
  zoneMixed?: boolean;

  // ── 토지/법규 심층 결과(rich) — /zoning/analyze 산출물 SSOT 보존(additive·옵셔널) ──
  // 하류(추천·설계·수지·분석 DAG 노드)가 /zoning/analyze 재호출 없이 읽도록 보존.
  // 단일필지=해당 필지값, 다필지=대표/통합 기준값. 미확보 시 부재(옵셔널) — 0 강제 금지.
  nationalFarPct?: number | null;     // 법정 상한 용적률(%)
  nationalBcrPct?: number | null;     // 법정 상한 건폐율(%)
  effectiveFarPct?: number | null;    // 현행 실효 용적률(%) — calc_effective_far(min 법정/조례/계획상한)
  effectiveBcrPct?: number | null;    // 현행 실효 건폐율(%)
  farBasis?: string | null;           // 실효용적률 최종 근거 라벨
  roadWidthM?: number | null;         // 접도 도로폭(m·NED 도로접면 추정) — 시니어 심의 접도 CSP 입력원

  // ── 다필지 통합 실효 한도/용도지역(integrated SSOT) — /zoning/integrated-analysis 산출 보존 ──
  // 단일 PNU(대표 1필지) 유래 effective*Pct/zoneCode가 혼재 다필지의 진실원천이 아니므로, 통합 경로
  // (ProjectAnalysisSummary가 호출)의 면적가중 blended 실효·dominant 용도지역을 SSOT에 보존한다.
  // 하류 소비처는 resolveFarPct/resolveBcrPct/resolveDominantZone(lib/zoning-ssot)로 이 값을 우선
  // 읽어 "통합값은 일부 컴포넌트엔 prop으로만 전파되고 나머지는 대표값을 읽던" 읽기 분기를 일원화한다.
  // 단일필지/통합 미확보면 부재(옵셔널) → 헬퍼가 effective*Pct/zoneCode로 폴백(무회귀).
  integratedFarEffPct?: number | null;  // 면적가중 통합 실효 용적률(%·blended_far_eff_pct)
  integratedBcrEffPct?: number | null;  // 면적가중 통합 실효 건폐율(%·blended_bcr_eff_pct)
  dominantZoneCode?: string | null;     // 통합 대표(우세) 용도지역(dominant_zone)

  upzoningPotentialFarHigh?: number | null;  // 종상향 잠재 상한 용적률(%) (potential_far_range 상단)
  upzoningFeasibilityTop?: string | null;    // 최상 가능성 등급('상'/'중'/'하') — 없으면 null
  // 종상향 per-scenario 상세(미래 토지특성 SSOT) — comprehensive 산출 보존(additive·옵셔널).
  // 미확보(단일 analyze 경로 등) 시 부재/null → buildLandProfile이 집계값으로 폴백(무목업).
  upzoningScenarios?: UpzoningScenarioData[] | null;
  specialParcel?: {                   // 특이부지 게이트 요약 — 없으면 null
    isSpecial: boolean;
    developability: string | null;    // POSSIBLE|CONDITIONAL|PRECONDITION|RESTRICTED|BLOCKED 등
    resolvable: string | null;        // YES|CONDITIONAL|NO
    factors: string[];
    honest: string | null;
  } | null;

  // 한도 산출 근거·법령 원문 링크(EvidencePanel/LegalRefChip 소비형) — 부지분석/법규단계가
  //   백엔드 build_evidence_block(evidence[{claim,value,basis,source,link,confidence}] + legal_refs)을
  //   SSOT에 가산 보존(있을 때만·옵셔널). 소비처(예: 정본 메트릭바 근거 인스펙터)가 재호출 없이 읽는다.
  //   없으면 부재 → 소비처는 "근거 없음"으로 정직 처리(무목업). ComplianceData.evidence와 대칭 계약.
  evidence?: unknown[] | null; // 근거 트레이스(Evidence[] 구조)
  legalRefs?: unknown[] | null; // 법령 원문 링크(레지스트리 출력)

  // 다필지 정보 (LAYER 0) — 선택적 (점진적 확장)
  parcels?: ParcelData[];
  landUseDistricts?: LandUseDistrict[];
  ordinance?: OrdinanceData | null;
  buildingInfo?: BuildingInfo | null;
  officialPrices?: OfficialPriceData[];
  coordinates?: { lat: number; lon: number } | null;
  infrastructure?: Record<string, unknown> | null;
  dataSource?: string;
  fetchedAt?: string | null;
}

interface DesignData {
  totalGfaSqm: number | null;
  floorCount: number | null;
  buildingType: string | null;
  bcr: number | null;
  far: number | null;
  // 세대 구성(도면·해석·수지 다운스트림의 "데이터 없음" 해소용 SSOT)
  unitCount?: number | null;        // 총 세대수
  unitTypes?: string[] | null;      // 평형 구성(예: ["59A","84A"])
  efficiencyPct?: number | null;    // 전용률(%)
  daylightNorth?: boolean | null;   // P5: 정북일조 단계후퇴(북측 상부 매스 후퇴) 적용 여부
  // 시니어 자문(심의 CSP) 입력원 — 설계엔진 산출. 미확보면 null(평가 생략·무목업).
  heightM?: number | null;          // 설계 건물 높이(m·building_height_m)
  maxHeightM?: number | null;       // 법정 높이 한도(m·max_height_m·0/null=무제한/미산정)
  // ── 매스 기하(massGeom) — site/generate가 확정한 건물 덩어리 모양을 draw(CAD·BIM 3D)로 전파 ──
  // 왜 필요한가(쉬운 설명): 설계 생성 단계에서 정한 "건물 덩어리"(podium-tower 같은 2단 매스 포함)가
  //   3D 도면 단계로 넘어오지 않아, 도면 단계가 그 정보를 모른 채 단일 박스로 다시 역산하던 문제를 푼다.
  //   이 필드가 있으면 도면 단계가 /mass 재산출을 건너뛰고 이 모양 그대로 3D를 그린다.
  // 전부 옵셔널/nullable — 구 스냅샷·persist 왕복(저장→복원) 무손상. 미확보 값은 null(가짜 생성 금지).
  massGeom?: {
    buildingWidthM?: number | null;   // 건물 폭(m) — 단일 매스 또는 대표 매스
    buildingDepthM?: number | null;   // 건물 깊이(m)
    footprintSqm?: number | null;     // 건축면적(㎡·한 층이 땅을 덮는 넓이) — 부지면적 아님
    massingProfile?: string | null;   // 매스 형태("podium_tower" 등) — 없으면 null
    // 저층 큰 판(podium) — 주상복합 2단 매스의 아래 덩어리. 없으면 null.
    podium?: { widthM?: number | null; depthM?: number | null; floors?: number | null; footprintSqm?: number | null } | null;
    // 고층 작은 판(tower) — 주상복합 2단 매스의 위 덩어리. 없으면 null.
    tower?: { widthM?: number | null; depthM?: number | null; floors?: number | null; footprintSqm?: number | null } | null;
    floorsForUnits?: number | null;   // 주거 세대가 들어가는 층수(podium 상가층 제외) — 없으면 null
    residentialGfaSqm?: number | null; // 주거 전용 연면적(㎡) — 없으면 null
  } | null;
  // ── C2R 계약(compliance) — 백엔드 설계엔진이 /mass·/bim 응답에 동봉하는 "근거·검증" 묶음 ──
  // 왜 필요한가(쉬운 설명): 백엔드는 매스(층수·면적)를 산출하면서 "어떤 법규가 어떤 값으로
  //   적용됐고(rule_trace), 기하가 정상인지(PASS/WARN/FAIL), 어느 산출인지(run_id·해시)"를
  //   같이 계산해 보낸다. 지금까지 프론트는 이걸 한 군데도 안 읽고 버렸다(감사 적발). 이 필드가
  //   있어야 그 근거를 store에 담아 사용자에게 "근거+링크"로 보여줄 수 있다.
  // 전부 옵셔널/nullable — 구 스냅샷·persist 왕복(저장→복원)·구 백엔드 응답 무손상(additive).
  //   값이 없으면 null(가짜 생성 금지) — 소비처는 null을 "없음/미산출"로 정직 표기한다.
  // 형태는 lib/design-contract.ts의 DesignCompliance(백엔드 envelope_result.py·design_contract.py와 1:1).
  compliance?: DesignCompliance | null;
}

interface FeasibilityData {
  totalCostWon: number | null;
  totalRevenueWon: number | null;
  profitRatePct: number | null;
  grade: string | null;
  // 투자수익성(ROI 뷰) 정합용 — 옵셔널·하위호환. reader 무영향, persist round-trip 보존.
  // equityWon: 자기자본 절대액(원). 사용자/에디터 직접입력 우선, 없으면 총사업비×equityRatioPct 자동산출.
  equityWon?: number | null;
  // ★SSOT: 자기자본 비율(%) — 투자수익성 요약과 DCF 패널이 공유하는 단일 슬롯(기본 10%).
  //   DCF에서 사용자가 바꾸면 요약도 즉시 반영되고, 총사업비가 나오면 equityWon이 자동 채워진다.
  //   optional·하위호환(구 스냅샷=undefined → updateFeasibilityData가 기본 10% 폴백).
  equityRatioPct?: number | null;
  // ★수동입력 플래그 — true는 "사용자가 자기자본 절대액을 직접 입력했다"는 뜻일 때만 세팅한다
  //  (FeasibilityEditorV2 양수 환류·ModuleInputForm 자기자본 입력). 자동파생(ratio×cost)이나
  //  DCF 비율 변경은 manual이 아니다(false/미설정). updateFeasibilityData는 이 플래그로만
  //  "보존 vs 재파생"을 가른다 — 옛 equityWon 값의 양수 여부로 판단하면 자동파생값이 다음
  //  cost 변경 때도 옛 cost에 앵커돼 실효비율이 침묵 이탈한다(재실행 경로 회귀).
  equityIsManual?: boolean;
  roiPct?: number | null;
  npvWon?: number | null;
  // (Phase C-1) 추천 개발방식 코드(M01~M15) — 상류 추천 노드가 산출한 최상위 추천 유형.
  // 수지계산(feasibility) 입력 development_type을 이 값으로 채워(미확보 시 백엔드 기본 M06 폴백),
  // "모든 수지가 일반분양(M06) 고정"되던 결함을 푼다. optional·하위호환(구 스냅샷=undefined→폴백).
  // ★stamp 주의: 이 필드는 setRecommendedDevType로만 patch하며 updatedAt.feasibility를 건드리지 않는다
  // (파생 recommend가 feasibility staleness를 오염시켜 수지 노드가 영영 skipped-fresh되는 함정 회피).
  developmentType?: string | null;
  // (Phase C-2) 적정분양가 → 수지 매출단가 환류값. 단위=원/평(KRW per pyeong).
  // 상류 sales(시장보고서)가 산출한 아파트 평당 실거래가(trade.아파트.per_pyeong.avg, 만원/평)를
  // ×10000 변환해 저장한다 — 백엔드 FeasibilityCalculateRequest.avg_sale_price_per_pyeong과
  // "동일 단위(원/평)"로 보관해 bodyBuilder가 무변환으로 그대로 전달하게 한다.
  // 이 값으로 수지가 실거래 기반 매출단가로 계산되어 "수지가 분양가에 무관하던" 결함을 푼다.
  // optional·하위호환(구 스냅샷=undefined→bodyBuilder가 미주입→백엔드 기본 동작, 무회귀).
  // ★stamp 주의: setSalesPricePerPyeong로만 patch하며 updatedAt.feasibility를 건드리지 않는다
  // (파생 sales가 feasibility staleness를 오염시켜 수지 노드가 영영 skipped-fresh되는 함정 회피).
  salePricePerPyeongWon?: number | null;
}

// 공사비 분석 결과(건축개요 기반) — 수지·사업성과 단일 데이터원으로 연동.
interface CostData {
  totalConstructionCostWon: number | null;
  perSqmWon: number | null;
  perPyeongWon: number | null;
  abovegroundWon: number | null;
  undergroundWon: number | null;
  landscapeWon: number | null;
  directWon: number | null;
  indirectWon: number | null;
  rangeMinWon: number | null;
  rangeMaxWon: number | null;
  source: string | null; // overview | bim | boq | saving_scenario (적산 합계 1방향 주입)
  // ── P5 추가(additive·옵셔널·무회귀): 기존 호출부(BoqDetailTable.applyToFeasibility 등)는
  //    이 3필드를 채우지 않아도 계속 동작한다(full-replace 계약이지만 optional). ──
  qtoSource?: string | null; // "bim" | "derived" — 백엔드 qto_source 그대로(물량 산출 정밀도 근거)
  priceTierSummary?: string | null; // 사람이 읽는 단가출처 요약(예: "표준 8·DB 3·fallback 1")
  baselineDeviationPct?: number | null; // 기본형건축비 대비 편차(%) — baseline_check.deviation_pct
}

interface EsgData {
  embodiedCarbonKg: number | null;
  operationalCarbonKg: number | null;
  totalCarbonPerSqm: number | null;
}

interface ComplianceData {
  bcrCompliant: boolean | null;
  farCompliant: boolean | null;
  heightCompliant: boolean | null;
  violations: string[];
  // (Fix #1·감사 HIGH) 법령허브 환류 — 법규단계(/regulation/analyze)가 산출한 정량 한도·근거를
  // SSOT에 보존(additive·옵셔널). 적합판정 불리언은 설계 산출 후 계산되지만, 한도/근거는 그 이전에도
  // 보존돼 하류(추천·설계·보고서)가 재호출 없이 읽는다. 백엔드 실응답키(limits/evidence/legal_refs/zone_type) 정합.
  limits?: Record<string, unknown> | null; // 정량 한도(건폐/용적/높이 등)
  evidence?: unknown[] | null; // 한도 산출 근거 트레이스(EvidencePanel 구조)
  legalRefs?: unknown[] | null; // 법령 원문 링크(레지스트리 출력)
  zoneType?: string | null; // 용도지역
}

/* ── 필드 단위 provenance(manualFields) 모델 ──
   siteAnalysis.landAreaSqm 등 평탄 필드를 다수 소비처가 직접 읽으므로 {value, source}
   래핑은 전 소비자 파괴 → store 톱레벨 "병행 맵"으로 필드별 수동/자동 출처를 관리한다.
   merge 가드: source:"user"로 stamp된 필드는 자동(auto) 갱신이 덮어쓰지 못하며,
   revertFieldToAuto로 해제해야 다음 자동 갱신부터 다시 허용된다. */
export type FieldSource = "auto" | "user";
export interface FieldProvenance {
  source: FieldSource;
  updatedAt: number; // stamp 시각(epoch ms)
}
// WP-V: design/esg는 update 액션에 merge 가드 적용, tax는 전용 store 데이터
// 필드가 아직 없어 타입만 선등록(향후 세금 모듈 provenance 대비 — additive).
export type ProvenanceModule =
  | "siteAnalysis"
  | "cost"
  | "design"
  | "tax"
  | "esg";
type ManualFieldsMap = Partial<
  Record<ProvenanceModule, Record<string, FieldProvenance>>
>;

/* ── Lifecycle stage order ── */

const LIFECYCLE_STAGES = [
  "site-analysis",
  "legal",
  "design",
  "bim",
  "construction",
  "feasibility",
  "finance",
  "esg",
  "permit",
  "report",
  // WP-17: 여정 출구 단계 append-only — "보고서→운영" 동선 연결.
  // append이므로 기존 영속 스냅샷(completedStages/currentStage: string)과 호환되고,
  // NextStageCta는 SSOT 순서를 보므로 무수정으로 "보고서 다음 = 운영"이 자동 활성된다.
  "operations",
] as const;

export type LifecycleStage = (typeof LIFECYCLE_STAGES)[number];

/* ── Per-project snapshot ──
   프로젝트별 분석 상태를 보관해, 프로젝트 전환/재선택 시 이전 분석을 복원한다.
   (이전 버그: setProject가 전환 시 모든 분석을 초기화 → 불러오기 시 0/없음으로 표시) */
/* ── 무거운 휘발성 분석(지형·환경·AVM·디지털트윈 등) 영속 캐시 ──
   매 방문 재실행을 막기 위해, 분석종류(kind)별로 입력 시그니처와 결과를 보관한다.
   재방문 시 시그니처가 같으면 검증된 결과를 즉시 재사용하고, 입력(원·첨부·보강 데이터)이
   바뀌면 결과는 유지하되 stale=true로 "재분석 제안"을 띄운다(자동 재실행 안 함). */
export type AnalysisCacheKind =
  | "terrain"
  | "environment"
  | "avm"
  | "digitalTwin"
  | "l3";
export interface AnalysisCacheEntry {
  signature: string; // 재분석 트리거가 되는 입력값들의 결정적 문자열
  data: unknown; // 분석 결과(패널이 캐스팅해 사용)
  at: number; // 산출 시각(epoch ms)
}

interface ProjectSnapshot {
  siteAnalysis: SiteAnalysisData | null;
  designData: DesignData | null;
  feasibilityData: FeasibilityData | null;
  costData: CostData | null;
  esgData: EsgData | null;
  complianceData: ComplianceData | null;
  completedStages: string[];
  currentStage: string | null;
  analysisResults: AnalysisResult[];
  updatedAt: Partial<Record<ModuleKey, number>>;
  analysisCache: Partial<Record<AnalysisCacheKind, AnalysisCacheEntry>>;
  // 필드 provenance 병행 맵 — 전환/재선택 시 수동값 보호가 함께 복원되도록 포함.
  // 구 스냅샷(필드 부재)은 복원 시 ?? {} 폴백(analysisCache와 동일 패턴).
  manualFields: ManualFieldsMap;
}

/* ── Staleness / 의존성 모델 ──
   모듈별 최종 갱신 타임스탬프(epoch ms)를 보관해, 업스트림이 다운스트림보다 최신이면
   다운스트림을 "stale(재계산 필요)"로 판정한다. 순수 store는 API를 호출하지 않으며,
   마운트된 다운스트림 컴포넌트가 isStale를 보고 1회 자동재계산하거나 CTA를 띄운다. */
type ModuleKey =
  | "siteAnalysis"
  | "design"
  | "cost"
  | "feasibility"
  | "finance"
  | "esg"
  | "compliance"
  // Stage1 통합 의사결정 브리프 — 부지분석(주소·통합면적·용도지역 등) 파생물.
  // staleness 시스템에 편입해, 업스트림(siteAnalysis)이 더 최신이면 '재분석 필요'로 판정한다.
  | "decisionBrief";

/** 다운스트림 모듈 → 직접 업스트림 의존성 (기존 키 불변, finance·decisionBrief 추가) */
const MODULE_UPSTREAM: Record<ModuleKey, ModuleKey[]> = {
  siteAnalysis: [],
  design: ["siteAnalysis"],
  cost: ["siteAnalysis", "design"],
  feasibility: ["siteAnalysis", "design", "cost"],
  // 개발금융(P3)은 수지·공사비가 갱신되면 정교화 필요 → 다운스트림으로 추적.
  finance: ["feasibility", "cost"],
  esg: ["design"],
  compliance: ["siteAnalysis", "design"],
  // 통합 의사결정 브리프는 부지분석 입력(주소·통합면적·용도지역)에 의존한다.
  // siteAnalysis가 갱신되면 isStale('decisionBrief')=true → 패널이 '재분석' 배지/CTA 노출
  // (자동재실행 금지·인간게이트). 단, 주소/유효면적 자체가 바뀐 경우는 updateSiteAnalysis가
  // 브리프를 null로 리셋하므로(옛 입력 판정 표시 차단) 이 stale 경로와 책임이 겹치지 않는다:
  //   · 주소/유효면적 변경 → null 리셋(브리프 없음 → isStale=false, 패널이 새로 자동산출)
  //   · 그 외 부지 필드 변경(예: 용도지역) → 브리프 보존 + stale 배지(인간 재분석 게이트)
  decisionBrief: ["siteAnalysis"],
};

/* ── State interface ── */

export interface ProjectContextState {
  // Current project
  projectId: string | null;
  projectName: string;
  projectStatus: string;

  // Lifecycle stage tracking
  completedStages: string[];
  currentStage: string | null;

  // Cross-module data (capillary network)
  siteAnalysis: SiteAnalysisData | null;
  designData: DesignData | null;
  feasibilityData: FeasibilityData | null;
  costData: CostData | null;
  esgData: EsgData | null;
  complianceData: ComplianceData | null;

  // Analysis history
  analysisResults: AnalysisResult[];

  // 프로젝트별 분석 스냅샷(영속) — 전환/재선택 시 복원
  snapshots: Record<string, ProjectSnapshot>;

  // 모듈별 최종 갱신 타임스탬프(epoch ms) — staleness 판정용
  updatedAt: Partial<Record<ModuleKey, number>>;

  // 무거운 휘발성 분석 영속 캐시(현재 프로젝트 기준)
  analysisCache: Partial<Record<AnalysisCacheKind, AnalysisCacheEntry>>;

  // 필드 단위 provenance 병행 맵(현재 프로젝트 기준, 초기 {}).
  // "user"로 stamp된 필드는 auto 갱신의 덮어쓰기가 차단된다(merge 가드).
  manualFields: ManualFieldsMap;

  // 다필지 보강(enrichParcels) 진행 신호(휘발성·런타임 전용) — 보강 시작 시 true,
  // 모든 청크 완료 후 1회 false. 제출 완전성 게이트(프로젝트 생성)가 이 플래그를 읽어
  // 통합값 미수집(대표 1필지 부분상태) 캡처를 막는다. 단일필지·미검색은 항상 false(무회귀).
  // persist되더라도 setProject/clearProject가 false로 리셋해 stale true가 고착되지 않게 한다.
  parcelEnrichPending: boolean;

  // ── Stage1 통합 의사결정 브리프(옵셔널·휘발성 런타임 캐시) ──
  // POST /api/v1/projects/{id}/decision-brief 결과를 적재한다(additive·하위호환).
  // ★모세혈관 배선됨(P2): MODULE_UPSTREAM.decisionBrief=['siteAnalysis']로 staleness 시스템에
  //   편입돼, 부지분석이 더 최신이면 isStale('decisionBrief')=true가 된다. 실소비처:
  //     ① 생산자 패널(DecisionBriefPanel) — 자동호출 dedup + isStale 재분석 CTA.
  //     ② Tier2 드릴다운 재사용 — 인허가/사업성 패널이 decisionBrief.parts에서 해당 도메인
  //        요약을 읽어 'Stage1 통합분석 기반' 프리필/배너로 재사용(중복 재분석 회피).
  //   (그 외 Tier2 패널 일괄 재사용은 backlog — 스파이럴 방지로 명확한 1~2곳만 패턴 정립.)
  // 휘발성: ①스냅샷(snapOf) 영속 대상 아님(staleness 타임스탬프도 함께 제외) ②persist
  //   partialize 로 localStorage 직렬화에서도 제외(새로고침 후 옛 입력 판정 hydrate 잔류 차단).
  //   명시적 null 리셋으로 비운다 — setProject/clearProject(프로젝트 전환·초기화),
  //   updateSiteAnalysis에서 주소/유효면적이 바뀌면(=stale) null 리셋, purifyPollutedSnapshot
  //   (오염 정화)도 null. 이전 프로젝트·이전 입력의 판정이 누출·재사용되지 않게 한다.
  decisionBrief: DecisionBrief | null;

  // Actions
  // projectId 단일 SSOT writer. name/status를 원자 저장하고, address가 주어지면
  // (스냅샷 복원이 우선이되) 신규/주소 미설정 프로젝트에 한해 siteAnalysis.address를 시드한다.
  setProject: (id: string, name: string, status: string, address?: string) => void;
  clearProject: () => void;
  // 다필지 보강 진행 신호 writer(휘발성). enrichParcels 시작/완료 시 호출.
  setParcelEnrichPending: (pending: boolean) => void;
  // 통합 의사결정 브리프 writer(옵셔널·휘발성). DecisionBriefPanel이 분석 완료 시 적재.
  setDecisionBrief: (brief: DecisionBrief | null) => void;

  // meta 옵셔널(미전달 = "auto") — 기존 호출 무수정 호환.
  // auto: user 플래그 필드를 patch에서 제거(전부 제거돼 빈 patch면 갱신·stamp 생략).
  // user: patch의 각 키를 manualFields에 {source:"user"}로 stamp.
  updateSiteAnalysis: (
    data: Partial<SiteAnalysisData>,
    meta?: { source?: FieldSource },
  ) => void;
  // 머지-보존 가드(비null 키만 덮어씀) 유지 + provenance 가산(WP-V).
  // meta 옵셔널(미전달 = "auto") — 기존 호출 무수정 호환.
  // auto: user 플래그 키는 덮지 못함(이전값 보존). user: 변경된 비null 키만 stamp.
  updateDesignData: (
    data: DesignData,
    meta?: { source?: FieldSource },
  ) => void;
  // merge 패치 — 부분 writer(UnitMix/AutoRecommend)가 기존 totalCostWon 등을 보존하도록
  // 기존 feasibilityData 위에 병합한다. 전체 객체를 넘기던 기존 호출도 동일하게 동작.
  updateFeasibilityData: (data: Partial<FeasibilityData>) => void;
  // (Phase C-1) 추천 개발방식 코드(M01~M15)만 feasibilityData.developmentType에 부분패치.
  // ★updateFeasibilityData와 달리 updatedAt.feasibility를 stamp하지 않는다 —
  //  파생(recommend) 노드가 수지 staleness를 오염시켜 수지 노드가 영영 skipped-fresh되는
  //  함정을 피하기 위함. 다른 수지 슬롯(매출·원가·ROI)은 일절 건드리지 않는다(merge 보존).
  //  빈 문자열/null이면 no-op(무목업: 추천 미확보 시 백엔드 기본 M06 폴백 유지).
  setRecommendedDevType: (developmentType: string | null) => void;
  // (Phase C-2) 적정분양가(원/평)만 feasibilityData.salePricePerPyeongWon에 부분패치.
  // ★setRecommendedDevType와 동일하게 updatedAt.feasibility를 stamp하지 않는다 —
  //  파생(sales) 노드가 수지 staleness를 오염시켜 수지 노드가 영영 skipped-fresh되는
  //  함정을 피하기 위함. 다른 수지 슬롯(매출·원가·ROI·developmentType)은 일절 건드리지 않는다(merge 보존).
  //  null/비양수면 no-op(무목업: 실거래 자료 없으면 미환류 → 백엔드 기본 동작).
  setSalesPricePerPyeong: (won: number | null) => void;
  // ★자기자본 비율(%) SSOT 세터 — 투자수익성 요약·DCF 패널이 공유하는 단일 슬롯을 갱신한다.
  //  비율이 바뀌면 총사업비×비율로 equityWon을 자동 재산출(자동값·수동 아님)해 두 화면을 즉시 동기화한다.
  //  setSalesPricePerPyeong과 동일하게 updatedAt.feasibility는 stamp하지 않는다(자본구조 가정 변경이
  //  매출·원가 계산을 stale로 오염시키지 않도록). null/비양수면 no-op.
  setEquityRatioPct: (pct: number | null) => void;
  // full replace. meta 옵셔널(미전달 = "auto") — 기존 호출 무수정 호환.
  // auto: user 플래그 키의 이전값을 보존한 채 교체(merge 가드).
  // user: 이전값과 달라진 비null 키만 stamp(미변경 키까지 동결하면 자동 환류 무력화).
  updateCostData: (data: CostData, meta?: { source?: FieldSource }) => void;
  // full replace + provenance(WP-V) — updateCostData와 동일 merge 가드 규칙.
  // meta 옵셔널(미전달 = "auto") — 기존 호출 무수정 호환.
  updateEsgData: (data: EsgData, meta?: { source?: FieldSource }) => void;
  updateComplianceData: (data: ComplianceData) => void;
  // 개발금융(finance) 갱신 stamp — 별도 데이터 필드 없이 updatedAt만 갱신해
  // 수지·공사비 변경 대비 finance staleness 추적을 활성화한다(additive).
  markFinanceUpdated: () => void;

  // 해당 필드의 user 플래그를 해제 — 다음 자동(auto) 갱신부터 덮어쓰기를 재허용한다.
  revertFieldToAuto: (module: ProvenanceModule, field: string) => void;
  // 필드 provenance 조회 — 기록이 없으면 null(= auto 취급).
  getFieldProvenance: (
    module: ProvenanceModule,
    field: string,
  ) => FieldProvenance | null;

  markStageComplete: (stage: string) => void;
  setCurrentStage: (stage: string) => void;
  addAnalysisResult: (result: AnalysisResult) => void;

  // 분석캐시 — 현재 프로젝트의 kind별 캐시 조회/저장(저장은 스냅샷에 영속).
  getAnalysisCache: (kind: AnalysisCacheKind) => AnalysisCacheEntry | null;
  setAnalysisCache: (
    kind: AnalysisCacheKind,
    signature: string,
    data: unknown,
  ) => void;

  // Computed
  getNextRecommendedStage: () => string | null;
  // 다운스트림 모듈이 업스트림 갱신 이후로 재계산되지 않았으면 true.
  isStale: (downstream: ModuleKey) => boolean;
  // (additive) 모든 직접 업스트림이 "준비됨(실데이터 존재)"이고 다운스트림이 아직
  // 한 번도 산출되지 않았을 때 true → 최초 1회 자동 산출 허용 신호.
  // isStale의 "최초제외" 정책은 보존하고, 별도 경로로 업스트림 지연 채움 후의
  // 다운스트림 자동 최초산출을 활성화한다(무한루프는 호출측 시그니처/busy 가드).
  isReadyForFirstCompute: (downstream: ModuleKey) => boolean;
  // 수지분석에 실제 반영된 업스트림 단계 완성도(0~100, 무목업: 실데이터 유무 기반).
  feasibilityCompleteness: () => FeasibilityCompleteness;
  // 프로젝트 전체 완성도(부지·설계·공사비·법규·금융·ESG·인허가) — 감사 지적 반영.
  projectCompleteness: () => ProjectCompleteness;
  // 라이프사이클 단계 id(LIFECYCLE_STAGES 11종)별 "실데이터 존재" 판정(무목업·읽기전용).
  // true=실데이터 있음(완료 표시), false=없음, undefined=전용 데이터 없는 단계(배지 미표시).
  // 진행레일/파이프라인이 completedStages가 비어도 실데이터 기준으로 완료를 표시하도록 단일소비.
  stageHasData: (stageId: string) => boolean | undefined;
}

/* ── 수지 완성도/신뢰도 파생 모델 ──
   업스트림 단계(부지/설계/공사비/금융)별로 "수지에 반영 가능한 실데이터가 있는가"를
   판정해 단계 칩과 반영도(%)를 산출한다. 무목업: 실데이터가 없으면 done=false. */
export interface FeasibilityCompletenessStage {
  key: "site" | "design" | "cost" | "finance";
  label: string;
  done: boolean;
  // 부분 반영(예: 주소만 있고 면적 미확보) — done=false이되 정직 표기용 보조 플래그.
  partial?: boolean;
  weightPct: number; // 누적 가중치(부지30/설계60/공사비85/금융100)
}
export interface FeasibilityCompleteness {
  stages: FeasibilityCompletenessStage[];
  pct: number; // 반영도(%) — 완료된 마지막 단계의 누적 가중치
}

/* ── 프로젝트 전체 완성도 파생 모델 ──
   수지 투입(부지/설계/공사비/금융)에 더해 감사 지적 단계(법규/ESG/인허가)까지 포함해
   프로젝트 전주기 완성도를 산출한다. 무목업: 각 단계 done은 해당 store 데이터(또는
   완료 단계 기록) 유무로만 판정. 가중치 균등(7단계, 각 1/7) → 완료 비율(%). */
export type ProjectCompletenessKey =
  | "site"
  | "design"
  | "cost"
  | "compliance"
  | "finance"
  | "esg"
  | "permit";
export interface ProjectCompletenessStage {
  key: ProjectCompletenessKey;
  label: string;
  done: boolean;
  // 부분 반영(예: 주소만 있고 면적 미확보) — done=false이되 정직 표기용 보조 플래그.
  partial?: boolean;
}
export interface ProjectCompleteness {
  stages: ProjectCompletenessStage[];
  // 완료 단계 수
  doneCount: number;
  total: number;
  // 전체 완성도(%) — 완료 단계 / 전체 단계(균등 가중).
  pct: number;
}

/* ── Initial cross-module state ── */

const INITIAL_CROSS_MODULE = {
  siteAnalysis: null as SiteAnalysisData | null,
  designData: null as DesignData | null,
  feasibilityData: null as FeasibilityData | null,
  costData: null as CostData | null,
  esgData: null as EsgData | null,
  complianceData: null as ComplianceData | null,
};

/** 현재 cross-module 상태를 스냅샷으로 추출 */
/** updatedAt 맵에서 휘발성 decisionBrief 타임스탬프만 제거한 새 맵 반환(원본 불변). */
function omitDecisionBriefStamp(
  updatedAt: Partial<Record<ModuleKey, number>>,
): Partial<Record<ModuleKey, number>> {
  if (updatedAt.decisionBrief == null) return updatedAt;
  const next = { ...updatedAt };
  delete next.decisionBrief;
  return next;
}

function snapOf(s: ProjectContextState): ProjectSnapshot {
  return {
    siteAnalysis: s.siteAnalysis,
    designData: s.designData,
    feasibilityData: s.feasibilityData,
    costData: s.costData,
    esgData: s.esgData,
    complianceData: s.complianceData,
    completedStages: s.completedStages,
    currentStage: s.currentStage,
    analysisResults: s.analysisResults,
    // ★decisionBrief는 스냅샷·영속 제외(휘발성)이므로, 그 staleness 타임스탬프도 스냅샷에서
    //   제외한다(브리프 없는데 타임스탬프만 남는 불일치 차단). 다른 모듈 타임스탬프는 보존.
    updatedAt: omitDecisionBriefStamp(s.updatedAt),
    analysisCache: s.analysisCache,
    // 구 hydrated state(필드 부재) 호환 — analysisCache와 동일하게 ?? {} 방어.
    manualFields: s.manualFields ?? {},
  };
}

/** 실데이터 존재 판정(무목업): 부지/설계/공사비 채워짐 여부. */
function hasSiteData(s: ProjectContextState): boolean {
  return !!(
    (s.siteAnalysis?.landAreaSqm && s.siteAnalysis.landAreaSqm > 0) ||
    s.siteAnalysis?.address ||
    s.siteAnalysis?.zoneCode
  );
}
function hasDesignData(s: ProjectContextState): boolean {
  return !!(s.designData?.totalGfaSqm && s.designData.totalGfaSqm > 0);
}
function hasCostData(s: ProjectContextState): boolean {
  return !!(
    s.costData?.totalConstructionCostWon &&
    s.costData.totalConstructionCostWon > 0
  );
}
function hasFeasibilityData(s: ProjectContextState): boolean {
  return !!(
    s.feasibilityData?.totalRevenueWon && s.feasibilityData.totalRevenueWon > 0
  );
}
/** 법규(compliance) 실데이터 판정 — 적합판정 불리언/위반 또는 법령허브 산출(정량 한도/근거) 보존 시 true.
    (Fix #1) 설계 전 단계에서도 백엔드가 정량 한도·근거를 산출하면 법규단계 산출로 인정(환류 단선 해소). */
function complianceHasData(c: ComplianceData | null | undefined): boolean {
  if (!c) return false;
  return (
    c.bcrCompliant != null ||
    c.farCompliant != null ||
    c.heightCompliant != null ||
    (c.violations?.length ?? 0) > 0 ||
    (c.limits != null && Object.keys(c.limits).length > 0) ||
    (c.evidence?.length ?? 0) > 0
  );
}

/**
 * 모듈 키별 "실데이터가 준비됐는가" 판정(무목업) — isReadyForFirstCompute 보조.
 * finance/compliance/esg는 산출 결과(또는 stamp)가 곧 준비 신호이므로 그 기준을 쓴다.
 * 다운스트림이 직접 업스트림의 준비 여부만 확인하면 되도록 단일 진실원으로 둔다. */
function isModuleReady(s: ProjectContextState, key: ModuleKey): boolean {
  switch (key) {
    case "siteAnalysis":
      return hasSiteData(s);
    case "design":
      return hasDesignData(s);
    case "cost":
      return hasCostData(s);
    case "feasibility":
      return hasFeasibilityData(s);
    case "finance":
      return !!s.updatedAt.finance;
    case "esg":
      return !!(
        s.esgData &&
        ((s.esgData.totalCarbonPerSqm ?? 0) > 0 ||
          (s.esgData.embodiedCarbonKg ?? 0) > 0)
      );
    case "compliance":
      return complianceHasData(s.complianceData);
    default:
      return false;
  }
}

/**
 * 라이프사이클 단계의 업스트림 데이터가 준비됐는지 판정(getNextRecommendedStage 보조).
 * 무목업: 실제 cross-module 데이터 유무로 판정. 매핑되지 않은(업스트림 없는) 단계는
 * 항상 ready(true)로 두어 막다른길을 만들지 않는다. */
function isStageDataReady(
  s: ProjectContextState,
  stage: LifecycleStage,
): boolean {
  switch (stage) {
    case "site-analysis":
      return true; // 첫 단계 — 업스트림 없음
    case "legal":
    case "design":
      return hasSiteData(s);
    case "bim":
    case "esg":
    case "construction":
      return hasDesignData(s);
    case "feasibility":
      return hasSiteData(s) && hasDesignData(s);
    case "finance":
      return hasCostData(s) || hasFeasibilityData(s);
    case "permit":
    case "report":
    default:
      return true; // 종합 단계 — 데이터 준비도와 무관하게 진입 허용
  }
}

/** 모듈 갱신 타임스탬프를 현재 시각으로 stamp한 updatedAt 객체를 반환. */
function stampedAt(
  state: ProjectContextState,
  key: ModuleKey,
): Partial<Record<ModuleKey, number>> {
  return { ...state.updatedAt, [key]: Date.now() };
}

/** patch 적용 결과를 현재 프로젝트 스냅샷에도 함께 영속화한다. */
function withSnap(
  state: ProjectContextState,
  patch: Partial<ProjectContextState>,
): Partial<ProjectContextState> {
  if (!state.projectId) return patch;
  const merged = { ...state, ...patch } as ProjectContextState;
  return {
    ...patch,
    snapshots: { ...state.snapshots, [state.projectId]: snapOf(merged) },
  };
}

/* ── WP-D: SSOT 오염 차단 — 주소 토큰 검증 · 오염 스냅샷 정화 ──
   진단된 오염 사슬: 활성 프로젝트와 무관한 주소 검색 결과가 updateSiteAnalysis →
   withSnap으로 스냅샷 영속 → 전환 시 복원 → 서버 푸시로 고착.
   프로젝트 레코드 주소와 분석 주소의 "핵심 토큰"이 명백히 불일치할 때만 오염으로
   판정한다. 표기 차이(도로명/지번 혼용, 시도 축약, 행정동 숫자)에 의한 오탐 방지:
   - 시군구(광역 시도 제외) 토큰이 양쪽 모두 존재하고 전부 다르면 불일치
   - 법정동(숫자 정규화) 토큰이 양쪽 모두 존재하고 전부 다르면 불일치
   - 같은 법정동에서 번지가 양쪽 모두 존재하고 다르면 불일치
   비교 불능(주소 부재·토큰 추출 실패)은 "불일치 아님"으로 보수 처리(과차단 금지). */

interface AddressTokens {
  /** 시군구(광역 시도 제외) — 예: "강남구", "성남시", "분당구" */
  sigungu: string[];
  /** 법정동/읍/면/리/가(행정동 숫자 제거 정규화) — 예: "역삼동" */
  dong: string[];
  /** 법정동 토큰 직후의 지번(산·번지 표기 정규화) — 예: "737", "737-1" */
  bunji: string | null;
}

function extractAddressTokens(
  address: string | null | undefined,
): AddressTokens | null {
  if (!address || typeof address !== "string") return null;
  const words = address.trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return null;
  const sigungu: string[] = [];
  const dong: string[] = [];
  let bunji: string | null = null;
  for (let i = 0; i < words.length; i++) {
    const w = words[i];
    // 광역 시도(서울특별시·부산광역시·세종특별자치시 등)는 변별력이 낮아 제외.
    if (/(특별시|광역시|특별자치시|특별자치도)$/.test(w)) continue;
    if (w.length >= 2 && /(시|군|구)$/.test(w)) {
      sigungu.push(w);
      continue;
    }
    if (/^[가-힣0-9]+(동|읍|면|리|가)$/.test(w)) {
      // 행정동 숫자 정규화(역삼1동 → 역삼동). 숫자 제거 후 1글자(예: "101동")는
      // 건물 동호수 표기일 가능성이 높아 제외한다.
      const norm = w.replace(/[0-9]/g, "");
      if (norm.length < 2) continue;
      dong.push(norm);
      const next = words[i + 1];
      if (bunji == null && next && /^산?\d+(-\d+)?(번지)?$/.test(next)) {
        bunji = next.replace(/번지$/, "").replace(/^산/, "");
      }
      continue;
    }
  }
  if (sigungu.length === 0 && dong.length === 0) return null;
  return { sigungu, dong, bunji };
}

/** 두 주소의 핵심 토큰(시군구·법정동·번지)이 명백히 불일치하면 true.
    비교 불능(어느 한쪽 토큰 추출 실패)이면 false — 정상 동기화를 막지 않는다. */
export function addressTokenMismatch(
  a: string | null | undefined,
  b: string | null | undefined,
): boolean {
  const ta = extractAddressTokens(a);
  const tb = extractAddressTokens(b);
  if (!ta || !tb) return false;
  if (ta.sigungu.length > 0 && tb.sigungu.length > 0) {
    const setB = new Set(tb.sigungu);
    if (!ta.sigungu.some((t) => setB.has(t))) return true; // 시군구 전부 불일치
  }
  if (ta.dong.length > 0 && tb.dong.length > 0) {
    const setB = new Set(tb.dong);
    if (!ta.dong.some((t) => setB.has(t))) return true; // 법정동 전부 불일치
    if (ta.bunji && tb.bunji && ta.bunji !== tb.bunji) return true; // 같은 동, 다른 번지
  }
  return false;
}

/** 오염 스냅샷 정화 — siteAnalysis와 그 파생(designData)을 null로, completedStages에서
    site-analysis/design을 제거한다. 해당 updatedAt stamp·manualFields도 함께 정리해
    "null 데이터가 산출됨으로 잔존 → 최초 자동산출 차단" 부작용을 막는다. 그 외 필드 보존.
    ★decisionBrief(통합 의사결정 판정)도 siteAnalysis 파생이므로 함께 null로 정화한다 — 오염
    주소 기준의 옛 판정이 hydrate 후 잔류해 새 부지에 재사용되는 누출을 막는다(siteAnalysis와 대칭).
    원본 객체는 변경하지 않고 정화된 사본을 반환한다. */
export function purifyPollutedSnapshot(
  snap: Record<string, unknown>,
): Record<string, unknown> {
  const completedStages = Array.isArray(snap.completedStages)
    ? (snap.completedStages as unknown[]).filter(
        (st) => st !== "site-analysis" && st !== "design",
      )
    : [];
  const updatedAt = { ...((snap.updatedAt as Record<string, unknown>) ?? {}) };
  delete updatedAt.siteAnalysis;
  delete updatedAt.design;
  const manualFields = {
    ...((snap.manualFields as Record<string, unknown>) ?? {}),
  };
  delete manualFields.siteAnalysis;
  delete manualFields.design;
  return {
    ...snap,
    siteAnalysis: null,
    designData: null,
    // siteAnalysis 파생 — 오염 주소 기준 옛 판정 잔류·재사용 차단(siteAnalysis와 대칭 정화).
    decisionBrief: null,
    completedStages,
    updatedAt,
    manualFields,
  };
}

/** localStorage의 프로젝트 레코드(propai-project-storage)에서 id→주소 맵을 직접 읽는다.
    (useProjectStore import 대신 raw 접근 — persist hydrate 순서 의존·순환 import 제거) */
function readPersistedProjectAddressMap(): Record<string, string> {
  if (typeof window === "undefined") return {};
  try {
    const raw = window.localStorage.getItem("propai-project-storage");
    if (!raw) return {};
    const parsed = JSON.parse(raw) as {
      state?: { projects?: Array<{ id?: unknown; address?: unknown }> };
    };
    const map: Record<string, string> = {};
    for (const p of parsed.state?.projects ?? []) {
      if (
        typeof p?.id === "string" &&
        typeof p?.address === "string" &&
        p.address.trim()
      ) {
        map[p.id] = p.address;
      }
    }
    return map;
  } catch {
    return {};
  }
}

/** persist hydrate(migrate) 정화 — 프로젝트 레코드 주소와 토큰 불일치인 스냅샷과
    live 필드(현재 활성 프로젝트)를 정화한다. 레코드 주소가 없는 프로젝트는 비교
    불능이므로 보존한다. 오염이 전혀 없으면 원본 참조를 그대로 반환(무변경). */
export function purifyPersistedContextState(
  persisted: Record<string, unknown>,
  addressOf: Record<string, string> = readPersistedProjectAddressMap(),
): Record<string, unknown> {
  let next = persisted;
  const snaps = next.snapshots;
  if (snaps && typeof snaps === "object") {
    let changed = false;
    const purified: Record<string, unknown> = {
      ...(snaps as Record<string, unknown>),
    };
    for (const [pid, snap] of Object.entries(purified)) {
      if (!snap || typeof snap !== "object") continue;
      const recordAddress = addressOf[pid];
      const snapAddress = (
        (snap as Record<string, unknown>).siteAnalysis as
          | { address?: unknown }
          | null
          | undefined
      )?.address;
      if (
        recordAddress &&
        typeof snapAddress === "string" &&
        addressTokenMismatch(recordAddress, snapAddress)
      ) {
        purified[pid] = purifyPollutedSnapshot(
          snap as Record<string, unknown>,
        );
        changed = true;
      }
    }
    if (changed) next = { ...next, snapshots: purified };
  }
  // live 필드(현재 활성 프로젝트) 동일 기준 정화
  const pid = typeof next.projectId === "string" ? next.projectId : null;
  const recordAddress = pid ? addressOf[pid] : undefined;
  const liveAddress = (
    next.siteAnalysis as { address?: unknown } | null | undefined
  )?.address;
  if (
    recordAddress &&
    typeof liveAddress === "string" &&
    addressTokenMismatch(recordAddress, liveAddress)
  ) {
    next = purifyPollutedSnapshot({ ...next });
  }
  return next;
}

/* ── Store ── */

export const useProjectContextStore = create<ProjectContextState>()(
  persist(
    (set, get) => ({
      // Current project
      projectId: null,
      projectName: "",
      projectStatus: "",

      // Lifecycle
      completedStages: [],
      currentStage: null,

      // Cross-module
      ...INITIAL_CROSS_MODULE,

      // Analysis history
      analysisResults: [],

      // 프로젝트별 스냅샷
      snapshots: {},

      // 모듈별 갱신 타임스탬프
      updatedAt: {},

      // 분석캐시
      analysisCache: {},

      // 필드 단위 provenance 병행 맵
      manualFields: {},

      // 다필지 보강 진행 신호(휘발성 — 초기 false)
      parcelEnrichPending: false,

      // 통합 의사결정 브리프(휘발성 — 초기 null)
      decisionBrief: null,

      /* ── Actions ── */

      setProject: (id, name, status, address) => {
        const prev = get();
        // projectId가 동일하면 cross-module 데이터를 리셋하지 않는다(회귀 방지).
        // name/status만 원자 갱신하고, address가 주어졌고 아직 없으면 보조 시드.
        if (prev.projectId === id) {
          const polluted =
            !!address &&
            !!prev.siteAnalysis?.address &&
            addressTokenMismatch(address, prev.siteAnalysis.address);
          const patch: Partial<ProjectContextState> = {
            projectId: id,
            projectName: name,
            projectStatus: status,
          };
          if (polluted) {
            const updatedAt = { ...prev.updatedAt };
            delete updatedAt.siteAnalysis;
            delete updatedAt.design;
            delete updatedAt.decisionBrief;
            const manualFields = { ...(prev.manualFields ?? {}) };
            delete manualFields.siteAnalysis;
            delete manualFields.design;
            patch.siteAnalysis = {
              estimatedValue: null,
              landAreaSqm: null,
              zoneCode: null,
              pnu: null,
              address,
            } as SiteAnalysisData;
            patch.designData = null;
            patch.decisionBrief = null;
            patch.completedStages = (prev.completedStages ?? []).filter(
              (st) => st !== "site-analysis" && st !== "design",
            );
            patch.updatedAt = updatedAt;
            patch.manualFields = manualFields;
          } else if (address && !prev.siteAnalysis?.address) {
            patch.siteAnalysis = {
              ...(prev.siteAnalysis ?? {
                estimatedValue: null,
                landAreaSqm: null,
                zoneCode: null,
                pnu: null,
              }),
              address,
            } as SiteAnalysisData;
          }
          set(withSnap(prev, patch));
          return;
        }
        // 전환 전, 현재 프로젝트 상태를 스냅샷에 보존
        const snapshots = prev.projectId
          ? { ...prev.snapshots, [prev.projectId]: snapOf(prev) }
          : prev.snapshots;
        // 대상 프로젝트의 이전 분석이 있으면 복원, 없으면 초기화.
        // 구 hydrated 스냅샷 shape 호환을 위해 모든 필드에 ?? 폴백을 둔다.
        const snap = snapshots[id];
        const seededSite: SiteAnalysisData | null = address
          ? {
              estimatedValue: null,
              landAreaSqm: null,
              zoneCode: null,
              pnu: null,
              address,
            }
          : null;
        set({
          projectId: id,
          projectName: name,
          projectStatus: status,
          snapshots,
          // 프로젝트 전환 시 휘발성 보강 신호 리셋(이전 프로젝트 보강 진행이 새 프로젝트로 누출 방지).
          parcelEnrichPending: false,
          // 의사결정 브리프도 휘발성 — 이전 프로젝트 판정이 새 프로젝트로 누출되지 않게 리셋.
          decisionBrief: null,
          ...(snap
            ? {
                // 복원 우선. 단, 복원 스냅샷에 주소가 없고 시드 주소가 있으면 보조 주입.
                siteAnalysis:
                  snap.siteAnalysis ??
                  (seededSite as SiteAnalysisData | null) ??
                  null,
                designData: snap.designData ?? null,
                feasibilityData: snap.feasibilityData ?? null,
                costData: snap.costData ?? null,
                esgData: snap.esgData ?? null,
                complianceData: snap.complianceData ?? null,
                completedStages: snap.completedStages ?? [],
                currentStage: snap.currentStage ?? null,
                analysisResults: snap.analysisResults ?? [],
                updatedAt: snap.updatedAt ?? {},
                analysisCache: snap.analysisCache ?? {},
                manualFields: snap.manualFields ?? {},
              }
            : {
                completedStages: [],
                currentStage: null,
                analysisResults: [],
                updatedAt: {},
                analysisCache: {},
                manualFields: {},
                ...INITIAL_CROSS_MODULE,
                siteAnalysis: seededSite,
              }),
        });
      },

      clearProject: () => {
        const prev = get();
        // 현재 분석을 스냅샷에 보존(나중에 같은 프로젝트 재선택 시 복원)
        const snapshots = prev.projectId
          ? { ...prev.snapshots, [prev.projectId]: snapOf(prev) }
          : prev.snapshots;
        set({
          projectId: null,
          projectName: "",
          projectStatus: "",
          completedStages: [],
          currentStage: null,
          analysisResults: [],
          snapshots,
          updatedAt: {},
          analysisCache: {},
          manualFields: {},
          // 휘발성 보강 신호 리셋(새 프로젝트 진입 시 stale true 고착 방지).
          parcelEnrichPending: false,
          // 의사결정 브리프 리셋(프로젝트 비움 시 이전 판정 잔류 방지).
          decisionBrief: null,
          ...INITIAL_CROSS_MODULE,
        });
      },

      setParcelEnrichPending: (pending) => {
        // 휘발성 런타임 신호만 갱신(스냅샷·provenance 무접촉 — withSnap 미사용).
        if (get().parcelEnrichPending === pending) return;
        set({ parcelEnrichPending: pending });
      },

      setDecisionBrief: (brief) => {
        // 휘발성 런타임 캐시만 갱신(스냅샷·provenance 무접촉 — withSnap 미사용).
        // ★staleness 편입: 브리프 적재 시 updatedAt.decisionBrief를 stamp해, 이후 siteAnalysis가
        //   더 최신이면 isStale('decisionBrief')=true가 되어 '재분석' CTA를 띄울 수 있게 한다.
        //   null 리셋(전환·정화 등)이면 타임스탬프도 함께 제거 → own==null → isStale=false
        //   (브리프 없는데 stale로 오판하지 않게).
        set((state) => {
          if (brief == null) {
            return {
              decisionBrief: null,
              updatedAt: omitDecisionBriefStamp(state.updatedAt),
            };
          }
          return {
            decisionBrief: brief,
            updatedAt: stampedAt(state, "decisionBrief"),
          };
        });
      },

      getAnalysisCache: (kind) => {
        const c = get().analysisCache?.[kind];
        return c ?? null;
      },
      setAnalysisCache: (kind, signature, data) => {
        set((state) =>
          withSnap(state, {
            analysisCache: {
              ...(state.analysisCache ?? {}),
              [kind]: { signature, data, at: Date.now() },
            },
          }),
        );
      },

      updateSiteAnalysis: (data, meta) => {
        const source: FieldSource = meta?.source ?? "auto";
        set((state) => {
          const flagged = state.manualFields?.siteAnalysis ?? {};
          let patch: Partial<SiteAnalysisData> = data;
          if (source === "auto") {
            // merge 가드 — user 플래그 필드는 auto patch에서 제거해 수동값을 보존.
            const guarded = { ...data };
            for (const key of Object.keys(
              guarded,
            ) as (keyof SiteAnalysisData)[]) {
              if (flagged[key]) delete guarded[key];
            }
            // 전 키가 user 보호 대상(빈 patch)이면 갱신·stamp 생략
            // (불필요한 staleness 캐스케이드 오염 방지).
            if (Object.keys(guarded).length === 0) return {};
            patch = guarded;
          }
          const mergedSiteAnalysis = {
            ...(state.siteAnalysis ?? {
              estimatedValue: null,
              landAreaSqm: null,
              zoneCode: null,
              address: null,
              pnu: null,
            }),
            ...patch,
          } as SiteAnalysisData;
          const next: Partial<ProjectContextState> = {
            siteAnalysis: mergedSiteAnalysis,
            updatedAt: stampedAt(state, "siteAnalysis"),
          };
          // ★stale 의사결정 브리프 리셋(HIGH 'stale-brief'): 주소 또는 유효면적(다필지 통합면적 우선)이
          //   바뀌면, 이전 입력으로 만든 브리프는 더 이상 유효하지 않다(다필지 보강으로 통합면적이 커진
          //   경우 등). null로 리셋해 패널이 새 입력으로 재분석하게 한다(가짜 stale 재사용 금지).
          //   면적의존 캐시는 모두 이 staleness 규칙을 따라야 한다(공용 effectiveLandAreaSqm 기준).
          if (state.decisionBrief) {
            const prevAddr = state.siteAnalysis?.address ?? null;
            const prevArea = effectiveLandAreaSqm(state.siteAnalysis);
            const nextAddr = mergedSiteAnalysis.address ?? null;
            const nextArea = effectiveLandAreaSqm(mergedSiteAnalysis);
            if (prevAddr !== nextAddr || prevArea !== nextArea) {
              next.decisionBrief = null;
              // ★staleness 정합: 브리프를 리셋하면 updatedAt.decisionBrief도 함께 제거한다.
              //   (setDecisionBrief(null)과 동일 규칙 — 리셋 vs stale표기 일원화) 위에서 이미
              //   siteAnalysis를 stamp했으므로, 타임스탬프를 안 지우면 '브리프 없는데 stale'로
              //   오판될 수 있다. own==null로 두어 isStale('decisionBrief')=false 보장.
              if (next.updatedAt) {
                next.updatedAt = omitDecisionBriefStamp(next.updatedAt);
              }
            }
          }
          if (source === "user") {
            // user 갱신 — patch의 각 키를 stamp(이후 auto 덮어쓰기 차단).
            const now = Date.now();
            const stamped: Record<string, FieldProvenance> = { ...flagged };
            for (const key of Object.keys(data)) {
              stamped[key] = { source: "user", updatedAt: now };
            }
            next.manualFields = {
              ...(state.manualFields ?? {}),
              siteAnalysis: stamped,
            };
          }
          return withSnap(state, next);
        });
      },

      updateDesignData: (data, meta) => {
        const source: FieldSource = meta?.source ?? "auto";
        set((state) => {
          const flagged = state.manualFields?.design ?? {};
          // merge 가드(기존 동작 불변) — 부분 writer(예: cost만 재실행한 rerun의
          // design summary)가 누락하거나 null로 보낸 키가 기존 구체값(unitTypes/
          // unitCount 등)을 덮지 않도록, 기존값 위에 비null 키만 덮어쓴다
          // (updateFeasibilityData와 동일 의도).
          const prev = (state.designData ?? {}) as Record<string, unknown>;
          const merged: Record<string, unknown> = { ...prev };
          for (const [key, value] of Object.entries(data)) {
            if (value == null && prev[key] != null) continue; // null은 "데이터 없음" — 기존 구체값 보존
            // provenance merge 가드(WP-V 가산) — auto 갱신은 user 플래그 키를
            // 덮지 못한다(이전값 보존, cost와 동일 규칙). meta 미전달(=auto)
            // 기존 호출은 flagged가 비어 있어 종전과 완전히 동일하게 동작.
            if (source === "auto" && flagged[key]) continue;
            merged[key] = value;
          }
          const next: Partial<ProjectContextState> = {
            designData: merged as unknown as DesignData,
            updatedAt: stampedAt(state, "design"),
          };
          if (source === "user") {
            // user 갱신 stamp — 이전값과 달라진 비null 키만 기록(cost와 동일).
            // 미변경 키까지 동결하면 자동 환류가 무력화되고, null은 "데이터 없음"
            // 표기이므로 수동값 보호 대상이 아니다.
            const now = Date.now();
            const stamped: Record<string, FieldProvenance> = { ...flagged };
            for (const [key, value] of Object.entries(data)) {
              if (value == null) continue;
              if (value === prev[key]) continue;
              stamped[key] = { source: "user", updatedAt: now };
            }
            next.manualFields = {
              ...(state.manualFields ?? {}),
              design: stamped,
            };
          }
          return withSnap(state, next);
        });
      },

      updateFeasibilityData: (data) => {
        set((state) => {
          // merge: 기존값 보존 후 patch 적용(부분 writer가 totalCostWon을 null로 덮지 않도록).
          const merged = {
            totalCostWon: null,
            totalRevenueWon: null,
            profitRatePct: null,
            grade: null,
            ...(state.feasibilityData ?? {}),
            ...data,
          } as FeasibilityData;
          // ★자기자본 자동 환류(공용 규칙, resolveEquityWon 단일 계약):
          //   총사업비가 나오면 자기자본이 없어도 equityRatioPct(기본 10%)로 자동 산출해 채운다
          //   (0원 표시 방지). 자기자본 절대액이 "사용자 직접입력"(equityIsManual=true)일 때만 보존한다.
          //   비율 슬롯이 비어 있으면(구 스냅샷) 기본 10%로 정규화해 SSOT를 확정한다.
          //   ★양수값 존재만으로 "명시 입력"을 판단하면 안 된다 — 그 양수값이 직전 자동파생값일 수
          //   있어, 재실행 경로(부분 writer가 equityWon 키를 omit)에서 cost가 바뀌어도 옛 cost에
          //   앵커된 자기자본이 그대로 보존되며 실효비율이 침묵 이탈한다(적대적 리뷰 재현 [A]).
          //   그래서 "보존 vs 재파생"은 오직 equityIsManual 플래그로만 가른다.
          const ratio =
            merged.equityRatioPct != null && merged.equityRatioPct > 0
              ? merged.equityRatioPct
              : DEFAULT_EQUITY_RATIO_PCT;
          merged.equityRatioPct = ratio;
          const isManual = merged.equityIsManual === true;
          const explicitEquity =
            isManual && typeof merged.equityWon === "number" && merged.equityWon > 0
              ? merged.equityWon
              : null;
          merged.equityWon =
            explicitEquity ??
            resolveEquityWon({
              equityWon: null,
              totalCostWon: merged.totalCostWon,
              equityRatioPct: ratio,
            });
          return withSnap(state, {
            feasibilityData: merged,
            updatedAt: stampedAt(state, "feasibility"),
          });
        });
      },

      // (Phase C-1) 추천 개발방식 코드만 부분패치 — updatedAt 미변경(staleness 오염 회피).
      setRecommendedDevType: (developmentType) => {
        // 무목업: 추천 코드가 비었으면(없음) 아무것도 하지 않는다 → 수지는 백엔드 기본(M06) 폴백.
        const code =
          typeof developmentType === "string" && developmentType.trim()
            ? developmentType.trim()
            : null;
        if (!code) return;
        set((state) => {
          // 값이 같으면 no-op(불필요한 스냅샷 갱신 방지).
          if (state.feasibilityData?.developmentType === code) return {};
          return withSnap(state, {
            // merge: developmentType만 덮고 매출·원가·ROI 등 기존 수지 슬롯은 보존.
            feasibilityData: {
              totalCostWon: null,
              totalRevenueWon: null,
              profitRatePct: null,
              grade: null,
              ...(state.feasibilityData ?? {}),
              developmentType: code,
            } as FeasibilityData,
            // ★updatedAt 미변경 — feasibility staleness를 stamp하지 않는다(함정 회피).
          });
        });
      },

      // (Phase C-2) 적정분양가(원/평)만 부분패치 — updatedAt 미변경(staleness 오염 회피).
      setSalesPricePerPyeong: (won) => {
        // 무목업: 분양가가 비었거나 비양수면(실거래 자료 없음) 아무것도 하지 않는다 → 백엔드 기본 동작.
        const price =
          typeof won === "number" && Number.isFinite(won) && won > 0 ? won : null;
        if (price == null) return;
        set((state) => {
          // 값이 같으면 no-op(불필요한 스냅샷 갱신 방지).
          if (state.feasibilityData?.salePricePerPyeongWon === price) return {};
          return withSnap(state, {
            // merge: salePricePerPyeongWon만 덮고 매출·원가·ROI·developmentType 등 기존 슬롯은 보존.
            feasibilityData: {
              totalCostWon: null,
              totalRevenueWon: null,
              profitRatePct: null,
              grade: null,
              ...(state.feasibilityData ?? {}),
              salePricePerPyeongWon: price,
            } as FeasibilityData,
            // ★updatedAt 미변경 — feasibility staleness를 stamp하지 않는다(함정 회피).
          });
        });
      },

      // ★자기자본 비율(%) SSOT 세터 — 비율 갱신 + 총사업비×비율로 equityWon 자동 재산출.
      setEquityRatioPct: (pct) => {
        const ratio =
          typeof pct === "number" && Number.isFinite(pct) && pct > 0 ? pct : null;
        if (ratio == null) return;
        set((state) => {
          // 값이 같으면 no-op(불필요한 스냅샷 갱신 방지).
          if (state.feasibilityData?.equityRatioPct === ratio) return {};
          const totalCostWon = state.feasibilityData?.totalCostWon ?? null;
          // 비율 기반 자동 재산출 — 명시 자기자본이 있어도 비율 세터는 자동값으로 덮는다
          //  (DCF에서 사용자가 비율을 바꾸면 요약도 그 비율로 즉시 반영). 총사업비 없으면 null.
          const equityWon = resolveEquityWon({
            equityWon: null,
            totalCostWon,
            equityRatioPct: ratio,
          });
          return withSnap(state, {
            // merge: 비율·자기자본만 덮고 매출·원가·ROI 등 기존 슬롯은 보존.
            feasibilityData: {
              totalCostWon: null,
              totalRevenueWon: null,
              profitRatePct: null,
              grade: null,
              ...(state.feasibilityData ?? {}),
              equityRatioPct: ratio,
              equityWon,
              // ★비율 변경은 "수동 절대액 입력"을 대체하는 새 자동파생 기준이 된다 — equityIsManual을
              //  false로 되돌려, 이후 cost가 바뀌면 이 새 비율로 계속 재산출되게 한다(앵커링 방지).
              equityIsManual: false,
            } as FeasibilityData,
            // ★updatedAt 미변경 — 자본구조 가정 변경이 매출·원가 staleness를 오염시키지 않도록.
          });
        });
      },
      updateCostData: (data, meta) => {
        const source: FieldSource = meta?.source ?? "auto";
        set((state) => {
          const flagged = state.manualFields?.cost ?? {};
          const prevRec = state.costData
            ? (state.costData as unknown as Record<string, unknown>)
            : null;
          const next: Partial<ProjectContextState> = {
            costData: data,
            updatedAt: stampedAt(state, "cost"),
          };
          if (source === "auto") {
            // merge 가드 — full replace이되 user 플래그 키는 이전값 보존(auto 덮어쓰기 차단).
            const flaggedKeys = Object.keys(flagged);
            if (prevRec && flaggedKeys.length > 0) {
              const merged = { ...data } as unknown as Record<string, unknown>;
              for (const key of flaggedKeys) {
                if (key in prevRec) merged[key] = prevRec[key];
              }
              next.costData = merged as unknown as CostData;
            }
          } else {
            // user 갱신 stamp — 이전값과 달라진 비null 키만 기록한다.
            // 근거: full replace 특성상 전 키를 stamp하면 미변경 필드까지 user로
            // 동결돼 이후 자동 환류(saveToStore)가 무력화되고, null은 "데이터 없음"
            // 표기이므로 수동값 보호 대상이 아니다.
            const now = Date.now();
            const stamped: Record<string, FieldProvenance> = { ...flagged };
            for (const [key, value] of Object.entries(data)) {
              if (value == null) continue;
              if (prevRec && value === prevRec[key]) continue;
              stamped[key] = { source: "user", updatedAt: now };
            }
            next.manualFields = {
              ...(state.manualFields ?? {}),
              cost: stamped,
            };
          }
          return withSnap(state, next);
        });
      },

      updateEsgData: (data, meta) => {
        const source: FieldSource = meta?.source ?? "auto";
        set((state) => {
          const flagged = state.manualFields?.esg ?? {};
          const prevRec = state.esgData
            ? (state.esgData as unknown as Record<string, unknown>)
            : null;
          const next: Partial<ProjectContextState> = {
            esgData: data,
            updatedAt: stampedAt(state, "esg"),
          };
          if (source === "auto") {
            // merge 가드(WP-V, cost와 동일) — full replace이되 user 플래그 키는
            // 이전값 보존(auto 덮어쓰기 차단). 플래그 없으면 종전과 동일한 교체.
            const flaggedKeys = Object.keys(flagged);
            if (prevRec && flaggedKeys.length > 0) {
              const merged = { ...data } as unknown as Record<string, unknown>;
              for (const key of flaggedKeys) {
                if (key in prevRec) merged[key] = prevRec[key];
              }
              next.esgData = merged as unknown as EsgData;
            }
          } else {
            // user 갱신 stamp — 이전값과 달라진 비null 키만 기록(cost와 동일).
            const now = Date.now();
            const stamped: Record<string, FieldProvenance> = { ...flagged };
            for (const [key, value] of Object.entries(data)) {
              if (value == null) continue;
              if (prevRec && value === prevRec[key]) continue;
              stamped[key] = { source: "user", updatedAt: now };
            }
            next.manualFields = {
              ...(state.manualFields ?? {}),
              esg: stamped,
            };
          }
          return withSnap(state, next);
        });
      },

      updateComplianceData: (data) => {
        set((state) =>
          withSnap(state, {
            complianceData: data,
            updatedAt: stampedAt(state, "compliance"),
          }),
        );
      },

      markFinanceUpdated: () => {
        set((state) =>
          withSnap(state, { updatedAt: stampedAt(state, "finance") }),
        );
      },

      revertFieldToAuto: (module, field) => {
        set((state) => {
          const mod = state.manualFields?.[module];
          // 기록이 없으면 no-op(이미 auto) — 스냅샷 불필요 갱신 방지.
          if (!mod || !(field in mod)) return {};
          const rest: Record<string, FieldProvenance> = { ...mod };
          delete rest[field];
          return withSnap(state, {
            manualFields: { ...(state.manualFields ?? {}), [module]: rest },
          });
        });
      },

      getFieldProvenance: (module, field) => {
        return get().manualFields?.[module]?.[field] ?? null;
      },

      markStageComplete: (stage) => {
        const prev = get();
        if (prev.completedStages.includes(stage)) return;
        set(withSnap(prev, { completedStages: [...prev.completedStages, stage] }));
      },

      setCurrentStage: (stage) => {
        set((state) => withSnap(state, { currentStage: stage }));
      },

      addAnalysisResult: (result) => {
        set((state) =>
          withSnap(state, { analysisResults: [...state.analysisResults, result] }),
        );
      },

      getNextRecommendedStage: () => {
        const s = get();
        const { completedStages } = s;
        // 미완료 단계들을 순서대로 모으고, 그중 "업스트림 데이터가 준비된" 첫 단계를
        // 우선 반환한다. 준비된 단계가 없으면(막다른길 방지) 순서상 첫 미완료 단계를
        // 반환한다. 반환 타입/시그니처는 불변(string | null) — 기존 호출처 호환.
        const pending = LIFECYCLE_STAGES.filter(
          (stage) => !completedStages.includes(stage),
        );
        if (pending.length === 0) return null;
        const ready = pending.find((stage) => isStageDataReady(s, stage));
        return ready ?? pending[0];
      },

      isStale: (downstream) => {
        const { updatedAt } = get();
        const own = updatedAt[downstream];
        // 다운스트림이 아직 한 번도 계산되지 않았으면 stale로 보지 않는다
        // (자동재계산 무한 트리거 방지 — 최초 산출은 사용자/자동로드가 담당).
        if (own == null) return false;
        return MODULE_UPSTREAM[downstream].some((up) => {
          const upAt = updatedAt[up];
          return upAt != null && upAt > own;
        });
      },

      isReadyForFirstCompute: (downstream) => {
        const s = get();
        // 이미 한 번이라도 산출됐으면 "최초"가 아님 → false(staleness 경로가 담당).
        if (s.updatedAt[downstream] != null) return false;
        const ups = MODULE_UPSTREAM[downstream];
        // 업스트림이 없는 모듈(siteAnalysis)은 최초산출을 강제하지 않는다(사용자/로드 담당).
        if (ups.length === 0) return false;
        // 모든 직접 업스트림이 실데이터로 준비됐을 때만 최초 자동산출 허용.
        return ups.every((up) => isModuleReady(s, up));
      },

      feasibilityCompleteness: () => {
        const s = get();
        // 단계별 실데이터 반영 판정(무목업): 값이 존재해야 done.
        // ★부지 done은 "수치 확보(landAreaSqm>0)" 기준. 주소만 있고 면적이 없으면
        // 수지 baseline이 0이라 실제로는 미반영 → done=false(거짓 30% 제거).
        const siteDone = !!(
          s.siteAnalysis?.landAreaSqm && s.siteAnalysis.landAreaSqm > 0
        );
        // 주소만 확보된 부분 상태(면적 미확보) — 화면에서 "주소만(부분)"으로 정직 표시 가능.
        const siteAddressOnly = !siteDone && !!s.siteAnalysis?.address;
        const designDone = !!(
          s.designData?.totalGfaSqm && s.designData.totalGfaSqm > 0
        );
        const costDone = !!(
          s.costData?.totalConstructionCostWon &&
          s.costData.totalConstructionCostWon > 0
        );
        const financeDone = !!(
          s.feasibilityData?.totalRevenueWon &&
          s.feasibilityData.totalRevenueWon > 0
        );
        const stages: FeasibilityCompletenessStage[] = [
          { key: "site", label: "부지", done: siteDone, partial: siteAddressOnly, weightPct: 30 },
          { key: "design", label: "설계", done: designDone, weightPct: 60 },
          { key: "cost", label: "공사비", done: costDone, weightPct: 85 },
          { key: "finance", label: "금융", done: financeDone, weightPct: 100 },
        ];
        // 반영도 = 연속으로 완료된 마지막 단계의 누적 가중치(중간 누락 시 직전까지).
        let pct = 0;
        for (const st of stages) {
          if (!st.done) break;
          pct = st.weightPct;
        }
        return { stages, pct };
      },

      projectCompleteness: () => {
        const s = get();
        // 무목업: 각 단계 done은 실데이터(또는 완료 단계 기록)로만 판정.
        const siteDone = !!(
          s.siteAnalysis?.landAreaSqm && s.siteAnalysis.landAreaSqm > 0
        );
        const siteAddressOnly = !siteDone && !!s.siteAnalysis?.address;
        const designDone = !!(
          s.designData?.totalGfaSqm && s.designData.totalGfaSqm > 0
        );
        const costDone = !!(
          s.costData?.totalConstructionCostWon &&
          s.costData.totalConstructionCostWon > 0
        );
        // 법규: 적합판정 또는 법령허브 산출(한도/근거)이 채워졌는가(Fix #1 — 환류 단선 해소).
        const complianceDone = complianceHasData(s.complianceData);
        // 금융: finance 단계가 산출(updatedAt stamp)되었는가. 별도 데이터 필드가
        // 없으므로 staleness 타임스탬프를 done 신호로 사용(무목업: 실제 산출 시에만 stamp).
        const financeDone = !!s.updatedAt.finance;
        // ESG: 탄소 산출 결과가 채워졌는가.
        const esgDone = !!(
          s.esgData &&
          ((s.esgData.totalCarbonPerSqm ?? 0) > 0 ||
            (s.esgData.embodiedCarbonKg ?? 0) > 0)
        );
        // 인허가: 전용 데이터 필드가 없어 완료 단계 기록으로 판정(무목업).
        const permitDone = s.completedStages.includes("permit");

        const stages: ProjectCompletenessStage[] = [
          { key: "site", label: "부지", done: siteDone, partial: siteAddressOnly },
          { key: "design", label: "설계", done: designDone },
          { key: "cost", label: "공사비", done: costDone },
          { key: "compliance", label: "법규", done: complianceDone },
          { key: "finance", label: "금융", done: financeDone },
          { key: "esg", label: "ESG", done: esgDone },
          { key: "permit", label: "인허가", done: permitDone },
        ];
        const total = stages.length;
        const doneCount = stages.filter((st) => st.done).length;
        const pct = total > 0 ? Math.round((doneCount / total) * 100) : 0;
        return { stages, doneCount, total, pct };
      },

      stageHasData: (stageId) => {
        const s = get();
        // 라이프사이클 단계 id(LIFECYCLE_STAGES)별 실데이터 유무를 store 값만으로 판정.
        // 매핑 없는 종합·운영 단계(report/operations)는 undefined(배지 미표시).
        switch (stageId) {
          case "site-analysis":
            return !!(
              (s.siteAnalysis?.landAreaSqm && s.siteAnalysis.landAreaSqm > 0) ||
              s.siteAnalysis?.address ||
              s.siteAnalysis?.zoneCode
            );
          case "legal":
            return complianceHasData(s.complianceData);
          case "design":
          case "bim":
            return !!(s.designData?.totalGfaSqm && s.designData.totalGfaSqm > 0);
          case "construction":
            return !!(
              s.costData?.totalConstructionCostWon &&
              s.costData.totalConstructionCostWon > 0
            );
          case "feasibility":
            return !!(
              s.feasibilityData?.totalRevenueWon &&
              s.feasibilityData.totalRevenueWon > 0
            );
          case "finance":
            return !!s.updatedAt.finance;
          case "esg":
            return !!(
              s.esgData &&
              ((s.esgData.totalCarbonPerSqm ?? 0) > 0 ||
                (s.esgData.embodiedCarbonKg ?? 0) > 0)
            );
          // permit: 전용 데이터 필드가 없어 완료 단계 기록으로만 판정(무목업).
          case "permit":
            return s.completedStages.includes("permit");
          // report/operations 등 종합·운영 단계는 배지 미표시(undefined).
          default:
            return undefined;
        }
      },
    }),
    {
      name: "propai-project-context",
      // ★전 상태변경의 동기 직렬화 점유 제거(화면 전환 지연 근본해소). pagehide flush로 유실 0.
      storage: createDebouncedStorage<ProjectContextState>(500),
      // ★decisionBrief 영속 제외 — 통합 의사결정 브리프는 휘발성 런타임 캐시다(주석 :366의 약속을
      //   실제로 보장). localStorage 에 영속되면 새로고침 후 옛 입력(이전 면적/주소) 판정이
      //   hydrate 로 잔류해 stale 재사용·교차오염을 일으킨다. partialize 로 그 한 필드만 직렬화에서
      //   빼고 나머지 상태는 그대로 영속한다(무회귀). 빠진 필드는 hydrate 시 초기값 null.
      partialize: (state) => {
        const persisted: Record<string, unknown> = { ...state };
        delete persisted.decisionBrief;
        // ★브리프 자체가 영속 제외이므로 그 staleness 타임스탬프(updatedAt.decisionBrief)도 함께
        //   제외한다. 안 그러면 새로고침 후 '브리프는 없는데 타임스탬프만 남은' 불일치 상태가 되어
        //   isStale 판정 기반(own != null)이 어긋난다. 다른 모듈 타임스탬프는 그대로 영속(무회귀).
        if (
          persisted.updatedAt &&
          typeof persisted.updatedAt === "object" &&
          "decisionBrief" in (persisted.updatedAt as Record<string, unknown>)
        ) {
          const ua = { ...(persisted.updatedAt as Record<string, unknown>) };
          delete ua.decisionBrief;
          persisted.updatedAt = ua;
        }
        return persisted as unknown as ProjectContextState;
      },
      // WP-D: 오염 스냅샷 정화 마이그레이션 — hydrate 시 프로젝트 레코드 주소와
      // 핵심 토큰이 불일치하는 스냅샷·live 필드의 siteAnalysis와 파생 designData를
      // null로 정화하고 completedStages에서 site-analysis/design을 제거한다
      // (이미 영속된 오염이 전환 복원→서버 푸시로 고착되는 사슬 차단).
      version: 1,
      migrate: (persisted) => {
        if (!persisted || typeof persisted !== "object") {
          return persisted as ProjectContextState;
        }
        return purifyPersistedContextState(
          persisted as Record<string, unknown>,
        ) as unknown as ProjectContextState;
      },
    },
  ),
);

export { LIFECYCLE_STAGES };
export type { ModuleKey };
export type {
  AnalysisResult,
  SiteAnalysisData,
  DesignData,
  FeasibilityData,
  CostData,
  EsgData,
  ComplianceData,
};
