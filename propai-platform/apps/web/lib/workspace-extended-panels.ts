import { effectiveLandAreaSqm } from "@/lib/site-area";
// 배선 캠페인 2차(워크스페이스 클러스터 6건) 순수 로직.
//
// 왜 필요한가(쉬운 설명): permit-cases/cost-intelligence/underwriting/safety/construction/
// cad-correction 6개 백엔드 라우터는 이미 완성된 서비스인데 화면(UI)이 없어 아무도
// 호출하지 못했다(배선설계도 P2 트리아지 ② 배선 후보). 이 파일은 1차(ESG 클러스터,
// lib/esg-extended-panels.ts)와 동일한 구조로 "화면 입력값 → 백엔드 요청 바디" 조립
// 로직만 순수함수로 뽑아 단위테스트로 계약(필드명·타입)을 고정한다 — UI(각 *Section.tsx)는
// 이 함수들을 그대로 호출만 한다(로직 중복 없음, DRY).
//
// 표시 포맷·에러 추출 헬퍼(formatWon/formatPercent01/formatPercent100/formatNumber/
// formatTco2e/extractApiErrorMessage/validatePositiveFields)는 순수 범용 유틸이라 ESG
// 전용이 아니다 — 새로 복제하지 않고 lib/esg-extended-panels.ts에서 그대로 재사용한다
// (전역전파방지 원칙: 같은 로직 두 곳에 두지 않는다).
//
// 무날조 원칙: SSOT(store)에서 프리필 가능한 값만 채우고, 근거 없는 추정치는 절대
// 만들어 넣지 않는다(빈 문자열 → 사용자가 직접 입력).

/** 6개 라우터 패널이 공유하는 프리필 컨텍스트 — SSOT(store)에서 뽑아낸 최소 공통분모. */
export interface WorkspaceExtendedPanelContext {
  projectId: string;
  /** store.projectName(빈 문자열이면 null — 미확보와 빈 문자열을 구분). */
  projectName: string | null;
  /** 인허가 사례 조회(PNU 기준) 프리필 — siteAnalysis.pnu. */
  pnu: string | null;
  /** 부지 좌표(위경도) — 시공 기후리스크 lat/lon 프리필용. 미확보 시 null. */
  lat: number | null;
  lon: number | null;
  /** 설계 SSOT 연면적(㎡) — 시공일정/ZEB에너지 GFA 프리필용. */
  totalGfaSqm: number | null;
  /** 설계 SSOT 층수 — 시공일정/ZEB에너지 floors 프리필용. */
  floorCount: number | null;
  /** 부지분석 SSOT 대지면적(㎡) — CAD 자동보정 site_area_sqm 프리필용. */
  landAreaSqm: number | null;
  /** 설계 SSOT 매스 기하의 건축면적(㎡·1개층 footprint) — CAD 자동보정 building_area_sqm 프리필용.
   *  massGeom이 없으면 null(폭×깊이 역산 등 파생 금지 — 무날조). */
  buildingFootprintSqm: number | null;
  /** 부지분석 SSOT 실효 건폐율/용적률(%) — CAD 자동보정 규제 한도(max_bcr/max_far) 프리필용.
   *  실효값(조례 반영) 우선, 없으면 법정값으로 폴백. */
  effectiveBcrPct: number | null;
  effectiveFarPct: number | null;
  /** 설계 SSOT 법정 높이 한도(m) — CAD 자동보정 max_height_m 프리필용(없으면 컴포넌트가 0=무제한 처리). */
  maxHeightM: number | null;
  /** 수지 SSOT 총사업비/총매출(원) — 언더라이팅 total_cost_krw/projected_revenue_krw 프리필용. */
  totalCostWon: number | null;
  totalRevenueWon: number | null;
  /** 수지 SSOT 자기자본(원) — 언더라이팅 equity_krw 프리필용. */
  equityWon: number | null;
  /** 부지분석 SSOT 추정 토지가치(원·AVM/탁상) — 언더라이팅 acquisition_price_krw(매입가) 프리필용.
   *  다른 컴포넌트(DevelopmentFinancePanel 등)도 동일하게 estimatedValue를 취득원가/토지비 프록시로 쓴다. */
  estimatedLandValueWon: number | null;
  /** 공사비 SSOT 총공사비(원) — 자재가·에스컬레이션 base_construction_cost_krw 프리필용. */
  totalConstructionCostWon: number | null;
}

