import { expect, test, type Page } from "@playwright/test";

/**
 * 사통맵 **pane 서열** — 실브라우저 페인트 판정(P5: 공중에 뜬 위임을 수신한다).
 *
 * ## 왜 e2e 여야 하나
 *
 * `lib/__tests__/stacking-context.test.ts:149` 가 이렇게 위임했다:
 *
 *     it.todo("수작업 CSS·인라인 style 층 — e2e 페인트 순서 판정으로 덮는다");
 *
 * 그런데 **e2e 가 그 위임을 받지 않았다.** 저장소 전체에서 `elementFromPoint` 를 실제로
 * **호출**하는 곳은 `e2e/popover-layer.spec.ts:211` 한 곳뿐이고, 대상은 주소 후보 팝오버 vs
 * `z-[600]` 헤더다 — **지도 오버레이·Leaflet 은 사정거리 밖**이었다. 위임은 공중에 떴다.
 *
 * 그 공백에서 실제 결함이 살았다: `globals.css` 의 `.leaflet-pane { z-index:1 !important }` 가
 * pane 을 전부 1 로 눌러 **지도 내부 사다리를 죽였는데**, `satong-map-z.test.ts` 는
 * *"overlay < label < marker < tooltip < popup — 라벨이 팝업을 가리면 안 된다"* 를
 * **초록으로 보증**하고 있었다(같은 모듈 리터럴끼리의 항등식이라 실패 불가).
 * 평탄화를 걷어내 사다리를 복원했고(#683), **그 복원을 런타임에서 확인하는 것이 여기다.**
 *
 * ## 이 스펙이 닫는 정직 경계
 *
 * `lib/__tests__/satong-pane-ladder.test.ts` 는 스스로 *"이것은 여전히 **소스 검사**다.
 * 계산된 z 와 DOM 순서 판정은 e2e 몫이다"* 라고 적었다. 그 몫을 여기서 받는다.
 * jsdom 은 CSS 계단(`!important` 우선순위·계산된 z)을 재현하지 않으므로 **실브라우저여야 한다.**
 */

/** 클라이언트 인증은 localStorage 토큰이다(popover-layer.spec.ts 와 같은 harness). */
async function seedSession(page: Page): Promise<void> {
  await page.addInitScript(() => {
    localStorage.setItem("propai_access_token", "playwright-access-token");
    localStorage.setItem("propai_refresh_token", "playwright-refresh-token");
  });
  // ★API 를 전부 고정한다 — 층위 계약은 인증과 무관해야 한다. 미지정 엔드포인트를 200 `{}` 로
  //   답해 401 → `handleSessionExpired()` → 로그인 리다이렉트 경로가 생기지 않게 한다
  //   (그 함정으로 "로컬 초록 / CI 빨강"이 난 이력이 이 저장소에 있다).
  await page.route("**/api/v1/**", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: "{}" });
  });
}

