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

// ── 조례 폴백 confirmed 정직화 회귀앵커(live-fix① R2 — R1 리뷰 확정) ──
// 라이브 재현(용인시 수지구 자연녹지): 조례 미해석(ordinance_confirmed=false) 폴백값이
// "조례 용적률 (지자체)" 타일에 확정 수치처럼 표시되고, 바로 아래 "출처: 법정상한"과
// 자기모순을 일으켰다. 백엔드 SSOT가 미확정 시 ordinance_far_pct/ordinance_bcr_pct를
// None으로 반환해도, 이 타일은 ordinance_confirmed를 직접 게이트해야 안전하다(구버전
// 캐시 응답 등 값이 여전히 실리는 경로 방어).
describe("조례 폴백 confirmed 정직화(R1 봉합)", () => {
  it("조례 미확정(ordinance_confirmed=false)이면 '확인 필요'로 표시하고 폴백수치를 확정처럼 보여주지 않는다", () => {
    render(
      <SiteAnalysisDetail
        data={{
          basic: { address: "용인시 수지구 신봉동 56-19", land_area_sqm: 500 },
          zoning: {
            zone_type: "자연녹지지역",
            ordinance_source: "법정상한",
            effective_far: {
              national_bcr_pct: 20,
              national_far_pct: 100,
              ordinance_bcr_pct: null,
              ordinance_far_pct: null,
              effective_bcr_pct: 20,
              effective_far_pct: 80,
              ordinance_confirmed: false,
            },
          },
        }}
      />,
    );

    expect(screen.getByText("용도지역 · 법규한도")).toBeInTheDocument();
    // 폴백값(100%)이 "조례 용적률" 타일에 확정 수치로 나타나지 않는다.
    const farLabels = screen.getAllByText("조례 용적률 (지자체)");
    expect(farLabels.length).toBeGreaterThan(0);
    expect(screen.getAllByText("확인 필요").length).toBeGreaterThan(0);
  });

  it("조례 확정(ordinance_confirmed=true)이면 정상 수치를 표시한다(무회귀)", () => {
    render(
      <SiteAnalysisDetail
        data={{
          basic: { address: "서울특별시 종로구 1-1", land_area_sqm: 500 },
          zoning: {
            zone_type: "자연녹지지역",
            ordinance_source: "지자체 조례(정적캐시)",
            effective_far: {
              national_bcr_pct: 20,
              national_far_pct: 100,
              ordinance_bcr_pct: 20,
              ordinance_far_pct: 50,
              effective_bcr_pct: 20,
              effective_far_pct: 50,
              ordinance_confirmed: true,
            },
          },
        }}
      />,
    );

    expect(screen.getByText("조례 용적률 (지자체)")).toBeInTheDocument();
    expect(screen.getAllByText("50.0%").length).toBeGreaterThan(0);
    expect(screen.queryByText("확인 필요")).not.toBeInTheDocument();
  });
});
