/**
 * ★관리자 과금 화면이 **백엔드가 받는 요율 키를 전부** 그리는가.
 *
 * 【무엇이 있었나 · 실측 2026-09-03】
 * 화면이 세 칸을 **하드코딩**하고 있었는데 백엔드 `apply_config` 가 받는 평면 키는 **8개**였다.
 * 그래서 다섯 개를 **관리자가 화면에서 바꿀 수 없었고**, 그중 셋은 **실제 돈**이다:
 *
 *     photoreal_render   3,000원      registry_issue      1,200원
 *     registry_analysis  2,000원      concept_render          0원
 *     bulk_parcel_per_unit   0원  ← 배치 견적이 항상 「무료」로 계산되던 이유
 *
 * ★근본은 **목록형**이다. 백엔드에 키가 늘면 화면이 **조용히** 뒤처진다 —
 *   빨개지지 않고, 운영자는 그 항목이 존재하는지조차 모른다.
 *
 * 【이 락이 잠그는 것】
 *   ①탐지  백엔드 키 중 화면이 못 그리는 것이 있으면 실패한다
 *   ②배선  화면이 **파생형**으로 그리는가(하드코딩 목록으로 되돌리면 실패)
 *   ③특이도 중첩 묶음(`stages`·`analysis_modules`)은 평면 칸으로 그리지 않는다
 *   ④공허방지 양쪽 추출이 비면 **시끄럽게 실패**한다(0 vs 0 은 「일치」가 아니다)
 */
import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { flatFeeKeys } from "@/app/[locale]/(dashboard)/settings/billing/page";

const ROOT = path.resolve(__dirname, "../..");
const REPO = path.resolve(ROOT, "../..");
const BILLING_PY = path.join(REPO, "apps/api/app/core/billing.py");
const PAGE_TSX = path.join(ROOT, "app/[locale]/(dashboard)/settings/billing/page.tsx");

/** `apply_config` 의 평면 요율 화이트리스트를 **파이썬 소스에서 파생**한다. */
function backendFeeKeys(): string[] {
  const src = readFileSync(BILLING_PY, "utf8");
  const m = src.match(/for k in \(\s*((?:"[a-z_]+",?\s*)+)\):\s*\n\s*if k in sf/);
  if (!m) throw new Error("★추출기 사망 — apply_config 의 키 목록을 못 찾았다(위반 아님)");
  return [...m[1].matchAll(/"([a-z_]+)"/g)].map((x) => x[1]).sort();
}