test.describe("사통맵 pane 서열 — 실브라우저 페인트 판정", () => {
  test("★지도 내부 사다리가 살아 있다 — pane 이 평탄화되지 않는다", async ({ page }) => {
    await seedSession(page);
    await page.goto("/ko/precheck");

    // ★전제 — 지도가 마운트되지 않으면 이 판정은 통째로 공허하다. skip 이 아니라 **실패**로 둔다.
    const map = page.locator(".leaflet-container").first();
    await expect(
      map,
      "지도가 마운트되지 않았다 — 이 스펙은 아무것도 재지 못한다(공허한 초록 금지)",
    ).toBeVisible({ timeout: 45_000 });

    const measured = await page.evaluate(() => {
      const panes: Record<string, number> = {};
      for (const el of document.querySelectorAll(".leaflet-pane")) {
        const name = [...el.classList].find((c) => c !== "leaflet-pane") ?? "?";
        panes[name.replace("leaflet-", "").replace("-pane", "")] = Number(
          getComputedStyle(el).zIndex,
        );
      }
      const container = document.querySelector(".leaflet-container") as HTMLElement;
      const cs = getComputedStyle(container);
      return { panes, isolation: cs.isolation, containerZ: cs.zIndex };
    });

    // 공허 진리 가드 — pane 을 하나도 못 찾았으면 아래 비교가 무의미하다.
    const names = Object.keys(measured.panes);
    expect(names.length, `pane 을 찾지 못했다: ${JSON.stringify(measured)}`).toBeGreaterThanOrEqual(5);

    const z = (n: string) => measured.panes[n];

    // ★사다리 — 이것이 종전에 전부 1 로 눌려 있었다(라이브 실측 popup pane = 1).
    expect(
      z("popup"),
      `팝업 pane 이 툴팁 위가 아니다: ${JSON.stringify(measured.panes)} — ` +
        "`.leaflet-pane` 평탄화가 되살아났는지 globals.css 를 보라",
    ).toBeGreaterThan(z("tooltip"));
    expect(z("tooltip")).toBeGreaterThan(z("marker"));
    expect(z("marker")).toBeGreaterThan(z("overlay"));
    expect(z("overlay")).toBeGreaterThan(z("tile"));

    // ★평탄화 여부를 **직접** 본다 — 값이 전부 같으면 사다리가 없는 것이다.
    const distinct = new Set(Object.values(measured.panes).filter((v) => Number.isFinite(v)));
    expect(
      distinct.size,
      `pane z 가 ${distinct.size}종뿐이다 — 평탄화가 되살아났다: ${JSON.stringify(measured.panes)}`,
    ).toBeGreaterThan(3);

    // ★★격리는 유일한 방어다(#683 이 평탄화를 걷어낸 뒤로). 사라지면 지도가 헤더 위로 샌다.
    expect(
      measured.isolation,
      "`.leaflet-container` 의 isolation:isolate 가 사라졌다 — 사다리가 살아 있으므로 " +
        "이제 팝업(700)·마커(600)가 sticky 헤더(z-50) 위로 떠오른다",
    ).toBe("isolate");
    expect(measured.containerZ).toBe("0");
  });

  test("★격리가 실제로 가둔다 — 지도 밖 z=50 형제가 pane 을 이긴다(페인트 판정)", async ({ page }) => {
    await seedSession(page);
    await page.goto("/ko/precheck");
    await expect(page.locator(".leaflet-container").first()).toBeVisible({ timeout: 45_000 });

    const verdict = await page.evaluate(() => {
      const container = document.querySelector(".leaflet-container") as HTMLElement;
      const r = container.getBoundingClientRect();
      // 지도 위에 겹치는 **body 직속** 형제를 sticky 헤더와 같은 서열(z=50)로 심는다.
      const probe = document.createElement("div");
      probe.id = "__zprobe__";
      Object.assign(probe.style, {
        position: "fixed",
        left: `${Math.round(r.left + 40)}px`,
        top: `${Math.round(r.top + 40)}px`,
        width: "200px",
        height: "100px",
        zIndex: "50",
      });
      document.body.appendChild(probe);

      const x = Math.round(r.left + 140);
      const y = Math.round(r.top + 90);
      const inMap = (el: Element | null) => !!(el && container.contains(el));

      const atFifty = document.elementFromPoint(x, y);
      // ★음성 대조군 — z 를 -1 로 낮추면 **지도가 이겨야** 한다. 그래야 이 프로브에
      //   판별력이 있다는 것이 증명된다("크롬이 이김"이 그냥 기본값이 아님).
      probe.style.zIndex = "-1";
      const atNegative = document.elementFromPoint(x, y);
      probe.remove();

      return {
        fiftyWins: atFifty?.id === "__zprobe__",
        negativeGivesMap: inMap(atNegative),
        popupPaneZ: Number(
          getComputedStyle(document.querySelector(".leaflet-popup-pane") as HTMLElement).zIndex,
        ),
      };
    });

    // 판별력 먼저 — 대조군이 죽었으면 아래 단언은 근거가 없다.
    expect(
      verdict.negativeGivesMap,
      "음성대조(z=-1)에서도 지도가 이기지 못했다 — 이 프로브는 판별력이 없다",
    ).toBe(true);

    expect(
      verdict.popupPaneZ,
      "팝업 pane 이 낮다 — 사다리가 복원돼 있어야 이 판정이 의미를 갖는다",
    ).toBeGreaterThan(100);

    expect(
      verdict.fiftyWins,
      `팝업 pane z=${verdict.popupPaneZ} 인데 지도 밖 z=50 형제를 **이겼다** — ` +
        "격리(isolation:isolate)가 깨졌다. 이 상태면 지도가 sticky 헤더 위로 샌다",
    ).toBe(true);
  });
});
