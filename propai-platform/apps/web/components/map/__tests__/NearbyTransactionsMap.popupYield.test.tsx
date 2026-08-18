/**
 * 주변 실거래 지도의 **형제 크롬**이 실제로 양보하는지 — 렌더 결과 + 실제 CSS 선택자로 본다.
 *
 * ## 무엇을 태우나
 *
 * `app/globals.css` 에서 **실제 감쇄 규칙의 선택자 문자열을 그대로 떠와** 렌더된 DOM 에
 * `Element.matches()` 로 물린다. 즉 이 테스트가 통과하려면
 *   ① 배너가 지도의 **뒤따르는 형제** 위치에 있고
 *   ② 배너에 양보 표시가 붙어 있고
 *   ③ CSS 선택자가 그 형제 관계를 실제로 커버해야 한다
 * 셋이 동시에 맞아야 한다. 하나만 어긋나도 빨강이 된다.
 *
 * ★jsdom 은 외부 스타일시트를 적용하지 않으므로 `getComputedStyle` 로는 못 본다.
 *   그래서 "계산된 opacity"가 아니라 **선택자 매치**를 본다 — 감쇄 값 자체는
 *   `lib/__tests__/satong-popup-yield.test.ts` 가 상수↔CSS 일치로 따로 잠근다.
 * ★지도 엔진은 스텁이다(Leaflet 은 jsdom 불가). 스텁이 실제 층을 우회하지 않도록,
 *   "진짜 SatongMultiMap 이 트리거를 루트에 단다"는 사실은
 *   `SatongMultiMap.popupYieldRoot.test.tsx` 가 **실물 렌더로** 따로 잠근다.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SATONG_POPUP_YIELD } from "@/lib/satong-map-z";

const { postMock } = vi.hoisted(() => ({ postMock: vi.fn() }));

vi.mock("@/lib/api-client", () => ({
  apiClient: { post: postMock },
  ApiClientError: class ApiClientError extends Error {},
}));

// 지도 엔진 스텁 — 실물 컴포넌트의 **루트 계약**(트리거 속성)만 흉내 낸다.
vi.mock("@/components/map/SatongMultiMap", () => ({
  SatongMultiMap: () => (
    <div data-testid="satong-multi-map" {...{ [SATONG_POPUP_YIELD.wrapperAttr]: "false" }} />
  ),
}));

const WEB_ROOT = join(__dirname, "..", "..", "..");

/** globals.css 의 감쇄 규칙에서 **선택자 목록 원문**을 떠온다(손으로 다시 쓰지 않는다). */
function yieldSelectorFromCss(): string {
  const css = readFileSync(join(WEB_ROOT, "app/globals.css"), "utf8");
  const marker = `[${SATONG_POPUP_YIELD.wrapperAttr}="true"]`;
  const idx = css.indexOf(marker);
  if (idx < 0) throw new Error("globals.css 에서 양보 규칙을 찾지 못했다");
  const brace = css.indexOf("{", idx);
  const start = Math.max(css.lastIndexOf("}", idx) + 1, css.lastIndexOf("*/", idx) + 2, 0);
  return css.slice(start, brace).trim();
}

const FETCH_FAILED_PAYLOAD = {
  center: { lat: 37.57, lon: 126.98, address: "서울 종로구" },
  radius_m: 1000,
  lawd_cd: "11110",
  months: ["2026-06"],
  categories: {},
  fetch_failed: true,
  note: "국토부 실거래 공공데이터가 일시적으로 응답하지 않습니다.",
};

async function renderMap() {
  const { NearbyTransactionsMap } = await import("@/components/map/NearbyTransactionsMap");
  return render(<NearbyTransactionsMap address="서울 종로구 청운동 1-1" pnu="1111010100100010000" />);
}

describe("주변 실거래 지도 — 형제 크롬이 팝업에 양보한다", () => {
  // ★중괄호 필수: 화살표가 **모의함수를 반환**하면 vitest 가 그것을 훅의 teardown 으로 보고
  //   호출한다 — 그 모의가 '영원히 pending' 이면 훅이 10초 타임아웃으로 죽는다(실측).
  beforeEach(() => { postMock.mockReset(); });
  afterEach(() => { vi.resetModules(); });

  it("★팝업이 열리면 상시 고지 배너가 감쇄 규칙에 걸린다(닫히면 안 걸린다)", async () => {
    postMock.mockImplementation(async (path: string) =>
      path === "/zoning/nearby-map" ? FETCH_FAILED_PAYLOAD : { available: false, items: [] },
    );
    await renderMap();

    // 공허 진리 가드 — 검사할 대상이 실제로 DOM 에 떠 있는가.
    const banner = (await screen.findByText(/국토부 실거래 공공데이터/)).closest(
      `[${SATONG_POPUP_YIELD.passiveAttr}="${SATONG_POPUP_YIELD.passiveValue}"]`,
    ) as HTMLElement | null;
    expect(banner).toBeTruthy();

    const map = screen.getByTestId("satong-multi-map");
    // 형제 관계 자체를 먼저 못 박는다 — 부모가 달라지면 `~` 는 조용히 무력해진다.
    expect(map.parentElement).toBe(banner!.parentElement);

    const selector = yieldSelectorFromCss();
    // 대조군: 팝업이 닫혀 있으면 감쇄되지 않아야 한다(항상 참인 선택자면 무의미하다).
    expect(banner!.matches(selector)).toBe(false);

    // 팝업 열림 — 실물 SatongMultiMap 이 Leaflet `popupopen` 에서 하는 그 토글.
    map.setAttribute(SATONG_POPUP_YIELD.wrapperAttr, "true");
    expect(banner!.matches(selector)).toBe(true);
  });

  it("불양보 표면(전면 차단 스크림)은 감쇄되지 않는다 — 면제가 실제로 동작한다", async () => {
    // 조회를 끝내지 않아 로딩 스크림이 떠 있는 상태를 만든다.
    postMock.mockImplementation(() => new Promise<never>(() => {}));
    const { container } = await renderMap();

    const scrim = container.querySelector(
      `[${SATONG_POPUP_YIELD.exemptAttr}="blocking-scrim"]`,
    ) as HTMLElement | null;
    expect(scrim).toBeTruthy(); // 공허 진리 가드

    const map = screen.getByTestId("satong-multi-map");
    map.setAttribute(SATONG_POPUP_YIELD.wrapperAttr, "true");
    expect(scrim!.matches(yieldSelectorFromCss())).toBe(false);
  });
});
