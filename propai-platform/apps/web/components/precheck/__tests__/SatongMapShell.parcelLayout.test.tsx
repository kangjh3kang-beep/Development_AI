/**
 * SatongMapShell — 배치 미리보기 온디맨드 배선(W3) 관통 테스트.
 *
 * ★순수함수(lib/site-layout)와 패널 표시만으로는 부족하다: 셸이 조회를 붙이지 않으면 버튼만
 *   남고, **지도에 오버레이를 넘기지 않으면 핵심 기능(지도 위 배치)이 통째로 없다**.
 *   그래서 ①실제 호출 ②지도 prop 전달 ③대안 전환이 오버레이를 바꾸는지 ④가드 3종
 *   ⑤계정격리를 전부 관통 검증한다.
 */
import { useEffect, type ReactNode } from "react";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SatongMapShell } from "@/components/precheck/SatongMapShell";
import {
  SATONG_SITE_LAYOUT_KEY,
  readSatongViewCache,
  writeSatongViewCache,
  writeSatongMapSelection,
} from "@/components/precheck/satong-map-selection";
import { clearOnLogout } from "@/lib/projectSync";
import type { SiteLayoutOverlay, SiteLayoutResult } from "@/lib/site-layout";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { useProjectStore } from "@/store/useProjectStore";

vi.mock("next/navigation", () => ({
  useParams: () => ({ locale: "ko" }),
  usePathname: () => "/ko/precheck",
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn(), prefetch: vi.fn() }),
}));

/** 지도 스텁이 마지막으로 받은 layoutOverlay — "지도에 실제로 넘어갔나"를 본다. */
const mapProps: { layoutOverlay?: SiteLayoutOverlay | null } = {};

vi.mock("next/dynamic", () => ({
  default: () => {
    const DynamicStub = (props: {
      topRightSlot?: ReactNode;
      layoutOverlay?: SiteLayoutOverlay | null;
    }) => {
      useEffect(() => {
        mapProps.layoutOverlay = props.layoutOverlay ?? null;
      });
      return <div data-testid="dynamic-map-stub">{props.topRightSlot}</div>;
    };
    return DynamicStub;
  },
}));

const layout = {
  calls: [] as Array<Record<string, unknown>>,
  resolve: null as ((v: SiteLayoutResult) => void) | null,
  reject: null as ((e: unknown) => void) | null,
};

vi.mock("@/lib/api-client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api-client")>();
  const pending = () => new Promise<never>(() => {});
  return {
    ...actual,
    apiClient: {
      ...actual.apiClient,
      request: vi.fn(pending), get: vi.fn(pending), put: vi.fn(pending),
      patch: vi.fn(pending), delete: vi.fn(pending), getV2: vi.fn(pending),
      postV2: vi.fn(pending), putV2: vi.fn(pending), deleteV2: vi.fn(pending),
      post: vi.fn((path: string, opts?: { body?: Record<string, unknown> }) => {
        if (path !== "/analysis/site-layout") return pending();
        layout.calls.push(opts?.body ?? {});
        return new Promise<SiteLayoutResult>((res, rej) => {
          layout.resolve = res;
          layout.reject = rej;
        });
      }),
    },
  };
});

const ADDR_A = "경상북도 포항시 남구 호미곶면 대보리 산1-1";
const PNU_A = "4711025029000010001";
const ADDR_B = "경상북도 포항시 남구 호미곶면 대보리 산2-2";
const GEOM = {
  type: "Polygon",
  coordinates: [[[129.56, 36.07], [129.5604, 36.07], [129.5604, 36.0703], [129.56, 36.0703], [129.56, 36.07]]],
};

const OPT = (kind: string, angle: number) => ({
  kind, angle_deg: angle, buildings: 3, floors: 5, height_m: 15,
  spacing_meaningful: true, spacing_m: 12, total_units_est: 24,
  yield_pct: 72, openness_pct: 61,
  daylight: { meets_sunlight: true, direct_sun_hours: 5.2 },
  buildings_geojson: {
    type: "FeatureCollection" as const,
    features: [{ type: "Feature" as const, properties: { dong: 1, floors: 5 }, geometry: { type: "Polygon", coordinates: [[[129.561, 36.0701], [129.5612, 36.0701], [129.5612, 36.0702], [129.561, 36.0702], [129.561, 36.0701]]] } }],
  },
});

const RESULT_OK: SiteLayoutResult = {
  ok: true,
  honest_notes: ["v1 한계: 축정렬 직사각형 동·균일 세트백·동지 일조 근사. 부정형 정밀배치·3D 음영은 후속."],
  buildable_geojson: { type: "Polygon", coordinates: [[[129.5601, 36.0701], [129.5603, 36.0701], [129.5603, 36.0702], [129.5601, 36.0702], [129.5601, 36.0701]]] },
  buildable_area_sqm: 820,
  setback_m: 3,
  options: [OPT("판상형", 0), OPT("탑상형", 0)],
  best: OPT("판상형", 0),
};

