/**
 * ★배선 층 — 선택 무결성 고지가 **실제 컴포넌트에서** 뜨는가.
 *
 * 순수 판정은 `lib/__tests__/selection-integrity.test.ts` 가 잠근다. 여기서 잠그는 것은
 * **배선**이다: 판정은 맞는데 화면에 안 붙으면 사용자에게는 아무 일도 일어나지 않는다
 * (같은 세션에서 "순수 함수만 잠갔더니 변이 생존이 전부 배선"이 이미 두 번 났다).
 *
 * 픽스처는 라이브 오염(`4f8a6db5` 제천 성내리+모산동 15.86km)을 그대로 쓴다.
 *
 * ★**의도적 미잠금**(변이 생존이 정상인 것 — 점수 부풀리기 방지를 위해 적어 둔다):
 *   · 배너의 `className` 문자열(테두리·배경·아이콘 크기) — 디자인 토큰 변경을 테스트가
 *     막으면 안 된다. 잠그는 것은 **tone 분기**(bad/warn)와 **문구**이지 색이 아니다.
 *   · `SelectionVerdict` 유니온 리터럴(`"single_site"` 등) — vitest 로는 생존하지만
 *     **`tsc` 가 잡는다**(실측: 리터럴 하나를 바꾸니 TS2820·TS2367 두 건). CI 는 같은 잡에서
 *     `tsc` 를 돌리므로 잠겨 있다. ★면역을 추정하지 않고 직접 주입해 확인했다(규율 C11).
 */
import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SatongMapShell } from "@/components/precheck/SatongMapShell";
import { useProjectContextStore, type SiteAnalysisData } from "@/store/useProjectContextStore";
import { useProjectStore, type Project } from "@/store/useProjectStore";

// ★계측 통로를 목으로 가로챈다 — 테스트가 실제 네트워크를 태우지 않도록.
//   `trackEvent` 만 갈아 끼우고 나머지(타입·상수)는 원본을 쓴다.
const trackEventMock = vi.hoisted(() => vi.fn());
vi.mock("@/lib/growth/event-collector", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/growth/event-collector")>()),
  trackEvent: trackEventMock,
}));

vi.mock("next/navigation", () => ({
  useParams: () => ({ locale: "ko" }),
  usePathname: () => "/ko/precheck",
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn(), prefetch: vi.fn() }),
}));

vi.mock("next/dynamic", () => ({
  default: () => {
    const DynamicStub = () => <div data-testid="dynamic-map-stub" />;
    return DynamicStub;
  },
}));

vi.mock("@/lib/api-client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api-client")>();
  const pending = () => new Promise<never>(() => {});
  return {
    ...actual,
    apiClient: {
      ...actual.apiClient,
      request: vi.fn(pending), get: vi.fn(pending), post: vi.fn(pending),
      put: vi.fn(pending), patch: vi.fn(pending), delete: vi.fn(pending),
      getV2: vi.fn(pending), postV2: vi.fn(pending), putV2: vi.fn(pending), deleteV2: vi.fn(pending),
    },
  };
});

const PROJECT_ID = "proj-integrity";

function seed(parcels: Array<Record<string, unknown>>) {
  act(() => {
    useProjectStore.setState({
      projects: [
        {
          id: PROJECT_ID, name: "무결성 픽스처", type: "residential", pnu: "",
          address: "충청북도 제천시 금성면 성내리 산 7-1", area: "", status: "draft",
          createdAt: "2026-08-21T00:00:00.000Z",
        } as Project,
      ],
      syncing: false,
    });
    useProjectContextStore.setState({
      projectId: PROJECT_ID,
      projectName: "무결성 픽스처",
      projectStatus: "draft",
      siteAnalysis: {
        estimatedValue: null,
        address: "충청북도 제천시 금성면 성내리 산 7-1",
        pnu: "4315031022200070001",
        zoneCode: "보전관리지역",
        parcelCount: parcels.length,
        parcels,
      } as unknown as SiteAnalysisData,
    } as never);
  });
}

/** `4f8a6db5` 실측 — 성내리 3 + 모산동 3, **같은 제천시인데 15.86km**. */
const MIXED = [
  { pnu: "4315031022200070001", address: "충청북도 제천시 금성면 성내리 산 7-1", areaSqm: 326, landCategory: "임야", ownerType: "", zoneCode: "보전관리지역", lat: 37.036774796729205, lon: 128.17091456609188 },
  { pnu: "4315031022200070002", address: "충청북도 제천시 금성면 성내리 산 7-2", areaSqm: 423, landCategory: "임야", ownerType: "", zoneCode: "보전관리지역", lat: 37.03679040853061, lon: 128.1712281568772 },
  { pnu: "4315011400101230001", address: "충청북도 제천시 모산동 123-1", areaSqm: 3836, landCategory: "임야", ownerType: "", zoneCode: "자연녹지지역", lat: 37.1766866945329, lon: 128.20540025944734 },
];

/** 정상 — 같은 동 인접 3필지(위양성 대조군). */
const NORMAL = [
  { pnu: "4315031022200070001", address: "충청북도 제천시 금성면 성내리 산 7-1", areaSqm: 326, landCategory: "임야", ownerType: "", zoneCode: "보전관리지역", lat: 37.036774796729205, lon: 128.17091456609188 },
  { pnu: "4315031022200070002", address: "충청북도 제천시 금성면 성내리 산 7-2", areaSqm: 423, landCategory: "임야", ownerType: "", zoneCode: "보전관리지역", lat: 37.03679040853061, lon: 128.1712281568772 },
  { pnu: "4315031022200070003", address: "충청북도 제천시 금성면 성내리 산 7-3", areaSqm: 456, landCategory: "임야", ownerType: "", zoneCode: "보전관리지역", lat: 37.036831606395424, lon: 128.17239949810647 },
];

