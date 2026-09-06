/**
 * 네이버 로그인 검수 제출용 화면 캡처.
 *
 * ★네이버 요구(반려 안내 원문):
 *   1. 네이버 로그인 버튼을 적용한 화면
 *   2. 버튼 클릭 시 보이는 네이버 정보제공 동의창
 *   3. 신규 회원가입 과정의 추가 정보 입력 화면(있다면)
 *   4. 네이버 로그인 완료까지 보여지는 화면
 *
 * ★2·3·4 는 **Callback URL 이 등록돼야** 촬영 가능하다 —
 *   지금은 네이버가 authorize 에서 오류 페이지로 보내 동의창에 도달하지 못한다.
 *   이 스크립트는 1번을 찍고, 나머지는 **막힌 이유를 파일로 남긴다**(빈 자리를 숨기지 않는다).
 *
 * 사용: BASE=http://localhost:3100 node e2e/_naver-verify/capture.mjs
 */
import { chromium } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

const BASE = process.env.BASE || "https://www.4t8t.net";
const OUT = process.env.OUT || path.join(process.cwd(), "e2e", "_naver-verify", "shots");
fs.mkdirSync(OUT, { recursive: true });

// ★전자상거래법 표시항목 — **정본에서 파생**한다.
//   2026-09-06 실측: 여기가 손으로 고른 **3개 목록**이었다. 같은 날 테스트 락에서
//   같은 결함(법정 6종 중 3종만 검사)을 고치면서 **이 형제를 안 훑었다**(§29).
//   손수 목록은 곧 상한이 되고, 그 상한이 **검수 제출물의 품질 상한**이 된다.
const footerSrc = fs.readFileSync(
  path.join(process.cwd(), "components", "layout", "SiteFooter.tsx"),
  "utf-8",
);
const keyList = /LEGAL_DISCLOSURE_KEYS\s*=\s*\[(.*?)\]/s.exec(footerSrc);
if (!keyList) throw new Error("★정본 LEGAL_DISCLOSURE_KEYS 를 못 찾았다 — 판정 불가");
const infoBlock = /BUSINESS_INFO\s*=\s*\{(.*?)\n\}\s*as const;/s.exec(footerSrc);
if (!infoBlock) throw new Error("★정본 BUSINESS_INFO 를 못 찾았다 — 판정 불가");
const VALUES = Object.fromEntries(
  [...infoBlock[1].matchAll(/(\w+):\s*"([^"]+)"/g)].map((m) => [m[1], m[2]]),
);
const KEYS = [...keyList[1].matchAll(/"([a-zA-Z]+)"/g)].map((m) => m[1]);
if (KEYS.length < 6) throw new Error(`★표시항목 ${KEYS.length}개 — 6 미만이면 판정 불가`);
const REQUIRED = KEYS.map((k) => VALUES[k]);
// 라벨도 함께 — 값만 있고 무엇인지 안 쓰면 검수자가 못 찾는다
REQUIRED.push("통신판매업 신고번호", "사업자등록번호");
// ★대조군 — 없어야 할 문자열. 이것이 「있음」이면 조회기가 고장난 것이다.
const CONTROL = "ZZZ-NOT-PRESENT";

const VIEWPORTS = [
  { name: "pc", width: 1440, height: 1200 },
  { name: "mobile", width: 390, height: 844 }, // ★네이버는 「PC/모바일」을 모두 요구한다
];

const report = [];

for (const vp of VIEWPORTS) {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: vp.width, height: vp.height } });

  for (const [slug, url] of [
    ["01-home", `${BASE}/ko`],
    ["02-login", `${BASE}/ko/login`],
  ]) {
    await page.goto(url, { waitUntil: "networkidle", timeout: 60000 });
    const file = path.join(OUT, `${vp.name}_${slug}.png`);
    await page.screenshot({ path: file, fullPage: true });

    // ★찍은 것으로 끝내지 않는다 — 요구 항목이 **실제로 화면에 있는지** 태운다
    const text = await page.evaluate(() => document.body.innerText);
    // ★대조군을 본판정보다 **먼저** — 순서가 바뀌면 사람이 먼저 결론을 낸다
    if (text.includes(CONTROL)) throw new Error(`★대조군 오염(${url}) — 조회기 무효`);
    if (text.length < 200) throw new Error(`★본문 ${text.length}자(${url}) — 너무 작다, 판정 불가`);
    const missing = REQUIRED.filter((k) => !text.includes(k));
    const hasNaverButton = text.includes("네이버 로그인");
    report.push({
      viewport: vp.name,
      url,
      file: path.relative(process.cwd(), file),
      bytes: fs.statSync(file).size,
      naverButton: hasNaverButton,
      missingRequired: missing,
    });
  }
  await browser.close();
}

