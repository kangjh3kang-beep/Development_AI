/**
 * 값–라벨 정합 계약 (R2) — **목표를 성과처럼 그리지 않는다**.
 *
 * ## 무엇을 막는가 (소스 실측)
 *
 * `margin.developer_profit_won` 은 백엔드에서 이렇게 만들어진다:
 *
 *     developer_profit = int(round(total_cost * margin_rate_pct / 100.0))   # 총사업비 × 20%
 *
 * **매출을 전혀 보지 않는다 — 구조상 언제나 양수다.** 그런데 화면은 그것을
 * `개발이익(마진)` 이라 부르며 **무조건 강조색**(`accent`)으로 그렸다. 그래서 순이익이
 * 마이너스인 사업에서도 큰 양수가 성과처럼 읽혔다.
 *
 * 더 나쁜 것은 그 옆이다 — `순이익` 도 **무조건 강조색**이었다. 즉 **−2,936억 손실이
 * 강조색**으로 그려진다. 코드는 accent 를 "중요함"으로 썼는데 사용자는 "좋음"으로 읽는다.
 * ★같은 파일의 월별 현금흐름은 이미 `net < 0 ? status-error : status-success` 로 부호별
 * 색을 쓰고 있었다 — **헤드라인만 예외**였다.
 *
 * ## 이 저장소가 같은 이름을 두 뜻으로 쓴다
 *
 *     ai/feasibility_interpreter 프롬프트:  개발이익 = 완성 후 가치(분양수입) − 총투입원가
 *     이 패널 · 보고서 §5:                  개발이익 = 총사업비 × 마진율
 *
 * 읽는 사람이 어느 쪽도 믿을 수 없다. **값은 지우지 않고 이름을 `목표`로 바로잡는다.**
 *
 * ## 잠그는 것
 *
 * 1. 라벨이 **목표**임을 말한다
 * 2. 달성 여부를 **말(충족/미달)로도** 전달한다 — 색만으로 심각도를 전달하지 않는다
 * 3. 달성 못 한 목표를 **성과의 색으로 그리지 않는다**
 * 4. 손실인 순이익을 **강조색으로 그리지 않는다**
 * 5. 판정 근거가 없으면 **아무 색도 말도 붙이지 않는다**(모르면 모른다)
 * 6. 대조군 — 충족/미달이 **서로 다른 화면**을 낸다(같으면 락이 공허하다)
 * 7. ★**실제 칠해지는 색**까지 본다 — `data-tone` 만 잠그면 색 매핑을 통째로 바꿔도 초록이다
 *    (변이 검증에서 `negative: "var(--status-error)"` 삭제가 살아남았다). 여기서 색은
 *    장식이 아니라 **의미**다 — 손실을 성과의 색으로 칠하는 것이 바로 이 PR 이 고치는 결함이다.
 *
 * ■ 변이 후 남은 생존 — 의도적 비잠금(점수 부풀리기 방지)
 *   · 내가 쓴 **주석 문자열** 2건 — 동작에 영향이 없다.
 *   · `accent: "var(--data-accent)"` — **하위호환 경로**다. 이 패널에서 `Stat ... accent` 는
 *     이제 현금흐름 섹션의 IRR 한 곳뿐이고(그 자리는 부호가 아니라 **강조**가 맞는 의미다),
 *     그 섹션은 `cashflow` 데이터가 있어야 렌더된다. 값–라벨 정합과 무관해 잠그지 않는다.
 *   · `muted: undefined` 삭제 — **등가 변이**다. 키가 없어도 조회 결과는 `undefined` 로 같다.
 */
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { RoughScenarioPanel } from "@/components/feasibility/RoughScenarioPanel";
import { useProjectContextStore } from "@/store/useProjectContextStore";

