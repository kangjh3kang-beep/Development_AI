/**
 * 아이디어#4(지불여력→개략수지 원클릭 퍼널) — RoughScenarioPanel read 끝 봉합 검증.
 *
 * PricingBandPanel CTA가 축 명시 URL 파라미터(prefillSaleSupplyWon·공급면적 기준)로 실어보낸
 * 값을 기본 개략수지 생성 시 overrides.sale_price_per_pyeong로 프리필하는지, 프리필 출처
 * 문구가 뜨는지, 그리고 렌더만으로는 자동 실행되지 않는지를 검증한다.
 * (모호한 공유 스토어 슬롯이 아니라 축이 명시된 파라미터를 소비 — R1 P1 basis 봉합.)
 */
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { RoughScenarioPanel } from "@/components/feasibility/RoughScenarioPanel";
import { useProjectContextStore } from "@/store/useProjectContextStore";

// useSearchParams 모킹 — 각 테스트가 prefillSaleSupplyWon 유무를 제어한다.
const { searchParamsGet } = vi.hoisted(() => ({ searchParamsGet: vi.fn() }));
vi.mock("next/navigation", () => ({
  useSearchParams: () => ({ get: searchParamsGet }),
}));

vi.mock("@/components/common/ProjectSwitcher", () => ({
  ProjectSwitcher: () => null,
}));
vi.mock("@/components/common/ProjectAddressInput", () => ({
  ProjectAddressInput: ({
    value,
    onChange,
  }: {
    value: string;
    onChange: (v: string) => void;
  }) => (
    <input
      data-testid="addr-input"
      value={value}
      onChange={(e) => onChange(e.target.value)}
    />
  ),
}));

const { postV2Mock } = vi.hoisted(() => ({ postV2Mock: vi.fn() }));
vi.mock("@/lib/api-client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api-client")>();
  return {
    ...actual,
    apiClient: { ...actual.apiClient, postV2: postV2Mock },
  };
});

const { historyCardCalls } = vi.hoisted(() => ({ historyCardCalls: [] as Record<string, unknown>[] }));
vi.mock("@/components/common/AnalysisHistoryCard", () => ({
  AnalysisHistoryCard: (props: Record<string, unknown>) => {
    historyCardCalls.push(props);
    return <div data-testid="history-card" data-analysis-type={String(props.analysisType)} />;
  },
}));

function resetStore() {
  act(() => {
    useProjectContextStore.setState({
      projectId: null,
      projectName: "",
      projectStatus: "",
      siteAnalysis: null,
      feasibilityData: null,
    });
  });
}

function scenarioResult(pricePerPyeong: number, overridesApplied: string[] = []) {
  return {
    address: "서울시 강남구",
    project_id: null,
    scenario_status: "final",
    inputs: {
      land_area_sqm: 1000,
      zone_type: "제2종일반주거지역",
      effective_far_pct: 200,
      dev_type: "M06",
      gfa_sqm: 2000,
      saleable_area_pyeong: 500,
      parcel_count: 1,
      project_months: 30,
    },
    land_cost: { total_won: 1_000_000_000, per_sqm_won: 1_000_000, basis: "테스트", source: "live" },
    construction_cost: { total_won: 2_000_000_000, unit_per_sqm_won: 1_000_000, basis: "테스트", source: "live" },
    revenue: {
      total_won: 5_000_000_000,
      sale_price_per_pyeong: pricePerPyeong,
      saleable_area_pyeong: 500,
      basis: "테스트",
      source: overridesApplied.includes("sale_price_per_pyeong") ? "user_override" : "live",
    },
    cost_breakdown: { land_won: 1_000_000_000, construction_won: 2_000_000_000, finance_won: 0, other_won: 0 },
    margin: { developer_profit_won: 500_000_000, rate_pct: 20, target_revenue_won: 3_000_000_000 },
    summary: {
      total_cost_won: 3_000_000_000,
      total_revenue_won: 5_000_000_000,
      net_profit_won: 500_000_000,
      roi_pct: 10,
      npv_won: null,
      irr_pct: null,
      payback_month: null,
      grade: "B",
    },
    cashflow: null,
    overrides_applied: overridesApplied,
    degraded_notes: [],
  };
}

