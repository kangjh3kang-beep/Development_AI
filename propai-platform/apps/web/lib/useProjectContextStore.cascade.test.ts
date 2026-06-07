import { describe, it, expect, beforeEach, vi } from "vitest";
import { useProjectContextStore } from "@/store/useProjectContextStore";

/**
 * Phase2 자동 캐스케이드 — isReadyForFirstCompute / isStale 회귀안전 검증.
 *
 * 핵심 불변식:
 *  - isStale의 "최초제외(own==null → false)" 정책은 보존(기존 소비처 동작 유지).
 *  - isReadyForFirstCompute는 업스트림 준비 && 자체 미산출일 때만 true(최초 1회).
 *  - 산출 후(stamp) isReadyForFirstCompute=false → 무한루프 차단.
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

describe("Phase2 캐스케이드 — 최초 자동산출 허용", () => {
  beforeEach(reset);

  it("업스트림이 비어 있으면 design 최초산출 불허", () => {
    const s = useProjectContextStore.getState();
    expect(s.isReadyForFirstCompute("design")).toBe(false);
  });

  it("부지 준비(면적>0) 시 design 최초산출 허용", () => {
    useProjectContextStore.getState().updateSiteAnalysis({ landAreaSqm: 500 });
    expect(
      useProjectContextStore.getState().isReadyForFirstCompute("design"),
    ).toBe(true);
  });

  it("주소만 채워져도(부지 ready) design 최초산출 허용 — 업스트림 지연 채움", () => {
    useProjectContextStore
      .getState()
      .updateSiteAnalysis({ address: "서울시 중곡동 1-1" });
    expect(
      useProjectContextStore.getState().isReadyForFirstCompute("design"),
    ).toBe(true);
  });

  it("design 산출 후엔 design 최초산출 불허(무한루프 차단)", () => {
    const s0 = useProjectContextStore.getState();
    s0.updateSiteAnalysis({ landAreaSqm: 500 });
    s0.updateDesignData({
      totalGfaSqm: 2000,
      floorCount: 5,
      buildingType: "근생",
      bcr: 50,
      far: 200,
    });
    expect(
      useProjectContextStore.getState().isReadyForFirstCompute("design"),
    ).toBe(false);
  });

  it("feasibility는 모든 업스트림(부지·설계·공사비) 준비 전엔 최초산출 불허", () => {
    const s0 = useProjectContextStore.getState();
    s0.updateSiteAnalysis({ landAreaSqm: 500 });
    s0.updateDesignData({
      totalGfaSqm: 2000,
      floorCount: 5,
      buildingType: "근생",
      bcr: 50,
      far: 200,
    });
    // cost 미산출 → 아직 불허
    expect(
      useProjectContextStore.getState().isReadyForFirstCompute("feasibility"),
    ).toBe(false);
    useProjectContextStore.getState().updateCostData({
      totalConstructionCostWon: 5_000_000_000,
      perSqmWon: null,
      perPyeongWon: null,
      abovegroundWon: null,
      undergroundWon: null,
      landscapeWon: null,
      directWon: null,
      indirectWon: null,
      rangeMinWon: null,
      rangeMaxWon: null,
      source: "overview",
    });
    expect(
      useProjectContextStore.getState().isReadyForFirstCompute("feasibility"),
    ).toBe(true);
  });

  it("업스트림 없는 siteAnalysis는 최초산출 강제하지 않음", () => {
    expect(
      useProjectContextStore.getState().isReadyForFirstCompute("siteAnalysis"),
    ).toBe(false);
  });
});

describe("Phase2 캐스케이드 — isStale 정책 보존(회귀안전)", () => {
  beforeEach(reset);

  it("다운스트림 미산출(own==null)이면 isStale=false (기존 정책 유지)", () => {
    useProjectContextStore.getState().updateSiteAnalysis({ landAreaSqm: 500 });
    expect(useProjectContextStore.getState().isStale("design")).toBe(false);
  });

  it("다운스트림 산출 후 업스트림이 더 최신이면 isStale=true", () => {
    // 타임스탬프 단조 증가를 결정적으로 보장(같은 ms 충돌 방지 — 실사용은 사용자 조작 간격).
    let t = 1_000_000;
    const spy = vi.spyOn(Date, "now").mockImplementation(() => (t += 10));
    try {
      const s0 = useProjectContextStore.getState();
      s0.updateSiteAnalysis({ landAreaSqm: 500 });
      s0.updateDesignData({
        totalGfaSqm: 2000,
        floorCount: 5,
        buildingType: "근생",
        bcr: 50,
        far: 200,
      });
      // design 산출 후 업스트림(site) 재갱신 → stale
      useProjectContextStore.getState().updateSiteAnalysis({ landAreaSqm: 600 });
      expect(useProjectContextStore.getState().isStale("design")).toBe(true);
    } finally {
      spy.mockRestore();
    }
  });
});