const { searchParamsGet } = vi.hoisted(() => ({ searchParamsGet: vi.fn() }));
vi.mock("next/navigation", () => ({
  useSearchParams: () => ({ get: searchParamsGet }),
}));
vi.mock("@/components/common/ProjectSwitcher", () => ({ ProjectSwitcher: () => null }));
vi.mock("@/components/common/ProjectAddressInput", () => ({
  ProjectAddressInput: ({ value, onChange }: { value: string; onChange: (v: string) => void }) => (
    <input data-testid="addr-input" value={value} onChange={(e) => onChange(e.target.value)} />
  ),
}));
vi.mock("@/components/common/AnalysisHistoryCard", () => ({
  AnalysisHistoryCard: () => <div data-testid="history-card" />,
}));

const { postV2Mock } = vi.hoisted(() => ({ postV2Mock: vi.fn() }));
vi.mock("@/lib/api-client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api-client")>();
  return { ...actual, apiClient: { ...actual.apiClient, postV2: postV2Mock } };
});

const TARGET_REVENUE = 3_000_000_000;
const TARGET_PROFIT = 500_000_000; // 총사업비 × 20% — 매출과 무관하게 언제나 양수

function scenario({
  revenue,
  netProfit,
}: {
  revenue: number | null;
  netProfit: number | null;
}) {
  return {
    address: "서울시 강남구",
    project_id: null,
    scenario_status: "final",
    inputs: {
      land_area_sqm: 1000, zone_type: "제2종일반주거지역", effective_far_pct: 200,
      dev_type: "M06", gfa_sqm: 2000, saleable_area_pyeong: 500, parcel_count: 1, project_months: 30,
    },
    land_cost: { total_won: 1_000_000_000, per_sqm_won: 1_000_000, basis: "t", source: "live" },
    construction_cost: { total_won: 2_000_000_000, unit_per_sqm_won: 1_000_000, basis: "t", source: "live" },
    revenue: { total_won: revenue, sale_price_per_pyeong: 10_000_000, saleable_area_pyeong: 500, basis: "t", source: "live" },
    cost_breakdown: { land_won: 1_000_000_000, construction_won: 2_000_000_000, finance_won: 0, other_won: 0 },
    // ★목표치는 두 시나리오에서 **동일**하다 — 그래야 "화면이 무엇으로 갈리는지"가 드러난다.
    margin: { developer_profit_won: TARGET_PROFIT, rate_pct: 20, target_revenue_won: TARGET_REVENUE },
    summary: {
      total_cost_won: 2_500_000_000, total_revenue_won: revenue, net_profit_won: netProfit,
      roi_pct: null, npv_won: null, irr_pct: null, payback_month: null, grade: netProfit != null && netProfit < 0 ? "F" : "B",
    },
    cashflow: null,
    overrides_applied: [],
    degraded_notes: [],
  };
}

/** 라벨로 지표 칸을 찾아 값 span 을 돌려준다(없으면 null). */
function statValue(labelPrefix: string): HTMLElement | null {
  const labels = Array.from(document.querySelectorAll(".sa-di-stat__label"));
  const hit = labels.find((el) => (el.textContent ?? "").startsWith(labelPrefix));
  return (hit?.parentElement?.querySelector(".sa-di-stat__value") as HTMLElement) ?? null;
}

async function renderWith(result: unknown) {
  postV2Mock.mockResolvedValue(result);
  render(<RoughScenarioPanel />);
  await userEvent.type(screen.getByTestId("addr-input"), "서울시 강남구");
  await userEvent.click(screen.getByRole("button", { name: "개략수지 생성" }));
  await waitFor(() => expect(postV2Mock).toHaveBeenCalledTimes(1));
  // 결과 섹션이 실제로 렌더될 때까지 기다린다(대상 0개 통과 방지).
  await waitFor(() => expect(statValue("목표 개발이익")).not.toBeNull());
}

beforeEach(() => {
  postV2Mock.mockReset();
  searchParamsGet.mockReset();
  searchParamsGet.mockReturnValue(null);
  act(() => {
    useProjectContextStore.setState({
      projectId: null, projectName: "", projectStatus: "", siteAnalysis: null, feasibilityData: null,
    });
  });
});