/** store slice(있는 필드만) → WorkspaceExtendedPanelContext. 순수 매핑(폴백 우선순위만 담당). */
export function buildWorkspaceExtendedContext(input: {
  projectId: string;
  projectName?: string | null;
  siteAnalysis?: {
    pnu?: string | null;
    coordinates?: { lat: number; lon: number } | null;
    landAreaSqm?: number | null;
    // 다필지 통합면적·필지수 — effectiveLandAreaSqm(SSOT)이 통합면적 우선 판정에 사용.
    landAreaSqmTotal?: number | null;
    parcelCount?: number | null;
    effectiveBcrPct?: number | null;
    effectiveFarPct?: number | null;
    nationalBcrPct?: number | null;
    nationalFarPct?: number | null;
    estimatedValue?: number | null;
  } | null;
  designData?: {
    totalGfaSqm?: number | null;
    floorCount?: number | null;
    maxHeightM?: number | null;
    massGeom?: { footprintSqm?: number | null } | null;
  } | null;
  feasibilityData?: {
    totalCostWon?: number | null;
    totalRevenueWon?: number | null;
    equityWon?: number | null;
  } | null;
  costData?: { totalConstructionCostWon?: number | null } | null;
}): WorkspaceExtendedPanelContext {
  return {
    projectId: input.projectId,
    projectName: input.projectName?.trim() ? input.projectName.trim() : null,
    pnu: input.siteAnalysis?.pnu ?? null,
    lat: input.siteAnalysis?.coordinates?.lat ?? null,
    lon: input.siteAnalysis?.coordinates?.lon ?? null,
    totalGfaSqm: input.designData?.totalGfaSqm ?? null,
    floorCount: input.designData?.floorCount ?? null,
    // ★면적은 effectiveLandAreaSqm(SSOT) — raw 금지. 이 값은 CadCorrectionSection 의
    //   '대지면적' 표시 필드·/cad-correction/check 바디로 흘러가므로 다필지에서 raw 면적이면
    //   CAD 법규검증이 대표필지 면적 기준으로 오판한다.
    landAreaSqm: effectiveLandAreaSqm(input.siteAnalysis) ?? null,
    buildingFootprintSqm: input.designData?.massGeom?.footprintSqm ?? null,
    // 실효(조례 반영) 우선 → 없으면 법정 상한으로 폴백(단일필지/통합 모두 자연 동작).
    effectiveBcrPct:
      input.siteAnalysis?.effectiveBcrPct ?? input.siteAnalysis?.nationalBcrPct ?? null,
    effectiveFarPct:
      input.siteAnalysis?.effectiveFarPct ?? input.siteAnalysis?.nationalFarPct ?? null,
    maxHeightM: input.designData?.maxHeightM ?? null,
    totalCostWon: input.feasibilityData?.totalCostWon ?? null,
    totalRevenueWon: input.feasibilityData?.totalRevenueWon ?? null,
    equityWon: input.feasibilityData?.equityWon ?? null,
    estimatedLandValueWon: input.siteAnalysis?.estimatedValue ?? null,
    totalConstructionCostWon: input.costData?.totalConstructionCostWon ?? null,
  };
}

/* ════════════════════════════════════════════════════════════════
   ① 인허가 사례(GET /permit-cases?pnu=&kind=&page=&page_size=) —
   건축HUB 기반 사례 조회(routers/permit_cases.py). GET+쿼리라 body가
   아니라 쿼리 파라미터를 조립한다(ExtendedAnalysisPanel의 POST 폼과
   달리 전용 소형 컴포넌트가 이 함수를 사용).
   ════════════════════════════════════════════════════════════════ */

export type PermitCaseKind = "arch" | "hs";

export interface PermitCaseFormValues {
  pnu: string;
  kind: PermitCaseKind;
}

export function permitCaseInitialValues(
  ctx: Pick<WorkspaceExtendedPanelContext, "pnu">,
): PermitCaseFormValues {
  return { pnu: ctx.pnu ?? "", kind: "arch" };
}

