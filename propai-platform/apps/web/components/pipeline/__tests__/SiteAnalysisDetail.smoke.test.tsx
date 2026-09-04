/**
 * SiteAnalysisDetail 스모크(W3-2) — "크래시 없이 마운트 + 핵심 랜드마크 존재"만 확인.
 * 깊은 동작(지도 렌더·필지 조회)은 검증하지 않는다. 지도는 dynamicMap(next/dynamic)
 * 기반이라 jsdom에서 Leaflet을 실로드할 수 없어 스텁으로 대체한다.
 */
import { fireEvent, render, screen } from "@testing-library/react";
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

// ── 규제구역 저촉상태 표시 회귀앵커(2026-08-20 라이브 실측) ──
// 라이브 재현(오산 내삼미동 741 · 실계정 POST /api/v1/zoning/comprehensive):
// `land_use_plan.districts` 11건에 `conflict_status` 가 **3종**으로 실려 있었다 —
// 포함 7 · 접함 3 · 저촉 1. 그런데 화면은 `district_name` 만 뽑아 **11건을 모두 같은
// 경고 점으로** 나열했다. 그 결과 단지 **접함**(경계 인접)인 공원·보전녹지가 필지를
// **포함**하는 도로구역과 구분되지 않았다 — 개발자에게 그 차이는 사업 성립 여부를 가른다.
// ★백엔드는 `conflict_status` 를 계속 내보내고 있었고 **화면만 버리고 있었다**(소비처 0).
describe("규제구역 저촉상태 표시", () => {
  // ★"규제 사항" 카드는 `CategoryCard` 의 `defaultOpen=false` 라 **닫힌 상태로 마운트**되고
  //   `{open && ...}` 이므로 내용이 **DOM 에 아예 없다.** 열지 않고 단언하면 무엇을 넣든
  //   "못 찾음"으로 실패하거나(여기) 반대로 "위반 0"이 공허하게 참이 된다.
  //   → 상태를 만들어서 검사한다(CLAUDE.md §회귀망 A.1).
  const openRegulations = (container: HTMLElement) => {
    const head = screen.getByText("규제 사항").closest("button");
    expect(head).not.toBeNull();
    fireEvent.click(head as HTMLElement);
    // ★공허 진리 가드 — 실제로 열렸는지 먼저 단언한다. 안 열렸으면 아래는 의미가 없다.
    expect(head).toHaveAttribute("aria-expanded", "true");
    return container;
  };

  const districtsData = {
    basic: { address: "경기도 오산시 내삼미동 741", land_area_sqm: 1015 },
    regulations: {
      land_use_plan: {
        districts: [
          { district_name: "도로구역", conflict_status: "포함" },
          { district_name: "공원", conflict_status: "접함" },
          { district_name: "교통광장", conflict_status: "저촉" },
        ],
      },
    },
  };

  it("구역 이름과 함께 저촉상태(포함/저촉/접함)를 보인다", () => {
    const { container } = render(<SiteAnalysisDetail data={districtsData} />);
    openRegulations(container);
    // ★이름만 단언하면 종전 코드도 통과한다 — 상태가 화면에 있는지가 이 테스트의 본체다.
    expect(screen.getByText("도로구역")).toBeInTheDocument();
    expect(screen.getByText("포함")).toBeInTheDocument();
    expect(screen.getByText("저촉")).toBeInTheDocument();
    expect(screen.getByText("접함")).toBeInTheDocument();
  });

  it("접함(경계 인접)은 경고 점을 낮추고, 포함·저촉은 경고로 남긴다", () => {
    const { container } = render(<SiteAnalysisDetail data={districtsData} />);
    openRegulations(container);
    // ★양성 대조군 — 점이 하나도 없으면 아래 단언이 공허하게 참이 된다.
    expect(container.querySelectorAll(".sa-dot").length).toBeGreaterThanOrEqual(3);
    expect(container.querySelectorAll(".sa-dot--muted").length).toBeGreaterThanOrEqual(1);
    expect(container.querySelectorAll(".sa-dot--warning").length).toBeGreaterThanOrEqual(2);
  });

  it("상태가 없으면 경고를 낮추지 않는다(모르는 값을 안전하게 다룬다)", () => {
    // ★새 상태값이 생기거나 필드가 비어도 경고가 **조용히 사라지면 안 된다**.
    const { container } = render(
      <SiteAnalysisDetail
        data={{
          basic: { address: "테스트", land_area_sqm: 100 },
          regulations: { land_use_plan: { districts: [{ district_name: "미상구역" }] } },
        }}
      />,
    );
    openRegulations(container);
    expect(screen.getByText("미상구역")).toBeInTheDocument();
    expect(container.querySelectorAll(".sa-dot--warning").length).toBeGreaterThanOrEqual(1);
    expect(container.querySelectorAll(".sa-dot--muted").length).toBe(0);
  });
});
