/**
 * 우세 용도지역 표시 락 — **내부 센티널이 화면에 맨몸으로 나가지 않는다**.
 *
 * ★실측(2026-08-24, 앞 세션): 화면에 `mixed_review_required 외 (혼재·분리검토)` 가 떴다.
 *   ★내가 라이브에서 **재현하지는 못했다**(입력 2필지가 한 zone 으로 합쳐져 조건에 도달
 *     하지 못함) — 발행 조건은 `special_parcel.py:1869` 소스에서 확인했다(동률 ±5% 또는
 *     규제성격 상이). 즉 **미재현이지 부재가 아니다.**
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import {
  MIXED_REVIEW_SENTINEL,
  formatDominantZone,
  isMixedReviewRequired,
} from "../dominant-zone";

describe("formatDominantZone — 판정 보류를 값처럼 말하지 않는다", () => {
  it("센티널이면 raw 문자열을 절대 내보내지 않는다", () => {
    const r = formatDominantZone(MIXED_REVIEW_SENTINEL);
    expect(r.label).not.toContain(MIXED_REVIEW_SENTINEL);
    expect(r.withheld).toBe(true);
    expect(r.label).toMatch(/판정하지 않았습니다/);
  });

  it("basis 쪽에만 센티널이 있어도 잡는다(백엔드가 두 필드를 다 쓴다)", () => {
    const r = formatDominantZone("제2종일반주거지역", { dominantBasis: MIXED_REVIEW_SENTINEL });
    expect(r.withheld).toBe(true);
    expect(r.label).not.toContain(MIXED_REVIEW_SENTINEL);
  });

  it("★센티널을 대표 용도지역으로 **대체하지 않는다**(#787 이 고친 결함)", () => {
    const r = formatDominantZone(MIXED_REVIEW_SENTINEL);
    expect(r.label).not.toMatch(/제\d종|일반상업지역|녹지지역/);
  });

  it("정상 값은 그대로 통과한다(특이도 — 가드가 정상을 막으면 그것도 결함이다)", () => {
    const r = formatDominantZone("일반상업지역");
    expect(r).toEqual({ label: "일반상업지역", withheld: false });
  });

  it("미확보(null·공백)와 보류는 **다른 문구**다 — 모른다 ≠ 단일화를 거부했다", () => {
    const empty = formatDominantZone(null, { fallback: "미확보" });
    const mixed = formatDominantZone(MIXED_REVIEW_SENTINEL);
    expect(empty.label).toBe("미확보");
    expect(empty.label).not.toBe(mixed.label);
  });

  it("isMixedReviewRequired 는 정상값에 false 를 준다", () => {
    expect(isMixedReviewRequired("일반상업지역", "area_weighted")).toBe(false);
    expect(isMixedReviewRequired(null, null)).toBe(false);
  });
});

/** 소스에서 `dominant_zone` 을 **그리는** 자리를 파생형으로 모아 잠근다. */
function walk(dir: string, out: string[] = []): string[] {
  for (const e of readdirSync(dir)) {
    if (e === "node_modules" || e === ".next" || e.startsWith(".")) continue;
    const p = join(dir, e);
    if (statSync(p).isDirectory()) walk(p, out);
    else if (/\.tsx?$/.test(e) && !/\.test\.tsx?$/.test(e)) out.push(p);
  }
  return out;
}

describe("전역 스윕 — 새 화면이 생겨도 자동으로 감시망에 든다", () => {
  const WEB_ROOT = join(__dirname, "..", "..", "..");

  it("`dominant_zone ||` 형태의 **falsy-only 폴백**이 남아 있지 않다", () => {
    const files = walk(WEB_ROOT);
    // ── 공허진리 가드: 조회기가 살아 있는가(대조군) ──
    expect(files.length).toBeGreaterThan(200);
    const mentioning = files.filter((f) => readFileSync(f, "utf8").includes("dominant_zone"));
    expect(mentioning.length).toBeGreaterThan(0);

    const offenders: string[] = [];
    for (const f of mentioning) {
      if (f.endsWith(join("lib", "zoning", "dominant-zone.ts"))) continue;  // 헬퍼 자신
      const src = readFileSync(f, "utf8");
      const code = src
        .split("\n")
        .filter((l) => !/^\s*(\/\/|\*|\/\*)/.test(l))   // 주석 배제
        .join("\n");
      // `dominant_zone || "…"` / `?? "…"` — 센티널은 truthy 라 이 폴백을 통과해 버린다.
      //
      // ★위양성 둘을 실제로 겪고 좁혔다(가드가 정상 코드를 막으면 그것도 결함이다):
      //   ① `dominant_zone || ""` 는 **빈 문자열 정규화**다(그 다음 줄에서 센티널을 본다).
      //      → 따옴표 안에 **한 글자 이상** 있을 때만 표시 폴백으로 센다.
      //   ② 이 헬퍼 파일 **자신의 주석**이 예시로 그 형태를 적고 있다.
      //      → 주석 제거 후에 검사하고, 헬퍼 자신은 대상에서 뺀다.
      if (/dominant_zone\s*(\|\||\?\?)\s*["'`][^"'`]/.test(code)) {
        offenders.push(f.replace(WEB_ROOT, ""));
      }
    }
    expect(offenders, `센티널이 그대로 화면에 나가는 자리 — formatDominantZone 을 경유하라`).toEqual([]);
  });
});
