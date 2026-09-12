import { describe, expect, it } from "vitest";

import { deriveLandAreaIntake, describeSelectionArea } from "@/lib/building-overview-intake";

const S = (verdict: "single_site" | "multi_region" | "malformed", spreadKm: number | null = null) =>
  ({ verdict, spreadKm }) as const;

describe("대지면적 자동 산입 게이트", () => {
  it("★단일 부지면 합계를 산입한다", () => {
    const got = deriveLandAreaIntake([1000, 500.5], S("single_site", 0.2));
    expect(got.autoLandAreaSqm).toBe(1500.5);
    expect(got.withheldReason).toBeNull();
  });

  it("★★원거리 혼합이면 **보류**한다 — 2026-08-23 사고(15.86km 6필지 「통합 5,781㎡」) 재현 방지", () => {
    const got = deriveLandAreaIntake([1000, 500], S("multi_region", 15.86));
    expect(got.autoLandAreaSqm).toBeNull();
    expect(got.withheldReason).toContain("15.9km"); // 거리를 사유에 싣는다
  });

  it("★거리를 모르면 「0km」라고 쓰지 않는다", () => {
    const got = deriveLandAreaIntake([1000, 500], S("multi_region", null));
    expect(got.withheldReason).not.toContain("0.0km");
    expect(got.withheldReason).toContain("서로 다른 지역");
  });

  it("★깨진 데이터면 보류한다(소유자명이 주소 칸에 들어온 사고)", () => {
    expect(deriveLandAreaIntake([1000], S("malformed")).autoLandAreaSqm).toBeNull();
  });

  it("★필지가 없거나 면적이 없으면 **0㎡ 가 아니라 모름**", () => {
    for (const areas of [[], [null, undefined], [0, -5, NaN]]) {
      const got = deriveLandAreaIntake(areas as (number | null)[], S("single_site"));
      expect(got.autoLandAreaSqm, JSON.stringify(areas)).toBeNull();
      expect(got.withheldReason).toBeTruthy();
    }
    // ★대조군 — 정상 입력은 값이 나온다(위 단언이 「항상 null」로 공허해지지 않게)
    expect(deriveLandAreaIntake([10], S("single_site")).autoLandAreaSqm).toBe(10);
  });

  it("★보류할 때는 **사유가 반드시 있다**(무언 보류 금지)", () => {
    for (const v of ["multi_region", "malformed"] as const) {
      const got = deriveLandAreaIntake([100], S(v, 3));
      expect(got.autoLandAreaSqm).toBeNull();
      expect(got.withheldReason, v).toBeTruthy();
    }
  });
});

describe("★같은 화면이 두 서사를 말하지 않는다 — describeSelectionArea", () => {
  it("산입되면 「합산 면적」이라 부른다", () => {
    const got = describeSelectionArea("5,781㎡", { autoLandAreaSqm: 5781, withheldReason: null });
    expect(got.withheld).toBe(false);
    expect(got.label).toBe("합산 면적 5,781㎡");
  });

  it("★★보류되면 「합산 면적」이라 **부르지 않고** 사유를 싣는다(2026-08-23 사고의 형태)", () => {
    const reason = "최대 15.9km 떨어진 지역의 필지가 섞여 있어 합계를 하나의 대지면적으로 보지 않습니다.";
    const got = describeSelectionArea("5,781㎡", { autoLandAreaSqm: null, withheldReason: reason });
    expect(got.withheld).toBe(true);
    // ★숫자는 남는다 — 지우면 「왜 안 보이지」가 된다
    expect(got.label).toContain("5,781㎡");
    // ★그러나 「하나의 대지」라는 주장은 빠진다
    expect(got.label).not.toContain("합산 면적");
    // ★사유가 **그대로** 도달한다(무언 보류 금지)
    expect(got.label).toContain(reason);
  });

  it("[판별력] 두 경로가 실제로 **다른 문자열**을 낸다 — 같으면 게이트가 장식이다", () => {
    const ok = describeSelectionArea("100㎡", { autoLandAreaSqm: 100, withheldReason: null }).label;
    const held = describeSelectionArea("100㎡", { autoLandAreaSqm: null, withheldReason: "사유가 여기 온다" }).label;
    expect(ok).not.toBe(held);
  });
});
