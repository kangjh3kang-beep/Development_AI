/**
 * 하단 도크 단일화(2026-07-17 겹침 구조 처방) — bottomDockSlot 계약.
 *
 * ★배경: 지도 위 부유 요소들이 독립 absolute 섬(스위처 bottom-20 right-4 등)으로 존재해
 *   칩 행의 암묵 예약값(max-w calc 152px)을 침묵 초과하는 순간 겹침이 재발해 왔다(라이브
 *   신고 3회). 처방 = 같은 flex flow에 흘리기 — flow 안에서는 겹침이 문법적으로 불가능.
 *   이 테스트는 ①슬롯이 도크 컨테이너 '안'에 마운트되고 ②칩이 없어도 슬롯만으로 도크가
 *   렌더되며 ③도크에 암묵 예약값(max-w calc)이 재도입되지 않음을 고정한다.
 */
import { render, screen } from "@testing-library/react";
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

describe("SatongMultiMap 하단 도크(bottomDockSlot)", () => {
  it("★슬롯은 도크 컨테이너 안에 흐른다 — 독립 absolute 섬 금지(겹침 구조 불가화)", () => {
    render(<SatongMultiMap bottomDockSlot={<button type="button">스위처 슬롯</button>} />);
    const slotButton = screen.getByRole("button", { name: "스위처 슬롯" });
    const dock = slotButton.closest('[data-testid="satong-bottom-dock"]');
    expect(dock).not.toBeNull();
    // 우측 정렬은 ml-auto(flow) — absolute 좌표가 아니어야 한다.
    expect(slotButton.parentElement?.className).toContain("ml-auto");
    expect(slotButton.parentElement?.className).not.toContain("absolute");
  });

  it("칩·노트가 없어도 슬롯만으로 도크가 렌더된다(스위처 소실 방지)", () => {
    render(<SatongMultiMap bottomDockSlot={<span>슬롯</span>} />);
    expect(screen.getByTestId("satong-bottom-dock")).toBeInTheDocument();
  });

  it("도크에 암묵 예약값(max-w calc) 재도입 금지 — 전폭 flow + wrap가 계약", () => {
    // 종전 max-w-[calc(100%-152px)]는 스위처 실폭(~280px)에 침묵 초과당해 칩이 밑으로
    // 파고들었다. 예약값 대신 right-3 전폭 + flex-wrap이 정답 — 회귀를 클래스로 고정한다.
    render(<SatongMultiMap bottomDockSlot={<span>슬롯</span>} />);
    const dock = screen.getByTestId("satong-bottom-dock");
    expect(dock.className).not.toMatch(/max-w-\[calc/);
    expect(dock.className).toContain("right-3");
    expect(dock.className).toContain("flex-wrap");
  });
});
