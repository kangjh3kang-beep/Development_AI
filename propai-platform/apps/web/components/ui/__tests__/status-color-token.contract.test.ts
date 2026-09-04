/**
 * 상태색 토큰 계약 — 상태 의미를 Tailwind 팔레트로 표현하지 않는다.
 *
 * ★근거는 DESIGN.md:335 다: "❌ Tailwind 팔레트로 상태색 표현(`emerald-500`·`rose-500`·
 *   `amber-500` 등) — 테마 전환 시 안 바뀐다." 이 금지는 **지금도 참**이다(2026-08-16 실측):
 *
 *     .text-emerald-400{color:var(--color-emerald-400)}   ← 단일 값, 테마 분기 없음
 *     --status-success: #3A9668 (:root) / #22c55e (.dark)  ← 테마별로 갈린다
 *
 *   ※같은 날 그림자(B4.1)는 정반대였다 — `shadow-lg` 는 `@theme inline` 이 이미
 *     `var(--shadow-lg)` 로 수렴시켜 **치환해도 CSS 가 안 바뀌는 유령 부채**였다.
 *     둘을 같은 "팔레트 부채"로 묶으면 안 된다. 판정 기준은 **테마 분기 여부**다.
 *
 * ★이전 캠페인이 여기서 멈췄던 이유(해소됨): `var()` 에 opacity 수정자를 못 붙인다고
 *   알려져 있었으나, Tailwind v4 는 `bg-[var(--x)]/10` 을
 *   `color-mix(in oklab, var(--x) 20%, transparent)` 로 컴파일한다(라이브 CSS 1,245회 확인).
 *
 * ★적용 범위: **상태 칩 서명**(같은 색의 `bg-<색>-<N>` 의 10~15% 알파 + `border-*` 동시 출현)이 있는 파일만
 *   바꿨다. 장식·브랜드 강조 용례는 손대지 않는다 — 이전 캠페인이 "의도적 브랜드 서피스"로
 *   판정한 영역이고, 기계적 서명이 없으면 그 판단을 사람이 다시 해야 하기 때문이다.
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

const WEB = path.resolve(__dirname, "../../..");
const STATUS = { amber: "warning", emerald: "success", rose: "error" } as const;

function walk(dir: string, out: string[] = []): string[] {
  for (const e of readdirSync(dir)) {
    if (e === "node_modules" || e === ".next" || e === ".open-next") continue;
    const p = path.join(dir, e);
    if (statSync(p).isDirectory()) walk(p, out);
    else if (p.endsWith(".tsx") && !p.includes("__tests__") && !p.includes(".test.")) out.push(p);
  }
  return out;
}

const FILES = walk(path.join(WEB, "components")).concat(walk(path.join(WEB, "app")));

/** 상태 칩 서명 — 같은 색의 반투명 배경 + 보더가 함께 있으면 상태 표현이다(DESIGN.md:271). */
function hasChipSignature(src: string, color: string): boolean {
  return new RegExp(`bg-${color}-\\d+/1[0-5]\\b`).test(src)
    && new RegExp(`border-${color}-`).test(src);
}

describe("상태색 토큰 계약", () => {
  it("★상태 칩 서명이 있는 파일은 팔레트 상태색을 쓰지 않는다", () => {
    const offenders: string[] = [];
    for (const f of FILES) {
      const src = readFileSync(f, "utf8");
      for (const color of Object.keys(STATUS)) {
        if (!hasChipSignature(src, color)) continue;
        // 서명이 있는데 팔레트 표기가 남아 있으면 테마 전환에서 빠진다.
        const left = src.match(new RegExp(`\\b(bg|border|text)-${color}-(400|500)\\b`, "g"));
        if (left) offenders.push(`${path.relative(WEB, f)}: ${[...new Set(left)].join(",")}`);
      }
    }
    expect(offenders, `상태 칩인데 팔레트 색이 남았다:\n${offenders.join("\n")}`).toEqual([]);
  });

  it("★토큰 표기가 실제로 쓰이고 있다 — 공허진리 방지", () => {
    // 위 단언은 "서명 파일이 0개"여도 통과한다. 대상이 실재하는지 먼저 잠근다.
    const used = FILES.filter((f) =>
      /\[var\(--status-(success|warning|error)\)\]/.test(readFileSync(f, "utf8")));
    expect(used.length).toBeGreaterThan(30);
  });

  it("★opacity 수정자를 붙인 형태가 살아 있다(v4 color-mix 경로)", () => {
    const withAlpha = FILES.filter((f) =>
      /\[var\(--status-(success|warning|error)\)\]\/\d+/.test(readFileSync(f, "utf8")));
    expect(withAlpha.length).toBeGreaterThan(20);
  });
});
