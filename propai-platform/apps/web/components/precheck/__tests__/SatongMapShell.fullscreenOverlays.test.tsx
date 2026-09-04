/**
 * H2 결함 회귀망 — 풀스크린에서 지도 제어(레이어 레일·팝오버·활성 배지)가 사라지지 않는다.
 *
 * ★실결함(2026-07-29 감사): 풀스크린은 SatongMultiMap '내부 래퍼'에 CSS 폴백
 *   `fixed inset-0 z-[9990]`을 입히거나(useMapFullscreen) 네이티브 Fullscreen API로 그
 *   래퍼만 top layer에 올린다. 그런데 셸이 소유한 오버레이(배지행 z-380 · 레일 z-420 ·
 *   팝오버 3종 z-430)는 그 래퍼의 **형제**라, 폴백에선 9990 밑에 깔리고 네이티브에선 아예
 *   화면 밖으로 밀려 전부 사라졌다 — "크게 보려고" 누른 버튼이 정확히 레이어 제어를
 *   없애는 모순.
 * ★수정: 오버레이를 topRightSlot으로 넘겨 래퍼 '안'에서 렌더한다(하단 선택바에서 이미
 *   검증된 '래퍼 안으로 이동' 선례를 전파). 이 파일은 그 전달 계약과 DOM 소속을 고정한다 —
 *   `topRightSlot={mapOverlays}` 한 줄만 지워도 아래 3건이 전부 깨진다(변이 검증 완료).
 *
 * ※ 슬롯 반대편(래퍼 안에서 실제로 렌더되는지)은 SatongMultiMap.topRightSlot.test.tsx가 고정한다.
 */
import type { ReactNode } from "react";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SatongMapShell } from "@/components/precheck/SatongMapShell";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { useProjectStore } from "@/store/useProjectStore";

vi.mock("next/navigation", () => ({
  useParams: () => ({ locale: "ko" }),
  usePathname: () => "/ko/precheck",
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn(), prefetch: vi.fn() }),
}));

// 스텁이 슬롯을 삼키면 '전달 안 함'과 구분이 안 된다 — 실컴포넌트와 동일하게 슬롯을 렌더하고,
// props도 캡처해 전달 계약 자체(=null이 아님)를 직접 단언한다(basemapSwitcher.test.tsx 기법).
const capturedMapProps: Record<string, unknown>[] = [];
vi.mock("next/dynamic", () => ({
  default: () => {
    const DynamicStub = (props: Record<string, unknown>) => {
      capturedMapProps.push(props);
      return <div data-testid="dynamic-map-stub">{props.topRightSlot as ReactNode}</div>;
    };
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

// ★jsdom의 fireEvent.click은 선행 mouseenter를 합성하지 않는다. 실브라우저는 반드시
//   mouseenter→click 순서라, click만 쏘면 '현실에 없는 순서'를 고정하게 된다.
function hoverClick(el: HTMLElement) {
  fireEvent.mouseEnter(el);
  fireEvent.click(el);
}

describe("SatongMapShell — 풀스크린 오버레이 소속(H2)", () => {
  beforeEach(() => { capturedMapProps.length = 0; window.sessionStorage.clear(); resetStores(); });
  afterEach(() => { window.sessionStorage.clear(); resetStores(); });

  it("★레일·배지행은 지도 래퍼 안(topRightSlot)에서 렌더된다 — 형제 배치 회귀 금지", () => {
    render(<SatongMapShell locale="ko" />);

    // ① 전달 계약: 슬롯이 실제로 넘어갔고 비어 있지 않다.
    const props = capturedMapProps.at(-1);
    expect(props).toBeDefined();
    expect(props).toHaveProperty("topRightSlot");
    expect(props?.topRightSlot ?? null).not.toBeNull();

    // ② DOM 소속: 풀스크린 대상(=지도 래퍼) 서브트리 '안'에 있어야 한다.
    const wrapper = screen.getByTestId("dynamic-map-stub");
    expect(wrapper.contains(screen.getByLabelText(/레이어 목록/))).toBe(true); // 레일 앵커
    expect(wrapper.contains(screen.getByRole("button", { name: "지적도" }))).toBe(true); // 레일 14버튼
    expect(wrapper.contains(screen.getByText("사통팔땅 멀티지도"))).toBe(true); // 좌상단 배지행(z-380)
  });

  it("★레일이 여는 팝오버(베이스맵·레이어)도 래퍼 안에서 뜬다 — 확정 경로 도달성 보존", () => {
    render(<SatongMapShell locale="ko" />);
    const wrapper = screen.getByTestId("dynamic-map-stub");

    hoverClick(screen.getByRole("button", { name: "베이스맵 선택" }));
    expect(wrapper.contains(screen.getByRole("dialog", { name: "베이스맵" }))).toBe(true);

    hoverClick(screen.getByRole("button", { name: "지적도" }));
    expect(wrapper.contains(screen.getByRole("dialog", { name: "지적도" }))).toBe(true);
  });
});
