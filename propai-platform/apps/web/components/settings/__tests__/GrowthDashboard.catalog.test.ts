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


/** `type InsightType = | "a" | "b" ...` 의 리터럴(문장 끝 `;` 까지 — 고정 길이 아님). */
function frontendUnion(): Set<string> {
  const src = readFileSync(DASHBOARD, "utf-8");
  const start = src.indexOf("type InsightType");
  expect(start, "InsightType 선언을 찾지 못했다").toBeGreaterThanOrEqual(0);
  const end = src.indexOf(";", start);
  expect(end).toBeGreaterThan(start);
  const out = new Set<string>();
  for (const m of src.slice(start, end).matchAll(/"([a-z_]+)"/g)) out.add(m[1]);
  return out;
}

/** metrics 렌더러 `switch` 안의 `case "<type>":` 라벨. */
function metricsCases(): Set<string> {
  const src = readFileSync(DASHBOARD, "utf-8");
  const start = src.indexOf("function InsightMetrics");
  expect(start, "InsightMetrics 를 찾지 못했다").toBeGreaterThanOrEqual(0);
  // 다음 최상위 함수 전까지.
  const nextFn = src.indexOf("\nfunction ", start + 1);
  const body = src.slice(start, nextFn > 0 ? nextFn : undefined)
    .split("\n")
    .map((ln) => ln.replace(/(^|\s)\/\/.*$/, "$1"))
    .join("\n");
  const out = new Set<string>();
  for (const m of body.matchAll(/case\s+"([a-z_]+)"\s*:/g)) out.add(m[1]);
  return out;
}

