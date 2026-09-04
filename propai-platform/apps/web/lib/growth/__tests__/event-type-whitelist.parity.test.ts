/**
 * ★계약 락 — 프론트 이벤트 타입 유니온과 백엔드 화이트리스트가 **갈라지면 잡는다.**
 *
 * 왜 필요한가(쉬운 설명):
 * 프론트는 `GrowthEventType` 에 있는 이름만 보낼 수 있고, 백엔드는 `_ALLOWED_TYPES` 에
 * 있는 이름만 받는다. **한쪽에만 추가하면 아무도 오류를 보지 못한다** — 프론트 collector 는
 * 논블로킹이라 조용히 성공하고, 백엔드는 조용히 `rejected` 로 세고 버린다. 결과는
 * "계측을 붙였는데 데이터가 안 쌓인다"이고, 그 사실은 **몇 주 뒤 대시보드가 빌 때** 드러난다.
 *
 * `event-collector.ts` 헤더는 이미 *"백엔드 화이트리스트와 1:1 일치"* 라고 **선언**하고
 * 있었다. 그런데 그것을 **강제하는 것이 아무것도 없었다**(실측: 두 이름을 언급하는
 * 테스트 파일 0건). 주석이 선언한 면역을 코드가 갖고 있는지 확인하라 — 규율 §C-11.
 *
 * ★파서 주의(실수 #42 재발 방지): **고정 길이 창으로 자르지 않는다.** 그렇게 하면 옆 표까지
 *   읽어 "없는 불일치"를 만든다. 여기서는 **구분자 균형**(`{}` / `;`)으로 경계를 정하고,
 *   추출이 비면 **시끄럽게 실패**시킨다(빈 집합끼리 비교해 공허하게 초록이 되지 않도록).
 */
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const HERE = dirname(fileURLToPath(import.meta.url));
const WEB_ROOT = resolve(HERE, "../../..");           // apps/web
const COLLECTOR = resolve(WEB_ROOT, "lib/growth/event-collector.ts");
const GROWTH_ROUTER = resolve(WEB_ROOT, "../api/app/routers/growth.py");

/** 주석·문자열이 아닌 **실제 리터럴**만 모은다(줄 주석 제거 후 따옴표 토큰 추출). */
function stringLiterals(block: string): Set<string> {
  const withoutLineComments = block
    .split("\n")
    .map((line) => line.replace(/(^|\s)(\/\/|#).*$/, "$1"))
    .join("\n");
  const out = new Set<string>();
  for (const m of withoutLineComments.matchAll(/"([a-z_]+)"|'([a-z_]+)'/g)) {
    out.add((m[1] ?? m[2]) as string);
  }
  return out;
}

/** `export type GrowthEventType =` 부터 **문장 끝(`;`)** 까지 — 고정 길이 아님. */
function readTsUnion(): Set<string> {
  const src = readFileSync(COLLECTOR, "utf-8");
  const start = src.indexOf("export type GrowthEventType");
  expect(start, "GrowthEventType 선언을 찾지 못했다 — 파서가 낡았다").toBeGreaterThanOrEqual(0);
  const end = src.indexOf(";", start);
  expect(end, "유니온 선언의 끝(;)을 찾지 못했다").toBeGreaterThan(start);
  return stringLiterals(src.slice(start, end));
}

/** `_ALLOWED_TYPES = {` 부터 **중괄호 균형**이 맞는 지점까지 — 고정 길이 아님. */
function readPythonSet(): Set<string> {
  const src = readFileSync(GROWTH_ROUTER, "utf-8");
  const decl = src.indexOf("_ALLOWED_TYPES");
  expect(decl, "_ALLOWED_TYPES 선언을 찾지 못했다 — 파서가 낡았다").toBeGreaterThanOrEqual(0);
  const open = src.indexOf("{", decl);
  expect(open, "_ALLOWED_TYPES 의 여는 중괄호를 찾지 못했다").toBeGreaterThan(decl);
  let depth = 0;
  let close = -1;
  for (let i = open; i < src.length; i += 1) {
    if (src[i] === "{") depth += 1;
    else if (src[i] === "}") {
      depth -= 1;
      if (depth === 0) { close = i; break; }
    }
  }
  expect(close, "중괄호 균형이 맞는 닫는 괄호를 찾지 못했다").toBeGreaterThan(open);
  return stringLiterals(src.slice(open, close + 1));
}

describe("★계약 — 프론트 이벤트 타입 ≡ 백엔드 화이트리스트", () => {
  it("추출 자체가 비어 있지 않다(공허한 초록 방지)", () => {
    // ★이 가드가 단언 **앞에** 있어야 한다. 파서가 깨져 양쪽이 빈 집합이 되면
    //   "완전 일치"가 공허하게 참이 된다 — 규율 §A-2.
    expect(readTsUnion().size).toBeGreaterThanOrEqual(12);
    expect(readPythonSet().size).toBeGreaterThanOrEqual(12);
  });

  it("두 목록이 정확히 같다 — 한쪽에만 있는 타입은 조용히 버려진다", () => {
    const ts = [...readTsUnion()].sort();
    const py = [...readPythonSet()].sort();
    // 목록을 손으로 적지 않는다(사람이 센 목록이 상한이 된다 — 규율 §A-4).
    // 파일에서 **파생**시키므로 새 타입이 생기면 자동으로 이 락에 들어온다.
    expect(ts).toEqual(py);
  });

  it("선택 오염 관측 타입이 양쪽에 있다", () => {
    // 이 PR 이 추가한 항목 — 위 전수 비교가 통과해도 **둘 다 빠졌으면** 통과하므로
    // 존재를 따로 못 박는다(전수 일치는 '둘 다 없음'과 구별하지 못한다).
    expect(readTsUnion()).toContain("selection_contamination_observation");
    expect(readPythonSet()).toContain("selection_contamination_observation");
  });
});
