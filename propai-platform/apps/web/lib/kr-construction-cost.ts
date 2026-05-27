/**
 * 한국 건설 공사비 계산기
 * 국토부 표준품셈 기반 13개 공정별 비용 산출
 */

// ── 건물 용도별 기본 단가 (원/m²) ──
const BASE_COST_PER_SQM: Record<string, number> = {
  apartment: 2_200_000,     // 공동주택
  neighborhood: 1_800_000,  // 근린생활시설
  office: 2_500_000,        // 업무시설
  officetel: 2_400_000,     // 오피스텔
  commercial: 2_100_000,    // 상업시설
  warehouse: 1_200_000,     // 창고시설
  factory: 1_400_000,       // 공장
};

// ── 13개 공정별 비율 (%) ──
const PROCESS_RATIOS: Array<{ id: string; name: string; ratio: number }> = [
  { id: "temporary", name: "가설공사", ratio: 5.0 },
  { id: "earthwork", name: "토공사", ratio: 4.0 },
  { id: "foundation", name: "기초공사", ratio: 6.0 },
  { id: "concrete", name: "철근콘크리트공사", ratio: 22.0 },
  { id: "steel", name: "철골공사", ratio: 8.0 },
  { id: "masonry", name: "조적공사", ratio: 3.0 },
  { id: "waterproof", name: "방수공사", ratio: 3.0 },
  { id: "finishing", name: "미장공사", ratio: 5.0 },
  { id: "tile", name: "타일공사", ratio: 4.0 },
  { id: "carpentry", name: "목공사", ratio: 6.0 },
  { id: "window", name: "창호공사", ratio: 12.0 },
  { id: "painting", name: "도장공사", ratio: 4.0 },
  { id: "interior", name: "내장공사", ratio: 18.0 },
];

// ── 간접비 비율 ──
const INDIRECT_COSTS = {
  design: 0.03,       // 설계비 3%
  supervision: 0.025,  // 감리비 2.5%
  overhead: 0.06,      // 제경비 6%
  profit: 0.05,        // 이윤 5%
  vat: 0.10,          // 부가세 10%
};

// ── 인터페이스 ──
export interface CostInput {
  /** 연면적 (m²) */
  totalFloorArea: number;
  /** 건물 용도 */
  buildingUse: string;
  /** 지하 층수 */
  basementFloors: number;
  /** 지상 층수 */
  aboveGroundFloors: number;
  /** 물가상승률 (%) — 기본 3% */
  inflationRate?: number;
  /** 지역 보정계수 (서울=1.0, 수도권=0.95, 지방=0.85) */
  regionFactor?: number;
}

export interface ProcessCost {
  id: string;
  name: string;
  ratio: number;
  amount: number;
}

export interface CostBreakdown {
  /** 공정별 직접공사비 */
  processes: ProcessCost[];
  /** 직접공사비 합계 */
  directCostTotal: number;
  /** 설계비 */
  designFee: number;
  /** 감리비 */
  supervisionFee: number;
  /** 제경비 */
  overhead: number;
  /** 이윤 */
  profit: number;
  /** 부가세 */
  vat: number;
  /** 간접비 합계 */
  indirectCostTotal: number;
}

export interface CostResult {
  /** 기본 단가 (원/m²) */
  baseCostPerSqm: number;
  /** 보정 단가 (원/m²) */
  adjustedCostPerSqm: number;
  /** 연면적 (m²) */
  totalFloorArea: number;
  /** 비용 분석 */
  breakdown: CostBreakdown;
  /** 총 공사비 (원) */
  totalCost: number;
  /** 평당 공사비 (원/평) */
  costPerPyeong: number;
  /** 지하 추가비용 (원) */
  basementPremium: number;
}

/**
 * 공사비 계산
 */
export function calculateConstructionCost(input: CostInput): CostResult {
  const baseCost = BASE_COST_PER_SQM[input.buildingUse] ?? BASE_COST_PER_SQM.apartment;
  const inflation = 1 + (input.inflationRate ?? 3) / 100;
  const regionFactor = input.regionFactor ?? 1.0;

  // 보정 단가 = 기본 단가 × 물가상승률 × 지역 보정
  const adjustedCost = Math.round(baseCost * inflation * regionFactor);

  // 직접공사비 (지상)
  const aboveGroundArea = input.totalFloorArea * (input.aboveGroundFloors / (input.aboveGroundFloors + input.basementFloors || 1));
  const basementArea = input.totalFloorArea - aboveGroundArea;

  // 지하 할증 30%
  const basementPremium = Math.round(basementArea * adjustedCost * 0.3);
  const directCostBase = input.totalFloorArea * adjustedCost + basementPremium;

  // 공정별 분배
  const processes: ProcessCost[] = PROCESS_RATIOS.map((p) => ({
    id: p.id,
    name: p.name,
    ratio: p.ratio,
    amount: Math.round(directCostBase * (p.ratio / 100)),
  }));

  const directCostTotal = processes.reduce((s, p) => s + p.amount, 0);

  // 간접비
  const designFee = Math.round(directCostTotal * INDIRECT_COSTS.design);
  const supervisionFee = Math.round(directCostTotal * INDIRECT_COSTS.supervision);
  const overhead = Math.round(directCostTotal * INDIRECT_COSTS.overhead);
  const profit = Math.round(directCostTotal * INDIRECT_COSTS.profit);
  const subtotal = directCostTotal + designFee + supervisionFee + overhead + profit;
  const vat = Math.round(subtotal * INDIRECT_COSTS.vat);
  const indirectCostTotal = designFee + supervisionFee + overhead + profit + vat;

  const totalCost = directCostTotal + indirectCostTotal;
  const costPerPyeong = input.totalFloorArea > 0 ? Math.round(totalCost / (input.totalFloorArea / 3.3058)) : 0;

  return {
    baseCostPerSqm: baseCost,
    adjustedCostPerSqm: adjustedCost,
    totalFloorArea: input.totalFloorArea,
    breakdown: {
      processes,
      directCostTotal,
      designFee,
      supervisionFee,
      overhead,
      profit,
      vat,
      indirectCostTotal,
    },
    totalCost,
    costPerPyeong,
    basementPremium,
  };
}
