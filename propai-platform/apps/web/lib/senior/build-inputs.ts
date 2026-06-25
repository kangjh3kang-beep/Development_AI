/**
 * buildSeniorInputs — 프로젝트 분석 store 데이터 → 시니어 평가기(context.inputs) 매핑(순수함수).
 *
 * ★무목업: 실재하는 값만 매핑(없으면 키 생략 → 백엔드 평가기가 해당 항목 생략). 단위·의미가
 * 확실히 정합하는 도메인만 자동 채운다. 나머지 도메인은 undefined(프레임워크만 표시·정직).
 *
 * 확신 매핑(v1):
 *  - 심의(senior_deliberation_member): 설계 bcr/far(actual) vs 실효(조례)한도(limit) → 다조항 CSP.
 *  - 금융(senior_financial_advisor): 자기자본/총사업비 → 자기자본비율(연도 미상 시 최신 기준).
 *  - 도시계획(senior_urban_planner): 수지의 종후자산(총분양수입)·총사업비 → 비례율 분자/사업비
 *    (분모인 종전자산평가는 토지+건물 감정이라 store 미보유 → 수동입력 surface; manual-inputs 참조).
 * 미매핑(의미·단위 불명확 또는 store 미보유): 설계(실측 이격/일조분)·세무(취득가액 semantics)·
 *  회계(리스)·BIM(clash) → undefined.
 */

import { resolveFarPct, resolveBcrPct } from "@/lib/zoning-ssot";

/** 매핑 입력원(store 셀렉터 결과의 부분집합 — 순수성 위해 평면 객체로 받는다). */
export interface SeniorInputSources {
  siteAnalysis?: {
    effectiveFarPct?: number | null;
    effectiveBcrPct?: number | null;
    nationalFarPct?: number | null;
    nationalBcrPct?: number | null;
    // 다필지 통합 실효 한도(SSOT) — resolveFarPct/resolveBcrPct가 단일 실효보다 우선 읽는다.
    integratedFarEffPct?: number | null;
    integratedBcrEffPct?: number | null;
    roadWidthM?: number | null;   // 접도 도로폭(m) — 심의 road_width_actual
    estimatedValue?: number | null;  // 부지 추정가(원·AVM/탁상) — 감정평가/법무사 감정가 입력원
  } | null;
  designData?: {
    bcr?: number | null;
    far?: number | null;
    heightM?: number | null;      // 설계 건물 높이(m) — 심의 height_actual
    maxHeightM?: number | null;   // 법정 높이 한도(m) — 심의 height_limit
    totalGfaSqm?: number | null;  // 연면적(㎡) — 건축법 44조 접도 required 산정(≥2000→6m)
  } | null;
  feasibilityData?: {
    totalCostWon?: number | null;
    totalRevenueWon?: number | null;  // 총 분양수입(매출) — 정비사업 종후자산총평가 근사(비례율 분자)
    equityWon?: number | null;
  } | null;
}

type Inputs = Record<string, number>;

/** 유한 양수만 통과(0/음수/NaN/null → undefined). 한도·분모용. */
function posNum(v: number | null | undefined): number | undefined {
  return typeof v === "number" && Number.isFinite(v) && v > 0 ? v : undefined;
}

/** 유한 비음수(actual용 — 0 허용). */
function nonNegNum(v: number | null | undefined): number | undefined {
  return typeof v === "number" && Number.isFinite(v) && v >= 0 ? v : undefined;
}

