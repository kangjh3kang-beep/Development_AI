/**
 * SatongMapShell — 매스 시드 **인계 배선**(W4) 관통 테스트.
 *
 * ★왜 배선을 따로 잠그나: 이 저장소가 반복해서 뚫린 자리가 정확히 여기다(순수 로직은
 *   초록인데 소비처가 호출하지 않아 기능이 통째로 없는 상태). `lib/satong-mass-seed`의
 *   단위 테스트만으로는 "CTA를 눌렀을 때 실제로 저장되고 설계 스튜디오로 이동하는가"를
 *   전혀 보지 못한다. 그래서 ①CTA 존재 조건 ②저장 페이로드 ③이동 ④계정격리를 관통한다.
 */
import { useEffect, type ReactNode } from "react";
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SatongMapShell } from "@/components/precheck/SatongMapShell";
import { writeSatongMapSelection } from "@/components/precheck/satong-map-selection";
import { clearOnLogout } from "@/lib/projectSync";
import { SATONG_MASS_SEED_KEY, readMassSeedHandoff } from "@/lib/satong-mass-seed";
import type { SiteLayoutResult } from "@/lib/site-layout";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { useProjectStore } from "@/store/useProjectStore";

const push = vi.hoisted(() => vi.fn());

vi.mock("next/navigation", () => ({
  useParams: () => ({ locale: "ko" }),
  usePathname: () => "/ko/precheck",
  useRouter: () => ({ push, replace: vi.fn(), back: vi.fn(), prefetch: vi.fn() }),
}));

vi.mock("next/dynamic", () => ({
  default: () => {
    const DynamicStub = (props: { topRightSlot?: ReactNode }) => {
      useEffect(() => {}, []);
      return <div data-testid="dynamic-map-stub">{props.topRightSlot}</div>;
    };
    return DynamicStub;
  },
}));

const layout = {
  resolve: null as ((v: SiteLayoutResult) => void) | null,
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
      post: vi.fn((path: string) => {
        if (path !== "/analysis/site-layout") return pending();
        return new Promise<SiteLayoutResult>((res) => {
          layout.resolve = res;
        });
      }),
    },
  };
});

const ADDR_A = "경상북도 포항시 남구 호미곶면 대보리 산1-1";
const PNU_A = "4711025029000010001";
const GEOM = {
  type: "Polygon",
  coordinates: [[[129.56, 36.07], [129.5604, 36.07], [129.5604, 36.0703], [129.56, 36.0703], [129.56, 36.07]]],
};

/** ★상류 실응답 형태에 충실하게 — 라이브에서 확인한 키만 쓴다(가짜 형태로 초록 만들지 않는다). */
const OPT = (kind: string, angle: number, floors: number) => ({
  kind, angle_deg: angle, buildings: 3, floors, height_m: floors * 3,
  spacing_meaningful: true, spacing_m: 12, total_units_est: 24,
  yield_pct: 72, openness_pct: 61,
  daylight: { meets_sunlight: true, direct_sun_hours: 5.2 },
  buildings_geojson: {
    type: "FeatureCollection" as const,
    features: [{ type: "Feature" as const, properties: { dong: 1, floors }, geometry: GEOM }],
  },
});

const RESULT_OK: SiteLayoutResult = {
  ok: true,
  honest_notes: ["v1 한계: 축정렬 직사각형 동·균일 세트백·동지 일조 근사."],
  buildable_geojson: GEOM as never,
  buildable_area_sqm: 820,
  // ★라이브 응답에 실제로 있는 키(프로덕션 실측 확인).
  //   ★★두 면적을 **일부러 다르게** 둔다(R3 HIGH 회귀락): `land_area_sqm`은 배치가 실제로
  //   산정된 면적(클라이언트가 보낸 지적면적 우선)이고, `parcel_area_sqm`은 **폴리곤 기하
  //   근사**다. 같은 서비스가 두 값의 20% 괴리까지 정상으로 취급하므로, 픽스처에서 둘을
  //   같게 두면 어느 필드를 읽는지 구분되지 않아 잘못된 필드를 골라도 초록이 된다.
  land_area_sqm: 1000,
  parcel_area_sqm: 1050,
  setback_m: 3,
  options: [OPT("판상형", 25.3, 15), OPT("탑상형", 0, 12)],
  best: OPT("판상형", 25.3, 15),
} as SiteLayoutResult;

/** 층수가 0인 응답 — 넘길 게 없으면 CTA가 뜨면 안 된다(죽은 버튼 금지). */
const RESULT_NO_FLOORS: SiteLayoutResult = {
  ...RESULT_OK,
  options: [OPT("판상형", 0, 0)],
  best: OPT("판상형", 0, 0),
} as SiteLayoutResult;

function resetStores() {
  act(() => {
    useProjectStore.setState({ projects: [], syncing: false });
    useProjectContextStore.setState({ projectId: null, projectName: "", projectStatus: "", siteAnalysis: null });
  });
}

