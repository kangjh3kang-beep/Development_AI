import { describe, expect, it } from "vitest";

import {
  planSatongLabels,
  satongLabelBudget,
  satongLabelLOD,
  SATONG_LABEL_BUDGET,
  SATONG_LABEL_BUDGET_NEAR,
  SATONG_LABEL_BUDGET_MID,
} from "./satong-map-labels";

describe("satong-map-labels — 줌 LOD", () => {
  it("줌 레벨을 LOD 3단계로 판정한다", () => {
    expect(satongLabelLOD(19)).toBe("all");
    expect(satongLabelLOD(17)).toBe("all");
    expect(satongLabelLOD(16)).toBe("top");
    expect(satongLabelLOD(15)).toBe("top");
    expect(satongLabelLOD(14)).toBe("hover-only");
    expect(satongLabelLOD(12)).toBe("hover-only");
  });

  it("LOD에 대응하는 전역 상시 라벨 버짓을 돌려준다(2026-07-17 정보 상시화 상향)", () => {
    expect(satongLabelBudget(17)).toBe(SATONG_LABEL_BUDGET); // 64
    expect(satongLabelBudget(18)).toBe(SATONG_LABEL_BUDGET_NEAR); // 96 — 초근접 사실상 전 마커
    expect(satongLabelBudget(19)).toBe(96);
    expect(satongLabelBudget(15)).toBe(SATONG_LABEL_BUDGET_MID); // 24
    expect(satongLabelBudget(16)).toBe(24);
    expect(satongLabelBudget(14)).toBe(0); // hover-only
    expect(satongLabelBudget(10)).toBe(0);
  });
});

describe("satong-map-labels — 전역 버짓 배분(planSatongLabels)", () => {
  it("<15 줌은 모든 레이어 상시 라벨 0(hover-only)", () => {
    const plan = planSatongLabels(13, [
      { id: "market", count: 30 },
      { id: "poi", count: 40 },
      { id: "development", count: 50 },
    ]);
    expect(plan).toEqual({ market: 0, poi: 0, development: 0 });
  });

  it("후보 합계가 버짓 이하면 전부 상시 라벨을 허용한다", () => {
    const plan = planSatongLabels(17, [
      { id: "market", count: 5 },
      { id: "poi", count: 10 },
      { id: "development", count: 8 },
    ]);
    expect(plan).toEqual({ market: 5, poi: 10, development: 8 });
  });

  it("★버짓 초과 시 우선순위 순으로 배분하고 합산이 버짓(64)을 넘지 않는다", () => {
    const plan = planSatongLabels(17, [
      { id: "market", count: 30 },
      { id: "presale", count: 30 },
      { id: "auction", count: 30 },
      { id: "poi", count: 83 },
      { id: "development", count: 67 },
    ]);
    // market 30 → presale 30 → 남은 4 → auction 4 → 이후 0
    expect(plan.market).toBe(30);
    expect(plan.presale).toBe(30);
    expect(plan.auction).toBe(4);
    expect(plan.poi).toBe(0);
    expect(plan.development).toBe(0);
    const total = Object.values(plan).reduce((a, b) => a + b, 0);
    expect(total).toBe(SATONG_LABEL_BUDGET);
    expect(total).toBeLessThanOrEqual(SATONG_LABEL_BUDGET);
  });

  it("중간 줌(15~16)은 축소 버짓(24)만 배분한다", () => {
    const plan = planSatongLabels(16, [
      { id: "poi", count: 83 },
      { id: "development", count: 67 },
    ]);
    expect(plan.poi).toBe(24);
    expect(plan.development).toBe(0);
    const total = Object.values(plan).reduce((a, b) => a + b, 0);
    expect(total).toBe(SATONG_LABEL_BUDGET_MID);
  });

  it("음수/0 후보 수는 0으로 안전 처리한다", () => {
    const plan = planSatongLabels(17, [
      { id: "market", count: -3 },
      { id: "poi", count: 0 },
    ]);
    expect(plan).toEqual({ market: 0, poi: 0 });
  });
});