/** GET 쿼리 파라미터 조립(routers/permit_cases.py list_permit_cases 계약 1:1). */
export function buildPermitCaseQuery(values: PermitCaseFormValues): Record<string, string> {
  return {
    pnu: values.pnu.trim(),
    kind: values.kind === "hs" ? "hs" : "arch",
    page: "1",
    page_size: "20",
  };
}

/* ════════════════════════════════════════════════════════════════
   ② 자재가·에스컬레이션 (POST /cost-intelligence/escalation/analyze) —
   KCCI 자재가 기반 공사비 에스컬레이션(routers/cost_intelligence.py).
   material-prices/latest(GET)는 프로젝트별 자재가 스냅샷을 별도로
   자동조회(폼 없음 — 컴포넌트가 useQuery로 직접 처리).
   ════════════════════════════════════════════════════════════════ */

export interface CostEscalationFormValues {
  baseConstructionCostKrw: string;
  baselineYear: string;
  targetYear: string;
  constructionDurationMonths: string;
  regionCode: string;
  [key: string]: string | boolean;
}

export function costEscalationInitialValues(
  ctx: Pick<WorkspaceExtendedPanelContext, "totalConstructionCostWon">,
): CostEscalationFormValues {
  return {
    baseConstructionCostKrw:
      ctx.totalConstructionCostWon != null ? String(ctx.totalConstructionCostWon) : "",
    baselineYear: String(new Date().getFullYear()),
    targetYear: "",
    // 백엔드 기본값(CostEscalationRequest.construction_duration_months default=18)과 동일.
    constructionDurationMonths: "18",
    // 백엔드 기본값(region_code default="KR")과 동일.
    regionCode: "KR",
  };
}

/** CostEscalationRequest 핵심 필드 계약(routers/cost_intelligence.py) — material/labor/overhead/
 *  contingency 비율·material_codes는 백엔드 기본값에 위임(선택 필드 생략, LCC 패턴과 동일). */
export function buildCostEscalationBody(
  values: CostEscalationFormValues,
  ctx: Pick<WorkspaceExtendedPanelContext, "projectId">,
) {
  return {
    project_id: ctx.projectId,
    base_construction_cost_krw: Number(values.baseConstructionCostKrw) || 0,
    baseline_year: Number(values.baselineYear) || new Date().getFullYear(),
    target_year: Number(values.targetYear) || 0,
    construction_duration_months: Number(values.constructionDurationMonths) || 18,
    region_code: values.regionCode?.trim() || "KR",
  };
}

/* ════════════════════════════════════════════════════════════════
   ③ 언더라이팅 (POST /underwriting/{project_id}) — 투자 심사
   리스크·수익성 평가(routers/underwriting.py). endpoint는 project_id를
   경로에도 포함하므로 호출부가 `/underwriting/${projectId}`로 조립한다.
   ════════════════════════════════════════════════════════════════ */

export interface UnderwritingFormValues {
  projectName: string;
  totalCostKrw: string;
  projectedRevenueKrw: string;
  acquisitionPriceKrw: string;
  equityKrw: string;
  debtKrw: string;
  jeonseRatio: string;
  [key: string]: string | boolean;
}

export function underwritingInitialValues(
  ctx: Pick<
    WorkspaceExtendedPanelContext,
    "projectName" | "totalCostWon" | "totalRevenueWon" | "estimatedLandValueWon" | "equityWon"
  >,
): UnderwritingFormValues {
  const totalCost = ctx.totalCostWon;
  const equity = ctx.equityWon;
  // 부채(debt) = 총사업비 - 자기자본(둘 다 확보되고 자기자본이 총사업비 이하일 때만 산술 파생 —
  // 무날조: 하나라도 없거나 앞뒤가 안 맞으면 공란으로 두어 사용자가 직접 입력하게 한다).
  const debt =
    totalCost != null && equity != null && totalCost >= equity ? totalCost - equity : null;
  return {
    projectName: ctx.projectName ?? "",
    totalCostKrw: totalCost != null ? String(totalCost) : "",
    projectedRevenueKrw: ctx.totalRevenueWon != null ? String(ctx.totalRevenueWon) : "",
    acquisitionPriceKrw:
      ctx.estimatedLandValueWon != null ? String(ctx.estimatedLandValueWon) : "",
    equityKrw: equity != null ? String(equity) : "",
    debtKrw: debt != null ? String(debt) : "",
    jeonseRatio: "",
  };
}

