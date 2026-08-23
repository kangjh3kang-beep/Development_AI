/**
 * ★배선 층 — 서버가 보고한 **탈락 필지**를 구획도가 실제로 고지하는가.
 *
 * 백엔드가 `requested_count`/`resolved_count`/`dropped[]` 를 돌려줘도 화면이 안 읽으면
 * **소비처 0** 이다 — 이 저장소가 반복해서 데인 형태다(계약만 만들고 아무도 안 씀).
 * 그래서 판정(백엔드 테스트)과 별개로 **렌더**를 따로 태운다.
 *
 * 이 화면(`ParcelBoundaryMap`)이 사용자가 "필지가 구획도에 다 안 나온다"고 말한 그 화면이다.
 *
 * ★**의도적 미잠금**(변이 생존이 정상 — 점수 부풀리기 방지를 위해 적어 둔다):
 *   배너의 `className` 문자열(테두리·배경·아이콘 크기). 디자인 토큰 변경을 테스트가 막으면
 *   안 된다. 잠그는 것은 **존재·`role`·문구**이지 색이 아니다.
 */
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ParcelBoundaryMap } from "@/components/map/ParcelBoundaryMap";

const postMock = vi.fn();

vi.mock("@/lib/api-client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api-client")>();
  return { ...actual, apiClient: { ...actual.apiClient, post: (...a: unknown[]) => postMock(...a) } };
});

// Leaflet 실로드 불가 — 지도 자체는 이 스위트의 관심사가 아니다.
vi.mock("@/components/map/SatongMultiMap", () => ({
  SatongMultiMap: () => <div data-testid="map-stub" />,
}));

const GEOM = {
  type: "Polygon",
  coordinates: [[[127.1, 37.3], [127.1001, 37.3], [127.1001, 37.3001], [127.1, 37.3001], [127.1, 37.3]]],
};

function boundaries(over: Record<string, unknown>) {
  return {
    features: [
      { pnu: "1", address: "경기도 성남시 분당구 정자동 1", area_sqm: 1000, geometry: GEOM, zone_type: "제2종일반주거지역" },
    ],
    center: { lat: 37.3, lon: 127.1 },
    total_area_sqm: 1000,
    parcel_count: 1,
    ...over,
  };
}

describe("★배선 — 탈락 필지 고지", () => {
  beforeEach(() => postMock.mockReset());
  afterEach(() => vi.clearAllMocks());

  it("A) 3필지를 넣었는데 1건만 해석되면 **그 사실과 어느 필지인지**를 말한다", async () => {
    postMock.mockResolvedValue(
      boundaries({
        requested_count: 3,
        resolved_count: 1,
        dropped: [
          { address: "경기도 어딘가 없는동 111-111", pnu: null, reason: "pnu_unresolved", detail: null },
          { address: "경기도 어딘가 없는동 222-222", pnu: null, reason: "pnu_unresolved", detail: null },
        ],
      }),
    );

    render(<ParcelBoundaryMap parcels={["경기도 성남시 분당구 정자동 1", "경기도 어딘가 없는동 111-111", "경기도 어딘가 없는동 222-222"]} />);

    const notice = await screen.findByTestId("parcel-drop-notice");
    // 공허 진리 가드 — 조회가 실제로 일어나 응답을 소비했는지 먼저 본다.
    expect(postMock).toHaveBeenCalled();
    expect(notice).toHaveAttribute("role", "status"); // 스크린리더에도 고지된다
    expect(notice.textContent).toContain("3필지 중 2필지를 찾지 못했습니다");
    // ★어느 필지가 빠졌는지 — 이것이 없으면 사용자는 고칠 수 없다.
    expect(notice.textContent).toContain("경기도 어딘가 없는동 111-111");
    expect(notice.textContent).toContain("경기도 어딘가 없는동 222-222");
    // 남은 값이 무엇 기준인지도 말한다(합계 면적이 부분집합 기준임을 숨기지 않는다).
    //   ★문장 **전체**를 잠근다 — "1필지 기준입니다"만 보면 앞의 "아래 구획도·합계 면적은"
    //     조각이 무잠금이라, 무엇이 부분집합인지 안 밝히는 문구로 바뀌어도 초록이었다(변이 생존분).
    expect(notice.textContent).toContain("아래 구획도·합계 면적은 1필지 기준입니다");
  });

  it("★B) 위양성 방지 — 탈락이 없으면(빈 배열) 아무것도 그리지 않는다", async () => {
    postMock.mockResolvedValue(
      boundaries({ requested_count: 1, resolved_count: 1, dropped: [] }),
    );

    render(<ParcelBoundaryMap parcels={["경기도 성남시 분당구 정자동 1"]} />);

    await waitFor(() => expect(postMock).toHaveBeenCalled());
    // 대상 존재 가드 — 응답이 소비돼 지도가 그려진 뒤에 '없음'을 단언한다(공허한 통과 방지).
    await screen.findByTestId("map-stub");
    expect(screen.queryByTestId("parcel-drop-notice")).not.toBeInTheDocument();
  });

  it("★C) 무회귀 — 구 서버(계수 키 자체가 없음)에서도 고지하지 않는다", async () => {
    // 배포 중간 상태(프론트 먼저 나가고 백엔드가 아직 옛 버전)에서 오탐이 나면 안 된다.
    postMock.mockResolvedValue(boundaries({}));

    render(<ParcelBoundaryMap parcels={["경기도 성남시 분당구 정자동 1"]} />);

    await waitFor(() => expect(postMock).toHaveBeenCalled());
    await screen.findByTestId("map-stub");
    expect(screen.queryByTestId("parcel-drop-notice")).not.toBeInTheDocument();
  });
});
