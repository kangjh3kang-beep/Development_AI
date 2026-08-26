/**
 * 하이드레이션(React #418) **재현·귀속 프로브**.
 *
 * 사용:
 *   0) 자격증명은 **환경변수로만** 준다(기본값 없음 — 없으면 exit 2):
 *        export PROBE_EMAIL=… PROBE_PASSWORD=…
 *   1) 라이브에서 로그인 상태의 localStorage 를 떠 놓는다(토큰 포함 — **커밋 금지**):
 *        node e2e/support/hydration-probe.mjs dump   (cwd = apps/web)   → /tmp/live_ls.json
 *   1-b) ★**양성 대조군**(이 프로브가 정말 #418 을 잡는지 증명):
 *        node e2e/support/hydration-probe.mjs control /ko/permits
 *        서버 HTML 의 텍스트 한 곳을 하이드레이션 직전에 바꿔 **강제로 불일치**를 만든다.
 *        기대: hydration>=1 (exit 0). 0 이면 **프로브가 죽은 것**이므로 그 뒤의 "0건"은 근거가 아니다.
 *   2) 로컬 dev(개발 모드 React 는 **컴포넌트 이름과 어긋난 텍스트를 그대로 찍는다**)에 이식:
 *        cd apps/web && npx next dev -p 3411
 *        PROBE_BASE=http://localhost:3411 node e2e/support/hydration-probe.mjs run /ko/regulations
 *
 * ★왜 이 형태인가(2026-08-26 실측으로 얻은 규율)
 *   · **회차마다 새 컨텍스트로 재면 재현되지 않는다** — 한 세션 안에서 연속 하드 내비해야 난다.
 *   · **대조군 없이 "0건"을 말하지 마라.** 이 스크립트는 매 회차 ①수집기 생존(일부러 던진 에러가
 *     잡히는가) ②최종 URL 이 목표와 같은가(리다이렉트면 **다른 페이지를 잰 것**)를 함께 단언한다.
 *     실제로 로그인 없이 재다가 다섯 회차 전부 `/ko/login` 을 재고 "0건" 을 얻을 뻔했다.
 *   · **에러의 `args` 를 먼저 읽어라.** `args[]=text` 면 텍스트 불일치라 노드 유무 수정으로는 안 없어진다.
 *   · ★**서비스워커가 `page.route` 를 무력화한다.** 라이브에서 HTML 을 가로채려면
 *     `context.route` + `serviceWorkers: "block"` 이어야 한다 — 실측 2026-08-27: `page.route` 는
 *     핸들러가 **아예 발화하지 않아** 대조군이 조용히 무효가 됐다(그걸 음성으로 읽을 뻔했다).
 *     그래서 control 모드는 `handlerRan`·`htmlLen`·`picked` 를 함께 찍어
 *     **"핸들러 미실행" 과 "문자열 없음" 을 가른다.**
 *   · **기능 보존을 함께 단언하라** — 게이트로 기능을 죽여도 "오류 0" 은 나온다(공허한 초록).
 */
import { chromium } from "@playwright/test";
import { readFileSync, writeFileSync } from "node:fs";

const MODE = process.argv[2] ?? "run";
const PATHS = process.argv.slice(3);
const BASE = process.env.PROBE_BASE ?? "https://4t8t.net";
const LIVE = process.env.PROBE_LIVE ?? "https://4t8t.net";
const LS_FILE = process.env.PROBE_LS ?? "/tmp/live_ls.json";
// ★자격증명에 **기본값을 두지 않는다** — 저장소에 평문으로 남으면 그 자체가 유출이다.
//   미설정이면 조용히 비로그인으로 재는 대신 **시끄럽게 실패**한다(그 침묵이 "0건" 오보를 만든다).
const EMAIL = process.env.PROBE_EMAIL;
const PASSWORD = process.env.PROBE_PASSWORD;
if (!EMAIL || !PASSWORD) {
  console.error("★PROBE_EMAIL / PROBE_PASSWORD 를 주지 않았다 — 로그인 없이 재면 라우트가 /ko/login 으로\n" +
    "  리다이렉트되어 '0건'이 나온다(실측: 다섯 회차를 그렇게 잃을 뻔했다). 측정 무효로 중단한다.");
  process.exit(2);
}

