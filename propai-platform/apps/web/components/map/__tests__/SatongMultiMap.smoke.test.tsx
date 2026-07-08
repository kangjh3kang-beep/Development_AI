/**
 * SatongMultiMap 스모크(W3-2) — "크래시 없이 마운트 + 핵심 랜드마크 존재"만 확인.
 * Leaflet은 CDN 스크립트 동적 로드 방식인데 jsdom은 외부 리소스를 로드하지 않아
 * onload가 발화하지 않는다 → 지도 초기화는 영구 pending(안내문·컨트롤만 렌더).
 * window.L을 가짜로 주입하지 않는다(억지 모킹 금지 — 초기 UI 크롬만 스모크).
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { SatongMultiMap } from "@/components/map/SatongMultiMap";

// 네트워크 차단: 필지 조회(/zoning/parcel-at-point 등)는 영구 pending으로 고정.
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

describe("SatongMultiMap 스모크", () => {
  it("props 없이 크래시 없이 마운트되고 안내문·전체화면 버튼이 보인다", () => {
    render(<SatongMultiMap />);

    expect(
      screen.getByText(/지도를 클릭하면 해당 필지가 확인 카드로 표시됩니다/),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "전체화면" })).toBeInTheDocument();
  });
});
