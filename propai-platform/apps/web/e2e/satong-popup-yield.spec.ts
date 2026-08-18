import { expect, test, type Page } from "@playwright/test";

/**
 * 상세정보팝업 **양보 계약** — 실브라우저에서 *실제로 먹는지* 판정한다.
 *
 * ## 왜 e2e 여야 하나 (지금까지 아무도 안 본 것)
 *
 * 이 계약의 락은 전부 "선택자가 매치되나"까지만 본다. jsdom 은 외부 스타일시트를 계산하지
 * 않으므로 **감쇄 값(0.25)이 실제로 적용되는지 · `pointer-events` 가 먹는지 · 팝업이 정말
 * 위에 오는지**는 아무도 확인하지 않았다. 게다가 처방이 `:has()` 로 옮겨 가면서
 * **CSS 파이프라인이 그걸 그대로 내보내는지**도 정적 판독으로는 단정할 수 없다.
 * 여기서 실측한다 — 이 스펙이 초록이면 `:has()` 지원·빌드 통과가 함께 증명된다.
 *
 * ## 무엇을 태우나 / 무엇은 못 태우나(정직)
 *
 * 태운다: 실제 Leaflet 팝업 + 실제 `globals.css` + 실제 페인트 순서(`elementFromPoint`).
 *   팝업은 앱이 쓰는 것과 **같은 Leaflet API**(`popup().openOn(map)`)로 연다 — 그러면 앱의
 *   `map.on("popupopen")` 배선이 그대로 돌아 트리거 속성을 **실제 코드가** 켠다.
 *   · 지도 **안**의 수동 크롬(자손 경로)
 *   · 지도의 **뒤따르는 형제 · 앞선 형제 · 래퍼 한 겹 건너 형제**(프로브 주입)
 *   · `passive` 와 `passive-visual` 의 차이(클릭 차단 유지 여부)
 * 못 태운다: `NearbyTransactionsMap` 의 **실제 고지 리본**. 그 화면은 프로젝트 컨텍스트와
 *   명시 실행 버튼을 거쳐야 지도가 뜨는 라우트라 여기서 세우지 못했다 — 그 리본이 계약
 *   위치에 있다는 것은 jsdom 렌더 락이 보고, 계약이 **실제로 먹는다**는 것은 여기가 본다.
 *   두 조각이 만나는 지점(리본 자체를 실브라우저에서)은 남은 부채다.
 *
 * ★D.18 — z 판정은 좌표 교차가 아니라 **페인트 순서**(`elementFromPoint`)로 한다.
 */

/**
 * 클라이언트 인증(localStorage 토큰) + API 고정 — satong-pane-ladder.spec.ts 와 같은 harness.
 * ★여기에 **Leaflet 맵 인스턴스 포획**을 얹는다. `window.L` 에 **setter** 를 걸어 두면
 *   CDN 스크립트가 대입하는 순간을 놓치지 않는다(폴링은 지도 생성과 경합해 플레이키하다).
 *   포획한 맵으로 **진짜 Leaflet 팝업**을 연다 — 그러면 앱의 `popupopen` 배선이 그대로 돌아
 *   트리거 속성까지 **실제 코드가** 바꾼다(테스트가 속성을 손으로 칠하지 않는다).
 */
async function seedSession(page: Page): Promise<void> {
  await page.addInitScript(() => {
    localStorage.setItem("propai_access_token", "playwright-access-token");
    localStorage.setItem("propai_refresh_token", "playwright-refresh-token");
    let leaflet: unknown;
    Object.defineProperty(window, "L", {
      configurable: true,
      get: () => leaflet,
      set: (value: unknown) => {
        leaflet = value;
        try {
          (value as { Map: { addInitHook: (fn: () => void) => void } }).Map.addInitHook(
            function (this: unknown) { (window as unknown as Record<string, unknown>).__satongMap = this; },
          );
        } catch { /* Leaflet 이 아닌 값이면 무시 */ }
      },
    });
  });
  await page.route("**/api/v1/**", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: "{}" });
  });
}

/** 지도가 실제로 초기화될 때까지 기다린다(컨테이너 가시 ≠ 준비 완료). */
async function waitForMap(page: Page): Promise<void> {
  await expect(
    page.locator(".leaflet-container").first(),
    "지도가 마운트되지 않았다 — 이 스펙은 아무것도 재지 못한다(공허한 초록 금지)",
  ).toBeVisible({ timeout: 60_000 });
  await expect(
    page.locator(".leaflet-control-attribution"),
    "지도 초기화(attribution 부착)가 끝나지 않았다",
  ).toContainText("VWorld", { timeout: 60_000 });
  await page.waitForFunction(() => !!(window as unknown as Record<string, unknown>).__satongMap, null, {
    timeout: 30_000,
  });
}

