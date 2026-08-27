/**
 * **조기 오류 포착이 배포본에서 실제로 사는가** — 배포 후 확인용 프로브.
 *
 * 왜 필요한가(2026-08-27 실측): `#893` 은 **배포됐는데 작동하지 않았다.**
 * 인라인 부트스트랩을 백틱 조각의 `+` 연결로 썼더니 빌드가 `${…}` 보간 직후를 버려
 * 라이브 HTML 에 **문법이 깨진 스크립트**가 실렸다. 증상:
 *   · HTML 에는 `__propaiEarly` 문자열이 **있다**(그래서 "배포됐다"로 오독하기 쉽다)
 *   · 그런데 런타임 `window.__propaiEarly` 는 **`undefined`**
 *   · `#418` 이 나도 `js_error` **0건**(대조군 `api_call` 은 실림 — 수집기 자체는 산다)
 *
 * ★**"HTML 에 있다" 와 "실행된다" 는 다른 명제다.** 이 프로브는 후자를 잰다.
 *
 * 사용(cwd = apps/web):
 *   export PROBE_EMAIL=… PROBE_PASSWORD=…      # 미설정이면 exit 2(조용한 비로그인 측정 방지)
 *   node e2e/support/early-capture-probe.mjs [경로]
 *
 * 종료코드: 0=살아 있음 · 1=죽음(배포본에 없거나 문법이 깨졌다) · 2=측정 무효
 */
import { chromium } from "@playwright/test";

const BASE = process.env.PROBE_BASE ?? "https://4t8t.net";
const EMAIL = process.env.PROBE_EMAIL;
const PASSWORD = process.env.PROBE_PASSWORD;
if (!EMAIL || !PASSWORD) {
  console.error("★PROBE_EMAIL / PROBE_PASSWORD 를 주지 않았다 — 로그인 없이 재면 /ko/login 을 재고\n" +
    "  '없다'는 결론이 나온다. 측정 무효로 중단한다.");
  process.exit(2);
}
const TARGET = process.argv[2] ?? "/ko/permits";

const browser = await chromium.launch();
const ctx = await browser.newContext({ locale: "ko-KR", timezoneId: "Asia/Seoul" });
const page = await ctx.newPage();
await page.goto(BASE + "/ko/login", { waitUntil: "domcontentloaded" });
await page.waitForTimeout(2500);
await page.fill("input[name=email]", EMAIL);
await page.fill("input[name=password]", PASSWORD);
await Promise.all([
  page.waitForURL((u) => !/\/login/.test(u.toString()), { timeout: 45000 }).catch(() => {}),
  page.click("button[type=submit]"),
]);
await page.waitForLoadState("networkidle").catch(() => {});
if (/\/login/.test(page.url())) { console.error("★로그인 실패 — 측정 무효"); await browser.close(); process.exit(2); }

let html = "";
await ctx.route("**" + TARGET, async (route) => {
  const r = await route.fetch();
  html = await r.text();
  await route.fulfill({ response: r, body: html });
});
await page.goto(BASE + TARGET, { waitUntil: "domcontentloaded" });
await page.waitForTimeout(4000);

const runtime = await page.evaluate(() => {
  const s = window.__propaiEarly;
  return { exists: typeof s !== "undefined", hasBuf: Array.isArray(s?.buf), closed: s?.closed ?? null };
});
// ★양성 대조군 — 실제로 오류를 던져 **담기는지** 본다("존재한다"만으로는 부족하다).
const caught = await page.evaluate(() => {
  const before = window.__propaiEarly?.buf?.length ?? -1;
  window.dispatchEvent(new ErrorEvent("error", { message: "PROBE_EARLY_CANARY", error: new Error("PROBE_EARLY_CANARY") }));
  const after = window.__propaiEarly?.buf?.length ?? -1;
  return { before, after, grew: after > before };
});
// ★음성 대조군 — HTML 에 문자열이 있는지(있는데 실행이 안 되면 **빌드 잘림**이다)
const inHtml = html.includes("__propaiEarly");
const themeInHtml = html.includes('localStorage.getItem("theme")'); // 대조군: 수집기 생존 증명

const verdict = runtime.exists && runtime.hasBuf && caught.grew;
console.log(JSON.stringify({ target: TARGET, inHtml, themeInHtml, runtime, caught, verdict }, null, 1));
await browser.close();

if (!themeInHtml) { console.error("★대조군 실패 — theme 부트스트랩조차 HTML 에 없다. 조회가 틀렸다(측정 무효)."); process.exit(2); }
if (verdict) { console.log("◎ 조기 포착이 배포본에서 살아 있다(오류를 실제로 담았다)"); process.exit(0); }
if (inHtml) console.error("★HTML 에는 있는데 **실행되지 않는다** — 빌드가 스크립트를 잘랐을 가능성이 높다\n" +
  "  (백틱 조각을 `+` 로 이으면 `${…}` 보간 직후가 버려진다 — 2026-08-27 실측).");
else console.error("★배포본에 아예 없다 — 그 커밋이 실제로 배포됐는지 sw.js 로 확인하라.");
process.exit(1);
