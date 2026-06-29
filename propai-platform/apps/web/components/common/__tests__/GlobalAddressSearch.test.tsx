import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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

describe("GlobalAddressSearch multi-map console", () => {
  it("explains all Satong map layers and keeps parcel-dependent layers gated before address input", () => {
    render(<GlobalAddressSearch single={false} writeToContext={false} />);

    expect(screen.getByText("지도 레이어 콘솔")).toBeInTheDocument();
    expect(screen.getByText("지적도·용도지역")).toBeInTheDocument();
    expect(screen.getByText("공시지가·노후도")).toBeInTheDocument();
    expect(screen.getByText("실거래·시세")).toBeInTheDocument();
    expect(screen.getByText("분양·공·경매")).toBeInTheDocument();
    expect(screen.getByText("위성·지형·교통·로드뷰")).toBeInTheDocument();
    expect(screen.getByText("상단에서 지번·주소를 검색하거나 엑셀을 올리면 지적·공시지가·노후도 레이어가 열립니다.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /지적도·용도지역/ })).toBeDisabled();
  });

  it("switches the visible workflow hint after a parcel exists and the market layer is selected", async () => {
    render(
      <GlobalAddressSearch
        single={false}
        writeToContext={false}
        initialAddress="경기도 의정부시 의정부동 224"
      />,
    );

    const marketButton = screen.getByRole("button", { name: /실거래·시세/ });
    expect(marketButton).toBeEnabled();

    await userEvent.click(marketButton);

    expect(screen.getByText("현재 실거래·분양")).toBeInTheDocument();
    expect(screen.getByText("필지 경계와 시장 레이어를 오가며 후보지 검토, 인허가, 설계 산출물로 이어갈 수 있습니다.")).toBeInTheDocument();
  });
});
