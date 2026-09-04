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

/**
 * ★**보류값 계약(정본)** — `X: null` + `X_absent: 닫힌 코드`.
 *
 * 종전에 이 모듈은 **센티널 계약만** 다뤄서, 값이 `null` 로 오는 경로에서는 「왜 보류인지」를
 * **원리적으로 말할 수 없었다** — 백엔드가 실어 보낸 사유 코드를 받는 인자가 없었다.
 * 사유를 버리는 것은 그 자체로 장애다(사용자도 조사자도 원인을 모른다).
 */
describe("formatDominantZone — `_absent` 코드로 **왜** 보류인지 말한다", () => {
  it("★두 모집단이 같은 실행에서 갈린다 — 사유가 있으면 말하고, 없으면 종전 그대로다", () => {
    const withCode = formatDominantZone(null, { fallback: "용도미상", absent: "ambiguous" });
    const without = formatDominantZone(null, { fallback: "용도미상" });
    // 있는 쪽: 사유가 붙는다
    expect(withCode.reason).toBeTruthy();
    expect(withCode.reason).toMatch(/단일화/);
    // 없는 쪽: **종전과 바이트 동일** — 이것이 회귀가 아니라는 근거다
    expect(without).toEqual({ label: "용도미상", withheld: true });
    expect("reason" in without).toBe(false);
    // ★두 모집단이 실제로 다르다(차가 0인 픽스처는 잠금이 아니다)
    expect(withCode.reason).not.toBe((without as { reason?: string }).reason);
  });

  it("★raw 코드를 화면에 내보내지 않는다 — 이 모듈의 존재 이유", () => {
    const r = formatDominantZone(null, { fallback: "용도미상", absent: "insufficient_coverage" });
    expect(r.reason).not.toContain("insufficient_coverage");
    expect(r.label).not.toContain("insufficient_coverage");
  });

  it("★음성 대조군 — 어휘 밖 코드는 **조용히 무시**한다(지어내지 않는다)", () => {
    // 이것이 없으면 «무엇이 와도 뭔가 말한다» 는 구현도 만점을 받는다(위양성도 결함).
    for (const bad of ["zzz_not_in_vocabulary", "", null, undefined, 7]) {
      const r = formatDominantZone(null, { fallback: "용도미상", absent: bad });
      expect(r, `어휘 밖 ${String(bad)} 에 사유를 지어냈다`).toEqual({ label: "용도미상", withheld: true });
    }
  });

  it("★값이 있으면 사유를 붙이지 않는다 — 계약이 값과 사유를 **배타**로 둔다", () => {
    // 값이 있는데 `_absent` 가 남아 있으면 그건 백엔드의 계약 위반이고
    // `validate_withheld_pair` 가 **거기서** 잡을 일이지, 화면이 덮어 감출 일이 아니다.
    const r = formatDominantZone("제2종일반주거지역", { absent: "ambiguous" });
    expect(r).toEqual({ label: "제2종일반주거지역", withheld: false });
  });

  it("센티널 경로는 `absent` 가 있어도 **종전 문구 그대로** — 구판 계약이 우선한다", () => {
    const r = formatDominantZone(MIXED_REVIEW_SENTINEL, { absent: "ambiguous" });
    expect(r.label).toMatch(/판정하지 않았습니다/);
    expect(r.label).not.toContain(MIXED_REVIEW_SENTINEL);
  });

  /**
   * ★**부채를 초록 안에 드러낸다**(커밋 메시지에만 적으면 안 드러난다).
   *
   * `primary_zone_basis` 가 `first_parcel_no_area` 면 **값은 있지만 근거가 약하다**
   * (면적 미확보라 첫 필지로 떨어졌다). 그건 「보류」와 **다른 축**이라 이 PR 에 넣지 않았다 —
   * 기존 `primary_zone_is_inferred` 칩과 겹칠 수 있고, **겹침을 재기 전에 칩을 늘리면
   * 모순되는 칩이 나란히 선다**(그 컴포넌트 주석이 경고하는 형태).
   */
  it.todo("값은 있으나 근거가 약한 경우(first_parcel_no_area)를 화면이 고지한다");
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