/** UnderwritingRequest 계약 1:1(routers/underwriting.py) — assumptions_json/data_room_documents는
 *  백엔드 기본값(빈 dict/list)에 위임(문서 업로드는 이 패널 범위 밖 — 별도 데이터룸 기능). */
export function buildUnderwritingBody(
  values: UnderwritingFormValues,
  ctx: Pick<WorkspaceExtendedPanelContext, "projectId">,
) {
  const jeonse = values.jeonseRatio.trim();
  return {
    project_id: ctx.projectId,
    project_name: values.projectName.trim(),
    total_cost_krw: Number(values.totalCostKrw) || 0,
    projected_revenue_krw: Number(values.projectedRevenueKrw) || 0,
    acquisition_price_krw: Number(values.acquisitionPriceKrw) || 0,
    equity_krw: Number(values.equityKrw) || 0,
    debt_krw: Number(values.debtKrw) || 0,
    jeonse_ratio: jeonse === "" ? null : Number(jeonse),
    assumptions_json: {},
    data_room_documents: [],
  };
}

/* ════════════════════════════════════════════════════════════════
   ④ 시공/ESG AI (routers/construction.py) — 4개 엔드포인트.
   ════════════════════════════════════════════════════════════════ */

/* ── ④-1 시공 일정 생성 (POST /construction/schedule) ── */

export interface ConstructionScheduleFormValues {
  totalAreaSqm: string;
  floorsAbove: string;
  floorsBelow: string;
  structureType: string;
  [key: string]: string | boolean;
}

export function constructionScheduleInitialValues(
  ctx: Pick<WorkspaceExtendedPanelContext, "totalGfaSqm" | "floorCount">,
): ConstructionScheduleFormValues {
  return {
    totalAreaSqm: ctx.totalGfaSqm != null ? String(ctx.totalGfaSqm) : "",
    floorsAbove: ctx.floorCount != null ? String(ctx.floorCount) : "",
    // 백엔드 기본값(ConstructionScheduleRequest.floors_below default=1)과 동일.
    floorsBelow: "1",
    // 백엔드 기본값(structure_type default="RC")과 동일.
    structureType: "RC",
  };
}

/** ConstructionScheduleRequest 계약 1:1(routers/construction.py). */
export function buildConstructionScheduleBody(
  values: ConstructionScheduleFormValues,
  ctx: Pick<WorkspaceExtendedPanelContext, "projectId">,
) {
  return {
    project_id: ctx.projectId,
    total_area_sqm: Number(values.totalAreaSqm) || 0,
    floors_above: Number(values.floorsAbove) || 1,
    floors_below: Number(values.floorsBelow) || 0,
    structure_type: values.structureType?.trim() || "RC",
  };
}

/* ── ④-2 ZEB 에너지 시뮬레이션 (POST /construction/zeb-energy) ── */

export interface ZebEnergyFormValues {
  totalAreaSqm: string;
  floors: string;
  windowWallRatio: string;
  insulationGrade: string;
  [key: string]: string | boolean;
}

export function zebEnergyInitialValues(
  ctx: Pick<WorkspaceExtendedPanelContext, "totalGfaSqm" | "floorCount">,
): ZebEnergyFormValues {
  return {
    totalAreaSqm: ctx.totalGfaSqm != null ? String(ctx.totalGfaSqm) : "",
    floors: ctx.floorCount != null ? String(ctx.floorCount) : "",
    // 백엔드 기본값(ZEBEnergyRequest.window_wall_ratio default=0.35)과 동일.
    windowWallRatio: "0.35",
    // 백엔드 기본값(insulation_grade default="1등급")과 동일(energy.py 손상 기본값 재현 금지 —
    // 1차 ESG 에너지인증 패널과 동일 판단).
    insulationGrade: "1등급",
  };
}

