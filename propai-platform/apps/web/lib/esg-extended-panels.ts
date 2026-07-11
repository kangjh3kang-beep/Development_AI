import { ApiClientError } from "@/lib/api-client";

// 확장 ESG 분석 패널(배선 캠페인 1차 — ESG 클러스터 5건) 순수 로직.
//
// 왜 필요한가(쉬운 설명): RE100/LCC/EU Taxonomy/기후리스크/에너지인증 5개 백엔드 라우터는
// 이미 완성된 서비스인데 화면(UI)이 없어 아무도 호출하지 못했다(배선설계도 P2 트리아지
// ② 배선 후보). 이 파일은 "화면 입력값 → 백엔드 요청 바디" 조립 로직만 순수함수로 뽑아
// 단위테스트로 계약(필드명·타입)을 고정한다 — UI(components/common/ExtendedAnalysisPanel.tsx,
// 배선 캠페인 2차에서 공용 폴더로 이동·리네임됨)는 이 함수들을 그대로 호출만 한다(로직 중복 없음, DRY).
//
// 무날조 원칙: SSOT(store)에서 프리필 가능한 값만 채우고, 근거 없는 추정치는 절대
// 만들어 넣지 않는다(빈 문자열 → 사용자가 직접 입력).

/** 확장 ESG 패널 공용 에러 메시지 추출 — ProjectEsgWorkspaceClient의 동명 로컬 헬퍼와
 *  동일 판정(401/403=인증 안내, 그외=상태코드 노출)이지만 여기서는 독립 export로 두어
 *  기존 파일(불변 요구)을 건드리지 않고 components/common/ExtendedAnalysisPanel.tsx(및
 *  배선 캠페인 2차의 신규 lib/workspace-extended-panels.ts)가 재사용할 수 있게 한다. */
