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

// ★전자상거래법 3종 — 검수가 이 화면에서 확인한다
const REQUIRED = ["강재희", "682-38-01463", "통신판매업 신고번호"];

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

// 2·3·4 는 왜 없는지 남긴다 — 빈 자리를 설명 없이 두지 않는다
fs.writeFileSync(
  path.join(OUT, "BLOCKED_02_03_04.txt"),
  [
    "네이버 검수 제출 캡처 2·3·4 는 현재 촬영 불가합니다.",
    "",
    "이유: 네이버 authorize 가 로그인 화면 대신 오류 페이지로 리다이렉트합니다.",
    "  location.replace(nid.naver.com/login/ext/error.inapp?...disp_stat=207)",
    "  → 정보제공 동의창(2번)에 도달하지 못하므로 3·4번도 불가능합니다.",
    "",
    "선행 조치: 네이버 개발자센터 → API 설정 → 서비스 URL / Callback URL 등록",
    "  https://www.4t8t.net/{ko,en,zh-CN}/naver/callback",
    "  https://4t8t.net/{ko,en,zh-CN}/naver/callback",
    "",
    "등록 후 이 스크립트를 다시 실행하면 1번이 갱신되고,",
    "2·3·4 는 실제 네이버 계정 로그인이 필요하므로 사용자가 직접 촬영해야 합니다.",
  ].join("\n"),
  "utf-8",
);

fs.writeFileSync(path.join(OUT, "report.json"), JSON.stringify(report, null, 2), "utf-8");
console.log(JSON.stringify(report, null, 2));

const bad = report.filter((r) => r.missingRequired.length > 0 || !r.naverButton);
if (bad.length) {
  console.error("\n★검수 요구 항목이 빠진 화면이 있습니다:");
  for (const b of bad) console.error(`  ${b.viewport} ${b.url} → 누락 ${JSON.stringify(b.missingRequired)} · 네이버버튼 ${b.naverButton}`);
  process.exit(1);
}
console.log("\n::VERDICT=OK 모든 화면에 전자상거래법 3종 + 네이버 로그인 버튼 실재");
