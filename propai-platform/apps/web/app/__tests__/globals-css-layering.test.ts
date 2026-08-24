/**
 * ★구조 불변식 — **요소 기본값은 `@layer` 안에 있어야 한다**.
 *
 * ## 왜 (라이브 실측 2026-08-24)
 *
 * Tailwind v4(`@import "tailwindcss"`)는 유틸리티를 `@layer utilities` 에 넣는다.
 * CSS 캐스케이드 레이어 규칙상 **언레이어드 선언은 어떤 레이어보다 우선**한다 —
 * 특이도와 무관하다. 따라서 `@layer` 밖의 요소 규칙은 **모든 유틸리티를 이긴다.**
 *
 * 실제 브라우저(`getComputedStyle`, 4t8t.net)에서 잰 값:
 *
 *     <h1 class="font-medium">   기대 500  → **700**      유틸리티 무시
 *     <h2 class="font-normal">   기대 400  → **600**      무시
 *     <p  class="leading-none">  기대 16px → **27.2px**   무시
 *     <button class="text-xs">   기대 12px → **16px**     무시
 *     <div class="font-medium">  기대 500  → 500          ← 대조군: 정상
 *
 * 대조군이 정상이라 "유틸리티 전반의 문제"가 아니라 **언레이어드 규칙이 있는 요소 한정**이다.
 * 영향 실측: 헤딩 **380** · `<p>` **417** · 버튼 **47** 곳의 유틸리티가 조용히 무시됐다.
 * ★우회 흔적(`!important`)은 **0건** — 아무도 이 사실을 몰랐다는 뜻이다.
 *
 * ## 왜 이 테스트인가
 *
 * 종전에 `a { color: inherit }` **하나만** base 로 옮기고 **형제를 스윕하지 않아**
 * 같은 결함이 남았다(규율 §6). 인스턴스를 고치지 말고 **구조를 잠근다** —
 * 새 요소 규칙을 `@layer` 밖에 쓰면 여기서 빨개진다.
 */
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const HERE = dirname(fileURLToPath(import.meta.url));
const CSS = resolve(HERE, "../globals.css");

/** `@layer …{ }` 범위를 **중괄호 균형**으로 정확히 잘라낸다(고정 창 금지 — 실수 #42). */
function layerSpans(src: string): Array<[number, number]> {
  const spans: Array<[number, number]> = [];
  for (const m of src.matchAll(/@layer[^{]*\{/g)) {
    const s = (m.index ?? 0) + m[0].length - 1;
    let d = 0;
    for (let j = s; j < src.length; j += 1) {
      if (src[j] === "{") d += 1;
      else if (src[j] === "}") {
        d -= 1;
        if (d === 0) { spans.push([m.index ?? 0, j + 1]); break; }
      }
    }
  }
  return spans;
}

const ELEM =
  "(?:html|body|p|h[1-6]|a|li|ul|ol|button|input|select|textarea|table|td|th|img|svg)";

function unlayeredElementRules(): string[] {
  const src = readFileSync(CSS, "utf-8").replace(/\/\*[\s\S]*?\*\//g, "");
  const spans = layerSpans(src);
  const inLayer = (i: number) => spans.some(([a, b]) => i >= a && i < b);
  const re = new RegExp(
    `^([ \\t]*${ELEM}(?:[ \\t]*,[ \\t]*\\n?[ \\t]*${ELEM})*[ \\t]*)\\{`,
    "gm",
  );
  const out: string[] = [];
  for (const m of src.matchAll(re)) {
    if (!inLayer(m.index ?? 0)) out.push(m[1].trim().replace(/\s+/g, " "));
  }
  return out;
}

describe("★globals.css — 요소 기본값은 @layer 안에 있어야 유틸리티가 이긴다", () => {
  it("파서가 실제로 @layer 를 찾았다(공허한 초록 방지)", () => {
    // ★이 가드가 단언 **앞에** 있어야 한다 — 파서가 깨져 spans 가 비면
    //   "언레이어드 0건"이 공허하게 참이 된다(§A-2).
    const src = readFileSync(CSS, "utf-8");
    expect(layerSpans(src).length, "@layer 블록을 하나도 못 찾았다 — 파서가 낡았다")
      .toBeGreaterThanOrEqual(3);
    expect(src).toContain('@import "tailwindcss"');   // 전제: v4 레이어 체계
  });

  it("★@layer 밖에 요소 규칙이 없다 — 있으면 모든 유틸리티를 이긴다", () => {
    const bad = unlayeredElementRules();
    expect(
      bad,
      `@layer 밖 요소 규칙 ${bad.length}건 — 이 선택자에 걸리는 요소는 Tailwind 유틸리티가 ` +
      `**조용히 무시**된다(특이도 무관). \`@layer base { … }\` 안으로 옮겨라: ${bad.join(" | ")}`,
    ).toEqual([]);
  });

  it("★대조군 — 옮긴 규칙이 사라지지 않았다(이동이지 삭제가 아니다)", () => {
    // 규칙을 통째로 지워도 위 테스트는 통과한다. 그건 고침이 아니라 파괴다.
    const src = readFileSync(CSS, "utf-8");
    for (const needle of [
      "font-family: var(--font-display)",   // h1..h6
      "line-height: 1.7",                   // p
      "font: inherit",                      // button/input/select/textarea
      "scroll-behavior: smooth",            // html
    ]) {
      expect(src, `옮기는 과정에서 규칙이 사라졌다: ${needle}`).toContain(needle);
    }
  });
});
