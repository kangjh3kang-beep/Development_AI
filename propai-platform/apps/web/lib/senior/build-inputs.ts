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
  } | null;
  designData?: {
    bcr?: number | null;
    far?: number | null;
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