/** **진짜** Leaflet 팝업을 연다 — 앱이 `bindPopup` 9곳에서 쓰는 그 API 그대로. */
async function openMapPopup(page: Page): Promise<void> {
  await page.evaluate(() => {
    const w = window as unknown as { __satongMap: { getCenter: () => unknown }; L: { popup: () => { setLatLng: (c: unknown) => { setContent: (h: string) => { openOn: (m: unknown) => void } } } } };
    w.L.popup().setLatLng(w.__satongMap.getCenter()).setContent("<b>양보 계약 e2e 팝업</b>").openOn(w.__satongMap);
  });
  await expect(
    page.locator(".leaflet-popup").first(),
    "Leaflet 팝업이 열리지 않았다 — 이 스펙의 전제가 무너졌다",
  ).toBeVisible({ timeout: 15_000 });
  // ★전제 강제: 앱의 `popupopen` 배선이 실제로 트리거를 켰는가. 안 켜졌으면 이하 판정은 공허하다.
  await expect(page.locator('[data-satong-popup-open="true"]')).toHaveCount(1, { timeout: 10_000 });
  // ★감쇄에는 `transition: opacity 160ms` 가 걸려 있다 — 곧바로 읽으면 **전이 중간값**(≈1)이
  //   잡힌다(실측: 이것 때문에 실제 크롬만 1 로 읽혀 오진할 뻔했다). 전이가 끝나길 기다린다.
  await page.waitForTimeout(400);
}

/** 팝업을 닫는다(대조군용) — 앱의 `popupclose` 배선까지 되돌아가야 한다. */
async function closeMapPopup(page: Page): Promise<void> {
  await page.evaluate(() => {
    (window as unknown as { __satongMap: { closePopup: () => void } }).__satongMap.closePopup();
  });
  await expect(page.locator(".leaflet-popup")).toHaveCount(0, { timeout: 10_000 });
  await expect(page.locator('[data-satong-popup-open="true"]')).toHaveCount(0, { timeout: 10_000 });
  await page.waitForTimeout(400); // 되돌아오는 전이도 160ms
}

/**
 * 지도 루트의 **부모 스코프**에 프로브를 심는다 — CSS `:has(> [트리거])` 의 도달 범위 그대로.
 * 조부모 자리에도 하나 심는다 — 그건 **계약 밖**임을 못 박는 경계 대조군이다.
 * 앞선 형제도 심는다: "앞선 형제는 지도보다 먼저 그려져 안전"은 CSS 스펙상 거짓이기 때문이다
 * (양수 z 를 쓰면 DOM 순서와 무관하게 지도 위로 간다).
 */
async function plantProbes(page: Page): Promise<void> {
  await page.evaluate(() => {
    const map = document.querySelector("[data-satong-popup-open]") as HTMLElement;
    if (!map || !map.parentElement) throw new Error("지도 루트를 못 찾았다");
    const make = (id: string, chrome: string | null) => {
      const el = document.createElement("div");
      el.id = id;
      if (chrome) el.setAttribute("data-satong-chrome", chrome);
      Object.assign(el.style, { position: "absolute", left: "0px", top: "0px", width: "10px", height: "10px" });
      return el;
    };
    const parent = map.parentElement;
    parent.appendChild(make("probe-after", "passive"));
    parent.insertBefore(make("probe-before", "passive"), map);
    parent.appendChild(make("probe-visual", "passive-visual"));
    parent.appendChild(make("probe-control", null)); // 음성 대조군 — 표시가 없으면 안 흐려져야 한다
    // ★경계 대조군 — 지도를 한 겹 더 감싼 자리(조부모 스코프)는 **계약 밖**이다.
    //   한때 `:has(> * > …)` 로 여기까지 덮었다가 걷어냈다(컴포넌트 경계를 넘어 같은 섹션의
    //   남의 크롬을 흐리는 것이 실측됐다). 그래서 이 프로브는 **감쇄되면 안 된다**.
    const grand = parent.parentElement;
    if (grand) {
      const wrapper = document.createElement("div");
      wrapper.id = "probe-wrapper";
      wrapper.appendChild(make("probe-nested", "passive"));
      grand.appendChild(wrapper);
    }
  });
}

type Probe = { opacity: string; pointerEvents: string };
const readProbes = (page: Page) =>
  page.evaluate(() => {
    const read = (id: string) => {
      const el = document.getElementById(id);
      if (!el) return null;
      const cs = getComputedStyle(el);
      return { opacity: cs.opacity, pointerEvents: cs.pointerEvents };
    };
    const chrome = document.querySelector('[data-satong-chrome="passive"]:not([id^="probe"])');
    return {
      after: read("probe-after"),
      before: read("probe-before"),
      nested: read("probe-nested"),
      visual: read("probe-visual"),
      control: read("probe-control"),
      realChrome: chrome ? { ...{ opacity: getComputedStyle(chrome).opacity, pointerEvents: getComputedStyle(chrome).pointerEvents } } : null,
    } as Record<string, Probe | null>;
  });

