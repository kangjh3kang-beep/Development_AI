/**
 * 금융 레버리지 파생 공용 헬퍼 — 자기자본·타인자본·ROE·실효 LTV 단일 계산원.
 *
 * ★공용화(국소패치 금지): 투자수익성(ROI 뷰)·DCF·시니어 금융입력·은행제출 보고서 등
 *   equityWon을 소비하는 모든 경로가 이 한 함수/계약을 통해 동일한 규칙으로 계산한다.
 *
 * ★무날조: 없는 값은 산출하지 않는다(null 유지). 자기자본 자동산출은 오직 명시 공식
 *   equityWon = round(equityRatioPct/100 × totalCostWon) 만 사용한다.
 *
 * 규칙(우선순위):
 *  1) 사용자/에디터가 자기자본 절대액(equityWon)을 직접 입력하면 그 값 우선(0 포함 유효 — 전액 차입).
 *  2) 절대액이 없고 총사업비(totalCostWon>0)와 자기자본비율(equityRatioPct)이 있으면 공식으로 자동산출.
 *  3) 둘 다 없으면 equityWon=null → 소비처가 "미산출"로 정직 표기(0원 날조 금지).
 */

/** 기본 자기자본 비율(%) — 사용자 명시 "자기자본 기본 10%". */
export const DEFAULT_EQUITY_RATIO_PCT = 10;

export interface LeverageInput {
  /** 순이익(원) — revenue - cost. ROE 분자. 없으면 ROE 미산출. */
  netProfitWon?: number | null;
  /** 총사업비(원) — LTV 분모·자기자본 자동산출 기준. */
  totalCostWon?: number | null;
  /** 자기자본 절대액(원). 명시 입력 시 최우선(0 허용). null이면 비율로 자동산출 시도. */
  equityWon?: number | null;
  /** 자기자본 비율(%). equityWon 미입력 시 총사업비×비율로 자동산출. 기본 10%. */
  equityRatioPct?: number | null;
}

export interface LeverageResult {
  /** 확정 자기자본(원) — 입력 우선, 없으면 비율×총사업비 자동산출, 둘 다 없으면 null. */
  equityWon: number | null;
  /** 타인자본(원) — max(0, 총사업비 - 자기자본). 산출 불가 시 null. */
  debtWon: number | null;
  /** 자기자본수익률(%) — 순이익/자기자본×100. 자기자본>0일 때만. */
  roePct: number | null;
  /** 실효 레버리지 LTV(%) — 타인자본/총사업비×100. */
  ltvPct: number | null;
  /** 실제 적용된 자기자본 비율(%) — 자동/입력 반영값. 산출 불가 시 null. */
  effectiveEquityRatioPct: number | null;
}

function isFiniteNum(v: number | null | undefined): v is number {
  return typeof v === "number" && Number.isFinite(v);
}

/**
 * 자기자본 절대액을 확정한다. 입력값(equityWon) 우선(0 포함), 없으면 비율×총사업비 자동산출.
 * 자동산출은 총사업비>0 이고 비율>0 일 때만(무날조: 0/음수는 미산출).
 */
export function resolveEquityWon(input: LeverageInput): number | null {
  const { equityWon, totalCostWon, equityRatioPct } = input;
  // ① 명시 입력 우선(0=전액 차입도 유효한 실제 입력).
  if (isFiniteNum(equityWon) && equityWon >= 0) return equityWon;
  // ② 비율 자동산출: 총사업비·비율이 모두 유효(양수)일 때만.
  if (isFiniteNum(totalCostWon) && totalCostWon > 0 && isFiniteNum(equityRatioPct) && equityRatioPct > 0) {
    return Math.round((equityRatioPct / 100) * totalCostWon);
  }
  return null;
}

/**
 * 레버리지 파생 지표를 단일 규칙으로 계산한다(공용 계약).
 * equity/debt/roe/ltv/effectiveEquityRatioPct 를 함께 반환한다.
 */
export function deriveLeverage(input: LeverageInput): LeverageResult {
  const cost = isFiniteNum(input.totalCostWon) ? input.totalCostWon : null;
  const netProfit = isFiniteNum(input.netProfitWon) ? input.netProfitWon : null;
  const equity = resolveEquityWon(input);

  const debt =
    cost != null && equity != null ? Math.max(0, cost - equity) : null;
  const roe =
    netProfit != null && equity != null && equity > 0
      ? (netProfit / equity) * 100
      : null;
  const ltv = cost != null && cost > 0 && debt != null ? (debt / cost) * 100 : null;
  const effectiveEquityRatioPct =
    equity != null && cost != null && cost > 0 ? (equity / cost) * 100 : null;

  return { equityWon: equity, debtWon: debt, roePct: roe, ltvPct: ltv, effectiveEquityRatioPct };
}