/** `ad66982a` 실측 — 소유자명이 주소 칸에(★좌표 전무). */
const MALFORMED = [
  { pnu: "", address: "◀ 전성결", areaSqm: 0, landCategory: "", ownerType: "", zoneCode: null },
  { pnu: "4146510300106890000", address: "경기도 용인시 수지구 고기동 689", areaSqm: 372, landCategory: "임야", ownerType: "", zoneCode: "자연녹지지역" },
];

describe("★배선 — 선택 무결성 고지가 실제 화면에 뜬다", () => {
  beforeEach(() => window.sessionStorage.clear());
  afterEach(() => {
    window.sessionStorage.clear();
    act(() => {
      useProjectStore.setState({ projects: [], syncing: false });
      useProjectContextStore.setState({ projectId: null, projectName: "", projectStatus: "", siteAnalysis: null } as never);
    });
  });

  it("A) 15.86km 혼합이면 '하나의 개발 부지가 아닙니다'를 고지한다", () => {
    seed(MIXED);
    render(<SatongMapShell locale="ko" />);

    // 공허 진리 가드 — 선택이 실제로 하이드레이션돼야 판정이 의미를 가진다.
    expect(screen.getByText(/필지 선택 3건/)).toBeInTheDocument();

    const notice = screen.getByTestId("selection-integrity-notice");
    expect(notice).toBeInTheDocument();
    // ★스크린리더 고지 계약 — `role="status"` 가 없으면 보이는 사람에게만 고지된다.
    //   변이(그 줄 삭제)가 생존해 추가했다: testid 로만 찾으면 접근성 배선이 무잠금이 된다.
    expect(notice).toHaveAttribute("role", "status");
    expect(notice.textContent).toContain("하나의 개발 부지가 아닙니다");
    expect(notice.textContent).toContain("통합 대지면적이 아니며");
    expect(notice.textContent).toMatch(/최대 15\.\d+km/); // 실측 거리가 화면에 실린다
  });

  it("★B) 위양성 방지 — 같은 동 인접 필지면 고지하지 않는다", () => {
    seed(NORMAL);
    render(<SatongMapShell locale="ko" />);
    expect(screen.getByText(/필지 선택 3건/)).toBeInTheDocument(); // 대상 존재 가드
    expect(screen.queryByTestId("selection-integrity-notice")).not.toBeInTheDocument();
  });

  it("C) 소유자명이 주소 칸에 있으면 그 사실을 원문과 함께 고지한다", () => {
    seed(MALFORMED);
    render(<SatongMapShell locale="ko" />);
    expect(screen.getByText(/필지 선택 2건/)).toBeInTheDocument();

    const notice = screen.getByTestId("selection-integrity-notice");
    expect(notice.textContent).toContain("주소가 아닌 값");
    expect(notice.textContent).toContain("◀ 전성결");
    expect(notice.textContent).toContain("소유자");
  });

  // ★부채 상환(2026-08-24) — 위 `it.todo` 를 실제 잠금으로 바꾼다.
  //   ★그리고 그 부채의 **사유가 거짓이었다**: *"프론트에 클라이언트 계측 헬퍼가 없다
  //     (실측: lib/** 에 recordEvent/captureEvent 계열 0건)"* 라고 적혀 있었는데,
  //     `lib/growth/event-collector.ts` 의 `trackEvent` 가 **이미 있었고** `api-client` 에
  //     배선까지 돼 있었다. 틀린 이름으로만 찾은 것이다 — **"0건은 부재가 아니다."**
  //     부채 메모의 *사유*는 *사실*보다 빨리 낡는다. 물려받기 전에 다시 재라.
  it("D) ★관측 — 오염이면 selection_contamination_observation 이 적재된다", () => {
    trackEventMock.mockClear();
    seed(MIXED);
    render(<SatongMapShell locale="ko" />);
    expect(screen.getByText(/필지 선택 3건/)).toBeInTheDocument(); // 대상 존재 가드

    const calls = trackEventMock.mock.calls.filter(
      ([type]) => type === "selection_contamination_observation",
    );
    expect(calls.length, "관측이 한 건도 적재되지 않았다").toBe(1);
    const [, props] = calls[0];
    expect(props.service).toBe("precheck.selection-integrity");
    expect(props.payload).toMatchObject({ verdict: "multi_region", region_groups: 2 });
    // 실측 거리가 그대로 실린다(화면 문구와 같은 사실을 계측도 본다).
    expect(props.payload.spread_km).toBeGreaterThan(15);
  });

  it("★E) 위양성 방지 — 정상 선택은 관측을 적재하지 않는다(대조군)", () => {
    trackEventMock.mockClear();
    seed(NORMAL);
    render(<SatongMapShell locale="ko" />);
    expect(screen.getByText(/필지 선택 3건/)).toBeInTheDocument();
    expect(
      trackEventMock.mock.calls.filter(
        ([type]) => type === "selection_contamination_observation",
      ),
    ).toHaveLength(0);
  });
});
