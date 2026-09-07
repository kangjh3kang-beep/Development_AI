import { expect, test } from "@playwright/test";

import { FIELD_APP_WINDOW_NAME } from "../lib/field-app-shell";

/**
 * 현장앱 「별도 창」 판별자의 **브라우저 계약** — `window.open(url, NAME, …)` 으로 연 창에서
 * `window.name` 이 유지되는가.
 *
 * ## 왜 이 파일이 있나 (2026-09-07)
 *
 * `useFieldAppShell` 은 「이미 앱 안인가」를 두 축으로 본다 — `standalone`(설치본)과
 * **별도 창**. 후자의 판별자는 `window.name` **하나뿐**이고, 그것이 실제 브라우저에서
 * 유지되지 않으면 **사용자가 신고한 모집단이 통째로 무보호**가 된다.
 *
 * ★jsdom 단위 테스트로는 이 축을 **원리적으로 잴 수 없다** — 그 테스트는 `window.name` 을
 *   **직접 대입**하므로 «브라우저가 유지해 주는가» 를 묻지 않는다. 그래서 실제 크로미움을 태운다.
 *
 * ## ★이 레인은 **PR 게이트가 아니다** — nightly 로 돈다 (2026-09-07 정정)
 *
 * ★한때 여기에 *"CI 가 playwright 를 돌지 않는다"* 고 적었다 — **거짓이었다.**
 *   `ci.yml` **한 파일만** 조회하고 결론을 「CI」로 일반화했다(§G-26: 「라우트 0건」은
 *   「진입점 0건」이 아니다). 실제로는 `.github/workflows/e2e-nightly.yml` 이 **경로 필터 없이**
 *   `playwright test` 를 돌린다 — cron `0 18 * * *`(03:00 KST) + 수동 트리거이고,
 *   `playwright.config.ts` 의 `testDir: "./e2e"` 라 **이 파일도 수집된다.**
 *
 * ⇒ 정확히는 **PR 을 막는 게이트는 아니지만 깨지면 야간 레인이 빨개진다.** 지금 확인하려면:
 *
 *     cd propai-platform/apps/web && ./node_modules/.bin/playwright test e2e/field-app-window-name.spec.ts
 *
 * ## 실측 결과 (Chromium 1228 · Playwright 1.58.2 · 2026-09-07)
 *
 *     named    "propai-field-app"   ← 유지됨
 *     unnamed  ""                   ← 대조군(_blank)은 빈 이름 = 조회기 생존
 *     afterNav "propai-field-app"   ← 팝업 안에서 라우팅한 뒤에도 유지
 *
 * ★**다른 엔진(WebKit/Firefox)은 미측정**이다. `window.name` 은 HTML 표준의 오래된 동작이라
 *   위험은 낮다고 보지만, **잰 것은 크로미움뿐**이다.
 */

// 앱 서버가 없어도 도는 자족 테스트 — 라우트를 가로채 최소 HTML 을 돌려준다.
// (판정 대상은 우리 화면이 아니라 **브라우저의 window.name 동작**이다.)
const ORIGIN = "https://propai-field-app.test";

test.describe("별도 창 판별자 — window.name 브라우저 계약", () => {
  test("이름을 준 창은 그 이름을 갖고, 라우팅 뒤에도 유지된다(대조군: 이름 없는 창은 빈 문자열)", async ({
    context,
  }) => {
    await context.route(`${ORIGIN}/**`, (route) =>
      route.fulfill({ status: 200, contentType: "text/html", body: "<title>t</title><p>ok</p>" }),
    );
    const page = await context.newPage();
    await page.goto(`${ORIGIN}/a`);

    // ① 이름을 준 팝업 — 우리 코드와 **같은 상수**를 쓴다.
    const [popup] = await Promise.all([
      context.waitForEvent("page"),
      page.evaluate(
        ([url, name]) => {
          window.open(url, name, "popup=yes,width=800,height=600");
        },
        [`${ORIGIN}/a`, FIELD_APP_WINDOW_NAME],
      ),
    ]);
    await popup.waitForLoadState();
    expect(await popup.evaluate(() => window.name)).toBe(FIELD_APP_WINDOW_NAME);

    // ② ★대조군 — 이름 없이 연 창은 빈 이름이어야 한다.
    //    이게 없으면 "무엇을 열어도 이름이 붙는다"는 상황과 구별할 수 없다.
    const [blank] = await Promise.all([
      context.waitForEvent("page"),
      page.evaluate((url) => {
        window.open(url, "_blank");
      }, `${ORIGIN}/a`),
    ]);
    await blank.waitForLoadState();
    expect(await blank.evaluate(() => window.name)).toBe("");

    // ③ 팝업 안에서 라우팅해도 유지되는가 — 현장앱은 그 창 안에서 탭을 옮겨 다닌다.
    await popup.goto(`${ORIGIN}/b`);
    expect(await popup.evaluate(() => window.name)).toBe(FIELD_APP_WINDOW_NAME);
  });
});
