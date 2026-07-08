/**
 * SatongMapShell 스모크(W3-2) — "크래시 없이 마운트 + 핵심 랜드마크 존재"만 확인.
 * 내부 지도(SatongMultiMap)는 next/dynamic 로드라 스텁으로 대체하고,
 * 마운트 시 프로젝트 동기화(syncFromBackend → /projects)는 pending으로 고정한다.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { SatongMapShell } from "@/components/precheck/SatongMapShell";

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

// next/dynamic(SatongMultiMap)은 jsdom에서 Leaflet 실로드가 불가 — 스텁으로 대체.
vi.mock("next/dynamic", () => ({
  default: () => {
    const DynamicStub = () => <div data-testid="dynamic-map-stub" />;
    return DynamicStub;
  },
}));

// 네트워크 차단: /projects 동기화·검색·레이어 조회 전부 영구 pending으로 고정.
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

describe("SatongMapShell 스모크", () => {
  it("크래시 없이 마운트되고 헤더·필지 입력 패널·지도 스텁이 보인다", () => {
    render(<SatongMapShell locale="ko" />);

    expect(
      screen.getByRole("heading", { name: /지도 위에서 입력부터 산출물 생성까지/ }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "통합 필지 입력" }),
    ).toBeInTheDocument();
    expect(screen.getByTestId("dynamic-map-stub")).toBeInTheDocument();
  });
});
