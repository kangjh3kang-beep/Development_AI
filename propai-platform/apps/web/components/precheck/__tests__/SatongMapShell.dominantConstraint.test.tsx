/**
 * SatongMapShell — 지배 제약 배너 배선(W1) 관통 테스트.
 *
 * ★왜 순수함수 테스트로 부족한가(2026-07-30 회고): 직전 세션에 "순수함수만 초록이고 배선을
 *   되돌리면 그대로 통과"한 사례가 4번 있었다. 배너 컴포넌트와 서버 산식이 전부 초록이어도
 *   `openFeatureDetail`이 값을 합류시키지 않으면 화면엔 아무것도 안 나온다. 그래서 여기서
 *   **두 사용자 경로**를 실제로 태운다:
 *     ① 지도 폴리곤 클릭 (onFeatureClick — 피처가 지배 제약을 직접 보유)
 *     ② 좌측 필지 카드 클릭 (선택 SSOT 유래 피처 — 경계 응답 캐시에서 합류돼야 한다)
 *   ②가 이 배선의 취약점이다: 카드 경로 피처엔 dominantConstraint가 없으므로, 합류를
 *   빼먹으면 "지도를 누르면 보이는데 카드를 누르면 안 보이는" 발산이 조용히 생긴다.
 */
import { useEffect, type ReactNode } from "react";
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SatongMapShell } from "@/components/precheck/SatongMapShell";
import { writeSatongMapSelection } from "@/components/precheck/satong-map-selection";
import type { DominantConstraint, SatongMapFeature } from "@/lib/satong-map-layers";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { useProjectStore } from "@/store/useProjectStore";

vi.mock("next/navigation", () => ({
  useParams: () => ({ locale: "ko" }),
  usePathname: () => "/ko/precheck",
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    back: vi.fn(),
    prefetch: vi.fn(),
  }),
}));

/** 지도 스텁이 마지막으로 받은 콜백들 — 테스트가 실제 소비 경로를 호출하기 위한 창구. */
const mapProps: {
  onFeatureClick?: (f: SatongMapFeature) => void;
  onBoundaryEnriched?: (f: SatongMapFeature[]) => void;
} = {};

