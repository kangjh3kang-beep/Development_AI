/**
 * 한국 경공매 분석 계산기
 * 낙찰가율, 대항력, 배당순위, 투자수익률 계산
 */

// ── 지역별 평균 낙찰가율 (%) ──
const REGIONAL_RATES: Record<string, { min: number; max: number }> = {
  서울: { min: 90, max: 95 },
  수도권: { min: 85, max: 90 },
  광역시: { min: 80, max: 85 },
  지방: { min: 70, max: 80 },
};

// ── 용도별 평균 낙찰가율 (%) ──
const USE_RATES: Record<string, number> = {
  아파트: 95,
  다세대: 85,
  상가: 80,
  토지: 75,
  공장: 70,
  오피스텔: 88,
};

// ── 인터페이스 ──
export interface AuctionInput {
  /** 감정가 (원) */
  appraisalPrice: number;
  /** 예상 시세 (원) */
  estimatedMarketPrice: number;
  /** 입찰가 (원) */
  bidPrice: number;
  /** 지역 */
  region: string;
  /** 용도 */
  propertyUse: string;
  /** 유찰 횟수 */
  failedBids: number;
  /** 담보물권 (근저당 등) 합계 (원) */
  securedDebt: number;
  /** 선순위 임차보증금 합계 (원) */
  seniorDeposits: number;
  /** 후순위 임차보증금 합계 (원) */
  juniorDeposits: number;
  /** 체납 조세 (원) */
  delinquentTax: number;
  /** 전입일자 (YYYY-MM-DD) */
  tenantMoveInDate?: string;
  /** 근저당 설정일 (YYYY-MM-DD) */
  mortgageSetDate?: string;
  /** 예상 보유 기간 (년) */
  holdingPeriod?: number;
  /** 예상 월 임대수입 (원) */
  monthlyRent?: number;
}

export interface DistributionItem {
  category: string;
  amount: number;
  recovered: number;
  shortfall: number;
  priority: number;
}

export interface AuctionAnalysis {
  /** 낙찰가율 (감정가 대비, %) */
  bidToAppraisalRate: number;
  /** 시세 대비 할인율 (%) */
  discountRate: number;
  /** 지역 평균 낙찰가율 (%) */
  regionalAvgRate: number;
  /** 용도 평균 낙찰가율 (%) */
  useAvgRate: number;
  /** 유찰 횟수에 따른 최저가 (원) */
  minimumBid: number;
  /** 대항력 분석 */
  tenantProtection: {
    hasProtection: boolean;
    description: string;
  };
  /** 배당 시뮬레이션 */
  distribution: DistributionItem[];
  /** 배당 후 낙찰자 잔여금 (원) */
  remainderAfterDistribution: number;
  /** 명도 리스크 등급 */
  evictionRisk: "LOW" | "MEDIUM" | "HIGH";
  /** 명도 리스크 설명 */
  evictionRiskDesc: string;
  /** 예상 제비용 (원) */
  estimatedCosts: {
    acquisitionTax: number;
    registrationTax: number;
    agentFee: number;
    movingCost: number;
    total: number;
  };
  /** 투자 수익률 (%) */
  roi: number;
  /** 연간 임대수익률 (%) */
  annualYield: number;
  /** 총 투자액 (원) */
  totalInvestment: number;
  /** 예상 순수익 (원) */
  netProfit: number;
}

/**
 * 경공매 분석
 */