function seed() {
  writeSatongMapSelection([
    { id: "P-a", address: ADDR_A, pnu: PNU_A, source: "map", areaSqm: 1000, zoneType: "제2종일반주거지역", jimok: "대", geometry: GEOM },
  ]);
}

/** 상세 열기 → 배치 조회 → 응답까지. */
async function openWithLayout(result: SiteLayoutResult) {
  seed();
  render(<SatongMapShell locale="ko" />);
  fireEvent.click(screen.getByText("대보리 산1-1"));
  fireEvent.click(screen.getByTestId("parcel-layout-request"));
  await act(async () => {
    layout.resolve?.(result);
  });
  return screen.getByTestId("parcel-detail-panel");
}

describe("SatongMapShell 매스 시드 인계 배선(W4)", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
    resetStores();
    push.mockClear();
    layout.resolve = null;
  });

  afterEach(() => {
    window.sessionStorage.clear();
    resetStores();
  });

  it("① 조회 전에는 인계 CTA가 없다(고를 안이 없으면 넘길 것도 없다)", () => {
    seed();
    render(<SatongMapShell locale="ko" />);
    fireEvent.click(screen.getByText("대보리 산1-1"));
    expect(screen.queryByTestId("parcel-layout-seed-design")).toBeNull();
  });

  it("★② CTA를 누르면 **고른 안의 층수**가 저장되고 설계 스튜디오로 이동한다", async () => {
    const panel = await openWithLayout(RESULT_OK);

    const cta = within(panel).getByTestId("parcel-layout-seed-design");
    expect(cta.textContent).toContain("판상형");
    expect(cta.textContent).toContain("15층");

    fireEvent.click(cta);

    // ★저장: 필지 식별자까지 함께 실려야 수신측이 다른 필지에 오적용하지 않는다.
    const saved = readMassSeedHandoff(Date.now());
    expect(saved).not.toBeNull();
    expect(saved!.targetFloors).toBe(15);
    expect(saved!.optionLabel).toBe("판상형 25°");
    expect(saved!.pnu).toBe(PNU_A);
    expect(saved!.address).toBe(ADDR_A);
    // ★R1 HIGH-3: 이 층수가 산정된 부지 면적도 함께 실려야 수신측이 다필지 합산 부지를 걸러낸다.
    // ★지적면적(1000)이어야 한다. 폴리곤 근사(1050)를 실으면 수신측이 지적면적과 2%로
    //   대조하므로 같은 필지를 "다른 부지"로 판정하고 **사실이 아닌 배너**를 띄운다.
    expect(saved!.areaSqm).toBe(1000);

    // ★이동: 저장만 하고 안 보내면 사용자는 아무 일도 안 일어난 걸로 본다.
    expect(push).toHaveBeenCalledWith("/ko/design-studio");
  });

  it("★③ 대안을 바꾸면 **바뀐 안**이 인계된다(첫 안이 박제되지 않는다)", async () => {
    const panel = await openWithLayout(RESULT_OK);

    fireEvent.click(within(panel).getByTestId("parcel-layout-option-탑상형@0"));
    fireEvent.click(within(panel).getByTestId("parcel-layout-seed-design"));

    const saved = readMassSeedHandoff(Date.now());
    expect(saved!.targetFloors).toBe(12);
    // 0°는 '각도 없음'이 아니라 **축 정렬**이라는 유효한 정보다 — 라벨에 그대로 남는다.
    expect(saved!.optionLabel).toBe("탑상형 0°");
  });

  it("★⑥ 필지 면적을 모르면 CTA 대신 사유를 표시한다(R2 MEDIUM-1 — 죽은 버튼 금지)", async () => {
    // 면적이 없으면 수신측이 **무조건 거부**한다(다필지 판정 불가). 그 상태로 버튼을 그리면
    // 눌러도 아무 일이 없다 — 사용자에게 신호가 0인 무음 실패가 된다.
    const panel = await openWithLayout({ ...RESULT_OK, land_area_sqm: undefined } as SiteLayoutResult);
    expect(within(panel).queryByTestId("parcel-layout-seed-design")).toBeNull();
    expect(within(panel).getByText(/면적을 확인하지 못해/)).toBeTruthy();
  });

  it("★④ 층수가 없는 안이면 CTA를 그리지 않는다(빈 인계·죽은 버튼 금지)", async () => {
    const panel = await openWithLayout(RESULT_NO_FLOORS);
    expect(within(panel).queryByTestId("parcel-layout-seed-design")).toBeNull();
  });

  it("★⑤ 계정 전환(로그아웃) 시 인계가 지워진다 — 남으면 이전 계정 선택이 다음 계정 설계 시드가 된다", async () => {
    const panel = await openWithLayout(RESULT_OK);
    fireEvent.click(within(panel).getByTestId("parcel-layout-seed-design"));
    expect(window.sessionStorage.getItem(SATONG_MASS_SEED_KEY)).not.toBeNull();

    act(() => {
      clearOnLogout();
    });

    expect(window.sessionStorage.getItem(SATONG_MASS_SEED_KEY)).toBeNull();
  });
});