function buildDeliberationInputs(src: SeniorInputSources): Inputs | undefined {
  const inputs: Inputs = {};
  const bcrA = nonNegNum(src.designData?.bcr);
  // ★SSOT 읽기 통일: 단일 실효(effectiveBcrPct) 직접읽기 대신 resolveBcrPct(통합 > 실효 > 법정)로
  //   일원화한다(다필지 통합 한도 우선). 한도(분모)이므로 posNum으로 양수만 통과(0/음수 한도 무의미).
  const bcrL = posNum(resolveBcrPct(src.siteAnalysis));
  if (bcrA !== undefined && bcrL !== undefined) {
    inputs.bcr_actual = bcrA;
    inputs.bcr_limit = bcrL;
  }
  const farA = nonNegNum(src.designData?.far);
  const farL = posNum(resolveFarPct(src.siteAnalysis));
  if (farA !== undefined && farL !== undefined) {
    inputs.far_actual = farA;
    inputs.far_limit = farL;
  }
  // 높이: 설계 높이(actual) vs 법정 높이한도(limit). 한도 0/null(무제한/미산정)이면 생략(무목업).
  // ★provenance: heightM=설계엔진 building_height(층수×층고 근사·플랫폼 canonical 높이와 동일).
  //   maxHeightM=용도지역 법정상한(ZONE_LIMITS·조례/가로구역 최고높이 미반영·보수적 상한 → 거짓 BLOCK 없음).
  //   향후 실측 매스높이·조례 실효 높이한도(effectiveMaxHeightM) 확보 시 우선 폴백(백엔드 백로그).
  const hA = nonNegNum(src.designData?.heightM);
  const hL = posNum(src.designData?.maxHeightM);
  if (hA !== undefined && hL !== undefined) {
    inputs.height_actual = hA;
    inputs.height_limit = hL;
  }
  // 접도: 실 도로폭(actual·0=맹지 유효) vs 건축법 44조·시행령 28조 required(연면적≥2000㎡→6m·else 4m).
  //   road_width_m null(도로접면 미확보)이면 생략(무목업). 0(맹지)은 유효 actual→위반 판정.
  //   ★v1 범위: 일반 연면적 룰만(공장 3000㎡·막다른도로 완화·자동차전용도로 의제는 후속 — 보수적
  //   기본값이라 거짓 BLOCK은 없으나 특수 케이스 거짓 PASS 여지·최종 인허가청 확인 게이트).
  const rwA = nonNegNum(src.siteAnalysis?.roadWidthM);
  if (rwA !== undefined) {
    const gfa = nonNegNum(src.designData?.totalGfaSqm);
    inputs.road_width_actual = rwA;
    inputs.road_width_required = gfa !== undefined && gfa >= 2000 ? 6 : 4;
  }
  return Object.keys(inputs).length ? inputs : undefined;
}

function buildFinancialInputs(src: SeniorInputSources): Inputs | undefined {
  const equity = nonNegNum(src.feasibilityData?.equityWon);
  const totalCost = posNum(src.feasibilityData?.totalCostWon);
  if (equity !== undefined && totalCost !== undefined) {
    return { equity, total_cost: totalCost };
  }
  return undefined;
}

// 감정평가사: 부지 추정가(estimatedValue)를 토지 감정가로 매핑(탁상 추정·건물 감정은 store 부재→토지만).
function buildAppraiserInputs(src: SeniorInputSources): Inputs | undefined {
  const land = posNum(src.siteAnalysis?.estimatedValue);
  return land !== undefined ? { land_appraised_total: land } : undefined;
}

// 법무사: 감정가(appraised_value)=부지 추정가 전파(★감정평가사 통합) → 권리분석 인수율 기초.
//   senior_liens_total(인수 선순위·등기 분석)·동의율은 store 부재→해당 평가 생략(무목업).
function buildLegalInputs(src: SeniorInputSources): Inputs | undefined {
  const appraised = posNum(src.siteAnalysis?.estimatedValue);
  return appraised !== undefined ? { appraised_value: appraised } : undefined;
}

// 도시계획: 정비사업 비례율=(종후자산총평가−총사업비)/종전자산총평가×100.
//   ★수지(타당성) 산출을 비례율 분자/사업비로 배선(SSOT) — 종후자산총평가≈총분양수입(totalRevenueWon·
//   완공자산 총 매각가치, 관리처분 추산액과는 ±오차→평가기가 종후 미확정 잠정·민감도 동반), 총사업비=
//   totalCostWon. 분모인 종전자산평가(토지+건물 감정)는 store 미보유(estimatedValue는 토지만·탁상 →
//   분모 과소→비례율 과대 오도) → 자동매핑하지 않고 수동입력(manual-inputs senior_urban_planner)으로 받는다.
//   각각 독립적으로 emit(부분 보유 시 평가기가 종전평가 입력될 때까지 비례율 생략 — 무목업).
function buildUrbanInputs(src: SeniorInputSources): Inputs | undefined {
  const inputs: Inputs = {};
  const post = posNum(src.feasibilityData?.totalRevenueWon);  // 종후자산총평가(비례율 분자)
  const cost = posNum(src.feasibilityData?.totalCostWon);     // 총사업비
  if (post !== undefined) inputs.post_appraisal_total = post;
  if (cost !== undefined) inputs.total_project_cost = cost;
  return Object.keys(inputs).length ? inputs : undefined;
}

/** 도메인 키 → 평가기 inputs(없으면 undefined → consult는 프레임워크만). */
export function buildSeniorInputs(
  agentKey: string,
  src: SeniorInputSources,
): Inputs | undefined {
  switch (agentKey) {
    case "senior_deliberation_member":
      return buildDeliberationInputs(src);
    case "senior_financial_advisor":
      return buildFinancialInputs(src);
    case "senior_appraiser":
      return buildAppraiserInputs(src);
    case "senior_legal_scrivener":
      return buildLegalInputs(src);
    case "senior_urban_planner":
      return buildUrbanInputs(src);
    default:
      return undefined;
  }
}
