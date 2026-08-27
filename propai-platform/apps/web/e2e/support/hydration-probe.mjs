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
 *        기대: hydration>=1 → exit 0. `hydration:0` 은 **세 갈래**로 갈린다 —
 *        핸들러 미실행·URL 불일치·개변 텍스트 없음은 **exit 2(무효)**, 그 셋이 아닌데 0 이면
 *        **exit 1(프로브 사망)** 이고 그 뒤의 "0건"은 근거가 아니다.
 *   1-c) ★**음성 대조군**(가로채기 자체가 #418 을 만들지 않는지):
 *        PROBE_NO_MUTATE=1 node e2e/support/hydration-probe.mjs control /ko/permits
 *        기대: hydration==0 (exit 0). 1 이상이면 위 양성이 **위양성**이다.
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
 *   · ★**서비스워커가 내비게이션을 가로채면 `page.route` 는 발화하지 않는다.**
 *     실측 2026-08-27 — 핸들러가 **아예 안 돌아** 대조군이 조용히 무효가 됐다(음성으로 읽을 뻔했다).
 *     ★★**초판은 여기에 거짓 인과를 적었다**: *"그러므로 `context.route` **+** `serviceWorkers:'block'`
 *     이어야 한다"*. 두 변수를 **동시에** 바꾼 뒤 그 합집합을 필요조건으로 적은 것이고,
 *     독립 리뷰가 2×2 로 반증했다 — **둘 중 하나면 충분하다**:
 *
 *         │              page.route          context.route
 *         │ SW 허용      미발화 · exit 2      발화 · hydration=1 · exit 0
 *         │ SW 차단      발화 · exit 0        발화 · exit 0
 *
 *     그래서 이 파일은 `ctx.route` **하나만** 쓰고 SW 는 건드리지 않는다 —
 *     그러면 대조군 회차와 측정 회차가 **같은 환경**이 되어 생존 증명이 그대로 이전된다.
 *   · 그리고 `handlerRan`·`htmlLen`·`picked` 를 함께 찍어
 *     **"핸들러 미실행" 과 "문자열 없음" 을 가른다**(둘 다 `hydration: 0` 을 낸다).
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

import { countHydration, buildRunSample, isCollectorAlive, samePath, pickMutableText, decideControlVerdict, decideRunVerdict } from "../../lib/hydration/probe-text.mjs";

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
// ★모드별로 컨텍스트 옵션을 갈지 않는다 — control 이 증명한 "프로브 생존" 이 run 회차로 그대로
//   이전되려면 **두 회차의 환경이 같아야** 한다. (초판은 control 에만 `serviceWorkers:'block'` 을
//   걸었는데, 리뷰 실측상 `ctx.route` 만으로 SW 허용 환경에서도 발화한다 — 불필요했고 환경만 갈랐다.)
const ctx = await browser.newContext({ locale: "ko-KR", timezoneId: "Asia/Seoul" });
const page = await ctx.newPage();

if (MODE === "dump") {
  await login(page, LIVE);
  await page.goto(LIVE + (PATHS[0] ?? "/ko/regulations"), { waitUntil: "domcontentloaded" });
  await page.waitForLoadState("networkidle").catch(() => {});
  await page.waitForTimeout(5000);
  const ls = await page.evaluate(() => Object.fromEntries(Object.entries(localStorage)));
  writeFileSync(LS_FILE, JSON.stringify(ls));
  await browser.close();
  console.log("떴다:", LS_FILE, "· 키", Object.keys(ls).length, "개 (★토큰 포함 — 커밋 금지)");
} else if (MODE === "control") {
  // ── ★양성 대조군 — 이 프로브가 프로덕션 번들에서 #418 을 잡는지 증명한다 ──
  //   서버가 그린 텍스트 한 곳을 바꾸면 클라이언트 렌더와 달라져 **하이드레이션 텍스트 불일치**가 난다.
  //   실측(2026-08-27 · 라이브 propai-v002822): 개변 → `Minified React error #418 … args[]=text`,
  //   **개변만 무력화하면 0** (아래 PROBE_NO_MUTATE) — 즉 양성의 원인은 **가로채기가 아니라 개변**이다.
  const errs = [];
  page.on("pageerror", (e) => errs.push("[pageerror] " + String(e?.message ?? e)));
  page.on("console", (m) => { if (m.type() === "error") errs.push("[console] " + m.text()); });
  await login(page, BASE);
  const target = PATHS[0] ?? "/ko/permits";
  // ★음성 대조군 — 같은 가로채기를 하되 **개변만 하지 않는다.** 이게 없으면
  //   "가로채기 자체가 #418 을 만든다"는 위양성을 영원히 구별할 수 없다(특이도 축).
  const noMutate = process.env.PROBE_NO_MUTATE === "1";
  let handlerRan = false, htmlLen = 0, picked = null;
  await ctx.route("**" + target, async (route) => {
    handlerRan = true;
    const r = await route.fetch();
    let html = await r.text();
    htmlLen = html.length;
    const cand = pickMutableText(html);
    if (cand && !noMutate) {
      html = html.replace(">" + cand.text + "<", ">" + cand.text + "XX<");
    }
    if (cand) picked = { text: cand.text, at: cand.at, context: cand.context.replace(/\s+/g, " ") };
    await route.fulfill({ response: r, body: html });
  });
  const before = errs.length;
  await page.goto(BASE + target, { waitUntil: "domcontentloaded" });
  await page.waitForLoadState("networkidle").catch(() => {});
  await page.waitForTimeout(5000);
  const hydration = countHydration(errs.slice(before));
  const urlOk = samePath(page.url(), target, BASE);
  console.log(JSON.stringify({ mode: noMutate ? "control-negative" : "control", target,
    finalUrl: page.url(), urlOk, handlerRan, htmlLen, picked, hydration,
    sample: errs.slice(before).filter((e) => /418|Hydration/.test(e)).slice(0, 1) }, null, 1));
  await browser.close();   // ★아래 분기들은 전부 process.exit 하거나 이 블록에서 끝난다(파일 끝 close 는 run 전용)
  const verdict = decideControlVerdict({ handlerRan, urlOk, picked, hydration, noMutate });
  if (verdict.code === 0) console.log(verdict.message);
  else console.error(verdict.message);
  if (verdict.code !== 0) process.exit(verdict.code);
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
    const finalUrl = page.url();
    const collectorAlive = isCollectorAlive(slice);
    const hydration = countHydration(slice);          // ★control 과 **같은 계수 경로**
    const urlOk = samePath(finalUrl, path, BASE);      // ★한글 경로·쿼리에서 위양성 나던 것 교정
    console.log(JSON.stringify({ path, finalUrl, collectorAlive, urlOk, hydration,
      sample: buildRunSample(slice) }, null, 1));
    // ★대조군을 **찍기만 하면 아무것도 막지 못한다** — 종료코드로 단언한다.
    //   막겠다고 적어 둔 실패(리다이렉트로 다른 페이지를 재고 "0건")가 조용히 통과하던 것을 고친다.
    if (!collectorAlive) { console.error(`★수집기가 죽었다(${path}) — 이 회차의 '0건'은 근거가 아니다`); invalid = true; }
    if (!urlOk) { console.error(`★목표와 다른 페이지를 쟀다: ${path} → ${finalUrl}`); invalid = true; }
    if (hydration > 0) found += hydration;
  }
  await browser.close();
  const v = decideRunVerdict({ invalid, found });   // ★판정은 순수 함수 하나로(계약이 테스트로 잠긴다)
  if (v.code !== 0) process.exit(v.code);
}
