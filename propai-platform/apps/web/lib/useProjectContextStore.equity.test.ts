import { describe, it, expect, beforeEach } from "vitest";
import { useProjectContextStore } from "@/store/useProjectContextStore";

/**
 * 적대적 리뷰 확정 결함(MEDIUM, [A]) 회귀 테스트 — equityWon 앵커링 재발방지.
 *
 * 결함: updateFeasibilityData가 "병합된 equityWon > 0"이면 무조건 명시 입력으로
 *  보존했다. 그 양수값이 직전 자동파생(ratio×cost)값이면, cost가 나중에 바뀌어도
 *  (부분 writer가 equityWon 키를 omit — 예: ProjectPipelinePanel 재실행 경로)
 *  equity가 옛 cost에 앵커돼 실효비율이 침묵 이탈한다.
 *
 * 수정: equityIsManual 플래그로만 "보존 vs 재파생"을 가른다. manual=true는 오직
 *  사용자가 자기자본 절대액을 직접 입력한 경로(FeasibilityEditorV2 양수 환류)에서만 세팅.
 */

function reset() {
  useProjectContextStore.setState({
    projectId: "p1",
    siteAnalysis: null,
    designData: null,
    feasibilityData: null,
    costData: null,
    esgData: null,
    complianceData: null,
    updatedAt: {},
    snapshots: {},
  });
}

describe("자기자본 SSOT — equityIsManual 게이트 회귀", () => {
  beforeEach(reset);

  it("[A] 재현: 자동파생 자기자본은 cost 변경 시(equityWon omit) 새 비율로 재산출된다(앵커링 없음)", () => {
    const s = useProjectContextStore.getState();
    // 1) cost=100억, ratio=30% → equity=30억(자동파생).
    s.setEquityRatioPct(30);
    s.updateFeasibilityData({ totalCostWon: 10_000_000_000 });
    expect(useProjectContextStore.getState().feasibilityData?.equityWon).toBe(3_000_000_000);

    // 2) 재실행 경로 — totalCostWon만 전달, equityWon 키 자체를 omit(ProjectPipelinePanel 패턴).
    s.updateFeasibilityData({ totalCostWon: 20_000_000_000, totalRevenueWon: null, profitRatePct: null, grade: null });

    // 3) 옛 cost(100억)에 앵커되지 않고 새 cost(200억)×동일 30%로 재산출돼야 한다.
    const after = useProjectContextStore.getState().feasibilityData;
    expect(after?.equityWon).toBe(6_000_000_000);
    expect(after?.equityRatioPct).toBe(30);
  });

  it("사용자 수동 입력(equityIsManual=true)은 cost 변경에도 절대액이 보존된다", () => {
    const s = useProjectContextStore.getState();
    // 사용자가 FeasibilityEditorV2 경로로 자기자본 35억을 직접 입력·환류.
    s.updateFeasibilityData({
      totalCostWon: 10_000_000_000,
      totalRevenueWon: null,
      profitRatePct: null,
      grade: null,
      equityWon: 3_500_000_000,
      equityIsManual: true,
    });
    expect(useProjectContextStore.getState().feasibilityData?.equityWon).toBe(3_500_000_000);

    // cost가 바뀌어도(equityWon 키 omit) 수동 입력값은 보존돼야 한다.
    s.updateFeasibilityData({ totalCostWon: 20_000_000_000, totalRevenueWon: null, profitRatePct: null, grade: null });
    const after = useProjectContextStore.getState().feasibilityData;
    expect(after?.equityWon).toBe(3_500_000_000);
  });

  it("equityWon: undefined(미입력 센티넬) + equityIsManual: false → 항상 재파생(기존 정상동작 보존)", () => {
    const s = useProjectContextStore.getState();
    // 최초 수동 입력으로 3.5억 자기자본이 있던 상태에서,
    s.updateFeasibilityData({
      totalCostWon: 10_000_000_000,
      totalRevenueWon: null,
      profitRatePct: null,
      grade: null,
      equityWon: 3_500_000_000,
      equityIsManual: true,
    });
    // 사용자가 입력을 지우고(0) 재계산 — FeasibilityEditorV2가 undefined+manual:false로 환류.
    s.updateFeasibilityData({
      totalCostWon: 10_000_000_000,
      totalRevenueWon: null,
      profitRatePct: null,
      grade: null,
      equityWon: undefined,
      equityIsManual: false,
    });
    // 기본 10% 비율로 재파생(수동 흔적 사라짐).
    const after = useProjectContextStore.getState().feasibilityData;
    expect(after?.equityWon).toBe(1_000_000_000);
    expect(after?.equityIsManual).toBe(false);
  });

  it("setEquityRatioPct(DCF 변경)는 equityIsManual을 false로 되돌리고 현재 cost로 즉시 재산출한다", () => {
    const s = useProjectContextStore.getState();
    // 수동 입력 상태에서 시작.
    s.updateFeasibilityData({
      totalCostWon: 10_000_000_000,
      totalRevenueWon: null,
      profitRatePct: null,
      grade: null,
      equityWon: 3_500_000_000,
      equityIsManual: true,
    });
    // DCF에서 비율을 20%로 변경.
    s.setEquityRatioPct(20);
    const afterRatio = useProjectContextStore.getState().feasibilityData;
    expect(afterRatio?.equityRatioPct).toBe(20);
    expect(afterRatio?.equityWon).toBe(2_000_000_000); // 10억×20%
    expect(afterRatio?.equityIsManual).toBe(false);

    // 이후 cost가 바뀌면(재실행) 새 비율 20%로 계속 추종해야 한다(앵커링 없음).
    s.updateFeasibilityData({ totalCostWon: 30_000_000_000, totalRevenueWon: null, profitRatePct: null, grade: null });
    expect(useProjectContextStore.getState().feasibilityData?.equityWon).toBe(6_000_000_000);
  });
});
