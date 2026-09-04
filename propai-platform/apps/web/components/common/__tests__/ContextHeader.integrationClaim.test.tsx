/**
 * ★헤더가 "통합 N필지"라고 **단정**하던 것을 멈춘다(2026-08-24 · 라이브 화면에서 발견).
 *
 * 라이브 `/ko/precheck` 에서 실제로 본 것:
 *   배너 : "하나의 개발 부지가 아닙니다 — 3개 지역에 최대 290.33km 떨어져 있습니다"
 *   헤더 : "대지면적 162,033㎡  [통합 3필지]"     ← **같은 화면·같은 순간**
 *
 * 사용자는 위쪽(헤더)을 먼저 읽는다. 배너가 아무리 정확해도 헤더가 반대로 말하면
 * 그 화면은 여전히 자기모순이다.
 *
 * ★판정은 선택 화면과 **같은 판별자**(`classifySelection`)를 쓴다 — 두 표면이 갈리면 그게 결함이다.
 */
import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ContextHeader } from "@/components/common/ContextHeader";
import { useProjectContextStore, type SiteAnalysisData } from "@/store/useProjectContextStore";

vi.mock("next/navigation", () => ({
  useParams: () => ({ locale: "ko" }),
  usePathname: () => "/ko/precheck",
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn(), prefetch: vi.fn() }),
}));

function seed(parcels: Array<Record<string, unknown>>) {
  useProjectContextStore.setState({
    projectId: "p1",
    projectName: "역삼동 736",
    siteAnalysis: {
      estimatedValue: null,
      address: "서울특별시 강남구 역삼동 736",
      pnu: "1168010100107360000",
      zoneCode: "일반상업지역",
      parcelCount: parcels.length,
      landAreaSqm: 162033,
      landAreaSqmTotal: 162033,
      parcels,
    } as unknown as SiteAnalysisData,
  } as never);
}

/** 라이브 실측 — 역삼동 + 포항 대보리 + 의정부동(290km). */
const FAR = [
  { address: "서울특별시 강남구 역삼동 736", areaSqm: 629.8, lat: 37.5, lon: 127.03 },
  { address: "경상북도 포항시 남구 호미곶면 대보리 산 1-1", areaSqm: 147074, lat: 36.07, lon: 129.56 },
  { address: "경기도 의정부시 의정부동 224", areaSqm: 14958.7, lat: 37.73, lon: 127.04 },
];
/** 정상 — 같은 동 인접 3필지(위양성 대조군). */
const NEAR = [
  { address: "서울특별시 강남구 역삼동 736", areaSqm: 629.8, lat: 37.5, lon: 127.03 },
  { address: "서울특별시 강남구 역삼동 737", areaSqm: 500, lat: 37.5001, lon: 127.0301 },
  { address: "서울특별시 강남구 역삼동 738", areaSqm: 400, lat: 37.5002, lon: 127.0302 },
];

describe("헤더는 하나의 부지가 아닌 것을 '통합'이라 부르지 않는다", () => {
  afterEach(() => {
    useProjectContextStore.setState({ projectId: null, projectName: "", siteAnalysis: null } as never);
  });

  it("★A) 290km 흩어진 선택 — '통합 N필지' 대신 '합계 · 통합 부지 아님'", () => {
    seed(FAR);
    render(<ContextHeader />);
    // 공허 진리 가드 — 헤더가 실제로 그려졌는지 먼저 본다.
    expect(screen.getByText("대지면적")).toBeInTheDocument();

    expect(screen.getByText(/3필지 합계 · 통합 부지 아님/)).toBeInTheDocument();
    // ★거짓 단정이 사라졌는지 반대 방향으로도 확인(음성 대조군).
    expect(screen.queryByText("통합 3필지")).not.toBeInTheDocument();
  });

  it("★B) 위양성 방지 — 같은 동 인접이면 종전대로 '통합 3필지'(무회귀)", () => {
    seed(NEAR);
    render(<ContextHeader />);
    expect(screen.getByText("대지면적")).toBeInTheDocument();
    expect(screen.getByText("통합 3필지")).toBeInTheDocument();
    expect(screen.queryByText(/통합 부지 아님/)).not.toBeInTheDocument();
  });

  it("★C) 두 경로가 실제로 갈린다 — 같으면 위 단언이 잠금이 아니다", () => {
    seed(FAR);
    const { unmount } = render(<ContextHeader />);
    const far = screen.getByText(/필지/).textContent;
    unmount();
    seed(NEAR);
    render(<ContextHeader />);
    expect(screen.getByText(/필지/).textContent).not.toBe(far);
  });
});
