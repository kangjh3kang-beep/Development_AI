/**
 * P3 G7 — KakaoRoadview 마운트(선택 위치 로드뷰, 접힘 기본값 additive).
 *
 * KakaoRoadview 는 백엔드 계약 없이 props(lat/lon)만으로 완결된 컴포넌트라
 * "1:1 계약" 검증 대신, 기존 흐름(NearbyTransactionsMap)에 additive 로 얹혔는지 —
 * ①focusTarget 이 없으면 토글이 아예 안 보이고 ②있으면 접힘 상태로 보이며
 * ③펼치면 정확한 lat/lon 이 전달되는지를 검증한다.
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { postMock, multiMapSpy, roadviewSpy } = vi.hoisted(() => ({
  postMock: vi.fn(),
  multiMapSpy: vi.fn(),
  roadviewSpy: vi.fn(),
}));

vi.mock("@/lib/api-client", () => ({
  apiClient: { post: postMock },
}));

// Leaflet 은 jsdom 에서 구동 불가 — 지도 엔진은 프로프 캡처 스텁으로 대체.
vi.mock("@/components/map/SatongMultiMap", () => ({
  SatongMultiMap: (props: Record<string, unknown>) => {
    multiMapSpy(props);
    return <div data-testid="satong-multi-map" />;
  },
}));

// 카카오 SDK 는 실제 네트워크가 필요 — 프로프 캡처 스텁으로 대체(마운트 여부·좌표 전달만 검증).
vi.mock("@/components/map/KakaoRoadview", () => ({
  KakaoRoadview: (props: Record<string, unknown>) => {
    roadviewSpy(props);
    return <div data-testid="kakao-roadview" />;
  },
}));

const CENTER_PAYLOAD = {
  center: { lat: 37.57, lon: 126.98, address: "서울" },
  radius_m: 1000,
  lawd_cd: "11110",
  months: ["2026-04", "2026-05", "2026-06"],
  categories: {},
};

const NO_CENTER_PAYLOAD = {
  center: null,
  radius_m: 1000,
  lawd_cd: "11110",
  months: ["2026-04", "2026-05", "2026-06"],
  categories: {},
};

async function renderMap() {
  const { NearbyTransactionsMap } = await import(
    "@/components/map/NearbyTransactionsMap"
  );
  return render(
    <NearbyTransactionsMap address="서울 종로구 청운동 1-1" pnu="1111010100100010000" />,
  );
}

describe("NearbyTransactionsMap — 선택 위치 로드뷰 additive 마운트", () => {
  beforeEach(() => {
    postMock.mockReset();
    multiMapSpy.mockClear();
    roadviewSpy.mockClear();
  });

  afterEach(() => {
    vi.resetModules();
  });

  it("focusTarget 이 있으면 로드뷰 토글이 접힘 상태로 노출되고, 펼치면 lat/lon 이 전달된다", async () => {
    postMock.mockImplementation(async (path: string) => {
      if (path === "/zoning/nearby-map") return CENTER_PAYLOAD;
      return { available: false, items: [] };
    });

    await renderMap();

    const toggle = await screen.findByRole("button", { name: /선택 위치 로드뷰 보기/ });
    expect(toggle).toBeInTheDocument();
    // 접힘 기본값 — 펼치기 전에는 로드뷰가 마운트되지 않는다.
    expect(screen.queryByTestId("kakao-roadview")).not.toBeInTheDocument();

    await userEvent.click(toggle);

    await waitFor(() => {
      expect(screen.getByTestId("kakao-roadview")).toBeInTheDocument();
    });
    expect(roadviewSpy).toHaveBeenCalledWith(
      expect.objectContaining({ lat: 37.57, lon: 126.98 }),
    );
    expect(
      screen.getByRole("button", { name: /선택 위치 로드뷰 접기/ }),
    ).toBeInTheDocument();
  });

  it("focusTarget 이 없으면(좌표 확인 불가) 로드뷰 토글 자체가 렌더되지 않는다", async () => {
    postMock.mockImplementation(async (path: string) => {
      if (path === "/zoning/nearby-map") return NO_CENTER_PAYLOAD;
      if (path === "/zoning/parcel-boundaries") throw new Error("network timeout");
      return { available: false, items: [] };
    });

    await renderMap();

    await screen.findByText(/위치 확인 불가/);
    expect(
      screen.queryByRole("button", { name: /선택 위치 로드뷰 보기/ }),
    ).not.toBeInTheDocument();
    expect(roadviewSpy).not.toHaveBeenCalled();
  });
});
