/**
 * 팝업 양보 계약의 **트리거 위치** 런타임 락 — "루트에 붙는가"를 렌더 결과로 본다.
 *
 * 왜 소스 검사로 부족한가: 형제 결합자(`~`)는 트리거가 **컴포넌트 루트**에 있을 때만
 * 형제에 닿는다. 트리거가 한 겹만 안쪽으로 들어가도 CSS 는 조용히 아무것도 안 한다
 * (에러도, 경고도 없다). 그래서 실제 DOM 에서 위치를 확인한다.
 *
 * ★Leaflet 은 jsdom 에서 못 뜬다(CDN 로드가 발화하지 않음) — 그래도 이 락이 보는 것은
 *   지도 초기화가 아니라 **루트 요소의 속성**이라 영향이 없다(스모크 테스트와 같은 전제).
 */
import type React from "react";

import { render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { SatongMultiMap } from "@/components/map/SatongMultiMap";
import { SATONG_POPUP_YIELD } from "@/lib/satong-map-z";

vi.mock("@/lib/api-client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api-client")>();
  const pending = () => new Promise<never>(() => {});
  return { ...actual, apiClient: { ...actual.apiClient, get: vi.fn(pending), post: vi.fn(pending) } };
});

/**
 * ★실 소비처는 대부분 `chrome="immersive"` + `readOnly` 다(NearbyTransactionsMap ·
 *   ZoningSignalMap · ParcelBoundaryMap). 기본 크롬만 검사하면 그 분기에서 루트가
 *   달라져도 모른다 — 두 분기를 모두 태운다.
 */
const VARIANTS: Array<{ label: string; node: React.ReactElement }> = [
  { label: 'chrome="default"', node: <SatongMultiMap /> },
  { label: 'chrome="immersive" + readOnly', node: <SatongMultiMap chrome="immersive" readOnly /> },
];

describe("SatongMultiMap — 팝업 양보 트리거는 루트에 산다", () => {
  it.each(VARIANTS)("$label — 루트 요소가 트리거를 갖고 닫힘 값이 'false' 다", ({ node }) => {
    const { container } = render(node);
    const root = container.firstElementChild as HTMLElement;
    expect(root).toBeTruthy();
    // ★속성을 **항상** 렌더한다 — 닫힘일 때 속성을 지우면 위치를 관측할 수 없다.
    expect(root.getAttribute(SATONG_POPUP_YIELD.wrapperAttr)).toBe("false");
  });

  it.each(VARIANTS)("$label — 트리거는 딱 하나다(안쪽에 중복이 남으면 어느 쪽이 진짜인지 모른다)", ({ node }) => {
    const { container } = render(node);
    const all = container.querySelectorAll(`[${SATONG_POPUP_YIELD.wrapperAttr}]`);
    expect(all).toHaveLength(1);
    expect(all[0]).toBe(container.firstElementChild);
  });
});
