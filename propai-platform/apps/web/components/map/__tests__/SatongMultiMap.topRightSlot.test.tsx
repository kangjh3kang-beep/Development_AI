/**
 * topRightSlot 계약 — 슬롯은 '풀스크린 대상 래퍼 안'에서 렌더된다(H2 결함의 반대편 자물쇠).
 *
 * ★배경: 풀스크린은 이 컴포넌트 내부 래퍼에만 CSS 폴백 `fixed inset-0 z-[9990]`(또는
 *   네이티브 Fullscreen)을 입힌다. 셸이 소유한 레이어 레일·팝오버가 그 래퍼의 형제로 남으면
 *   z를 아무리 키워도 풀스크린에서 사라진다(하단 선택바에서 이미 한 번 겪은 결함 클래스).
 *   그래서 슬롯이 '래퍼 안'에 있다는 것 자체가 계약이다 — 셸이 슬롯을 잘 넘겨도 이쪽에서
 *   래퍼 밖으로 옮기면 결함이 그대로 부활하므로 여기서 별도로 고정한다.
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

describe("SatongMultiMap 우상단 슬롯(topRightSlot)", () => {
  it("★슬롯은 풀스크린 래퍼 안에 마운트된다 — 전체화면 토글 후에도 남는다", () => {
    render(<SatongMultiMap topRightSlot={<button type="button">레일 슬롯</button>} />);

    const slot = screen.getByRole("button", { name: "레일 슬롯" });
    const fsButton = screen.getByRole("button", { name: "전체화면" });
    // 풀스크린 클래스를 받는 래퍼 = 풀스크린 버튼의 부모. 슬롯이 같은 래퍼 소속이어야 한다.
    const wrapper = fsButton.parentElement;
    expect(wrapper).not.toBeNull();
    expect(wrapper?.contains(slot)).toBe(true);

    // 전체화면 진입(jsdom엔 requestFullscreen이 없어 CSS 폴백 경로 — 실브라우저 네이티브
    // 경로도 같은 래퍼를 top layer에 올리므로 소속 계약은 동일하다).
    fireEvent.click(fsButton);
    expect(wrapper?.className).toContain("z-[9990]");
    expect(wrapper?.contains(screen.getByRole("button", { name: "레일 슬롯" }))).toBe(true);
  });
});