export function analyzeAuction(input: AuctionInput): AuctionAnalysis {
  // 1. 낙찰가율
  const bidToAppraisalRate = (input.bidPrice / input.appraisalPrice) * 100;
  const discountRate = ((input.estimatedMarketPrice - input.bidPrice) / input.estimatedMarketPrice) * 100;

  // 2. 지역/용도 평균
  const regionalData = REGIONAL_RATES[input.region] ?? REGIONAL_RATES["지방"];
  const regionalAvgRate = (regionalData.min + regionalData.max) / 2;
  const useAvgRate = USE_RATES[input.propertyUse] ?? 80;

  // 3. 유찰에 따른 최저가 (매 유찰시 20% 감액)
  const minimumBid = Math.round(input.appraisalPrice * Math.pow(0.8, input.failedBids));

  // 4. 대항력 분석
  let hasProtection = false;
  let protectionDesc = "대항력 분석 불가 (날짜 정보 부족)";
  if (input.tenantMoveInDate && input.mortgageSetDate) {
    hasProtection = input.tenantMoveInDate < input.mortgageSetDate;
    protectionDesc = hasProtection
      ? `전입일(${input.tenantMoveInDate})이 근저당 설정일(${input.mortgageSetDate})보다 앞서 대항력 있음`
      : `근저당 설정일(${input.mortgageSetDate})이 전입일(${input.tenantMoveInDate})보다 앞서 대항력 없음`;
  }

  // 5. 배당 시뮬레이션 (법정 배당 순위)
  let pool = input.bidPrice;
  const distribution: DistributionItem[] = [];

  // (1) 경매비용 (약 입찰가의 1%)
  const auctionCost = Math.round(input.bidPrice * 0.01);
  const recAuction = Math.min(pool, auctionCost);
  distribution.push({ category: "경매비용", amount: auctionCost, recovered: recAuction, shortfall: auctionCost - recAuction, priority: 1 });
  pool -= recAuction;

  // (2) 체납 조세
  const recTax = Math.min(pool, input.delinquentTax);
  distribution.push({ category: "체납 조세", amount: input.delinquentTax, recovered: recTax, shortfall: input.delinquentTax - recTax, priority: 2 });
  pool -= recTax;

  // (3) 선순위 임차보증금 (대항력 있는 경우)
  if (hasProtection) {
    const recSenior = Math.min(pool, input.seniorDeposits);
    distribution.push({ category: "선순위 임차보증금", amount: input.seniorDeposits, recovered: recSenior, shortfall: input.seniorDeposits - recSenior, priority: 3 });
    pool -= recSenior;
  }

  // (4) 담보물권
  const recSecured = Math.min(pool, input.securedDebt);
  distribution.push({ category: "담보물권 (근저당)", amount: input.securedDebt, recovered: recSecured, shortfall: input.securedDebt - recSecured, priority: 4 });
  pool -= recSecured;

  // (5) 후순위 임차보증금
  const recJunior = Math.min(pool, input.juniorDeposits);
  distribution.push({ category: "후순위 임차보증금", amount: input.juniorDeposits, recovered: recJunior, shortfall: input.juniorDeposits - recJunior, priority: 5 });
  pool -= recJunior;

  // 6. 명도 리스크
  const totalUnrecoveredDeposits = distribution
    .filter((d) => d.category.includes("임차"))
    .reduce((s, d) => s + d.shortfall, 0);
  let evictionRisk: "LOW" | "MEDIUM" | "HIGH" = "LOW";
  let evictionRiskDesc = "명도 리스크 낮음 — 임차인 전액 배당 가능";
  if (totalUnrecoveredDeposits > 0 && hasProtection) {
    evictionRisk = "HIGH";
    evictionRiskDesc = `대항력 있는 임차인 보증금 ${Math.round(totalUnrecoveredDeposits / 10000).toLocaleString()}만원 미배당 — 명도 소송 필요`;
  } else if (totalUnrecoveredDeposits > 0) {
    evictionRisk = "MEDIUM";
    evictionRiskDesc = `임차인 보증금 ${Math.round(totalUnrecoveredDeposits / 10000).toLocaleString()}만원 미배당 — 협의 명도 권장`;
  }

  // 7. 제비용
  const acquisitionTax = Math.round(input.bidPrice * 0.046); // 취득세+농특+교육
  const registrationTax = Math.round(input.bidPrice * 0.002);
  const agentFee = Math.round(input.bidPrice * 0.004);
  const movingCost = 3_000_000; // 이사비용 기본
  const totalCosts = acquisitionTax + registrationTax + agentFee + movingCost;

  // 8. 수익 계산
  const totalInvestment = input.bidPrice + totalCosts;
  const netProfit = input.estimatedMarketPrice - totalInvestment;
  const roi = totalInvestment > 0 ? (netProfit / totalInvestment) * 100 : 0;

  const holdingPeriod = input.holdingPeriod ?? 1;
  const monthlyRent = input.monthlyRent ?? 0;
  const annualRent = monthlyRent * 12;
  const annualYield = totalInvestment > 0 ? (annualRent / totalInvestment) * 100 : 0;

  return {
    bidToAppraisalRate: Math.round(bidToAppraisalRate * 10) / 10,
    discountRate: Math.round(discountRate * 10) / 10,
    regionalAvgRate,
    useAvgRate,
    minimumBid,
    tenantProtection: { hasProtection, description: protectionDesc },
    distribution,
    remainderAfterDistribution: pool,
    evictionRisk,
    evictionRiskDesc,
    estimatedCosts: { acquisitionTax, registrationTax, agentFee, movingCost, total: totalCosts },
    roi: Math.round(roi * 10) / 10,
    annualYield: Math.round(annualYield * 10) / 10,
    totalInvestment,
    netProfit,
  };
}