describe("RoughScenarioPanel — 지불여력→개략수지 프리필 read", () => {
  beforeEach(() => {
    postV2Mock.mockReset();
    searchParamsGet.mockReset();
    historyCardCalls.length = 0;
    resetStore();
  });

  it("렌더만으로는 자동으로 개략수지를 요청하지 않는다(자동 실행 금지)", () => {
    searchParamsGet.mockReturnValue("29394450");
    render(<RoughScenarioPanel />);
    expect(postV2Mock).not.toHaveBeenCalled();
  });

  it("prefillSaleSupplyWon 파라미터가 있으면 기본 생성 요청에 overrides.sale_price_per_pyeong로 프리필하고 출처 문구를 표시한다", async () => {
    searchParamsGet.mockImplementation((k: string) => (k === "prefillSaleSupplyWon" ? "29394450" : null));
    postV2Mock.mockResolvedValue(scenarioResult(29_394_450, ["sale_price_per_pyeong"]));

    render(<RoughScenarioPanel />);
    await userEvent.type(screen.getByTestId("addr-input"), "서울시 강남구");
    await userEvent.click(screen.getByRole("button", { name: "개략수지 생성" }));

    await waitFor(() => expect(postV2Mock).toHaveBeenCalledTimes(1));
    const [path, options] = postV2Mock.mock.calls[0] as [string, { body: { overrides?: Record<string, number> } }];
    expect(path).toBe("/feasibility/rough-scenario");
    expect(options.body.overrides).toEqual({ sale_price_per_pyeong: 29_394_450 });

    expect(await screen.findByTestId("market-prefill-notice")).toBeInTheDocument();
    expect(screen.getByText(/시장 지불여력 상한에서 프리필되었습니다/)).toBeInTheDocument();
  });

  it("파라미터가 없으면 overrides를 보내지 않고 프리필 문구도 표시하지 않는다", async () => {
    searchParamsGet.mockReturnValue(null);
    postV2Mock.mockResolvedValue(scenarioResult(30_000_000, []));

    render(<RoughScenarioPanel />);
    await userEvent.type(screen.getByTestId("addr-input"), "서울시 강남구");
    await userEvent.click(screen.getByRole("button", { name: "개략수지 생성" }));

    await waitFor(() => expect(postV2Mock).toHaveBeenCalledTimes(1));
    const [, options] = postV2Mock.mock.calls[0] as [string, { body: { overrides?: Record<string, number> } }];
    expect(options.body.overrides).toBeUndefined();

    expect(screen.queryByTestId("market-prefill-notice")).not.toBeInTheDocument();
  });
});

describe("RoughScenarioPanel — 분석 히스토리 카드 배선", () => {
  beforeEach(() => {
    postV2Mock.mockReset();
    searchParamsGet.mockReturnValue(null);
    historyCardCalls.length = 0;
    resetStore();
  });

  it("주소 미확정 시 히스토리 카드를 렌더하지 않는다", () => {
    render(<RoughScenarioPanel />);
    expect(screen.queryByTestId("history-card")).not.toBeInTheDocument();
  });

  it("개략수지 생성 성공 후 결과 섹션 뒤에 feasibility 히스토리 카드를 배선한다", async () => {
    postV2Mock.mockResolvedValue(scenarioResult(30_000_000, []));

    render(<RoughScenarioPanel />);
    await userEvent.type(screen.getByTestId("addr-input"), "서울시 강남구");
    await userEvent.click(screen.getByRole("button", { name: "개략수지 생성" }));

    await waitFor(() => expect(postV2Mock).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(screen.getByTestId("history-card")).toBeInTheDocument());

    // DataSourceNotice(결과 섹션의 실제 마지막 콘텐츠) 뒤에 카드가 오는지 DOM 순서로 확인.
    const notice = screen.getByText(/국토교통부 실거래가/);
    const historyCard = screen.getByTestId("history-card");
    expect(notice.compareDocumentPosition(historyCard) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();

    expect(historyCardCalls.at(-1)).toMatchObject({
      analysisType: "feasibility",
      address: "서울시 강남구",
      pnu: null,
      reanalyzing: false,
      refreshSignal: 1,
    });
    expect(historyCardCalls.at(-1)?.currentSignatureParts).toEqual([
      "서울시 강남구",
      "",
      "1",
      "false",
      "",
    ]);
  });

  it("siteAnalysis.pnu가 채워져 있어도 히스토리 카드는 pnu=null로 조회한다(P1 — rough write/read pnu 비대칭 봉합, WRITE는 pnu 미전달 address-스코프)", async () => {
    act(() => {
      useProjectContextStore.setState({
        siteAnalysis: {
          estimatedValue: null,
          landAreaSqm: null,
          zoneCode: null,
          address: "서울시 강남구",
          pnu: "1168010100108250000",
        },
      });
    });
    postV2Mock.mockResolvedValue(scenarioResult(30_000_000, []));

    render(<RoughScenarioPanel />);
    await userEvent.click(screen.getByRole("button", { name: "개략수지 생성" }));

    await waitFor(() => expect(postV2Mock).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(screen.getByTestId("history-card")).toBeInTheDocument());

    expect(historyCardCalls.at(-1)).toMatchObject({
      analysisType: "feasibility",
      address: "서울시 강남구",
      pnu: null,
    });
  });
});