export function extractApiErrorMessage(error: unknown, authMessage: string): string {
  if (error instanceof ApiClientError) {
    if (error.status === 401 || error.status === 403) {
      return authMessage;
    }
    return `API request failed with status ${error.status}.`;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "Request failed.";
}

/* ── 표시 포맷 헬퍼(순수함수 — 단위테스트 대상) ──
   ★QA F1: 라우터마다 백엔드가 비율을 "0.0~1.0"로 주는지 "0~100"으로 이미 주는지가 다르다.
   두 포매터를 이름으로 명확히 구분해 혼동/재발을 막는다(같은 "…Rate" 이름이라도 실제
   스케일이 다르면 반드시 맞는 포매터를 골라 써야 한다 — 호출부 주석에 근거를 남길 것). */

/** 0.0~1.0 비율 → "45.3%"(×100 후 표시). 예: RE100Response.re100_rate(re100.py:67
 *  "0.0~1.0"), roadmap.target_rate(RE100_TARGETS 0.60/0.90/1.00), LCC real_discount_rate. */
export function formatPercent01(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return "-";
  return `${(v * 100).toFixed(1)}%`;
}

/** 이미 0~100 스케일인 값 → "45.3%"(×100 없이 그대로 표시). 예:
 *  EnergyCertificationResponse.energy_independence_rate(construction_ai_service.py:244
 *  "independence_rate = pv_generation / total_demand * 100" — 백엔드가 이미 퍼센트로 반환). */
export function formatPercent100(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return "-";
  return `${v.toFixed(1)}%`;
}

export function formatWon(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return "-";
  if (Math.abs(v) >= 1e8) return `${(v / 1e8).toFixed(1)}억원`;
  if (Math.abs(v) >= 1e4) return `${Math.round(v / 1e4).toLocaleString()}만원`;
  return `${Math.round(v).toLocaleString()}원`;
}

export function formatTco2e(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return "-";
  return `${v.toLocaleString(undefined, { maximumFractionDigits: 1 })} tCO2e`;
}

export function formatNumber(v: number | null | undefined, unit = ""): string {
  if (v == null || !Number.isFinite(v)) return "-";
  return `${v.toLocaleString(undefined, { maximumFractionDigits: 2 })}${unit}`;
}

/* ── 클라이언트 측 gt=0 필수값 검증(순수함수 — QA F3) ──
   백엔드 Pydantic gt=0 제약(전력사용량·초기공사비·GFA·자산가치·연면적)을 제출 전에 미리
   걸러 "빈 값 제출 → 422 일반 에러"가 아니라 해당 필드 옆에 바로 안내한다. */
export function validatePositiveFields(
  values: Record<string, string | boolean>,
  keys: string[],
): Record<string, string> {
  const errors: Record<string, string> = {};
  for (const key of keys) {
    const raw = values[key];
    const num = typeof raw === "string" ? Number(raw) : NaN;
    if (typeof raw !== "string" || raw.trim() === "" || !Number.isFinite(num) || num <= 0) {
      errors[key] = "0보다 큰 값을 입력하세요.";
    }
  }
  return errors;
}

/** ESG 워크스페이스 SSOT에서 뽑아낸, 확장 패널 프리필에 필요한 최소 컨텍스트. */
export interface EsgExtendedPanelContext {
  projectId: string;
  /** 부지 좌표(위경도) — 기후리스크 lat/lon 프리필용. 미확보 시 null. */
  lat: number | null;
  lon: number | null;
  /** 설계 SSOT 연면적(㎡) — EU Taxonomy/에너지인증 GFA 프리필용. */
  totalGfaSqm: number | null;
  /** 설계 SSOT 층수 — 에너지인증 floors 프리필용. */
  floorCount: number | null;
  /** 공사비 우선 자산가치(원) — LCC 초기건설비 프리필용(공사비 특정값 우선). */
  constructionCostWon: number | null;
  /** 총사업비 우선 자산가치(원) — 기후리스크 asset_value_krw 프리필용(보험대상 총자산 개념). */
  assetValueWon: number | null;
  /** LCA 산출 내재탄소(kg) ÷ 연면적(㎡) — EU Taxonomy embodied_carbon_kgco2e_m2 파생 프리필.
   *  둘 다 양수로 확보된 경우에만 계산(무날조 — 하나라도 없으면 null). */
  embodiedCarbonPerSqm: number | null;
}

/** store slice(있는 필드만) → EsgExtendedPanelContext. 순수 매핑(폴백 우선순위만 담당). */
export function buildEsgExtendedContext(input: {
  projectId: string;
  siteAnalysis?: { coordinates?: { lat: number; lon: number } | null } | null;
  designData?: { totalGfaSqm?: number | null; floorCount?: number | null } | null;
  feasibilityData?: { totalCostWon?: number | null } | null;
  costData?: { totalConstructionCostWon?: number | null } | null;
  esgData?: { embodiedCarbonKg?: number | null } | null;
}): EsgExtendedPanelContext {
  const totalGfaSqm = input.designData?.totalGfaSqm ?? null;
  const embodiedCarbonKg = input.esgData?.embodiedCarbonKg ?? null;
  const embodiedCarbonPerSqm =
    embodiedCarbonKg != null &&
    embodiedCarbonKg > 0 &&
    totalGfaSqm != null &&
    totalGfaSqm > 0
      ? embodiedCarbonKg / totalGfaSqm
      : null;

  return {
    projectId: input.projectId,
    lat: input.siteAnalysis?.coordinates?.lat ?? null,
    lon: input.siteAnalysis?.coordinates?.lon ?? null,
    totalGfaSqm,
    floorCount: input.designData?.floorCount ?? null,
    // 공사비(construction) 특정값 우선 → 없으면 총사업비로 폴백(둘 다 없으면 null).
    constructionCostWon:
      input.costData?.totalConstructionCostWon ??
      input.feasibilityData?.totalCostWon ??
      null,
    // 보험 대상 "자산가치"는 총사업비 개념이 더 가까우므로 우선순위를 반대로.
    assetValueWon:
      input.feasibilityData?.totalCostWon ??
      input.costData?.totalConstructionCostWon ??
      null,
    embodiedCarbonPerSqm,
  };
}

/* ────────────────────────────────────────────────────────────────
   ① RE100 (POST /re100/track) — RE100 이행률·K-ETS 배출권 비용 추적.
   전력 사용량은 SSOT에 없는 값(계량 데이터)이라 프리필 불가 — 사용자가 직접 입력.
   ──────────────────────────────────────────────────────────────── */

export interface Re100FormValues {
  trackingYear: string;
  totalElectricityMwh: string;
  renewableElectricityMwh: string;
  ktsUnitPriceKrw: string;
  // 인덱스 시그니처 — ExtendedAnalysisPanel(제네릭 공용 폼 렌더러)의 Record<string, string|boolean>
  // 제약과 구조적으로 호환되게 한다(폼 렌더러가 라우터별 타입을 몰라도 되게).
  [key: string]: string | boolean;
}

export function re100InitialValues(): Re100FormValues {
  return {
    trackingYear: String(new Date().getFullYear()),
    totalElectricityMwh: "",
    renewableElectricityMwh: "",
    // 백엔드 기본값(Re100TrackRequest.kts_unit_price_krw default=18_000)과 동일 — 발명 아님.
    ktsUnitPriceKrw: "18000",
  };
}

/** Re100TrackRequest 계약과 필드명·타입 1:1(routers/re100.py). */
export function buildRe100Body(
  values: Re100FormValues,
  ctx: Pick<EsgExtendedPanelContext, "projectId">,
) {
  return {
    project_id: ctx.projectId,
    tracking_year: Number(values.trackingYear) || 0,
    total_electricity_mwh: Number(values.totalElectricityMwh) || 0,
    renewable_electricity_mwh: Number(values.renewableElectricityMwh) || 0,
    kts_unit_price_krw: Number(values.ktsUnitPriceKrw) || 0,
  };
}

/* ────────────────────────────────────────────────────────────────
   ② LCC (POST /lcc/calculate) — ISO 15686-5 생애주기비용.
   할인율·분석기간 등은 백엔드 기본값이 있으므로 핵심 3필드만 폼에 노출하고
   나머지는 바디에서 생략(Pydantic 기본값 적용 — 발명 금지).
   ──────────────────────────────────────────────────────────────── */

export interface LccFormValues {
  initialConstructionCost: string;
  annualMaintenanceCost: string;
  annualEnergyCost: string;
  [key: string]: string | boolean;
}

export function lccInitialValues(
  ctx: Pick<EsgExtendedPanelContext, "constructionCostWon">,
): LccFormValues {
  return {
    initialConstructionCost:
      ctx.constructionCostWon != null ? String(ctx.constructionCostWon) : "",
    annualMaintenanceCost: "",
    annualEnergyCost: "",
  };
}

/** LccCalculateRequest 계약 핵심 필드(routers/lcc.py) — 나머지는 백엔드 기본값에 위임. */
export function buildLccBody(
  values: LccFormValues,
  ctx: Pick<EsgExtendedPanelContext, "projectId">,
) {
  return {
    project_id: ctx.projectId,
    initial_construction_cost: Number(values.initialConstructionCost) || 0,
    annual_maintenance_cost: Number(values.annualMaintenanceCost) || 0,
    annual_energy_cost: Number(values.annualEnergyCost) || 0,
  };
}

/* ────────────────────────────────────────────────────────────────
   ③ EU Taxonomy (POST /eu-taxonomy/check) — project_id 파라미터 없음(라우터 계약 확인 완료:
   EuTaxonomyCheckRequest에 project_id 필드 부재). 전 필드가 required(기본값 없음)이므로
   9개 전부가 "핵심 필드".
   ──────────────────────────────────────────────────────────────── */

export interface EuTaxonomyFormValues {
  primaryEnergyDemandKwhM2: string;
  renewableEnergyRatio: string; // 0~1
  embodiedCarbonKgco2eM2: string;
  waterUsageLitersPerDay: string;
  wasteRecyclingRate: string; // 0~1
  greenRatio: string; // 0~1
  hasClimateRiskAssessment: boolean;
  hasSocialSafeguards: boolean;
  grossFloorAreaSqm: string;
  [key: string]: string | boolean;
}

export function euTaxonomyInitialValues(
  ctx: Pick<EsgExtendedPanelContext, "totalGfaSqm" | "embodiedCarbonPerSqm">,
): EuTaxonomyFormValues {
  return {
    primaryEnergyDemandKwhM2: "",
    renewableEnergyRatio: "",
    embodiedCarbonKgco2eM2:
      ctx.embodiedCarbonPerSqm != null
        ? String(Math.round(ctx.embodiedCarbonPerSqm * 100) / 100)
        : "",
    waterUsageLitersPerDay: "",
    wasteRecyclingRate: "",
    greenRatio: "",
    hasClimateRiskAssessment: false,
    hasSocialSafeguards: false,
    grossFloorAreaSqm: ctx.totalGfaSqm != null ? String(ctx.totalGfaSqm) : "",
  };
}

/** EuTaxonomyCheckRequest 계약(routers/eu_taxonomy.py) — project_id 없음(라우터 확인 결과). */
export function buildEuTaxonomyBody(values: EuTaxonomyFormValues) {
  return {
    primary_energy_demand_kwh_m2: Number(values.primaryEnergyDemandKwhM2) || 0,
    renewable_energy_ratio: Number(values.renewableEnergyRatio) || 0,
    embodied_carbon_kgco2e_m2: Number(values.embodiedCarbonKgco2eM2) || 0,
    water_usage_liters_per_day: Number(values.waterUsageLitersPerDay) || 0,
    waste_recycling_rate: Number(values.wasteRecyclingRate) || 0,
    green_ratio: Number(values.greenRatio) || 0,
    has_climate_risk_assessment: !!values.hasClimateRiskAssessment,
    has_social_safeguards: !!values.hasSocialSafeguards,
    gross_floor_area_sqm: Number(values.grossFloorAreaSqm) || 0,
  };
}

/* ────────────────────────────────────────────────────────────────
   ④ 기후리스크 (POST /climate/risk) — packages/schemas/models.py ClimateRiskAssessmentRequest.
   ──────────────────────────────────────────────────────────────── */

export interface ClimateFormValues {
  lat: string;
  lon: string;
  assetValueKrw: string;
  constructionPeriodMonths: string;
  [key: string]: string | boolean;
}

export function climateInitialValues(
  ctx: Pick<EsgExtendedPanelContext, "lat" | "lon" | "assetValueWon">,
): ClimateFormValues {
  return {
    lat: ctx.lat != null ? String(ctx.lat) : "",
    lon: ctx.lon != null ? String(ctx.lon) : "",
    assetValueKrw: ctx.assetValueWon != null ? String(ctx.assetValueWon) : "",
    // 백엔드 기본값(ClimateRiskAssessmentRequest.construction_period_months default=24)과 동일.
    constructionPeriodMonths: "24",
  };
}

/** ClimateRiskAssessmentRequest 계약 1:1. */
export function buildClimateBody(
  values: ClimateFormValues,
  ctx: Pick<EsgExtendedPanelContext, "projectId">,
) {
  return {
    project_id: ctx.projectId,
    lat: Number(values.lat) || 0,
    lon: Number(values.lon) || 0,
    asset_value_krw: Number(values.assetValueKrw) || 0,
    construction_period_months: Number(values.constructionPeriodMonths) || 24,
  };
}

/* ────────────────────────────────────────────────────────────────
   ⑤ 에너지 인증 추정 (POST /energy/certification) — packages/schemas/models.py
   EnergyCertificationRequest. energy.py는 kepco/calculate 엔드포인트도 갖지만(요금
   계산), ESG 워크스페이스 취지(에너지등급·ZEB·에너지자립률)에 맞는 인증 엔드포인트만
   이번 배선 범위로 선택(스코프 결정 — 요금계산은 향후 별도 배선 후보).
   ──────────────────────────────────────────────────────────────── */

export interface EnergyCertificationFormValues {
  totalAreaSqm: string;
  floors: string;
  windowWallRatio: string;
  insulationGrade: string;
  bemsSavingRate: string;
  [key: string]: string | boolean;
}

export function energyCertificationInitialValues(
  ctx: Pick<EsgExtendedPanelContext, "totalGfaSqm" | "floorCount">,
): EnergyCertificationFormValues {
  return {
    totalAreaSqm: ctx.totalGfaSqm != null ? String(ctx.totalGfaSqm) : "",
    floors: ctx.floorCount != null ? String(ctx.floorCount) : "",
    // 백엔드 기본값(EnergyCertificationRequest.window_wall_ratio default=0.35)과 동일.
    windowWallRatio: "0.35",
    // ★백엔드 기본 문자열은 인코딩 손상값("1?깃툒")이라 그대로 재현하지 않고 정상 표기로
    //   대체 — 어차피 프론트가 항상 이 필드를 명시 전송하므로 손상값이 전송되지 않는다.
    insulationGrade: "1등급",
    bemsSavingRate: "0",
  };
}

/** EnergyCertificationRequest 계약 1:1. */
export function buildEnergyCertificationBody(
  values: EnergyCertificationFormValues,
  ctx: Pick<EsgExtendedPanelContext, "projectId">,
) {
  return {
    project_id: ctx.projectId,
    total_area_sqm: Number(values.totalAreaSqm) || 0,
    floors: Number(values.floors) || 1,
    window_wall_ratio: Number(values.windowWallRatio) || 0.35,
    insulation_grade: values.insulationGrade?.trim() || "1등급",
    bems_saving_rate: Number(values.bemsSavingRate) || 0,
  };
}