test.describe("상세팝업 양보 계약 — 실브라우저 판정", () => {
  test("★팝업이 열리면 수동 크롬이 실제로 감쇄된다(자손·앞뒤 형제) — 래퍼 건너는 계약 밖", async ({ page }) => {
    await seedSession(page);
    await page.goto("/ko/precheck");
    await waitForMap(page);
    await openMapPopup(page);
    await plantProbes(page);

    const open = await readProbes(page);

    // 공허 진리 가드 — 프로브가 심겼는지부터.
    expect(open.after, "프로브가 심기지 않았다").toBeTruthy();
    expect(open.control, "음성 대조군 프로브가 없다").toBeTruthy();

    // ★핵심: 감쇄가 **실제로 계산된다**. 여기가 초록이면 `:has()` 가 브라우저·빌드를 통과한 것이다.
    expect(open.after!.opacity, ":has() 형제 도달이 안 먹는다(뒤따르는 형제)").toBe("0.25");
    expect(open.before!.opacity, "앞선 형제가 계약 밖이다 — DOM 순서는 안전 보증이 아니다").toBe("0.25");
    // ★경계: 래퍼 한 겹 건너는 **계약 밖**이어야 한다. 0.25 가 되면 스코프가 다시 컴포넌트
    //   경계를 넘은 것이다(같은 섹션의 남의 크롬까지 흐려진다).
    expect(open.nested!.opacity, "스코프가 조부모까지 번졌다 — 남의 크롬을 흐린다").toBe("1");
    expect(open.after!.pointerEvents, "완전 양보인데 클릭이 안 통과된다").toBe("none");

    // ★두 단계 구분 — 시각만 양보는 흐려지되 **계속 막아야** 한다.
    expect(open.visual!.opacity).toBe("0.25");
    expect(open.visual!.pointerEvents, "passive-visual 이 클릭까지 놔줬다 — 차단이 목적인 스크림이 뚫린다").not.toBe("none");

    // ★음성 대조군 — 표시가 없으면 흐려지면 안 된다(규칙이 아무거나 잡는 게 아님을 증명).
    expect(open.control!.opacity).toBe("1");

    // ★실제 컴포넌트 크롬(레일·배지행·코너 도크)도 함께 물러났는지 — 프로브만 초록인 상황 방지.
    //   전제 강제: 이 화면에 진짜 수동 크롬이 하나라도 있어야 이 단언이 뜻을 갖는다.
    expect(open.realChrome, "실제 수동 크롬을 못 찾았다 — 이 판정이 공허해진다").toBeTruthy();
    expect(open.realChrome!.opacity).toBe("0.25");

    // ★대조군(닫힘) — 팝업을 닫으면 전부 되돌아와야 한다. 안 되돌아오면 "항상 흐림"이다.
    await closeMapPopup(page);
    const closed = await readProbes(page);
    expect(closed.after!.opacity).toBe("1");
    expect(closed.before!.opacity).toBe("1");
    expect(closed.nested!.opacity).toBe("1");
    expect(closed.visual!.opacity).toBe("1");
    expect(closed.after!.pointerEvents).not.toBe("none");
  });

  test("★팝업이 실제로 위에 그려진다 — 페인트 순서로 판정(rect 교차 금지)", async ({ page }) => {
    await seedSession(page);
    await page.goto("/ko/precheck");
    await waitForMap(page);
    await openMapPopup(page);

    const verdict = await page.evaluate(() => {
      const popup = document.querySelector(".leaflet-popup") as HTMLElement;
      const map = document.querySelector("[data-satong-popup-open]") as HTMLElement;
      const r = popup.getBoundingClientRect();
      const x = Math.round(r.left + r.width / 2);
      const y = Math.round(r.top + r.height / 2);

      // 팝업 중심에 **양보하는** 크롬을 겹쳐 놓는다 — 계약이 먹으면 클릭이 팝업에 닿아야 한다.
      const rival = document.createElement("div");
      rival.setAttribute("data-satong-chrome", "passive");
      Object.assign(rival.style, {
        position: "absolute", left: "0", top: "0", right: "0", bottom: "0", zIndex: "400",
      });
      map.parentElement!.appendChild(rival);
      const withYield = document.elementFromPoint(x, y);

      // ★음성 대조군 — 표시를 떼면 **크롬이 이겨야** 한다. 그래야 이 프로브에 판별력이 있다.
      rival.removeAttribute("data-satong-chrome");
      const withoutYield = document.elementFromPoint(x, y);
      rival.remove();

      return {
        yieldGivesPopup: !!withYield && popup.contains(withYield),
        noYieldGivesRival: withoutYield instanceof HTMLElement && !popup.contains(withoutYield),
      };
    });

    expect(
      verdict.noYieldGivesRival,
      "음성 대조군이 실패했다 — 양보 없이도 팝업이 이긴다면 이 판정엔 판별력이 없다",
    ).toBe(true);
    expect(
      verdict.yieldGivesPopup,
      "양보 표시가 붙었는데도 크롬이 팝업 위를 잡는다 — pointer-events:none 이 안 먹는다",
    ).toBe(true);
  });
});