/** ZEBEnergyRequest 계약 1:1(routers/construction.py). */
export function buildZebEnergyBody(
  values: ZebEnergyFormValues,
  ctx: Pick<WorkspaceExtendedPanelContext, "projectId">,
) {
  return {
    project_id: ctx.projectId,
    total_area_sqm: Number(values.totalAreaSqm) || 0,
    floors: Number(values.floors) || 1,
    window_wall_ratio: Number(values.windowWallRatio) || 0.35,
    insulation_grade: values.insulationGrade?.trim() || "1등급",
  };
}

/* ── ④-3 기후 리스크 분석 (POST /construction/climate-risk) —
   ★1차 ESG의 "/climate/risk"(routers/climate.py)와는 다른 라우터·다른 응답 모델이다
   (이쪽은 evidence는 있으나 annual_expected_loss_krw·insurance_recommendations가 없다).
   같은 이름의 두 리스크 엔드포인트가 존재하는 것은 배선 캠페인 범위 밖(트리아지 기록만). ── */

export interface ConstructionClimateFormValues {
  lat: string;
  lon: string;
  constructionPeriodMonths: string;
  [key: string]: string | boolean;
}

export function constructionClimateInitialValues(
  ctx: Pick<WorkspaceExtendedPanelContext, "lat" | "lon">,
): ConstructionClimateFormValues {
  return {
    lat: ctx.lat != null ? String(ctx.lat) : "",
    lon: ctx.lon != null ? String(ctx.lon) : "",
    // 백엔드 기본값(ClimateRiskRequest.construction_period_months default=24)과 동일.
    constructionPeriodMonths: "24",
  };
}

/** ClimateRiskRequest 계약 1:1(routers/construction.py packages/schemas/models.py). */
export function buildConstructionClimateBody(
  values: ConstructionClimateFormValues,
  ctx: Pick<WorkspaceExtendedPanelContext, "projectId">,
) {
  return {
    project_id: ctx.projectId,
    lat: Number(values.lat) || 0,
    lon: Number(values.lon) || 0,
    construction_period_months: Number(values.constructionPeriodMonths) || 24,
  };
}

/* ── ④-4 하자 사진 AI 분류 (POST /construction/defect-classify) —
   image_url은 SSOT 프리필 원천이 없다(사용자가 이미 업로드된 사진 URL을 직접 입력). ── */

export interface DefectClassificationFormValues {
  imageUrl: string;
  location: string;
  [key: string]: string | boolean;
}

export function defectClassificationInitialValues(): DefectClassificationFormValues {
  return { imageUrl: "", location: "" };
}

/** DefectClassificationRequest 계약 1:1(routers/construction.py). */
export function buildDefectClassificationBody(
  values: DefectClassificationFormValues,
  ctx: Pick<WorkspaceExtendedPanelContext, "projectId">,
) {
  return {
    project_id: ctx.projectId,
    image_url: values.imageUrl.trim(),
    location: values.location.trim(),
  };
}

/* ════════════════════════════════════════════════════════════════
   ⑤ CAD 파라메트릭 자동 보정 (routers/cad_correction.py) — 2개 엔드포인트.
   ★project_id 필드 없음(라우터 계약 확인 결과 — BuildingPayload/RegulationPayload에
   프로젝트 식별자가 없다). building/regulation 중첩 객체로 조립한다.
   ════════════════════════════════════════════════════════════════ */

export interface CadCorrectionFormValues {
  siteAreaSqm: string;
  buildingAreaSqm: string;
  numFloors: string;
  floorHeightM: string;
  maxBcr: string;
  maxFar: string;
  maxHeightM: string;
  [key: string]: string | boolean;
}

