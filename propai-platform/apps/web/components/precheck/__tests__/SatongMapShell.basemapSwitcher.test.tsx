/**
 * 베이스맵 썸네일 스위처(jootek 패리티) — terrain 컨트롤 상호배타 계약.
 *   ① 기본은 '일반' 활성. ② '위성' 클릭 → 위성만 활성(상호배타). ③ '일반' 복귀 가능.
 */
import { fireEvent, render, screen, act } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SatongMapShell } from "@/components/precheck/SatongMapShell";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { useProjectStore } from "@/store/useProjectStore";

vi.mock("next/navigation", () => ({
  useParams: () => ({ locale: "ko" }),
  usePathname: () => "/ko/precheck",
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn(), prefetch: vi.fn() }),
}));

vi.mock("next/dynamic", () => ({
  default: () => {
    const DynamicStub = () => <div data-testid="dynamic-map-stub" />;
    return DynamicStub;
  },
}));

vi.mock("@/lib/api-client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api-client")>();
  const pending = () => new Promise<never>(() => {});
  return {
    ...actual,
    apiClient: {
      ...actual.apiClient,
      request: vi.fn(pending), get: vi.fn(pending), post: vi.fn(pending), put: vi.fn(pending),
      patch: vi.fn(pending), delete: vi.fn(pending), getV2: vi.fn(pending), postV2: vi.fn(pending),
      putV2: vi.fn(pending), deleteV2: vi.fn(pending),
    },
  };
});

function resetStores() {
  act(() => {
    useProjectStore.setState({ projects: [], syncing: false });
    useProjectContextStore.setState({ projectId: null, projectName: "", projectStatus: "", siteAnalysis: null });
  });
}

describe("SatongMapShell 베이스맵 썸네일 스위처", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
    resetStores();
  });
  afterEach(() => {
    window.sessionStorage.clear();
    resetStores();
  });

  it("기본 '일반' 활성 → '위성' 클릭 시 상호배타 전환, '일반' 복귀 가능", () => {
    render(<SatongMapShell locale="ko" />);

    const base = screen.getByRole("button", { name: "베이스맵: 일반" });
    const satellite = screen.getByRole("button", { name: "베이스맵: 위성" });

    expect(base).toHaveAttribute("aria-pressed", "true");
    expect(satellite).toHaveAttribute("aria-pressed", "false");

    fireEvent.click(satellite);
    expect(satellite).toHaveAttribute("aria-pressed", "true");
    expect(base).toHaveAttribute("aria-pressed", "false");
    // 상호배타 — 하이브리드/회색도 비활성 유지
    expect(screen.getByRole("button", { name: "베이스맵: 하이브리드" })).toHaveAttribute("aria-pressed", "false");

    fireEvent.click(base);
    expect(base).toHaveAttribute("aria-pressed", "true");
    expect(satellite).toHaveAttribute("aria-pressed", "false");
  });
});
