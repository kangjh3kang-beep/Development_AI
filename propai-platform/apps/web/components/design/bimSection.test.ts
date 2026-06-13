import { describe, expect, it } from "vitest";
import { buildingHeightM, sectionCutHeightM, visibleFloorCount } from "./bimSection";

describe("buildingHeightM — 층수×층고", () => {
  it("5층 × 3m = 15m", () => {
    expect(buildingHeightM(5, 3)).toBe(15);
  });
  it("0/음수 입력은 0(가짜 높이 금지)", () => {
    expect(buildingHeightM(0, 3)).toBe(0);
    expect(buildingHeightM(5, 0)).toBe(0);
    expect(buildingHeightM(-2, 3)).toBe(0);
  });
});

describe("sectionCutHeightM — 슬라이더 % → 절단 높이(m)", () => {
  it("100% = 전체 높이(절단 없음 = 꼭대기)", () => {
    expect(sectionCutHeightM(100, 15)).toBe(15);
  });
  it("50% = 절반 높이", () => {
    expect(sectionCutHeightM(50, 15)).toBe(7.5);
  });
  it("0% = 0m(바닥)", () => {
    expect(sectionCutHeightM(0, 15)).toBe(0);
  });
  it("범위 밖 %는 0~100으로 클램프", () => {
    expect(sectionCutHeightM(150, 15)).toBe(15);
    expect(sectionCutHeightM(-10, 15)).toBe(0);
  });
});

describe("visibleFloorCount — 절단선 아래 완전 노출 층수", () => {
  it("절단 7.5m, 층고 3m → 2개 층(0~3, 3~6)이 완전 노출", () => {
    expect(visibleFloorCount(7.5, 3, 5)).toBe(2);
  });
  it("절단이 전체 높이면 전 층(클램프)", () => {
    expect(visibleFloorCount(15, 3, 5)).toBe(5);
  });
  it("절단 0m면 0개", () => {
    expect(visibleFloorCount(0, 3, 5)).toBe(0);
  });
  it("층고 0/음수는 0(0division 금지)", () => {
    expect(visibleFloorCount(7.5, 0, 5)).toBe(0);
  });
  it("절단이 전체보다 커도 numFloors로 클램프", () => {
    expect(visibleFloorCount(100, 3, 5)).toBe(5);
  });
  it("절단이 정확히 층 경계면 그 층까지 카운트(엡실론 안정)", () => {
    expect(visibleFloorCount(3, 3, 5)).toBe(1); // 1개 층(0~3) 완전 노출
    expect(visibleFloorCount(6, 3, 5)).toBe(2); // 2개 층(0~6) 완전 노출
    expect(visibleFloorCount(9, 3, 5)).toBe(3);
  });
});
