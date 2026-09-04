/**
 * ★배선 — 서버가 판정한 **우세 용도지역**을 구획도가 표시하는가(2026-08-24).
 *
 * 종전엔 이 값이 화면 어디에도 없었고, 스토어의 `dominantZoneCode` 는 이름과 달리
 * **첫 필지 값**이었다(실측 사례에서 면적 우세와 **반대**를 가리켰다).
 *
 * ★`mixed_review_required` 는 **값이 아니라 판정 보류**다 — 화면이 임의로 한 지역을
 *   고르면 서버가 거부한 단일화를 화면이 대신 저지르는 것이다. 그 분기를 따로 잠근다.
 *
 * ★**의도적 미잠금**(변이 생존이 정상 — 점수 부풀리기 방지를 위해 적어 둔다):
 *   배너 줄의 `className` 문자열. 도구의 문자열 변이는 라벨과 className 이 **같은 줄**에 있으면
 *   className 을 고를 수 있어 생존으로 보이는데, **라벨을 손으로 바꿔 보면 CAUGHT 다**
 *   (`우세 용도지역` → `우세 용적률` 주입 시 A·B 두 케이스가 함께 빨개진다 — 실측 확인).
 *   즉 잠긴 것은 **라벨·값·판정 분기**이고, 스타일은 의도적으로 열어 둔다.
 */
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ParcelBoundaryMap } from "@/components/map/ParcelBoundaryMap";

const postMock = vi.fn();
vi.mock("@/lib/api-client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api-client")>();
  return { ...actual, apiClient: { ...actual.apiClient, post: (...a: unknown[]) => postMock(...a) } };
});
vi.mock("@/components/map/SatongMultiMap", () => ({
  SatongMultiMap: () => <div data-testid="map-stub" />,
}));

const GEOM = { type: "Polygon", coordinates: [[[127.1, 37.3], [127.1001, 37.3], [127.1001, 37.3001], [127.1, 37.3001], [127.1, 37.3]]] };

function resp(ia: Record<string, unknown>) {
  return {
    features: [
      { pnu: "1", address: "a", area_sqm: 326, geometry: GEOM, zone_type: "생산녹지지역" },
      { pnu: "2", address: "b", area_sqm: 4576, geometry: GEOM, zone_type: "자연녹지지역" },
    ],
    center: { lat: 37.3, lon: 127.1 },
    total_area_sqm: 4902,
    parcel_count: 2,
    integrated_analysis: { total_area_pyeong: 1483, zone_mixed: true, zone_types: ["생산녹지지역", "자연녹지지역"], ...ia },
  };
}

describe("★배선 — 우세 용도지역 표시", () => {
  beforeEach(() => postMock.mockReset());
  afterEach(() => vi.clearAllMocks());

  it("A) 면적 우세 지역과 **면적 비중**을 함께 보여 준다", async () => {
    postMock.mockResolvedValue(resp({
      dominant_zone: "자연녹지지역",
      dominant_basis: "area_weighted",
      zone_mix: [
        { zone: "생산녹지지역", area_sqm: 326, share_pct: 6.7 },
        { zone: "자연녹지지역", area_sqm: 4576, share_pct: 93.3 },
      ],
    }));
    render(<ParcelBoundaryMap parcels={["a", "b"]} />);

    const el = await screen.findByTestId("dominant-zone");
    expect(postMock).toHaveBeenCalled(); // 공허 진리 가드
    // ★라벨까지 잠근다 — 값만 보면 "우세 용적률" 같은 오도 문구로 바뀌어도 초록이다(변이 생존분).
    expect(el.textContent).toContain("우세 용도지역");
    expect(el.textContent).toContain("자연녹지지역");
    expect(el.textContent).toContain("93.3%");
    // ★첫 필지(생산녹지)를 고르지 않았다 — 회귀 방향을 직접 막는다.
    expect(el.textContent).not.toContain("생산녹지지역");
  });

  it("★B) 판정 보류는 **한 지역을 고르지 않는다**(서버가 거부한 단일화를 화면이 저지르지 않게)", async () => {
    postMock.mockResolvedValue(resp({
      dominant_zone: "mixed_review_required",
      dominant_basis: "area_weighted",
      zone_mix: [
        { zone: "보전관리지역", area_sqm: 326, share_pct: 6.7 },
        { zone: "자연녹지지역", area_sqm: 4576, share_pct: 93.3 },
      ],
    }));
    render(<ParcelBoundaryMap parcels={["a", "b"]} />);

    const el = await screen.findByTestId("dominant-zone");
    // ★라벨 전체를 잠근다 — 무엇의 판정이 보류인지 안 밝히면 사용자는 못 읽는다(변이 생존분).
    expect(el.textContent).toContain("우세 용도지역 판정 보류");
    // ★면적이 큰 쪽을 슬쩍 고르면 안 된다.
    expect(el.textContent).not.toContain("자연녹지지역");
    expect(el.textContent).not.toContain("보전관리지역");
  });

  it("★C) 무회귀 — 구 서버(키 부재)면 아무것도 그리지 않는다", async () => {
    postMock.mockResolvedValue(resp({}));
    render(<ParcelBoundaryMap parcels={["a", "b"]} />);
    await waitFor(() => expect(postMock).toHaveBeenCalled());
    await screen.findByTestId("map-stub");
    expect(screen.queryByTestId("dominant-zone")).not.toBeInTheDocument();
  });
});
