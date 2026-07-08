/**
 * SiteAnalysisDetail 스모크(W3-2) — "크래시 없이 마운트 + 핵심 랜드마크 존재"만 확인.
 * 깊은 동작(지도 렌더·필지 조회)은 검증하지 않는다. 지도는 dynamicMap(next/dynamic)
 * 기반이라 jsdom에서 Leaflet을 실로드할 수 없어 스텁으로 대체한다.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { SiteAnalysisDetail } from "@/components/pipeline/SiteAnalysisDetail";

vi.mock("next/navigation", () => ({
  useParams: () => ({ locale: "ko" }),
  usePathname: () => "/ko/pipeline",
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    back: vi.fn(),
    prefetch: vi.fn(),
  }),
}));

// dynamicMap이 만드는 지도 컴포넌트(주변 실거래·필지 구획도)를 전부 스텁으로 대체.
vi.mock("next/dynamic", () => ({
  default: () => {
    const DynamicStub = () => <div data-testid="dynamic-map-stub" />;
    return DynamicStub;
  },
}));

// 네트워크 차단: 마운트 시 발생 가능한 조회(/zoning/parcels-info 등)는 영구 pending으로
// 고정해 늦은 setState(act 경고)와 실네트워크 시도를 모두 제거한다(스모크 안정성).
vi.mock("@/lib/api-client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api-client")>();
  const pending = () => new Promise<never>(() => {});
  return {
    ...actual,
    apiClient: {
      ...actual.apiClient,
      request: vi.fn(pending),
      get: vi.fn(pending),
      post: vi.fn(pending),
      put: vi.fn(pending),
      patch: vi.fn(pending),
      delete: vi.fn(pending),
      getV2: vi.fn(pending),
      postV2: vi.fn(pending),
      putV2: vi.fn(pending),
      deleteV2: vi.fn(pending),
    },
  };
});

describe("SiteAnalysisDetail 스모크", () => {
  it("최소 데이터로 크래시 없이 마운트되고 핵심 섹션이 보인다", () => {
    render(
      <SiteAnalysisDetail
        data={{ basic: { address: "서울특별시 강남구 역삼동 737", land_area_sqm: 500 } }}
      />,
    );

    expect(screen.getByText("기본 토지정보")).toBeInTheDocument();
    expect(screen.getByText("용도지역 · 법규한도")).toBeInTheDocument();
    expect(screen.getByText("서울특별시 강남구 역삼동 737")).toBeInTheDocument();
  });

  it("빈 데이터({})로도 크래시 없이 마운트된다", () => {
    render(<SiteAnalysisDetail data={{}} />);

    expect(screen.getByText("기본 토지정보")).toBeInTheDocument();
  });
});
