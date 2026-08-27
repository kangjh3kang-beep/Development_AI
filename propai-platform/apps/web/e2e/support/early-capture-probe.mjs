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
import { decideEarlyCaptureVerdict } from "../../lib/hydration/probe-text.mjs";

const BASE = process.env.PROBE_BASE ?? "https://4t8t.net";
const EMAIL = process.env.PROBE_EMAIL;
const PASSWORD = process.env.PROBE_PASSWORD;
if (!EMAIL || !PASSWORD) {
  console.error("★PROBE_EMAIL / PROBE_PASSWORD 를 주지 않았다 — 로그인 없이 재면 /ko/login 을 재고\n" +
    "  '없다'는 결론이 나온다. 측정 무효로 중단한다.");
  process.exit(2);
}
const TARGET = process.argv[2] ?? "/ko/permits";

/**
 * ★**비판정 실패는 전부 `exit 2`(무효)** — 결함(1)과 뭉치면 안 된다.
 *   초판은 `page.goto` 등에 try/catch 가 없어 **네트워크 오류가 `exit 1`(=결함)** 로 나갔고,
 *   헤더가 `1=죽음(배포본에 없거나 문법이 깨졌다)` 라고 **계약으로 선언**한 것과 어긋났다.
 *   배포 직후 오리진이 잠깐 5xx 면 *"빌드가 스크립트를 잘랐다"* 로 오보된다 —
 *   `#893` 이 태어난 그 함정(신호 오독)의 재판이다(독립 리뷰 지적).
 */
let browser;
try {
browser = await chromium.launch();
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

/**
 * ★**`closed === true` 가 가장 강한 증거다** — 그 플래그를 세우는 주체는 `drainEarlyErrors()` 뿐이고,
 *   그것은 `initEventCollector()` 안에서만 불린다. 즉 `closed:true` 는
 *   **부트스트랩이 실행됐고(전역이 생겼고) 수집기가 그 버퍼를 인계받았다**는 뜻이다.
 *
 * ★★초판은 이 값을 **찍기만 하고 판정에 안 썼다.** 대신 카나리를 던져 `buf` 가 자라는지 봤는데,
 *   `drain` 이 이미 `closed=true` 로 닫은 뒤라 **절대 자라지 않는다** → 고쳐진 배포본에서도
 *   `exit 1`("죽음")을 냈다. **신호가 반전돼 있었다** — `verdict:true` 가 나오는 유일한 조건이
 *   *"수집기가 안 돈 페이지"* 였다(독립 리뷰가 jsdom 재현으로 실증).
 */
// 카나리는 **아직 안 닫혔을 때만** 던진다. 닫혔으면 이미 판정이 끝났고, 열려 있다면
// 정식 핸들러가 아직 등록 전이라 **프로덕션 텔레메트리를 오염시키지 않는다**.
const caught = runtime.closed === false
  ? await page.evaluate(() => {
      const before = window.__propaiEarly?.buf?.length ?? -1;
      window.dispatchEvent(new ErrorEvent("error", { message: "PROBE_EARLY_CANARY", error: new Error("PROBE_EARLY_CANARY") }));
      const after = window.__propaiEarly?.buf?.length ?? -1;
      return { before, after, grew: after > before, thrown: true };
    })
  : { before: null, after: null, grew: false, thrown: false };
// ★음성 대조군 — HTML 에 문자열이 있는지(있는데 실행이 안 되면 **빌드 잘림**이다)
const inHtml = html.includes("__propaiEarly");
/**
 * ★음성 대조군을 **손으로 적지 않는다**(독립 리뷰 MINOR): `themeBootstrap` 을 손대면 대조군이
 *   조용히 죽고 이 프로브가 영구 `exit 2` 가 된다. layout 이 인라인하는 **다른 스크립트**가
 *   HTML 에 있는지로 조회기 생존을 증명한다 — 그 스크립트의 특징 문자열을 소스에서 파생시킨다.
 */
const themeInHtml = await (async () => {
  try {
    const { readFileSync } = await import("node:fs");
    const src = readFileSync(new URL("../../app/layout.tsx", import.meta.url), "utf8");
    // `themeBootstrap` 리터럴에서 충분히 특징적인 조각을 뽑는다(따옴표 포함 40자).
    const m = src.match(/const themeBootstrap = `([^`]{40,})`/);
    if (!m) return html.includes("data-theme"); // 파생 실패 시 최소 대조군
    const needle = m[1].slice(0, 60);
    return html.includes(needle);
  } catch { return html.includes("data-theme"); }
})();

// ★판정은 **순수 함수 하나**로 — 그래야 양성/음성 둘 다 테스트로 태울 수 있다
//   (초판은 판정이 본문에 있어 양성 방향을 못 태웠고, 그 사이 신호가 반전돼 있었다).
const verdict = decideEarlyCaptureVerdict({ runtime, caught });
console.log(JSON.stringify({ target: TARGET, inHtml, themeInHtml, runtime, caught, verdict }, null, 1));
await browser.close();
browser = undefined;

if (!themeInHtml) { console.error("★대조군 실패 — theme 부트스트랩조차 HTML 에 없다. 조회가 틀렸다(측정 무효)."); process.exit(2); }
if (verdict) {
  console.log(runtime.closed
    ? "◎ 조기 포착이 배포본에서 살아 있다(수집기가 버퍼를 인계했다 — closed=true)"
    : "◎ 조기 포착이 배포본에서 살아 있다(오류를 실제로 담았다)");
  process.exit(0);
}
if (inHtml) console.error("★HTML 에는 있는데 **실행되지 않는다** — 빌드가 스크립트를 잘랐을 가능성이 높다\n" +
  "  (보간 템플릿을 `+` 로 이으면 **좌변의 마지막 치환 이후 꼬리**가 버려진다 — 2026-08-27 실측).");
else console.error("★배포본에 아예 없다 — 그 커밋이 실제로 배포됐는지 sw.js 로 확인하라.");
process.exit(1);
} catch (e) {
  // ★네트워크·내비게이션·브라우저 실패는 **판정이 아니다.** 무효로 죽는다.
  console.error("★측정 무효 — 판정에 필요한 값을 재지 못했다:", String(e?.message ?? e).slice(0, 300));
  try { if (browser) await browser.close(); } catch { /* noop */ }
  process.exit(2);
}