describe("값–라벨 정합 — 목표를 성과처럼 그리지 않는다", () => {
  it("★미달·손실 — 목표는 '미달'로, 순이익은 '손실'로 말하고 성과의 색을 쓰지 않는다", async () => {
    await renderWith(scenario({ revenue: 1_000_000_000, netProfit: -1_500_000_000 }));

    const target = statValue("목표 개발이익")!;
    // 라벨이 **목표**임을 말한다(종전 라벨은 "개발이익(마진)" 이었다).
    const label = target.parentElement!.querySelector(".sa-di-stat__label")!.textContent ?? "";
    expect(label).toContain("목표 개발이익");
    expect(label).toContain("20%");
    // 색만으로 전달하지 않는다 — 말로도 전달한다.
    expect(target.textContent).toContain("미달");
    // ★달성 못 한 목표를 성과의 색으로 그리지 않는다.
    expect(target.getAttribute("data-tone")).toBe("negative");

    const net = statValue("실제 순이익")!;
    expect(net.textContent).toContain("손실");
    expect(net.getAttribute("data-tone")).toBe("negative");

    // ★실제 칠해지는 색까지 본다 — tone 만 잠그면 색 매핑을 바꿔도 초록이다.
    expect(target.style.color).toContain("--status-error");
    expect(net.style.color).toContain("--status-error");
    // ★종전 동작(무조건 강조색)으로 되돌리면 죽는다.
    expect(net.style.color).not.toContain("--data-accent");
  });

  it("★대조군 — 충족·이익이면 같은 자리가 '충족'과 성과의 색으로 바뀐다", async () => {
    await renderWith(scenario({ revenue: 5_000_000_000, netProfit: 1_200_000_000 }));

    const target = statValue("목표 개발이익")!;
    expect(target.textContent).toContain("충족");
    expect(target.textContent).not.toContain("미달");
    expect(target.getAttribute("data-tone")).toBe("positive");

    const net = statValue("실제 순이익")!;
    expect(net.textContent).not.toContain("손실");
    expect(net.getAttribute("data-tone")).toBe("positive");

    expect(target.style.color).toContain("--status-success");
    expect(net.style.color).toContain("--status-success");
  });

  it("★성과의 색과 손실의 색은 **서로 달라야** 한다(같은 색이면 구분이 없다)", async () => {
    await renderWith(scenario({ revenue: 1_000_000_000, netProfit: -1_500_000_000 }));
    const lossColor = statValue("실제 순이익")!.style.color;
    // 같은 컴포넌트를 새로 렌더해 반대 상태를 만든다.
    document.body.innerHTML = "";
    postV2Mock.mockReset();
    await renderWith(scenario({ revenue: 5_000_000_000, netProfit: 1_200_000_000 }));
    const gainColor = statValue("실제 순이익")!.style.color;
    expect(lossColor).not.toBe("");
    expect(gainColor).not.toBe("");
    expect(lossColor).not.toBe(gainColor);
  });

  it("★판정 근거가 없으면 아무 말도 색도 붙이지 않는다(모르면 모른다)", async () => {
    await renderWith(scenario({ revenue: null, netProfit: null }));

    const target = statValue("목표 개발이익")!;
    expect(target.textContent).not.toContain("충족");
    expect(target.textContent).not.toContain("미달");
    expect(target.getAttribute("data-tone")).toBe("muted");
    // ★판정이 없으면 색도 없다 — 없는 판정을 색으로 말하지 않는다.
    expect(target.style.color).toBe("");
  });

  it("★사업성 요약의 순이익도 손실이면 강조색을 쓰지 않는다(형제 표면 스윕)", async () => {
    await renderWith(scenario({ revenue: 1_000_000_000, netProfit: -1_500_000_000 }));
    // '순이익'(요약 섹션)과 '실제 순이익'(마진 카드)은 다른 칸이다 — 둘 다 본다.
    const summaryNet = statValue("순이익");
    expect(summaryNet, "요약 섹션의 순이익 칸이 없다 — 공허한 초록").not.toBeNull();
    expect(summaryNet!.getAttribute("data-tone")).toBe("negative");
    expect(summaryNet!.textContent).toContain("손실");
  });
});
