/**
 * 그림자 토큰 계약 — `shadow-*` 유틸이 **토큰으로 수렴**하는지 잠근다.
 *
 * ★왜 (2026-08-16):
 *   DESIGN.md B4.1 이 "Tailwind 기본 스케일(`shadow-sm`·`shadow-2xl`) ✕" 라고 적어 왔다.
 *   그런데 그건 **Tailwind v3 전제**였다. v4 에서는 `globals.css` 의 `@theme inline` 이
 *   기본 스케일을 `--shadow-*` 로 매핑해, `shadow-lg` 가 이미 `var(--shadow-lg)` 로 컴파일된다
 *   (라이브 CSS 실측: `.shadow-lg{--tw-shadow:var(--shadow-lg);…}`).
 *
 *   그 낡은 문구 때문에 완성도 감사가 `shadow-*` 사용 **160파일·394건을 "부채"로 집계**했고
 *   — 치환해도 산출 CSS 는 한 바이트도 안 바뀐다 — 그 수치가 "디자인 정합 78%" 의 실점 근거가 됐다.
 *   **문서가 만든 유령 부채**다.
 *
 * ★이 테스트가 지키는 것: 문서를 "유틸 이름 그대로 써도 된다"로 고쳤으므로, 그 전제인
 *   `@theme inline` 매핑과 값 SSOT 가 사라지면 **문서가 거짓이 되는 순간 여기서 깨져야 한다.**
 *   (매핑이 빠지면 `shadow-lg` 는 Tailwind 기본값으로 되돌아가 테마 전환에서 빠진다.)
 */
import { readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

const WEB = path.resolve(__dirname, "../..");
const REPO = path.resolve(WEB, "../..");

const GLOBALS = readFileSync(path.join(WEB, "app/globals.css"), "utf8");
const TOKENS = readFileSync(
  path.join(REPO, "packages/ui/src/styles/tokens.css"),
  "utf8",
);

/** DESIGN.md B4.1 이 열거한 스케일. 하나라도 매핑이 빠지면 그 단계만 조용히 테마를 잃는다. */
const SCALE = ["xs", "sm", "md", "lg", "xl", "2xl", "inner"] as const;

describe("그림자 토큰 계약", () => {
  it.each(SCALE)("★@theme inline 이 shadow-%s 를 토큰으로 수렴시킨다", (k) => {
    // `--shadow-lg: var(--shadow-lg)` — 우변은 tokens.css 의 :root/.dark 를 런타임에 참조한다.
    // 이 줄이 사라지면 유틸이 Tailwind 기본값으로 돌아가 다크에서 깊이가 안 바뀐다.
    expect(GLOBALS).toMatch(
      new RegExp(`--shadow-${k.replace("2xl", "2xl")}:\\s*var\\(--shadow-${k}\\)`),
    );
  });

  it.each(SCALE)("★tokens.css 가 shadow-%s 를 라이트·다크 **양쪽**에 정의한다", (k) => {
    // 값이 한쪽에만 있으면 반대 테마에서 변수 미해결 → box-shadow 자체가 무효가 된다.
    const defs = TOKENS.match(new RegExp(`--shadow-${k}:\\s*[^;]+;`, "g")) ?? [];
    expect(defs.length).toBeGreaterThanOrEqual(2);
    // ★공허진리 방지 — 두 정의가 실제로 **다른 값**이어야 테마 전환이 의미를 갖는다.
    //   (같은 값이면 parity 는 있으나 깊이 대비가 없다 = 계약이 말하는 '라이트 얕고 다크 깊다' 위반)
    expect(new Set(defs).size).toBeGreaterThanOrEqual(2);
  });

  it("★값이 var() 자기참조로만 채워져 있지 않다(SSOT 실재 확인)", () => {
    // globals.css 만 보면 `--shadow-lg: var(--shadow-lg)` 라 순환처럼 보인다.
    // 실제 값은 tokens.css 에 있다 — 그 사실을 잠가 둔다(내가 이걸 순환참조로 오진했다).
    // 라이트: rgba(24,33,43,...) 중성 / 다크: rgba(0,0,0,...) 깊음 — 계약이 말하는 대비.
    expect(TOKENS).toMatch(/--shadow-lg:\s*0 [\d.]+px [\d.]+px rgba\(24, 33, 43/);
    expect(TOKENS).toMatch(/--shadow-lg:\s*0 [\d.]+px [\d.]+px rgba\(0, 0, 0/);
  });

  it("★DESIGN.md 가 더 이상 '기본 스케일 금지'라고 말하지 않는다", () => {
    const doc = readFileSync(path.join(REPO, "DESIGN.md"), "utf8");
    const b41 = doc.slice(doc.indexOf("### B4.1"), doc.indexOf("## B5."));
    expect(b41).not.toMatch(/기본 스케일\(`shadow-sm`·`shadow-2xl`\) ✕/);
    // 금지 대상은 임의값이다 — 그 규칙은 남아 있어야 한다.
    expect(b41).toMatch(/임의값/);
  });
});
