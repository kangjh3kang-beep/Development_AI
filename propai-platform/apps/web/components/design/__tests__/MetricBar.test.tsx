import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { MetricBar } from "@/components/design/MetricBar";
import {
  useProjectContextStore,
  type DesignData,
  type SiteAnalysisData,
} from "@/store/useProjectContextStore";

function makeSite(partial: Partial<SiteAnalysisData>): SiteAnalysisData {
  return {
    estimatedValue: null,
    landAreaSqm: null,
    zoneCode: null,
    address: null,
    pnu: null,
    ...partial,
  };
}

function makeDesign(partial: Partial<DesignData>): DesignData {
  return {
    totalGfaSqm: null,
    floorCount: null,
    buildingType: null,
    bcr: null,
    far: null,
    ...partial,
  };
}

function resetStore() {
  window.localStorage.clear();
  useProjectContextStore.setState({
    projectId: "p1",
    siteAnalysis: null,
    designData: null,
    complianceData: null,
  });
}

// ── Pillar E(KPI바 상태 분기) — 설계 산출이 아직 없으면(미생성) 하단 KPI바는 "설계 산출 대기"로
//    정직 분기하고, 건폐/용적은 부지 실효 한도(법정상한/실효 배지·Phase 1 리졸버 재사용)로 폴백함을
//    라벨로 명시한다. 산출이 생성되면 종전 "생성 결과 KPI" 라벨을 유지한다(무회귀). ──
describe("MetricBar — 설계 산출 상태 분기(Pillar E)", () => {
  beforeEach(() => {
    resetStore();
  });

  it("설계 미생성(부지 한도만 있음) 시 '설계 산출 대기'로 표기하고 법정상한 배지를 보여준다", () => {
    // 설계 산출(designData) 없음 + 부지 법정상한만 있음 → 대기 상태 분기.
    useProjectContextStore.setState({
      siteAnalysis: makeSite({
        address: "서울특별시 강남구 역삼동 737",
        landAreaSqm: 500,
        zoneCode: "제2종일반주거지역",
        nationalFarPct: 250,
        nationalBcrPct: 60,
      }),
      designData: null,
    });

    render(<MetricBar />);

    // 미생성 라벨 — "생성 결과 KPI"가 아니라 "설계 산출 대기 / 추천안 생성 시 결과 표시".
    expect(screen.getByText("설계 산출 대기")).toBeInTheDocument();
    expect(screen.getByText("추천안 생성 시 결과 표시")).toBeInTheDocument();
    expect(screen.queryByText("생성 결과 KPI")).not.toBeInTheDocument();
    // 부지 폴백값은 '법정상한' 배지로 정직 구분(Phase 1 리졸버 재사용) — 최소 1곳.
    expect(screen.getAllByText("법정상한").length).toBeGreaterThanOrEqual(1);
  });

  it("설계 산출(연면적)이 있으면 '생성 결과 KPI' 라벨을 유지한다(무회귀)", () => {
    useProjectContextStore.setState({
      siteAnalysis: makeSite({
        address: "서울특별시 강남구 역삼동 737",
        landAreaSqm: 500,
        zoneCode: "제2종일반주거지역",
      }),
      designData: makeDesign({ totalGfaSqm: 1200, floorCount: 8, far: 240, bcr: 55 }),
    });

    render(<MetricBar />);

    expect(screen.getByText("생성 결과 KPI")).toBeInTheDocument();
    expect(screen.queryByText("설계 산출 대기")).not.toBeInTheDocument();
  });
});