describe("★과금 화면 ↔ 백엔드 요율 키 정합", () => {
  it("④ 공허 방지 — 양쪽 추출이 비어 있지 않다", () => {
    const be = backendFeeKeys();
    expect(be.length, "★백엔드 키 추출이 0 — 아래 「일치」가 공허해진다").toBeGreaterThanOrEqual(5);
    // 화면 쪽은 서버 응답에서 파생하므로, 헬퍼가 실제로 숫자 키를 고르는지 본다.
    const picked = flatFeeKeys(Object.fromEntries(be.map((k) => [k, 0])));
    expect(picked.length, "★헬퍼가 아무 키도 안 골랐다").toBe(be.length);
  });

  it("① ★백엔드가 받는 키를 화면이 전부 그린다(라벨이 없어도 키로 그린다)", () => {
    const be = backendFeeKeys();
    const cfg = Object.fromEntries(be.map((k) => [k, 0]));
    const rendered = flatFeeKeys(cfg);
    const missing = be.filter((k) => !rendered.includes(k));
    expect(missing, `★화면이 못 그리는 요율 키 — 관리자가 그 금액을 바꿀 수 없다: ${missing.join(", ")}`).toEqual([]);
  });

  it("③ 특이도 — 중첩 묶음은 평면 칸으로 그리지 않는다", () => {
    const picked = flatFeeKeys({
      project_create: 2000,
      stages: { site_analysis: 2000 },
      analysis_modules: {},
    } as Record<string, unknown>);
    expect(picked).toEqual(["project_create"]);
  });

  it("② ★배선 — 화면이 **파생형**으로 그린다(하드코딩 목록 금지)", () => {
    const src = readFileSync(PAGE_TSX, "utf8");
    // 파생 호출이 실제로 렌더 안에 있어야 한다.
    expect(src, "★flatFeeKeys 로 그리지 않는다 — 목록형으로 되돌아갔다").toContain("flatFeeKeys(cfg.service_fees)");
    // ★그리고 옛 하드코딩 형태가 되살아나면 실패한다(두 모집단: 파생 O · 하드코딩 X).
    const hard = [...src.matchAll(/setSvc\("([a-z_]+)"/g)].map((m) => m[1]);
    expect(hard, `★요율 키를 손으로 박았다: ${hard.join(", ")}`).toEqual([]);
  });

  /**
   * ★★**F5(적대 리뷰)** — 화면은 서버가 준 **숫자 키 전부**를 그리는데, 저장은
   * `apply_config` 의 **화이트리스트만** 반영한다. 두 목록이 **다른 곳에 손으로** 적혀 있다:
   * `_CONFIG["service_fees"]` 리터럴 ↔ `for k in (...)` 튜플.
   *
   * 어긋나면 **화면에 칸이 생기고, 관리자가 값을 고치고, 「저장되었습니다」를 보는데
   * 서버는 조용히 버린다** — 볼트 `2026-09-02_작동하지_않는_조작_수단을_만들_뻔했다` 의 재발이다.
   * ★**양방향**으로 건다(§D19) — 어느 쪽이 앞서도 빨개져야 한다.
   */
  it("★F5: `_CONFIG` 의 평면 요율 키 == `apply_config` 화이트리스트 (양방향)", () => {
    const src = readFileSync(BILLING_PY, "utf8");
    // ★`_CONFIG` 의 값은 숫자가 아니라 `_DEFAULT_CONFIG[...]` **참조**다 —
    //   첫 시도에서 「숫자냐」로 걸렀다가 **0건**이 나왔고, 추출기가 「사망」을 신고해서 알았다.
    //   판정은 «숫자냐»가 아니라 **«중첩이 아니냐»** 다(`dict(...)` 로 감싼 것이 중첩).
    const block = src.match(/^_CONFIG: dict\[str, Any\] = \{[\s\S]*?^\}/m);
    if (!block) throw new Error("★추출기 사망 — _CONFIG 리터럴을 못 찾았다(위반 아님)");
    const sf = block[0].match(/"service_fees": \{\n([\s\S]*?)\n {4}\},/);
    if (!sf) throw new Error("★추출기 사망 — service_fees 블록을 못 찾았다(위반 아님)");
    const declared = sf[1]
      .split("\n")
      .map((ln) => ln.match(/^\s*"([a-z_]+)":\s*(.+?),?\s*$/))
      .filter((m): m is RegExpMatchArray => !!m && !m[2].startsWith("dict("))
      .map((m) => m[1])
      .sort();
    const allowed = backendFeeKeys();
    expect(declared.length, "★_CONFIG 에서 뽑은 키가 0 — 추출기 사망").toBeGreaterThanOrEqual(5);
    expect(declared.filter((k) => !allowed.includes(k)),
      "★기본값에는 있는데 저장이 안 되는 키 — 화면에 칸이 생기고 저장은 조용히 버린다").toEqual([]);
    expect(allowed.filter((k) => !declared.includes(k)),
      "★저장은 받는데 기본값에 없는 키 — 화면에 칸이 안 생긴다").toEqual([]);
  });

  it("★라벨이 없는 키도 칸이 사라지지 않는다(라벨표는 표시용일 뿐)", () => {
    const picked = flatFeeKeys({ brand_new_fee_key: 0, project_create: 1 });
    expect(picked).toContain("brand_new_fee_key");
  });
});