export function cadCorrectionInitialValues(
  ctx: Pick<
    WorkspaceExtendedPanelContext,
    "landAreaSqm" | "buildingFootprintSqm" | "floorCount" | "effectiveBcrPct" | "effectiveFarPct" | "maxHeightM"
  >,
): CadCorrectionFormValues {
  return {
    siteAreaSqm: ctx.landAreaSqm != null ? String(ctx.landAreaSqm) : "",
    buildingAreaSqm: ctx.buildingFootprintSqm != null ? String(ctx.buildingFootprintSqm) : "",
    numFloors: ctx.floorCount != null ? String(ctx.floorCount) : "",
    // 백엔드 기본값(BuildingPayload.floor_height_m default=3.0)과 동일.
    floorHeightM: "3",
    maxBcr: ctx.effectiveBcrPct != null ? String(ctx.effectiveBcrPct) : "",
    maxFar: ctx.effectiveFarPct != null ? String(ctx.effectiveFarPct) : "",
    // 설계 SSOT 높이 한도가 있으면 그 값을, 없으면 백엔드 문서화된 sentinel(0=높이 제한 없음,
    // RegulationPayload.max_height_m default=0.0)을 그대로 사용(발명 아님).
    maxHeightM: ctx.maxHeightM != null ? String(ctx.maxHeightM) : "0",
  };
}

/** CheckRequest 계약 1:1(routers/cad_correction.py) — building/regulation 중첩. */
export function buildCadCheckBody(values: CadCorrectionFormValues) {
  return {
    building: {
      site_area_sqm: Number(values.siteAreaSqm) || 0,
      building_area_sqm: Number(values.buildingAreaSqm) || 0,
      num_floors: Number(values.numFloors) || 1,
      floor_height_m: Number(values.floorHeightM) || 3,
    },
    regulation: {
      max_bcr: Number(values.maxBcr) || 0,
      max_far: Number(values.maxFar) || 0,
      max_height_m: Number(values.maxHeightM) || 0,
    },
  };
}

export interface CadAutoCorrectFormValues extends CadCorrectionFormValues {
  maxIter: string;
}

export function cadAutoCorrectInitialValues(
  ctx: Pick<
    WorkspaceExtendedPanelContext,
    "landAreaSqm" | "buildingFootprintSqm" | "floorCount" | "effectiveBcrPct" | "effectiveFarPct" | "maxHeightM"
  >,
): CadAutoCorrectFormValues {
  return {
    ...cadCorrectionInitialValues(ctx),
    // 백엔드 기본값(AutoCorrectRequest.max_iter default=100)과 동일.
    maxIter: "100",
  };
}

/** AutoCorrectRequest 계약 1:1(routers/cad_correction.py) — building/regulation은 check와 동일 조립. */
export function buildCadAutoCorrectBody(values: CadAutoCorrectFormValues) {
  return {
    ...buildCadCheckBody(values),
    max_iter: Number(values.maxIter) || 100,
  };
}

/* ════════════════════════════════════════════════════════════════
   배선 캠페인 3차(운영/기타 5건) — apps/api/routers·apps/api/app/routers 실파일
   대조 확인(계약 1:1). 아래 ⑥~⑨는 프로젝트 목록(전역 페이지)에서 선택한 프로젝트를
   ctx로 넘기는 경우가 많아 projectId/projectName만 Pick하는 최소 컨텍스트를 쓴다
   (useProjectContextStore의 "현재 프로젝트" SSOT가 아니라 페이지 자체의 프로젝트
   선택 상태 — tenant/sales 목록 페이지는 프로젝트 스코프 라우트가 아니므로).
   ════════════════════════════════════════════════════════════════ */

/* ── ⑥ 공유시설 예약 (POST /facilities/reserve, POST /facilities/cancel) —
   routers/facility_reservations.py. project_id는 SSOT가 아니라 페이지에서 고른
   프로젝트 목록 중 선택값(무날조: 프리필 없음 — 사용자가 직접 고른다). ── */

export interface FacilityReserveFormValues {
  facilityName: string;
  startTime: string; // datetime-local 문자열(YYYY-MM-DDTHH:mm)
  endTime: string;
  notes: string;
  [key: string]: string | boolean;
}

export function facilityReserveInitialValues(): FacilityReserveFormValues {
  return { facilityName: "", startTime: "", endTime: "", notes: "" };
}

/** CreateReservationRequest 계약 1:1(routers/facility_reservations.py) — datetime-local
 *  문자열은 초 단위가 없어(YYYY-MM-DDTHH:mm) 그대로 두면 Pydantic datetime 파싱이
 *  통과한다(ISO 8601 부분 표현 허용). 별도 초 부착·타임존 변환은 하지 않는다(무날조). */