async function login(page, base) {
  await page.goto(base + "/ko/login", { waitUntil: "domcontentloaded" });
  await page.waitForLoadState("networkidle").catch(() => {});
  await page.waitForTimeout(2000); // 하이드레이션 완료 전에 채우면 **조용히 비워진다**(실측)
  for (let a = 0; a < 4; a++) {
    await page.click('input[name=email]');
    await page.fill('input[name=email]', "");
    await page.type('input[name=email]', EMAIL, { delay: 20 });
    await page.fill('input[name=password]', PASSWORD);
    const t = await page.evaluate(() => ({
      e: document.querySelector("input[name=email]").value,
      p: document.querySelector("input[name=password]").value.length,
    }));
    if (t.e === EMAIL && t.p === PASSWORD.length) break;
    await page.waitForTimeout(800);
  }
  await Promise.all([
    page.waitForURL((u) => !/\/login/.test(u.toString()), { timeout: 45000 }).catch(() => {}),
    page.click("button[type=submit]"),
  ]);
  await page.waitForLoadState("networkidle").catch(() => {});
  if (/\/login/.test(page.url())) throw new Error("★로그인 실패 — 측정 무효");
}

const browser = await chromium.launch();
// ★control 모드는 **서비스워커를 차단**해야 한다 — SW 가 내비게이션을 가로채면 라우트 핸들러가 발화하지 않는다.
const ctx = await browser.newContext({
  locale: "ko-KR", timezoneId: "Asia/Seoul",
  ...(MODE === "control" ? { serviceWorkers: "block" } : {}),
});
const page = await ctx.newPage();