/** 백엔드 `INSIGHT_LABELS` 의 **키→한글값** 을 뽑는다(선언 블록만 · 주석 배제). */
function backendLabels(): Record<string, string> {
  const src = readFileSync(CATALOG, "utf-8");
  const i = src.indexOf("INSIGHT_LABELS");
  expect(i, "INSIGHT_LABELS 선언을 찾지 못했다 — 파서가 낡았다").toBeGreaterThanOrEqual(0);
  const open = src.indexOf("{", i);
  let depth = 0;
  let close = -1;
  for (let j = open; j < src.length; j += 1) {
    if (src[j] === "{") depth += 1;
    else if (src[j] === "}") { depth -= 1; if (depth === 0) { close = j; break; } }
  }
  expect(close, "INSIGHT_LABELS 블록의 끝을 찾지 못했다").toBeGreaterThan(open);
  const body = src.slice(open, close)
    .split("\n")
    .map((ln) => ln.replace(/(^|\s)#.*$/, "$1"))
    .join("\n");
  const out: Record<string, string> = {};
  for (const m of body.matchAll(/"([a-z_]+)"\s*:\s*"([^"]+)"/g)) out[m[1]] = m[2];
  return out;
}

/** 화면 `TYPE_LABELS` 의 **키→값**. */
function frontendLabelPairs(): Record<string, string> {
  const src = readFileSync(DASHBOARD, "utf-8");
  const start = src.indexOf("const TYPE_LABELS");
  expect(start, "TYPE_LABELS 선언을 찾지 못했다").toBeGreaterThanOrEqual(0);
  const open = src.indexOf("{", start);
  let depth = 0;
  let close = -1;
  for (let j = open; j < src.length; j += 1) {
    if (src[j] === "{") depth += 1;
    else if (src[j] === "}") { depth -= 1; if (depth === 0) { close = j; break; } }
  }
  const body = src.slice(open, close)
    .split("\n")
    .map((ln) => ln.replace(/(^|\s)\/\/.*$/, "$1"))
    .join("\n");
  const out: Record<string, string> = {};
  for (const m of body.matchAll(/^\s*([a-z_]+)\s*:\s*"([^"]+)"/gm)) out[m[1]] = m[2];
  return out;
}

/** 파이썬 카탈로그의 `NON_ACTIONABLE` 집합. */
function backendNonActionable(): Set<string> {
  const src = readFileSync(CATALOG, "utf-8");
  const i = src.indexOf("NON_ACTIONABLE");
  expect(i, "NON_ACTIONABLE 선언을 찾지 못했다").toBeGreaterThanOrEqual(0);
  const open = src.indexOf("frozenset({", i);
  const close = src.indexOf("})", open);
  expect(close).toBeGreaterThan(open);
  const out = new Set<string>();
  for (const m of src.slice(open, close).matchAll(/"([a-z_]+)"/g)) out.add(m[1]);
  return out;
}

/** 화면의 `NON_ACTIONABLE_TYPES` Set 리터럴. */
function frontendNonActionable(): Set<string> {
  const src = readFileSync(DASHBOARD, "utf-8");
  const i = src.indexOf("const NON_ACTIONABLE_TYPES");
  expect(i, "NON_ACTIONABLE_TYPES 선언을 찾지 못했다").toBeGreaterThanOrEqual(0);
  const open = src.indexOf("[", i);
  const close = src.indexOf("]", open);
  const out = new Set<string>();
  for (const m of src.slice(open, close).matchAll(/"([a-z_]+)"/g)) out.add(m[1]);
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

  it("★TS 유니온도 카탈로그와 일치한다 — `(string & {})` 때문에 tsc 는 못 잡는다", () => {
    // 유니온에 `| (string & {})` 가 있어 **어떤 문자열이든 대입 가능**하다.
    // 즉 리터럴을 오타 내도 `tsc` 가 통과시킨다 — 그 유니온은 잠그지 않으면 **순수 장식**이다.
    const union = frontendUnion();
    expect(union.size).toBeGreaterThanOrEqual(10);          // 공허한 초록 방지
    expect([...backendCatalog()].filter((t) => !union.has(t)).sort()).toEqual([]);
    expect([...union].filter((t) => !backendCatalog().has(t)).sort()).toEqual([]);
  });

  it("★모든 타입이 metrics 렌더러에 case 를 가진다 — 없으면 지표가 한 줄도 안 뜬다", () => {
    // `switch` 에 case 가 없으면 `rows.length === 0` → **null 반환**(조용히 빈 화면).
    // 라벨만 잠그면 이 구멍이 남는다 — 실제로 `heal_escalation` 이 그 상태였다.
    const cases = metricsCases();
    expect(cases.size).toBeGreaterThanOrEqual(10);          // 공허한 초록 방지
    const missing = [...backendCatalog()].filter((t) => !cases.has(t)).sort();
    expect(missing, `metrics 렌더러가 없는 타입(지표가 안 뜬다): ${missing.join(", ")}`).toEqual([]);
  });

  it("★조치 대상 아님 목록이 백엔드 카탈로그와 일치한다", () => {
    // 백엔드에 `NON_ACTIONABLE` 을 두고 화면이 자기 목록을 따로 쓰면 **소비처 0**이 된다.
    const back = backendNonActionable();
    const front = frontendNonActionable();
    expect(back.size).toBeGreaterThan(0);
    expect([...front].sort()).toEqual([...back].sort());
  });

  it("★표시명이 **백엔드 SSOT 와 같다** — 백엔드도 사용자 산문을 조립한다", () => {
    // ★왜 값까지 보나(2026-08-25 라이브 실측): 백엔드가 `narrative`·`diagnosis` 를 **만들어
    //   저장**하는데 표시명을 몰라 영문 enum 을 그대로 끼웠다
    //   (*"critical 인사이트(recurring_verify_error) — 사람 진단 필요."*).
    //   프론트에 라벨이 아무리 많아도 그 문장은 못 고친다 — 표시명이 **백엔드 SSOT** 여야 한다.
    //   `#808` 이 세운 것은 **타입 목록** SSOT 였고 표시명은 아니었다.
    const back = backendLabels();
    const front = frontendLabelPairs();
    // 공허 진리 가드 — 추출이 비면 아래 비교가 통과한다.
    expect(Object.keys(back).length, "백엔드 라벨 추출이 비었다").toBeGreaterThanOrEqual(10);
    expect(Object.keys(front).length, "프론트 라벨 추출이 비었다").toBeGreaterThanOrEqual(10);
    expect(Object.keys(front).sort()).toEqual(Object.keys(back).sort());
    // ★키만 맞추면 값이 갈려도 통과한다 — 사용자는 **값**을 읽는다.
    expect(front).toEqual(back);
  });

  it("의미를 지는 라벨 문구는 잠근다(그 외 문안은 의도적 미잠금)", () => {
    // ★디자인 문안 전체를 얼리면 정상 개선을 막는다. 다만 **성격을 말하는** 두 개는
    //   그 문구가 곧 정보다 — 지워지면 사용자가 조치 대상으로 오해한다.
    const src = readFileSync(DASHBOARD, "utf-8");
    expect(src).toContain("회귀 아님");            // latency_baseline 이 조치 대상이 아님
    expect(src).toContain("후보지 비교면 정상");    // multi_region 이 결함이 아닐 수 있음
    expect(src).toContain("사람 점검");            // heal_escalation 이 사람을 부름
  });
});
