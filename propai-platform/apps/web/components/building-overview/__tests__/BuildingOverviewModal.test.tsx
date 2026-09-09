import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { BuildingOverviewModal } from "@/components/building-overview/BuildingOverviewModal";
import type { LandAreaIntake } from "@/lib/building-overview-intake";

const OK: LandAreaIntake = { autoLandAreaSqm: 1000, withheldReason: null };
const HELD: LandAreaIntake = {
  autoLandAreaSqm: null,
  withheldReason: "최대 15.9km 떨어진 지역의 필지가 섞여 있어 합계를 하나의 대지면적으로 보지 않습니다.",
};

function open(intake: LandAreaIntake = OK, onSave = vi.fn()) {
  render(
    <BuildingOverviewModal open intake={intake} initial={null} onSave={onSave} onCancel={vi.fn()} />,
  );
  return onSave;
}

describe("건축개요 모달", () => {
  it("★닫혀 있으면 아무것도 그리지 않는다", () => {
    render(
      <BuildingOverviewModal open={false} intake={OK} initial={null} onSave={vi.fn()} onCancel={vi.fn()} />,
    );
    expect(screen.queryByTestId("building-overview-modal")).toBeNull();
  });

  it("★자동 산입되면 값이 채워지고 **출처가 표시**된다", () => {
    open();
    expect((screen.getByTestId("land-area") as HTMLInputElement).value).toBe("1000");
    expect(screen.getByTestId("land-origin").textContent).toContain("선택 필지 합계");
    // 보류 사유는 없다
    expect(screen.queryByTestId("intake-withheld")).toBeNull();
  });

  // ★열림 초기화를 effect 가 아니라 **렌더 중 조정**으로 옮기면서 생기는 함정을 잠근다:
  //   「반영한 신호」를 닫힐 때 비우지 않으면 **두 번째 열기가 조용히 낡은 값을 들고 온다**.
  //   같은 필지(같은 intake)로 다시 여는 것이 그 자리다 — 신호가 같아 재초기화가 생략된다.
  it("★★닫았다 **다시 열면** 사람이 고친 값이 아니라 자동 산입값으로 돌아온다", async () => {
    const user = userEvent.setup();
    const props = { intake: OK, initial: null, onSave: vi.fn(), onCancel: vi.fn() };
    const view = render(<BuildingOverviewModal open {...props} />);

    const land = () => screen.getByTestId("land-area") as HTMLInputElement;
    expect(land().value).toBe("1000");
    await user.clear(land());
    await user.type(land(), "7");
    expect(land().value).toBe("7");

    view.rerender(<BuildingOverviewModal open={false} {...props} />);
    expect(screen.queryByTestId("building-overview-modal")).toBeNull();
    // ★같은 intake 로 다시 연다 — 신호가 동일해도 초기화가 돌아야 한다.
    view.rerender(<BuildingOverviewModal open {...props} />);

    expect(land().value, "다시 열었는데 직전 편집이 남았다 — 열림 신호를 안 비웠다").toBe("1000");
    expect(screen.getByTestId("land-origin").textContent).toContain("선택 필지 합계");
  });

  it("★★보류되면 **비워 두고 사유를 보여 준다**(2026-08-23 사고 재현 방지)", () => {
    open(HELD);
    expect((screen.getByTestId("land-area") as HTMLInputElement).value).toBe("");
    const note = screen.getByTestId("intake-withheld");
    expect(note.textContent).toContain("15.9km");
    expect(note.textContent).toContain("직접 입력"); // ★막지 않고 길을 준다
  });

  it("★사람이 덮어쓰면 출처가 **직접 입력**으로 바뀐다(자동값과 구별)", async () => {
    open();
    await userEvent.clear(screen.getByTestId("land-area"));
    await userEvent.type(screen.getByTestId("land-area"), "800");
    expect(screen.getByTestId("land-origin").textContent).toContain("직접 입력");
  });

  it("★파생값은 못 재면 「—」 — **0% 라고 쓰지 않는다**", () => {
    open(HELD); // 대지면적 미입력
    expect(screen.getByTestId("derived-far").textContent).toBe("—");
    expect(screen.getByTestId("derived-bcr").textContent).toBe("—");
    expect(screen.getByTestId("derived-gfa").textContent).toBe("—");
  });

  it("★용적률은 지상만 센다 — 지하를 넣어도 안 바뀐다", async () => {
    open(); // 대지 1000 자동
    await userEvent.type(screen.getByTestId("aboveGroundGfaSqm"), "2000");
    expect(screen.getByTestId("derived-far").textContent).toBe("200.0%");
    await userEvent.type(screen.getByTestId("basementGfaSqm"), "5000");
    expect(screen.getByTestId("derived-far").textContent).toBe("200.0%"); // ★불변
    // 대조군 — 연면적 합계는 늘어난다(위 단언이 「아무것도 안 변한다」로 공허하지 않게)
    expect(screen.getByTestId("derived-gfa").textContent).toContain("7,000");
  });

  it("★모순은 신고하되 저장을 **막지 않는다**", async () => {
    const onSave = open();
    await userEvent.type(screen.getByTestId("buildingAreaSqm"), "2000"); // 대지 1000 < 건축 2000
    expect(screen.getByTestId("overview-issues").textContent).toContain("건축면적");
    await userEvent.click(screen.getByTestId("overview-save"));
    expect(onSave).toHaveBeenCalledTimes(1); // ★막지 않는다
  });

  it("★저장 payload 에 파생값이 **들어 있지 않다**", async () => {
    const onSave = open();
    await userEvent.type(screen.getByTestId("aboveGroundGfaSqm"), "1500");
    await userEvent.click(screen.getByTestId("overview-save"));
    const arg = onSave.mock.calls[0][0] as Record<string, unknown>;
    for (const k of ["farPct", "bcrPct", "totalGfaSqm"]) expect(arg, k).not.toHaveProperty(k);
    // 대조군 — 입력값은 실려 있다
    expect(arg.aboveGroundGfaSqm).toBe(1500);
    expect(arg.landAreaSqm).toBe(1000);
  });

  it("★용도 선택지는 정본에서 파생된다", async () => {
    open();
    await userEvent.click(screen.getByTestId("add-use"));
    const sel = screen.getByTestId("use-0") as HTMLSelectElement;
    const codes = [...sel.options].map((o) => o.value);
    expect(codes.length).toBeGreaterThanOrEqual(11); // 모집단 하한
    expect(codes).toContain("apartment");
    expect(codes).toContain("retail");
    // ★다른 축의 항목이 안 들어온다
    expect(codes).not.toContain("토지");
  });
});