vi.mock("next/dynamic", () => ({
  default: () => {
    const DynamicStub = (props: {
      topRightSlot?: ReactNode;
      onFeatureClick?: (f: SatongMapFeature) => void;
      onBoundaryEnriched?: (f: SatongMapFeature[]) => void;
    }) => {
      // 콜백 캡처는 effect에서 한다(렌더 중 외부 변수 수정 금지 — react-hooks 규칙).
      useEffect(() => {
        mapProps.onFeatureClick = props.onFeatureClick;
        mapProps.onBoundaryEnriched = props.onBoundaryEnriched;
      });
      // 실컴포넌트와 동일하게 셸 오버레이(=필지 상세 패널)를 지도 래퍼 안에서 렌더한다.
      return <div data-testid="dynamic-map-stub">{props.topRightSlot}</div>;
    };
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

const ADDRESS = "경상북도 포항시 남구 호미곶면 대보리 산1-1";
const PNU = "4711025029000010001";

const HOMIGOT: DominantConstraint = {
  headline: "군사시설보호구역(통제보호구역) — 군부대 협의 없이는 건축 불가",
  severity: "높음",
  ranked: [
    { name: "군사시설보호구역(통제보호구역)", severity: "높음", action: "군부대 협의" },
    { name: "비행안전구역(제6구역)", severity: "보통", action: "고도 협의" },
  ],
  height: {
    governing_m: null,
    governing_source: null,
    incomplete: true,
    items: [
      {
        source: "비행안전구역(제6구역)",
        limit_m: null,
        note: "지정됨 — 수치는 조례 확인 필요(플랫폼 미보유)",
      },
    ],
  },
};

function resetStores() {
  act(() => {
    useProjectStore.setState({ projects: [], syncing: false });
    useProjectContextStore.setState({
      projectId: null,
      projectName: "",
      projectStatus: "",
      siteAnalysis: null,
    });
  });
}

function seedSelection() {
  writeSatongMapSelection([
    { id: "P-homigot", address: ADDRESS, pnu: PNU, source: "map", areaSqm: 147078, zoneType: "보전관리지역", jimok: "임야" },
  ]);
}

describe("SatongMapShell 지배 제약 배너 배선(W1)", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
    resetStores();
    mapProps.onFeatureClick = undefined;
    mapProps.onBoundaryEnriched = undefined;
  });

  afterEach(() => {
    window.sessionStorage.clear();
    resetStores();
  });

  it("① 지도 폴리곤 클릭 → 배너 표시(headline·일부 미반영 배지)", () => {
    seedSelection();
    render(<SatongMapShell locale="ko" />);

    act(() => {
      mapProps.onFeatureClick?.({
        id: "F-1",
        address: ADDRESS,
        pnu: PNU,
        dominantConstraint: HOMIGOT,
      });
    });

    const panel = screen.getByTestId("parcel-detail-panel");
    expect(within(panel).getByTestId("dominant-constraint-headline").textContent).toContain(
      "통제보호구역",
    );
    expect(
      within(panel).getByTestId("dominant-constraint-height-incomplete"),
    ).toBeInTheDocument();
  });

  it("★② 좌측 카드 클릭 → 경계 응답에서 받은 지배 제약이 합류돼 배너가 뜬다", () => {
    seedSelection();
    render(<SatongMapShell locale="ko" />);

    // 카드 경로 피처(선택 SSOT 유래)엔 dominantConstraint가 없다 — 합류 전에는 배너가 없다.
    fireEvent.click(screen.getByText("대보리 산1-1"));
    expect(screen.queryByTestId("dominant-constraint-banner")).not.toBeInTheDocument();

    // 경계 응답 도착(지도 내부 → onBoundaryEnriched 역전파)
    act(() => {
      mapProps.onBoundaryEnriched?.([
        {
          id: "B-1",
          address: ADDRESS,
          pnu: PNU,
          areaSqm: 147078,
          dominantConstraint: HOMIGOT,
        },
      ]);
    });

    // 다시 카드를 눌러 상세를 열면(같은 필지) 배너가 합류돼 있어야 한다.
    fireEvent.click(within(screen.getByTestId("parcel-detail-panel")).getByRole("button", { name: "필지 상세 닫기" }));
    fireEvent.click(screen.getByText("대보리 산1-1"));

    const panel = screen.getByTestId("parcel-detail-panel");
    expect(within(panel).getByTestId("dominant-constraint-headline").textContent).toContain(
      "통제보호구역",
    );
  });

  it("★④ R1 M-4: 패널이 열린 채로 경계 응답이 도착하면 배너가 즉시 합류한다", () => {
    // 실제 흐름: 필지를 담고 곧바로 카드를 누른다 → 경계 왕복(최대 45s)이 그 뒤에 끝난다.
    //   ref 갱신은 렌더를 유발하지 않으므로, 합류가 없으면 닫고 다시 열 때까지 배너를 못 본다.
    seedSelection();
    render(<SatongMapShell locale="ko" />);

    fireEvent.click(screen.getByText("대보리 산1-1"));
    expect(screen.getByTestId("parcel-detail-panel")).toBeInTheDocument();
    expect(screen.queryByTestId("dominant-constraint-banner")).not.toBeInTheDocument();

    act(() => {
      mapProps.onBoundaryEnriched?.([
        { id: "B-1", address: ADDRESS, pnu: PNU, areaSqm: 147078, dominantConstraint: HOMIGOT },
      ]);
    });

    // ★닫고 다시 열지 않는다 — 열린 패널이 그대로 갱신되어야 한다.
    const panel = screen.getByTestId("parcel-detail-panel");
    expect(within(panel).getByTestId("dominant-constraint-headline").textContent).toContain(
      "통제보호구역",
    );
  });

  it("★⑤ R1 M-3: 셸 재마운트(소프트 내비 왕복) 후에도 배너가 살아남는다", () => {
    seedSelection();
    const first = render(<SatongMapShell locale="ko" />);

    act(() => {
      mapProps.onBoundaryEnriched?.([
        { id: "B-1", address: ADDRESS, pnu: PNU, areaSqm: 147078, dominantConstraint: HOMIGOT },
      ]);
    });
    first.unmount();

    // 산출물 페이지 왕복 후 복귀 = 새 인스턴스. geometry·연식 보유 선택이면 경계 재조회도
    //   스킵되므로, 뷰 캐시가 세션에 남아 있지 않으면 배너가 영구 소실된다.
    render(<SatongMapShell locale="ko" />);
    fireEvent.click(screen.getByText("대보리 산1-1"));

    const panel = screen.getByTestId("parcel-detail-panel");
    expect(within(panel).getByTestId("dominant-constraint-headline").textContent).toContain(
      "통제보호구역",
    );
  });

  it("★⑥ R1 LOW-9: pnu 미확보 필지(주소 키)도 캐시가 적중한다", () => {
    // 엑셀·지오코딩 시드는 pnu 없이 들어오고 id는 클라이언트 합성값("P-…")이다.
    //   저장/조회 키가 비대칭이면(조회가 id로 잡히면) 캐시 미스로 배너가 안 뜬다.
    writeSatongMapSelection([
      { id: "P-noPnu", address: ADDRESS, source: "excel", areaSqm: 147078 },
    ]);
    render(<SatongMapShell locale="ko" />);

    act(() => {
      mapProps.onBoundaryEnriched?.([
        { id: "B-noPnu", address: ADDRESS, pnu: null, dominantConstraint: HOMIGOT },
      ]);
    });
    fireEvent.click(screen.getByText("대보리 산1-1"));

    const panel = screen.getByTestId("parcel-detail-panel");
    expect(within(panel).getByTestId("dominant-constraint-headline").textContent).toContain(
      "통제보호구역",
    );
  });

  it("③ 제약 없는 필지는 배너를 렌더하지 않는다(빈 배너 금지)", () => {
    writeSatongMapSelection([
      { id: "P-clean", address: "경기도 성남시 분당구 판교동 100", pnu: "PNU-CLEAN", source: "map", areaSqm: 800 },
    ]);
    render(<SatongMapShell locale="ko" />);

    // 서버가 제약 0건이면 dominant_constraint=null을 보낸다 → 그대로 역전파해도 배너 없음.
    act(() => {
      mapProps.onBoundaryEnriched?.([
        { id: "B-clean", address: "경기도 성남시 분당구 판교동 100", pnu: "PNU-CLEAN", dominantConstraint: null },
      ]);
    });
    fireEvent.click(screen.getByText("판교동 100"));

    expect(screen.getByTestId("parcel-detail-panel")).toBeInTheDocument();
    expect(screen.queryByTestId("dominant-constraint-banner")).not.toBeInTheDocument();
  });
});