export function buildFacilityReserveBody(
  values: FacilityReserveFormValues,
  ctx: { projectId: string },
) {
  return {
    project_id: ctx.projectId,
    facility_name: values.facilityName.trim(),
    start_time: values.startTime,
    end_time: values.endTime,
    notes: values.notes.trim() || null,
  };
}

/** CancelReservationRequest 계약 1:1(routers/facility_reservations.py). */
export function buildFacilityCancelBody(reservationId: string) {
  return { reservation_id: reservationId.trim() };
}

/* ── ⑦ 예지보전 이상감지 (POST /maintenance/detect-anomaly) —
   routers/maintenance.py + packages/schemas/models.py MaintenanceAnomalyRequest.
   gt=0 기본값 검증은 백엔드 Field(ge=0) 수준(0 허용)이라 이 패널은 gt=0 강제 없음
   (energy_efficiency_ratio=0도 백엔드가 수용하는 유효값). ── */

export interface MaintenanceAnomalyFormValues {
  equipmentName: string;
  equipmentType: string;
  location: string;
  vibrationMmS: string;
  temperatureC: string;
  energyEfficiencyRatio: string;
  [key: string]: string | boolean;
}

export function maintenanceAnomalyInitialValues(): MaintenanceAnomalyFormValues {
  return {
    equipmentName: "",
    // ★equipment_type은 백엔드 기본값이 없다(MaintenanceAnomalyRequest.equipment_type: str,
    // default 없음) — "hvac" 등을 프리필하면 사용자가 입력하지 않은 값을 지어내는 것이라
    // 무날조 원칙 위반. 빈 문자열로 두고 사용자가 직접 입력하게 한다(플레이스홀더로만 예시 제시).
    equipmentType: "",
    location: "",
    // 백엔드 기본값(MaintenanceAnomalyRequest 필드 default)과 동일.
    vibrationMmS: "0",
    temperatureC: "0",
    energyEfficiencyRatio: "1",
  };
}

/** MaintenanceAnomalyRequest 계약 1:1(packages/schemas/models.py:1177) — equipment_type은
 *  백엔드 기본값이 없으므로(위 초기값 주석 참조) 폴백 없이 트림한 값을 그대로 보낸다. */
export function buildMaintenanceAnomalyBody(
  values: MaintenanceAnomalyFormValues,
  ctx: { projectId: string },
) {
  return {
    project_id: ctx.projectId,
    equipment_name: values.equipmentName.trim(),
    equipment_type: values.equipmentType.trim(),
    location: values.location.trim() || null,
    vibration_mm_s: Number(values.vibrationMmS) || 0,
    temperature_c: Number(values.temperatureC) || 0,
    // ★효율비는 0이 유효 앵커값(설비 완전정지) — `|| 1` 폴백은 명시적 0 입력을 정상(1)으로
    //   위조해 이상감지를 무력화한다(QA MEDIUM). 빈값/NaN일 때만 백엔드 기본 1로 폴백.
    energy_efficiency_ratio: Number.isFinite(Number(values.energyEfficiencyRatio)) && values.energyEfficiencyRatio.trim() !== ""
      ? Number(values.energyEfficiencyRatio)
      : 1,
  };
}

/* ── ⑧ 마케팅 콘텐츠·OM 리포트 (POST /marketing/generate, POST /marketing/om-report) —
   routers/marketing.py + packages/schemas/models.py(MarketingContentRequest/OMReportRequest).
   highlights/investment_highlights/risk_factors는 콤마 구분 문자열 입력 → 배열 분해
   (DigitalTwinControlTowerWorkspaceClient의 submittedDocumentIds와 동일 관례). ── */

export interface MarketingContentFormValues {
  channel: string;
  assetType: string;
  targetAudience: string;
  tone: string;
  highlights: string;
  [key: string]: string | boolean;
}

export function marketingContentInitialValues(): MarketingContentFormValues {
  return {
    // ★channel은 백엔드 기본값이 없다(MarketingContentRequest.channel: str, default 없음) —
    // "web" 등을 프리필하면 사용자가 고르지 않은 채널을 지어내는 것이라 무날조 원칙 위반.
    // 빈 문자열로 두고 사용자가 직접 입력하게 한다.
    channel: "",
    assetType: "",
    targetAudience: "",
    // 백엔드 기본값(MarketingContentRequest.tone default="professional")과 동일.
    tone: "professional",
    highlights: "",
  };
}