function resetStores() {
  act(() => {
    useProjectStore.setState({ projects: [], syncing: false });
    useProjectContextStore.setState({ projectId: null, projectName: "", projectStatus: "", siteAnalysis: null });
  });
}

function seed() {
  writeSatongMapSelection([
    { id: "P-a", address: ADDR_A, pnu: PNU_A, source: "map", areaSqm: 1000, zoneType: "제2종일반주거지역", jimok: "대", geometry: GEOM },
    { id: "P-b", address: ADDR_B, pnu: "4711025029000020002", source: "map", areaSqm: 800, zoneType: "제2종일반주거지역", jimok: "대", geometry: GEOM },
  ]);
}

describe("SatongMapShell 배치 미리보기 배선(W3)", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
    resetStores();
    layout.calls = [];
    layout.resolve = null;
    layout.reject = null;
    mapProps.layoutOverlay = null;
  });

  afterEach(() => {
    window.sessionStorage.clear();
    resetStores();
  });

  it("① 상세를 열면 '미조회'이고, 버튼을 눌러야 조회가 나간다(자동 조회 금지)", () => {
    seed();
    render(<SatongMapShell locale="ko" />);
    fireEvent.click(screen.getByText("대보리 산1-1"));

    const panel = screen.getByTestId("parcel-detail-panel");
    expect(within(panel).getByTestId("parcel-layout-section")).toBeInTheDocument();
    expect(layout.calls).toHaveLength(0);

    fireEvent.click(within(panel).getByTestId("parcel-layout-request"));
    expect(layout.calls).toHaveLength(1);
    // 지도가 이미 가진 기하를 그대로 넘긴다(서버 재조회 회피).
    expect(layout.calls[0].parcel_geojson).toEqual(GEOM);
    expect(layout.calls[0].pnu).toBe(PNU_A);
  });

  it("★② 지도에 오버레이가 실제로 전달된다 — 이게 없으면 W3의 핵심이 통째로 없다", async () => {
    seed();
    render(<SatongMapShell locale="ko" />);
    fireEvent.click(screen.getByText("대보리 산1-1"));
    fireEvent.click(screen.getByTestId("parcel-layout-request"));
    expect(mapProps.layoutOverlay).toBeNull(); // 조회 전엔 오버레이 없음

    await act(async () => {
      layout.resolve?.(RESULT_OK);
    });

    expect(mapProps.layoutOverlay).not.toBeNull();
    expect(mapProps.layoutOverlay!.buildable).toBe(RESULT_OK.buildable_geojson);
    expect(mapProps.layoutOverlay!.buildings).toBe(RESULT_OK.options![0].buildings_geojson);
    // 패널 수치도 함께 표시된다.
    expect(screen.getByTestId("parcel-layout-buildings").textContent).toBe("3동");
    expect(screen.getByTestId("parcel-layout-notes").textContent).toContain("v1 한계");
  });

  it("★③ 대안 전환이 지도 오버레이를 바꾼다(이전 대안 잔존 금지)", async () => {
    seed();
    render(<SatongMapShell locale="ko" />);
    fireEvent.click(screen.getByText("대보리 산1-1"));
    fireEvent.click(screen.getByTestId("parcel-layout-request"));
    await act(async () => {
      layout.resolve?.(RESULT_OK);
    });
    const first = mapProps.layoutOverlay!.buildings;

    await act(async () => {
      screen.getByTestId("parcel-layout-option-탑상형@0").click();
    });

    expect(mapProps.layoutOverlay!.buildings).not.toBe(first);
    expect(mapProps.layoutOverlay!.buildings).toBe(RESULT_OK.options![1].buildings_geojson);
  });

  it("★④ ok:false — 지도에 아무것도 그리지 않고 서버 사유를 그대로 고지한다(가짜 배치 금지)", async () => {
    seed();
    render(<SatongMapShell locale="ko" />);
    fireEvent.click(screen.getByText("대보리 산1-1"));
    fireEvent.click(screen.getByTestId("parcel-layout-request"));

    // ★백엔드 실제 실패형태: ok=bool(options)이고 buildable_geojson은 항상 온다 →
    //   기하가 있는 ok:false로 가드를 관통시킨다(기하 없는 픽스처는 가드를 무의미하게 만든다).
    const reason = "세트백 적용 후 건축가능 영역에 표준 동이 들어가지 않습니다.";
    await act(async () => {
      layout.resolve?.({
        ok: false,
        honest_notes: [reason],
        buildable_geojson: RESULT_OK.buildable_geojson,
        buildable_area_sqm: 40,
        setback_m: 3,
        options: [],
        best: null,
      });
    });

    expect(mapProps.layoutOverlay).toBeNull();
    const unavailable = screen.getByTestId("parcel-layout-unavailable");
    expect(unavailable.textContent).toContain("임의 배치를 만들지 않습니다");
    expect(unavailable.textContent).toContain(reason);
    expect(screen.queryByTestId("parcel-layout-buildings")).not.toBeInTheDocument();
  });

  it("★⑤ 인플라이트 1건(전역) — 연타·다른 필지 모두 중복 호출을 만들지 않는다", async () => {
    seed();
    render(<SatongMapShell locale="ko" />);
    fireEvent.click(screen.getByText("대보리 산1-1"));
    const btn = screen.getByTestId("parcel-layout-request");
    // 한 batch 안에서 연타(fireEvent는 매 호출 flush → 버튼 언마운트로 가드에 못 닿는다)
    await act(async () => {
      btn.click(); btn.click(); btn.click();
    });
    expect(layout.calls).toHaveLength(1);

    // 다른 필지로 가서 눌러도 전역 잠금이라 나가지 않는다.
    fireEvent.click(screen.getByText("대보리 산2-2"));
    expect(screen.getByTestId("parcel-layout-busy-other")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("parcel-layout-request"));
    expect(layout.calls).toHaveLength(1);

    await act(async () => {
      layout.resolve?.(RESULT_OK);
    });
    expect(screen.queryByTestId("parcel-layout-busy-other")).not.toBeInTheDocument();
  });

  it("★⑥ 세션 캐시 — 같은 필지 재방문은 재조회 없이 즉시 표시", async () => {
    seed();
    render(<SatongMapShell locale="ko" />);
    fireEvent.click(screen.getByText("대보리 산1-1"));
    fireEvent.click(screen.getByTestId("parcel-layout-request"));
    await act(async () => {
      layout.resolve?.(RESULT_OK);
    });
    expect(layout.calls).toHaveLength(1);

    fireEvent.click(screen.getByText("대보리 산2-2"));
    fireEvent.click(screen.getByText("대보리 산1-1"));

    expect(layout.calls).toHaveLength(1);
    expect(screen.getByTestId("parcel-layout-buildings").textContent).toBe("3동");
  });

  it("★⑦ ok:false는 캐시하지 않는다 — '다시 조회'가 실제로 재요청을 보낸다", async () => {
    seed();
    render(<SatongMapShell locale="ko" />);
    fireEvent.click(screen.getByText("대보리 산1-1"));
    fireEvent.click(screen.getByTestId("parcel-layout-request"));
    await act(async () => {
      layout.resolve?.({ ok: false, honest_notes: ["사유"], options: [], best: null });
    });

    fireEvent.click(screen.getByText("대보리 산2-2"));
    fireEvent.click(screen.getByText("대보리 산1-1"));
    // 실패는 캐시되지 않아 미조회로 돌아간다.
    expect(screen.getByTestId("parcel-layout-request")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("parcel-layout-request"));
    expect(layout.calls).toHaveLength(2);
  });

  it("⑧ 스테일 가드 — 조회 중 다른 필지로 옮기면 남의 배치가 붙지 않는다", async () => {
    seed();
    render(<SatongMapShell locale="ko" />);
    fireEvent.click(screen.getByText("대보리 산1-1"));
    fireEvent.click(screen.getByTestId("parcel-layout-request"));

    fireEvent.click(screen.getByText("대보리 산2-2"));
    await act(async () => {
      layout.resolve?.(RESULT_OK);
    });

    expect(screen.queryByTestId("parcel-layout-buildings")).not.toBeInTheDocument();
    expect(mapProps.layoutOverlay).toBeNull();
  });

  it("⑨ 네트워크 예외 — 실패 표기 + 재조회 가능(잠금 해제)", async () => {
    seed();
    render(<SatongMapShell locale="ko" />);
    fireEvent.click(screen.getByText("대보리 산1-1"));
    fireEvent.click(screen.getByTestId("parcel-layout-request"));
    await act(async () => {
      layout.reject?.(new Error("boom"));
    });
    await waitFor(() => expect(screen.getByTestId("parcel-layout-error")).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: "다시 조회" }));
    expect(layout.calls).toHaveLength(2);
  });

  it("★⑩ 계정 격리 — 로그아웃 와이프가 배치 뷰 캐시를 지운다", () => {
    writeSatongViewCache<SiteLayoutResult>(
      SATONG_SITE_LAYOUT_KEY, new Map([["PNU-PREV", RESULT_OK]]),
    );
    expect(window.sessionStorage.getItem(SATONG_SITE_LAYOUT_KEY)).not.toBeNull();

    clearOnLogout();

    expect(window.sessionStorage.getItem(SATONG_SITE_LAYOUT_KEY)).toBeNull();
    expect(readSatongViewCache<SiteLayoutResult>(SATONG_SITE_LAYOUT_KEY).size).toBe(0);
  });
});
