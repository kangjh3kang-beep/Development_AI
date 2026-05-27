/**
 * 한국 부동산 양도소득세/취득세/종합부동산세 계산기
 * 백엔드 없이 프론트엔드에서 즉시 계산
 */

// ── 양도소득세 누진세율 (2025년 기준) ──
const PROGRESSIVE_BRACKETS = [
  { limit: 14_000_000, rate: 0.06, deduction: 0 },
  { limit: 50_000_000, rate: 0.15, deduction: 1_260_000 },
  { limit: 88_000_000, rate: 0.24, deduction: 5_760_000 },
  { limit: 150_000_000, rate: 0.35, deduction: 15_440_000 },
  { limit: 300_000_000, rate: 0.38, deduction: 19_940_000 },
  { limit: 500_000_000, rate: 0.40, deduction: 25_940_000 },
  { limit: 1_000_000_000, rate: 0.42, deduction: 35_940_000 },
  { limit: Infinity, rate: 0.45, deduction: 65_940_000 },
];

// ── 장기보유특별공제율 ──
const LTCG_GENERAL = [
  { years: 3, rate: 0.06 }, { years: 4, rate: 0.08 }, { years: 5, rate: 0.10 },
  { years: 6, rate: 0.12 }, { years: 7, rate: 0.14 }, { years: 8, rate: 0.16 },
  { years: 9, rate: 0.18 }, { years: 10, rate: 0.20 },
  { years: 11, rate: 0.22 }, { years: 12, rate: 0.24 },
  { years: 13, rate: 0.26 }, { years: 14, rate: 0.28 },
  { years: 15, rate: 0.30 },
];

const LTCG_1HOME = [
  { years: 3, rate: 0.12 }, { years: 4, rate: 0.16 }, { years: 5, rate: 0.20 },
  { years: 6, rate: 0.24 }, { years: 7, rate: 0.28 }, { years: 8, rate: 0.32 },
  { years: 9, rate: 0.36 }, { years: 10, rate: 0.40 },
];

// ── 취득세율 (주택) ──
const ACQ_TAX_BRACKETS = [
  { limit: 600_000_000, rate: 0.01 },
  { limit: 900_000_000, rate: 0.02 },
  { limit: Infinity, rate: 0.03 },
];

// ── 인터페이스 ──
export interface TaxInput {
  /** 취득가 (원) */
  acquisitionPrice: number;
  /** 양도가 (원) */
  salePrice: number;
  /** 보유 기간 (년) */
  holdingYears: number;
  /** 주택 수 */
  houseCount: number;
  /** 1세대 1주택 여부 */
  isSingleHome: boolean;
  /** 필요경비 (원) — 취득세, 중개수수료, 수리비 등 */
  expenses: number;
  /** 기본공제 (250만원) */
  basicDeduction?: number;
}

export interface CapitalGainsTaxResult {
  /** 양도차익 (원) */
  capitalGain: number;
  /** 장기보유특별공제액 (원) */
  ltcgDeduction: number;
  /** 장기보유특별공제율 (%) */
  ltcgRate: number;
  /** 양도소득금액 (원) */
  taxableIncome: number;
  /** 기본공제 (원) */
  basicDeduction: number;
  /** 과세표준 (원) */
  taxBase: number;
  /** 적용세율 (%) */
  appliedRate: number;
  /** 산출세액 (원) */
  calculatedTax: number;
  /** 다주택 중과세율 추가분 (%p) */
  multiHomeSurcharge: number;
  /** 지방소득세 (원, 산출세액의 10%) */
  localTax: number;
  /** 총 납부 세액 (원) */
  totalTax: number;
  /** 실효세율 (%) */
  effectiveRate: number;
  /** 세후 수익 (원) */
  afterTaxProfit: number;
}

export interface AcquisitionTaxResult {
  /** 취득가 (원) */
  acquisitionPrice: number;
  /** 취득세율 (%) */
  taxRate: number;
  /** 취득세 (원) */
  acquisitionTax: number;
  /** 농어촌특별세 (원) */
  ruralTax: number;
  /** 교육세 (원) */
  educationTax: number;
  /** 총 납부액 (원) */
  totalTax: number;
}

export interface PropertyTaxResult {
  /** 공시가격 (원) */
  assessedValue: number;
  /** 공정시장가액비율 (%) */
  fairMarketRatio: number;
  /** 과세표준 (원) */
  taxBase: number;
  /** 재산세 (원) */
  propertyTax: number;
  /** 종합부동산세 (원) */
  comprehensiveTax: number;
  /** 총 납부액 (원) */
  totalTax: number;
}

export interface TaxResult {
  capitalGains: CapitalGainsTaxResult;
  acquisition: AcquisitionTaxResult;
  property: PropertyTaxResult;
}

/**
 * 양도소득세 계산
 */
