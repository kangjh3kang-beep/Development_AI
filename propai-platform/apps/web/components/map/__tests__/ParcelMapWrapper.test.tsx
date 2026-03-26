import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const { dynamicMock } = vi.hoisted(() => ({
  dynamicMock: vi.fn(),
}));

vi.mock("next/dynamic", () => ({
  default: dynamicMock,
}));

describe("ParcelMapWrapper", () => {
  afterEach(() => {
    dynamicMock.mockReset();
    vi.resetModules();
  });

  it("wires the cadastral map dynamic loader and forwards typed parcel props", async () => {
    dynamicMock.mockImplementation(
      (loader, options) =>
        function DynamicParcelMap(props: Record<string, unknown>) {
          void loader;
          void options;
          return (
            <div data-testid="parcel-map-dynamic">{JSON.stringify(props)}</div>
          );
        },
    );

    const { default: ParcelMapWrapper } = await import(
      "@/components/map/ParcelMapWrapper"
    );

    render(
      <ParcelMapWrapper
        parcels={[
          {
            id: "parcel-a",
            label: "A-01",
            areaSqm: 128.4,
            owner: "Owner A",
            status: "available",
            x: 0,
            y: 0,
            width: 10,
            height: 12,
          },
        ]}
        labels={{
          title: "Parcel map",
          description: "Cadastral overview",
          legendTitle: "Legend",
          parcelInfoTitle: "Parcel info",
          areaLabel: "Area",
          ownerLabel: "Owner",
          statusLabel: "Status",
          statusLabels: {
            available: "Available",
            review: "Review",
            restricted: "Restricted",
          },
        }}
      />,
    );

    expect(dynamicMock).toHaveBeenCalledTimes(1);

    const loadingElement = (
      dynamicMock.mock.calls[0]?.[1] as {
        loading?: () => { props?: { className?: string } };
      }
    ).loading?.();

    expect(loadingElement?.props?.className).toContain("h-[500px]");
    expect(screen.getByTestId("parcel-map-dynamic")).toHaveTextContent(
      "parcel-a",
    );
    expect(screen.getByTestId("parcel-map-dynamic")).toHaveTextContent(
      "Available",
    );
  });
});