if (MODE === "dump") {
  await login(page, LIVE);
  await page.goto(LIVE + (PATHS[0] ?? "/ko/regulations"), { waitUntil: "domcontentloaded" });
  await page.waitForLoadState("networkidle").catch(() => {});
  await page.waitForTimeout(5000);
  const ls = await page.evaluate(() => Object.fromEntries(Object.entries(localStorage)));
  writeFileSync(LS_FILE, JSON.stringify(ls));
  console.log("떴다:", LS_FILE, "· 키", Object.keys(ls).length, "개 (★토큰 포함 — 커밋 금지)");
} else if (MODE === "control") {
  // ── ★양성 대조군 — 이 프로브가 프로덕션 번들에서 #418 을 잡는지 증명한다 ──
  //   서버가 그린 텍스트 한 곳을 바꾸면 클라이언트 렌더와 달라져 **하이드레이션 텍스트 불일치**가 난다.
  //   실측(2026-08-27 · 라이브): `본문으로 건너뛰기` 를 바꾸자
  //   `Minified React error #418 … args[]=text` — 실제 결함과 **같은 서명**이 나왔다.
  const errs = [];
  page.on("pageerror", (e) => errs.push("[pageerror] " + String(e?.message ?? e)));
  page.on("console", (m) => { if (m.type() === "error") errs.push("[console] " + m.text()); });
  await login(page, BASE);
  const target = PATHS[0] ?? "/ko/permits";
  let handlerRan = false, htmlLen = 0, picked = null;
  await ctx.route("**" + target, async (route) => {
    handlerRan = true;
    const r = await route.fetch();
    let html = await r.text();
    htmlLen = html.length;
    // ★바꿀 문자열을 **기억에서 지어내지 않는다** — 서버 HTML 에 실제로 있는 것만 고른다.
    for (const cand of ["본문으로 건너뛰기", "개발사업 전주기 관리플랫폼", "워크스페이스", "메뉴", "한국어"]) {
      const tag = ">" + cand + "<";
      if (html.includes(tag)) { html = html.replace(tag, ">" + cand + "XX<"); picked = cand; break; }
    }
    await route.fulfill({ response: r, body: html });
  });
  const before = errs.length;
  await page.goto(BASE + target, { waitUntil: "domcontentloaded" });
  await page.waitForLoadState("networkidle").catch(() => {});
  await page.waitForTimeout(5000);
  const hydration = errs.slice(before)
    .filter((e) => /Hydration failed|error #418|errors\/418|Text content/.test(e)).length;
  console.log(JSON.stringify({ mode: "control", target, handlerRan, htmlLen, picked, hydration,
    sample: errs.slice(before).filter((e) => /418|Hydration/.test(e)).slice(0, 1) }, null, 1));
  await browser.close();
  if (!handlerRan) { console.error("★라우트 핸들러가 발화하지 않았다 — 서비스워커가 가로챘을 수 있다. 이 회차는 **무효**다"); process.exit(2); }
  if (!picked) { console.error("★바꿀 텍스트를 서버 HTML 에서 찾지 못했다 — 후보 목록을 갱신하라. 이 회차는 **무효**다"); process.exit(2); }
  if (hydration < 1) { console.error("★대조군이 #418 을 못 만들었다 — **프로브가 죽었다.** 이 프로브로 잰 '0건'은 근거가 아니다"); process.exit(1); }
  console.log("대조군 통과 — 이 프로브는 프로덕션 번들에서 #418 을 잡는다");
} else {
  const errs = [];
  page.on("pageerror", (e) => errs.push("[pageerror] " + String(e?.message ?? e)));
  page.on("console", (m) => { if (m.type() === "error") errs.push("[console] " + m.text()); });
  if (BASE.includes("localhost")) {
    const ls = JSON.parse(readFileSync(LS_FILE, "utf8"));
    await page.addInitScript((d) => { for (const [k, v] of Object.entries(d)) localStorage.setItem(k, v); }, ls);
  } else {
    await login(page, BASE);
  }
  let invalid = false;
  let found = 0;
  for (const path of PATHS.length ? PATHS : ["/ko/regulations"]) {
    const before = errs.length;
    await page.goto(BASE + path, { waitUntil: "domcontentloaded" });
    await page.waitForLoadState("networkidle").catch(() => {});
    await page.waitForTimeout(5000);
    await page.evaluate(() => { setTimeout(() => { throw new Error("PROBE_ALIVE"); }, 0); });
    await page.waitForTimeout(600);
    const slice = errs.slice(before);
    const rel = slice.filter((e) => !/PROBE_ALIVE|Failed to load resource|net::|CORS/.test(e));
    const finalUrl = page.url();
    const collectorAlive = slice.some((e) => e.includes("PROBE_ALIVE"));
    const hydration = rel.filter((e) => /Hydration failed|error #418|errors\/418|Text content/.test(e)).length;
    const urlOk = new URL(finalUrl).pathname === path;
    console.log(JSON.stringify({ path, finalUrl, collectorAlive, urlOk, hydration,
      sample: rel.slice(0, 3).map((x) => x.slice(0, 400)) }, null, 1));
    // ★대조군을 **찍기만 하면 아무것도 막지 못한다** — 종료코드로 단언한다.
    //   막겠다고 적어 둔 실패(리다이렉트로 다른 페이지를 재고 "0건")가 조용히 통과하던 것을 고친다.
    if (!collectorAlive) { console.error(`★수집기가 죽었다(${path}) — 이 회차의 '0건'은 근거가 아니다`); invalid = true; }
    if (!urlOk) { console.error(`★목표와 다른 페이지를 쟀다: ${path} → ${finalUrl}`); invalid = true; }
    if (hydration > 0) found += hydration;
  }
  if (invalid) { await browser.close(); process.exit(2); }   // 무효 측정 — "0건"이라 말하지 마라
  if (found > 0) { await browser.close(); process.exit(1); } // 하이드레이션 불일치 실재
}
await browser.close();
