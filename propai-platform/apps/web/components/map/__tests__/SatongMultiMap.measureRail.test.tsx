/**
 * V2 측정 rail — 팝오버 없이도 거리/면적 도구 진입(상시 버튼) 계약.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { SatongMultiMap } from "@/components/map/SatongMultiMap";

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

describe("SatongMultiMap 측정 rail(V2)", () => {
  it("거리/면적 rail 버튼 → 측정 모드 칩 표시·aria-pressed 전환·ESC 종료", () => {
    render(<SatongMultiMap />);

    const distance = screen.getByRole("button", { name: "거리재기 도구" });
    const area = screen.getByRole("button", { name: "면적재기 도구" });
    expect(distance).toHaveAttribute("aria-pressed", "false");

    fireEvent.click(distance);
    expect(distance).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText(/거리재기 — 클릭: 점 추가/)).toBeInTheDocument();

    fireEvent.click(area);
    expect(area).toHaveAttribute("aria-pressed", "true");
    expect(distance).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByText(/면적재기 — 클릭: 점 추가/)).toBeInTheDocument();
    expect(screen.getByText(/점 3개 이상 필요/)).toBeInTheDocument();

    fireEvent.keyDown(document, { key: "Escape" });
    expect(area).toHaveAttribute("aria-pressed", "false");
  });
});
