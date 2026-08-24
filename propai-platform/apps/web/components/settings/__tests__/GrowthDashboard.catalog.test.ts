/**
 * ★계약 락 — 화면 라벨표가 **백엔드 카탈로그를 덮는가**.
 *
 * 왜 필요한가(쉬운 설명):
 * 인사이트 타입은 여러 백엔드 모듈이 각자 만들고, 화면은 **손으로 쓴 표**로 한글 라벨을 붙인다.
 * 두 목록이 갈라지면 화면에 `heal_escalation` 같은 **영문 raw 문자열**이 그대로 뜬다 —
 * 그런데 아무도 오류를 보지 못한다(그냥 못생긴 라벨로 보일 뿐이다).
 *
 * ★실측(2026-08-24): 백엔드 **11종** vs 화면 표 **7종**, 그 7종 중 **3종은 유령**
 *   (`funnel`·`usage_pattern`·`churn_risk` — 백엔드가 한 번도 안 내보낸다).
 *   즉 **7종이 라벨 없이** 떴고, 그중 `heal_escalation` 은
 *   *"자동치유 무효 · 사람 점검 필요"* 라는 **critical** 이었다.
 *
 * ★규율 §A-4: *"목록형이 아니라 전수/파생형으로 쓴다 — 사람이 센 목록이 곧 상한이 된다."*
 *   그래서 목록을 여기 적지 않고 **백엔드 카탈로그 파일에서 파생**시킨다.
 *   새 타입이 카탈로그에 들어오는 순간 이 테스트가 라벨을 요구한다.
 */
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const HERE = dirname(fileURLToPath(import.meta.url));
const WEB_ROOT = resolve(HERE, "../../..");                 // apps/web
const DASHBOARD = resolve(WEB_ROOT, "components/settings/GrowthDashboard.tsx");
const CATALOG = resolve(WEB_ROOT, "../api/app/services/growth/insight_types.py");

/** 파이썬 카탈로그의 frozenset 리터럴들에서 타입 이름을 뽑는다(줄 주석 제외). */
function backendCatalog(): Set<string> {
  const src = readFileSync(CATALOG, "utf-8");
  const out = new Set<string>();
  // `_ANALYZER = frozenset({ ... })` 블록들만 본다 — NON_ACTIONABLE 은 부분집합이라 겹쳐도 무해.
  for (const m of src.matchAll(/frozenset\(\{([\s\S]*?)\}\)/g)) {
    const body = m[1]
      .split("\n")
      .map((ln) => ln.replace(/(^|\s)#.*$/, "$1"))   // 주석의 예시가 세어지지 않게
      .join("\n");
    for (const q of body.matchAll(/"([a-z_]+)"/g)) out.add(q[1]);
  }
  return out;
}

/** 화면 라벨표의 키를 뽑는다(선언 블록만 — 다른 곳의 동명 문자열에 속지 않게). */
function frontendLabels(): Set<string> {
  const src = readFileSync(DASHBOARD, "utf-8");
  const start = src.indexOf("const TYPE_LABELS");
  expect(start, "TYPE_LABELS 선언을 찾지 못했다 — 파서가 낡았다").toBeGreaterThanOrEqual(0);
  const open = src.indexOf("{", start);
  let depth = 0;
  let close = -1;
  for (let i = open; i < src.length; i += 1) {
    if (src[i] === "{") depth += 1;
    else if (src[i] === "}") { depth -= 1; if (depth === 0) { close = i; break; } }
  }
  expect(close, "TYPE_LABELS 블록의 끝을 찾지 못했다").toBeGreaterThan(open);
  const body = src.slice(open, close)
    .split("\n")
    .map((ln) => ln.replace(/(^|\s)\/\/.*$/, "$1"))
    .join("\n");
  const out = new Set<string>();
  for (const m of body.matchAll(/^\s*([a-z_]+)\s*:/gm)) out.add(m[1]);
  return out;
}

describe("★계약 — 인사이트 타입 라벨이 백엔드 카탈로그를 덮는다", () => {
  it("양쪽 추출이 비어 있지 않다(공허한 초록 방지)", () => {
    // ★이 가드가 단언 **앞에** 있어야 한다 — 파서가 깨져 둘 다 빈 집합이면
    //   "완전히 덮는다"가 공허하게 참이 된다(규율 §A-2).
    expect(backendCatalog().size).toBeGreaterThanOrEqual(10);
    expect(frontendLabels().size).toBeGreaterThanOrEqual(10);
  });

  it("백엔드가 내보내는 모든 타입에 한글 라벨이 있다", () => {
    const back = backendCatalog();
    const front = frontendLabels();
    const missing = [...back].filter((t) => !front.has(t)).sort();
    expect(missing, `라벨 없는 타입(화면에 영문 raw 로 뜬다): ${missing.join(", ")}`).toEqual([]);
  });

  it("★화면에만 있는 유령 라벨이 없다 — 영원히 안 뜨는 항목", () => {
    const back = backendCatalog();
    const front = frontendLabels();
    const ghosts = [...front].filter((t) => !back.has(t)).sort();
    expect(ghosts, `백엔드가 내보내지 않는 유령 라벨: ${ghosts.join(", ")}`).toEqual([]);
  });

  it("전수 일치는 '둘 다 없음'과 구별 못 한다 — 대표 항목 존재를 못 박는다", () => {
    const front = frontendLabels();
    expect(front.has("selection_contamination")).toBe(true);
    expect(front.has("heal_escalation")).toBe(true);   // 라벨 누락이던 critical
    expect(front.has("latency_baseline")).toBe(true);
  });

  it("★조치 대상 아님 표시가 '확인 필요' 집계에서 실제로 제외된다", () => {
    // 값만 정의하고 소비처가 없으면 장식이다 — 실행되는 줄에서 쓰이는지 본다.
    const src = readFileSync(DASHBOARD, "utf-8");
    const live = src
      .split("\n")
      .filter((ln) => ln.trim() && !ln.trim().startsWith("//") && !ln.trim().startsWith("*"));
    const used = live.filter((ln) => ln.includes("NON_ACTIONABLE_TYPES.has("));
    expect(used.length, "NON_ACTIONABLE_TYPES 가 선언만 되고 쓰이지 않는다").toBeGreaterThan(0);
    expect(
      live.some((ln) => ln.includes("NON_ACTIONABLE_TYPES.has(") && ln.includes("!")),
      "제외(부정)로 쓰이지 않는다 — 포함으로 쓰면 의미가 뒤집힌다",
    ).toBe(true);
  });
});
