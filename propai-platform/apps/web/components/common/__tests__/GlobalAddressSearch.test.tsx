import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { GlobalAddressSearch } from "@/components/common/GlobalAddressSearch";

vi.mock("@/components/common/MapShell", () => ({
  MapShell: ({ children }: { children: ReactNode }) => (
    <div data-testid="map-shell">{children}</div>
  ),
  dynamicMap: () =>
    function DynamicMapStub() {
      return <div data-testid="dynamic-map" />;
    },
}));

vi.mock("@/components/ui/KakaoAddressSearch", () => ({
  KakaoAddressSearch: () => <div data-testid="kakao-address-search" />,
}));

// 471347cf: 레이어 콘솔 UI가 SatongMultiMap 통합엔진으로 대체됨.
// 통합지도는 next/dynamic으로 로드되므로 dynamic 자체를 스텁해
// 전달 props(활성 레이어·선택 필지)를 검증 가능한 DOM 속성으로 노출한다.
vi.mock("next/dynamic", () => ({
  default: () =>
    function SatongMultiMapStub(props: {
      layerState?: { enabledLayerIds?: string[] };
      selectedParcels?: unknown[];
    }) {
      return (
        <div
          data-testid="satong-multi-map"
          data-layers={props.layerState?.enabledLayerIds?.join(",") ?? ""}
          data-parcels={String(props.selectedParcels?.length ?? 0)}
        />
      );
    },
}));

describe("GlobalAddressSearch unified multi-map", () => {
  it("renders the unified Satong multi-map with the five data layers enabled", () => {
    render(<GlobalAddressSearch single={false} writeToContext={false} />);

    const map = screen.getByTestId("satong-multi-map");
    expect(map).toBeInTheDocument();
    // 지적·용도지역·공시지가·노후도·실거래 5개 레이어가 기본 활성으로 전달되는 계약.
    expect(map).toHaveAttribute(
      "data-layers",
      "cadastre,zoning,official-price,age,transactions",
    );
  });

  it("registers an initial address into the parcel list alongside the map", async () => {
    render(
      <GlobalAddressSearch
        single={false}
        writeToContext={false}
        initialAddress="경기도 의정부시 의정부동 224"
      />,
    );

    // 초기 주소가 좌측 필지 목록에 등재되고 통합지도가 함께 렌더된다.
    expect(await screen.findByText(/의정부동 224/)).toBeInTheDocument();
    expect(screen.getByTestId("satong-multi-map")).toBeInTheDocument();
  });
});
