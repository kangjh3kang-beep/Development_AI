/**
 * 아이디어#4(지불여력→개략수지 원클릭 퍼널) — PricingBandPanel CTA 검증.
 *
 * 검증 범위:
 *  ① CTA는 affordability_verdict==="over_band"일 때만 렌더(다른 verdict는 미노출).
 *  ② 단위변환이 (a)market_report_service.py:793 전용 평당가 관례 + (b)suggest.py:341 전용→공급
 *     전용률(0.747) 환산을 함께 적용해 **공급면적 기준 원/평**을 낸다(R1 P1 봉합 — 종전 전용값
 *     그대로 전송 시 +33.9% 과대).
 *  ③ 클릭 시 축이 명시된 URL 파라미터(prefillSaleSupplyWon)로 개략수지 앵커로 이동 — 모호한
 *     공유 스토어 슬롯은 쓰지 않는다. 클릭 전에는 아무 것도 자동 실행되지 않는다(정직 고지 포함).
 */
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  PricingBandPanel,
  capManwonToPricePerPyeongWon,
} from "@/components/operations/market/PricingBandPanel";
import type { PricingBand } from "@/components/operations/market/marketTypes";

const pushMock = vi.fn();
vi.mock("next/navigation", () => ({
  useParams: () => ({ locale: "ko" }),
  useRouter: () => ({ push: pushMock, replace: vi.fn(), back: vi.fn(), prefetch: vi.fn() }),
}));

// 독립 골든 산식(구현 비호출) — 전용 평당가 → ×전용률(0.747) 공급 평당가. round로 정수.
function goldenCapToSupplyWon(capManwon: number): number {
  const exclPerPyeongManwon = Math.round(capManwon / (84.0 / 3.305785));
  return Math.round(exclPerPyeongManwon * 10000 * 0.747);
}

const BASE: PricingBand = {
  fair_price_10k: 90000,
  market_reference: {
    comparable_trade_10k: 92000,
    nearby_presale_10k: 89000,
    fair_price_10k: 90000,
    method: "주변 분양가(60%) + 실거래 시세(40%) 가중",
    data_source: "live",
  },
  affordability: {
    annual_income_10k: 8000,
    affordable_by_pir_10k: 50400,
    affordable_by_dsr_ltv_10k: 62000,
    band_10k: [50400, 62000],
    recommended_cap_10k: 50400,
    assumptions: { dsr: 0.4, ltv: 0.5, stress_rate: 0.055, term_years: 30, pir: 6.3 },
    data_source: "live",
  },
  affordability_verdict: "over_band",
  data_source: "live",
  basis: "테스트 근거",
};

describe("PricingBandPanel — 지불여력→개략수지 원클릭 퍼널 CTA", () => {
  beforeEach(() => {
    pushMock.mockClear();
  });

  it("단위변환이 전용 평당가 관례 + 전용률(0.747) 공급환산까지 적용한다(공급면적 기준 원/평)", () => {
    // 구현 비호출 독립 골든과 대조 — 전용값 그대로면 39,350,000(과대), 공급환산 후 29,394,450.
    expect(capManwonToPricePerPyeongWon(100000)).toBe(29_394_450);
    expect(capManwonToPricePerPyeongWon(100000)).toBe(goldenCapToSupplyWon(100000));
    expect(capManwonToPricePerPyeongWon(88500)).toBe(goldenCapToSupplyWon(88500));
    // ★전용 미환산(구 결함)이 아님을 앵커로 고정 — 공급값은 전용값보다 반드시 작다.
    expect(capManwonToPricePerPyeongWon(100000)).toBeLessThan(39_350_000);
  });

  it("affordability_verdict!=='over_band'면 CTA를 렌더하지 않는다", () => {
    render(<PricingBandPanel data={{ ...BASE, affordability_verdict: "within_conservative" }} />);
    expect(screen.queryByTestId("afford-cap-recalc-cta")).not.toBeInTheDocument();
    expect(pushMock).not.toHaveBeenCalled();
  });

  it("over_band이고 recommended_cap_10k가 있으면 CTA와 정직 고지 문구를 렌더한다", () => {
    render(<PricingBandPanel data={BASE} />);
    expect(screen.getByTestId("afford-cap-recalc-cta")).toBeInTheDocument();
    expect(
      screen.getByText(/지불여력 상한 = 미분양 회피 하한 시나리오\(시장 실현가 아님\)/),
    ).toBeInTheDocument();
    expect(screen.getByText(/분양단가만 반영\(평형믹스는 별도\)/)).toBeInTheDocument();
    // 렌더만으로는 아무 것도 자동 실행되지 않는다(클릭 전 이동 0회).
    expect(pushMock).not.toHaveBeenCalled();
  });

  it("CTA 클릭 시 공급 원/평을 축 명시 URL 파라미터로 실어 개략수지 앵커로 이동한다", async () => {
    render(<PricingBandPanel data={BASE} />);
    await userEvent.click(screen.getByTestId("afford-cap-recalc-cta"));

    const expectedWon = capManwonToPricePerPyeongWon(50400); // recommended_cap_10k
    expect(pushMock).toHaveBeenCalledWith(
      `/ko/analytics/investment?prefillSaleSupplyWon=${expectedWon}#rough-scenario-base`,
    );
  });
});