// ★2·3·4 는 왜 이 폴더에 없는지 남긴다 — 빈 자리를 설명 없이 두지 않는다.
//   2026-09-06 정정: 종전 문구는 «네이버 authorize 가 오류 페이지로 보낸다» 였는데
//   Callback URL 등록 후 **동의창과 완료 화면까지 도달한다**(사용자 실측).
//   ★낡은 설명을 그대로 제출하면 심사자에게 **틀린 정보**를 준다.
fs.writeFileSync(
  path.join(OUT, "README_02_03_04.txt"),
  [
    "네이버 검수 제출 캡처 2·3·4 는 이 폴더에 없습니다 — 자동 촬영이 불가능하기 때문입니다.",
    "",
    "[상태] OAuth 왕복은 정상 동작합니다.",
    "  Callback URL 등록 완료 · authorize → 정보제공 동의창 → 콜백 완료 화면까지 도달 확인.",
    "  (2026-09-06 이전의 「authorize 가 오류 페이지로 리다이렉트」 상태는 해소되었습니다.)",
    "",
    "[왜 자동으로 못 찍는가]",
    "  2. 정보제공 동의창 — 네이버가 호스팅하는 화면이고 **실제 네이버 계정 로그인**이 필요합니다.",
    "  3. 추가 정보 입력 화면 — 신규 회원가입 경로에서만 나타납니다.",
    "  4. 로그인 완료 화면 — 2번을 통과해야 도달합니다.",
    "  자동화 도구에 실제 계정 자격증명을 넣지 않습니다(자격증명을 코드·산출물에 두지 않는 원칙).",
    "",
    "[촬영 방법 — 사용자가 직접]",
    "  ① https://www.4t8t.net/ko/login 에서 「네이버 로그인」 클릭",
    "  ② 네이버 로그인 → **정보제공 동의창**이 뜨면 그 화면 캡처   → 2번",
    "  ③ (신규 계정이면) 추가 정보 입력 화면 캡처                  → 3번",
    "  ④ 동의 후 이동하는 **로그인 완료 화면** 캡처                 → 4번",
    "  ★2·3·4 는 PC·모바일 중 한 쪽만 있어도 되지만, 1번은 양쪽 다 요구합니다.",
  ].join("\n"),
  "utf-8",
);

fs.writeFileSync(path.join(OUT, "report.json"), JSON.stringify(report, null, 2), "utf-8");
console.log(JSON.stringify(report, null, 2));

// ★판정 — 두 축을 **따로** 본다. 뭉치면 위양성이 난다.
//   ㉠ 법정 표시항목: **모든** 캡처 화면에 있어야 한다(검수자가 어느 화면을 보든).
//   ㉡ 네이버 로그인 버튼: 네이버 요구는 «버튼을 적용한 화면» **한 장**이다.
//      홈(/ko)은 마케팅 랜딩이라 버튼이 없는 것이 정상 — 여기에 요구하면 **정상을 위반으로 신고**한다.
//      2026-09-06 실측(원문 grep): /ko 에 「네이버」 0건 · /ko/login 에 「네이버 로그인」 실재.
const missingLegal = report.filter((r) => r.missingRequired.length > 0);
const loginShots = report.filter((r) => r.url.endsWith("/login"));
const loginWithoutButton = loginShots.filter((r) => !r.naverButton);

let failed = false;
if (missingLegal.length > 0) {
  failed = true;
  console.error("\n★법정 표시항목이 빠진 화면:");
  for (const b of missingLegal)
    console.error(`  ${b.viewport} ${b.url} → 누락 ${JSON.stringify(b.missingRequired)}`);
}
// ★공허 진리 가드 — 로그인 화면을 한 장도 안 찍었으면 「버튼 위반 0」은 무의미하다
if (loginShots.length === 0) {
  failed = true;
  console.error("\n★로그인 화면을 한 장도 찍지 못했다 — 버튼 판정이 공허하다");
}
if (loginWithoutButton.length > 0) {
  failed = true;
  console.error("\n★로그인 화면에 네이버 버튼이 없다:");
  for (const b of loginWithoutButton) console.error(`  ${b.viewport} ${b.url}`);
}
if (failed) process.exit(1);
console.log(
  `\n::VERDICT=OK 표시항목 ${REQUIRED.length}종 × 화면 ${report.length}장 전수 · ` +
    `네이버 버튼 로그인화면 ${loginShots.length}/${loginShots.length}`,
);
