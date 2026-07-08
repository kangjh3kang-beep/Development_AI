/**
 * MAP-008 P1 — 지오코딩 실패 + 폴백 center 조회 실패 시 '위치 확인 불가' 정직 라벨.
 *
 * 재현 시나리오: /zoning/nearby-map 이 center=null(실거래 지오코딩 실패)을 반환하고,
 * 폴백 /zoning/parcel-boundaries 호출마저 실패(네트워크·타임아웃)하면 focusTarget=null →
 * 지도는 초기 서울 좌표에 머문다. 이때 사용자에게 '위치 확인 불가' 안내가 반드시 떠야 한다
 * (무날조 원칙: 기본 지도 위치를 선택 위치처럼 보이게 방치하지 않는다).
 */
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { postMock, multiMapSpy } = vi.hoisted(() => ({
  postMock: vi.fn(),
  multiMapSpy: vi.fn(),
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

describe("NearbyTransactionsMap — 좌표 완전 폴백 실패(MAP-008 P1)", () => {
  beforeEach(() => {
    postMock.mockReset();
    multiMapSpy.mockClear();
  });

  afterEach(() => {
    vi.resetModules();
  });

  it("백엔드 center=null + 폴백 조회 실패 → '위치 확인 불가' 안내 + focusTarget=null 유지", async () => {
    postMock.mockImplementation(async (path: string) => {
      if (path === "/zoning/nearby-map") return NO_CENTER_PAYLOAD;
      if (path === "/zoning/parcel-boundaries") throw new Error("network timeout");
      return { available: false, items: [] };
    });

    await renderMap();

    // 폴백 실패가 확정되면 정직 라벨이 떠야 한다.
    expect(await screen.findByText(/위치 확인 불가/)).toBeInTheDocument();
    expect(screen.getByText(/기본 위치/)).toBeInTheDocument();

    // focusTarget 은 끝까지 null(가짜 좌표 금지) — 지도 스텁에 전달된 마지막 프로프로 검증.
    const lastProps = multiMapSpy.mock.calls.at(-1)?.[0] as { focusTarget: unknown };
    expect(lastProps.focusTarget).toBeNull();
  });

  it("폴백 조회가 center 를 못 주는 경우(응답은 성공)에도 '위치 확인 불가' 안내", async () => {
    postMock.mockImplementation(async (path: string) => {
      if (path === "/zoning/nearby-map") return NO_CENTER_PAYLOAD;
      if (path === "/zoning/parcel-boundaries") return { center: null, features: [] };
      return { available: false, items: [] };
    });

    await renderMap();

    expect(await screen.findByText(/위치 확인 불가/)).toBeInTheDocument();
  });

  it("폴백 center 조회 성공 시 안내 없음 + focusTarget=폴백 좌표", async () => {
    postMock.mockImplementation(async (path: string) => {
      if (path === "/zoning/nearby-map") return NO_CENTER_PAYLOAD;
      if (path === "/zoning/parcel-boundaries") {
        return { center: { lat: 37.586, lon: 126.969 }, features: [] };
      }
      return { available: false, items: [] };
    });

    await renderMap();

    await waitFor(() => {
      const lastProps = multiMapSpy.mock.calls.at(-1)?.[0] as {
        focusTarget: { lat: number; lon: number } | null;
      };
      expect(lastProps.focusTarget).toEqual(
        expect.objectContaining({ lat: 37.586, lon: 126.969 }),
      );
    });
    expect(screen.queryByText(/위치 확인 불가/)).not.toBeInTheDocument();
  });

  it("백엔드 center 정상일 땐 폴백 조회 자체가 없고 안내도 없음", async () => {
    postMock.mockImplementation(async (path: string) => {
      if (path === "/zoning/nearby-map") {
        return { ...NO_CENTER_PAYLOAD, center: { lat: 37.57, lon: 126.98, address: "서울" } };
      }
      if (path === "/zoning/parcel-boundaries") throw new Error("호출되면 안 됨");
      return { available: false, items: [] };
    });

    await renderMap();

    await waitFor(() => {
      const lastProps = multiMapSpy.mock.calls.at(-1)?.[0] as {
        focusTarget: { lat: number; lon: number } | null;
      };
      expect(lastProps.focusTarget).toEqual(
        expect.objectContaining({ lat: 37.57, lon: 126.98 }),
      );
    });
    expect(screen.queryByText(/위치 확인 불가/)).not.toBeInTheDocument();
    expect(
      postMock.mock.calls.filter(([path]) => path === "/zoning/parcel-boundaries"),
    ).toHaveLength(0);
  });
});
