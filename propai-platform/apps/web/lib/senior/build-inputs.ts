/**
 * buildSeniorInputs — 프로젝트 분석 store 데이터 → 시니어 평가기(context.inputs) 매핑(순수함수).
 *
 * ★무목업: 실재하는 값만 매핑(없으면 키 생략 → 백엔드 평가기가 해당 항목 생략). 단위·의미가
 * 확실히 정합하는 도메인만 자동 채운다. 나머지 도메인은 undefined(프레임워크만 표시·정직).
 *
 * 확신 매핑(v1):
 *  - 심의(senior_deliberation_member): 설계 bcr/far(actual) vs 실효(조례)한도(limit) → 다조항 CSP.
 *  - 금융(senior_financial_advisor): 자기자본/총사업비 → 자기자본비율(연도 미상 시 최신 기준).
 * 미매핑(의미·단위 불명확 또는 store 미보유): 도시계획(정비사업 자산평가)·설계(실측 이격/일조분)·
 *  세무(취득가액 semantics)·회계(리스)·BIM(clash) → undefined.
 */

/** 매핑 입력원(store 셀렉터 결과의 부분집합 — 순수성 위해 평면 객체로 받는다). */
export interface SeniorInputSources {
  siteAnalysis?: {
    effectiveFarPct?: number | null;
    effectiveBcrPct?: number | null;
    nationalFarPct?: number | null;
    nationalBcrPct?: number | null;
    roadWidthM?: number | null;   // 접도 도로폭(m) — 심의 road_width_actual
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
  const bcrL = posNum(src.siteAnalysis?.effectiveBcrPct) ?? posNum(src.siteAnalysis?.nationalBcrPct);
  if (bcrA !== undefined && bcrL !== undefined) {
    inputs.bcr_actual = bcrA;
    inputs.bcr_limit = bcrL;
  }
  const farA = nonNegNum(src.designData?.far);
  const farL = posNum(src.siteAnalysis?.effectiveFarPct) ?? posNum(src.siteAnalysis?.nationalFarPct);
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
    default:
      return undefined;
  }
}