export function calculateCapitalGainsTax(input: TaxInput): CapitalGainsTaxResult {
  const basicDeduction = input.basicDeduction ?? 2_500_000;

  // 1. 양도차익 = 양도가 - 취득가 - 필요경비
  const capitalGain = Math.max(0, input.salePrice - input.acquisitionPrice - input.expenses);

  // 2. 장기보유특별공제
  let ltcgRate = 0;
  if (input.holdingYears >= 3) {
    const table = input.isSingleHome ? LTCG_1HOME : LTCG_GENERAL;
    for (const entry of table) {
      if (input.holdingYears >= entry.years) ltcgRate = entry.rate;
    }
  }
  const ltcgDeduction = Math.round(capitalGain * ltcgRate);

  // 3. 양도소득금액
  const taxableIncome = capitalGain - ltcgDeduction;

  // 4. 과세표준
  const taxBase = Math.max(0, taxableIncome - basicDeduction);

  // 5. 다주택 중과세율
  let multiHomeSurcharge = 0;
  if (input.houseCount === 2) multiHomeSurcharge = 0.20;
  else if (input.houseCount >= 3) multiHomeSurcharge = 0.30;

  // 6. 세액 계산
  let calculatedTax = 0;
  let appliedRate = 0;
  for (const bracket of PROGRESSIVE_BRACKETS) {
    if (taxBase <= bracket.limit) {
      calculatedTax = Math.round(taxBase * bracket.rate - bracket.deduction);
      appliedRate = bracket.rate * 100;
      break;
    }
  }

  // 다주택 중과 추가
  if (multiHomeSurcharge > 0) {
    calculatedTax += Math.round(taxBase * multiHomeSurcharge);
  }

  // 7. 지방소득세 (10%)
  const localTax = Math.round(calculatedTax * 0.1);

  // 8. 총 세액
  const totalTax = calculatedTax + localTax;

  // 9. 실효세율
  const effectiveRate = capitalGain > 0 ? (totalTax / capitalGain) * 100 : 0;

  return {
    capitalGain,
    ltcgDeduction,
    ltcgRate: ltcgRate * 100,
    taxableIncome,
    basicDeduction,
    taxBase,
    appliedRate: appliedRate + multiHomeSurcharge * 100,
    calculatedTax,
    multiHomeSurcharge: multiHomeSurcharge * 100,
    localTax,
    totalTax,
    effectiveRate: Math.round(effectiveRate * 10) / 10,
    afterTaxProfit: capitalGain - totalTax,
  };
}

/**
 * 취득세 계산
 */
export function calculateAcquisitionTax(price: number, houseCount = 1): AcquisitionTaxResult {
  // 기본 세율 결정
  let taxRate = 0.01;
  for (const bracket of ACQ_TAX_BRACKETS) {
    if (price <= bracket.limit) {
      taxRate = bracket.rate;
      break;
    }
  }

  // 다주택 중과
  if (houseCount === 2) taxRate = 0.08;
  else if (houseCount >= 3) taxRate = 0.12;

  const acquisitionTax = Math.round(price * taxRate);
  const ruralTax = Math.round(acquisitionTax * 0.1); // 농특세 10%
  const educationTax = Math.round(acquisitionTax * 0.1); // 교육세 10%

  return {
    acquisitionPrice: price,
    taxRate: taxRate * 100,
    acquisitionTax,
    ruralTax,
    educationTax,
    totalTax: acquisitionTax + ruralTax + educationTax,
  };
}

/**
 * 종합부동산세 계산 (간이)
 */
export function calculateComprehensivePropertyTax(
  assessedValue: number,
  houseCount = 1,
): PropertyTaxResult {
  const fairMarketRatio = 0.60; // 2025년 공정시장가액비율
  const taxBase = Math.round(assessedValue * fairMarketRatio);

  // 재산세 (누진세율)
  let propertyTax: number;
  if (taxBase <= 60_000_000) propertyTax = Math.round(taxBase * 0.001);
  else if (taxBase <= 150_000_000) propertyTax = Math.round(60_000 + (taxBase - 60_000_000) * 0.0015);
  else if (taxBase <= 300_000_000) propertyTax = Math.round(195_000 + (taxBase - 150_000_000) * 0.0025);
  else propertyTax = Math.round(570_000 + (taxBase - 300_000_000) * 0.004);

  // 종합부동산세 (공시가 11억 초과분)
  const threshold = houseCount === 1 ? 1_100_000_000 : 600_000_000;
  let comprehensiveTax = 0;
  const excess = assessedValue - threshold;
  if (excess > 0) {
    const compBase = Math.round(excess * fairMarketRatio);
    if (houseCount <= 1) {
      if (compBase <= 300_000_000) comprehensiveTax = Math.round(compBase * 0.006);
      else if (compBase <= 600_000_000) comprehensiveTax = Math.round(compBase * 0.008);
      else comprehensiveTax = Math.round(compBase * 0.012);
    } else {
      if (compBase <= 300_000_000) comprehensiveTax = Math.round(compBase * 0.012);
      else if (compBase <= 600_000_000) comprehensiveTax = Math.round(compBase * 0.016);
      else comprehensiveTax = Math.round(compBase * 0.022);
    }
  }

  return {
    assessedValue,
    fairMarketRatio: fairMarketRatio * 100,
    taxBase,
    propertyTax,
    comprehensiveTax,
    totalTax: propertyTax + comprehensiveTax,
  };
}