function splitCommaList(raw: string): string[] {
  return raw
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

/** MarketingContentRequest 계약 1:1(packages/schemas/models.py:1019) — channel은 백엔드
 *  기본값이 없으므로(위 초기값 주석 참조) 폴백 없이 트림한 값을 그대로 보낸다. */
export function buildMarketingContentBody(
  values: MarketingContentFormValues,
  ctx: { projectId: string; projectName: string },
) {
  return {
    project_id: ctx.projectId,
    project_name: ctx.projectName,
    channel: values.channel.trim(),
    asset_type: values.assetType.trim(),
    target_audience: values.targetAudience.trim(),
    tone: values.tone.trim() || "professional",
    highlights: splitCommaList(values.highlights),
  };
}

export interface OmReportFormValues {
  assetType: string;
  investmentHighlights: string;
  targetAudience: string;
  riskFactors: string;
  outputFormat: string;
  [key: string]: string | boolean;
}

export function omReportInitialValues(): OmReportFormValues {
  return {
    assetType: "",
    investmentHighlights: "",
    // 백엔드 기본값(OMReportRequest.target_audience default="institutional")과 동일.
    targetAudience: "institutional",
    riskFactors: "",
    // 백엔드 기본값(OMReportRequest.output_format default="markdown")과 동일.
    outputFormat: "markdown",
  };
}

/** OMReportRequest 계약 1:1(packages/schemas/models.py:1043). */
export function buildOmReportBody(
  values: OmReportFormValues,
  ctx: { projectId: string; projectName: string },
) {
  return {
    project_id: ctx.projectId,
    project_name: ctx.projectName,
    asset_type: values.assetType.trim(),
    investment_highlights: splitCommaList(values.investmentHighlights),
    target_audience: values.targetAudience.trim() || "institutional",
    risk_factors: splitCommaList(values.riskFactors),
    output_format: values.outputFormat.trim() || "markdown",
  };
}

/* ── ⑨ C2R 좌표→렌더 브리프 (POST /c2r/brief) — apps/api/app/routers/c2r.py.
   render(POST /c2r/render)은 brief 응답 객체를 그대로 되돌려 보내는 2단계 흐름이라
   "폼값 → 바디" 순수함수로 뽑을 입력이 브리프 자체뿐이다(별도 계약 함수 불필요 —
   컴포넌트가 이전 단계 응답을 그대로 body.brief에 담는다). ── */

export interface C2rBriefFormValues {
  pnu: string;
  address: string;
  buildingUse: string;
  scale: string;
  useLlm: boolean;
  [key: string]: string | boolean;
}

/** pnu/address는 SSOT(siteAnalysis)에서 프리필 — 없으면 빈 문자열(무날조). */
export function c2rBriefInitialValues(
  ctx: Pick<WorkspaceExtendedPanelContext, "pnu"> & { address?: string | null },
): C2rBriefFormValues {
  return {
    pnu: ctx.pnu ?? "",
    address: ctx.address ?? "",
    buildingUse: "",
    scale: "",
    useLlm: false,
  };
}

/** BriefRequest 계약 1:1(apps/api/app/routers/c2r.py) — 라우터가 `pnu or address`로
 *  직접 우선순위를 매기므로(create_render_brief) 프론트는 둘 다 있는 그대로 보낸다
 *  (임의로 하나를 지우는 가공 없음 — 무날조). options는 building_use/scale 둘 다
 *  비어있으면 null(백엔드 옵션 없음과 동일 표현). */
export function buildC2rBriefBody(values: C2rBriefFormValues) {
  const buildingUse = values.buildingUse.trim();
  const scale = values.scale.trim();
  const options =
    buildingUse || scale
      ? { ...(buildingUse ? { building_use: buildingUse } : {}), ...(scale ? { scale } : {}) }
      : null;
  return {
    pnu: values.pnu.trim() || null,
    address: values.address.trim() || null,
    options,
    use_llm: !!values.useLlm,
  };
}
