/**
 * 소스 수준 배선 불변식 — "소비처가 정말 그 헬퍼를 거치는가"를 고정하는 공용 도구.
 *
 * ★왜 공용화하는가(2026-07-30 회고):
 *   한 세션에서 같은 불변식을 **손으로 세 번** 재작성했고(팝오버 앵커·identity churn·
 *   타일 판정), 매번 같은 함정을 반복해서 밟았다:
 *     ① `new URL(..., import.meta.url)` — vitest에서 file 스킴이 아니라 런타임 오류
 *     ② 매치 0건이면 공허진리로 **항상 통과**(가짜 안전)
 *     ③ 필터가 너무 넓어 정상 코드까지 위반으로 잡음(첫 시도가 기준선에서 실패)
 *   이 함수는 셋을 구조적으로 막는다 — 경로는 cwd 기준으로 고정하고, 최소 매치 수를
 *   **필수 인자**로 받아 공허진리를 불가능하게 하며, 스코프를 명시적으로 요구한다.
 *
 * ★왜 소스를 읽는가(한계 명시):
 *   "deps 배열에 무엇이 있는가", "핸들러가 어떤 함수를 부르는가" 같은 **정적 사실**은
 *   런타임 테스트로 닿기 어렵다(예: jsdom에서 Leaflet이 초기화를 못 끝내 effect가 아예
 *   실행되지 않아 카운터가 0 vs 0이 되는 공허한 테스트가 됐다).
 *   대신 이 도구는 **런타임 동작을 증명하지 않는다** — 계약이 코드에 남아있는지만 본다.
 *   행위 검증이 가능하면 그쪽이 우선이고, 이건 닿지 않는 곳의 최후 수단이다.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

export type WiringInvariant = {
  /** apps/web 기준 상대 경로. 예: "components/map/SatongMultiMap.tsx" */
  file: string;
  /** 검사 대상 줄을 고르는 좁은 조건 — 넓으면 정상 코드를 깨뜨린다(실제로 겪음). */
  scope: RegExp;
  /** scope에 걸린 줄이 반드시 포함해야 하는 문자열/패턴(= 거쳐야 하는 공용 경로). */
  mustContain: string | RegExp;
  /** scope에 걸린 줄이 있으면 안 되는 패턴(= 우회 경로). 선택. */
  mustNotContain?: string | RegExp;
  /**
   * 최소 매치 수 — **필수**. 0건이면 무엇을 바꿔도 통과하는 가짜 안전이 되므로
   * 호출자가 "몇 줄이 있어야 하는지"를 반드시 선언하게 한다.
   */
  minMatches: number;
};

/**
 * 줄 끝 주석을 떼어낸다 — ★2026-08-02 적발한 **세 번째 함정**.
 *
 * 이 검사는 `line.includes(mustContain)` 이라 **주석이 조건을 충족시킨다**. 이 저장소는
 * 줄마다 한국어 설명을 붙이는 스타일이라 적대적 의도가 없어도 발생하고, 실제로 5개 규칙이
 * 다음 한 줄들로 전부 우회됐다(리뷰어 실증):
 *
 *   const aggregatable = true;                 // locatedKeys.has 로 대체 예정(TODO)
 *   for (const g of cat.groups || []) {        // selectLocatedGroups 복구 필요
 *
 * 즉 배선을 되돌리면서 "되돌렸다"는 주석만 남기면 게이트가 초록이 된다. 앞선 두 함정
 * (①dict 키 이름을 함수 호출로 오인 ②스코프가 타입 선언까지 매치)과 같은 계열이다.
 *
 * `://`(URL) 뒤는 자르지 않는다 — 문자열 안의 슬래시를 주석으로 오인하면 정상 코드를
 * 위반으로 만들어(과도스코프) 기준선이 깨진다.
 */
function stripLineComment(line: string): string {
  return line.replace(/(^|[^:])\/\/.*$/, "$1");
}

/**
 * 파일 전체에서 JSX 주석(`{/* … *\/}`)을 **줄 수를 보존한 채** 지운다.
 *
 * ★R3(F-3)에서 한 줄짜리 JSX 주석만 벗겼는데, R4 가 **여러 줄 주석으로 뚫었다** —
 * 이 저장소의 지배적 주석 형태가 여러 줄이고, `assertWiredThrough` 는 줄 단위라
 * 주석 중간 줄에는 `{/*` 가 없어 아무것도 안 벗겨졌다. 렌더를 통째로 여러 줄 주석에
 * 넣으면 배선 락이 **그대로 초록**이 된다(= 화면은 침묵인데 게이트는 통과).
 * 이 PR 에서 공허한 참이 나온 **다섯 번째** 형태다.
 *
 * ★줄 단위 검사의 한계이므로 **줄 분할 전에** 파일 수준에서 지우는 것이 근원 수정이다.
 * 줄 번호를 보존해야 위반 위치를 정확히 보고할 수 있으므로, 지우는 대신 **개행만 남기고
 * 나머지를 공백으로 치환**한다.
 */
function stripJsxComments(src: string): string {
  // ★여는 괄호와 `/*` 사이에 **공백을 허용하지 않는다**. 허용했더니 TS 인터페이스의
  //   `{` + JSDoc `/** … */` 이 매치돼 **44,444자(1,113줄)를 통째로 삼켰다**(실측).
  //   JSX 주석은 `{/*` 로 붙여 쓰는 것이 이 저장소의 실제 형태다.
  //   닫는 쪽은 `*/}` · `*/ }` 를 모두 허용한다 — JSX 주석 안에 `*/` 가 올 수 없으므로
  //   non-greedy 매치가 첫 종료점에서 정확히 닫힌다.
  // ★★R5 리뷰(F-4) — `[\s\S]*?` 를 **`*/` 를 포함하지 않는 문자열**로 바꾼다.
  //   non-greedy 백트래킹은 `{/* c */ a: 1 }` 같은 객체 리터럴에서 폭주할 수 있고,
  //   그것이 R4 에서 44,444자를 삼킨 `{`+JSDoc 사고의 **직계 유사형**이다(공백 불허
  //   조건은 범위를 좁혔을 뿐 구조를 제거하지 못했다). 이 형태는 구조적으로 막는다.
  //   ★닫는 쪽 `\s*` 도 제거했다 — 저장소 전역 2,069 매치에서 **한 번도 발화한 적이 없고**,
  //   수용 조건만 넓히는 순손실이다(리뷰어 실측).
  const stripped = src.replace(/\{\/\*(?:(?!\*\/)[\s\S])*\*\/\}/g, (m) =>
    m.replace(/[^\n]/g, " "),
  );
  // ★폭주를 **큰 실패로 전환**한다. 저장소 최장 정당 JSX 주석은 13줄이다(실측).
  //   40줄을 넘겼다면 주석이 아니라 코드를 삼킨 것이고, 그때 조용히 통과시키면
  //   R4 사고(1,113줄 소실)가 **초록으로** 재발한다.
  for (const m of src.matchAll(/\{\/\*(?:(?!\*\/)[\s\S])*\*\/\}/g)) {
    const span = (m[0].match(/\n/g) || []).length;
    if (span > 40) {
      throw new Error(
        `[wiring-invariant] JSX 주석 제거가 ${span}줄을 삼켰다(상한 40). ` +
          "코드를 주석으로 오인했을 가능성이 높다 — 정규식을 점검하라.",
      );
    }
  }
  return stripped;
}

function includes(line: string, needle: string | RegExp): boolean {
  const code = stripLineComment(line);
  return typeof needle === "string" ? code.includes(needle) : needle.test(code);
}

/**
 * 소스에서 scope에 걸린 줄이 전부 공용 경로를 거치는지 단언한다.
 * 위반 시 어느 줄이 문제인지 그대로 보여준다(원인 오도 방지).
 */
export function assertWiredThrough(inv: WiringInvariant): void {
  // ★R4(H-1) — 줄 분할 **전에** JSX 주석을 지운다. 줄 단위로는 여러 줄 주석을 못 벗긴다.
  const src = stripJsxComments(readFileSync(resolve(process.cwd(), inv.file), "utf-8"));
  const lines = src.split("\n");
  const matched: { no: number; text: string }[] = [];
  lines.forEach((text, i) => {
    if (inv.scope.test(text)) matched.push({ no: i + 1, text });
  });

  if (matched.length < inv.minMatches) {
    throw new Error(
      `[wiring-invariant] ${inv.file}: scope(${inv.scope}) 매치 ${matched.length}건 ` +
        `< 최소 ${inv.minMatches}건. 스코프가 코드 변경으로 어긋났거나(→ 스코프 갱신), ` +
        `검사 대상이 사라졌다. 0건이면 이 검사는 무의미하므로 실패시킨다.`,
    );
  }

  const violations = matched.filter(
    (m) =>
      !includes(m.text, inv.mustContain) ||
      (inv.mustNotContain != null && includes(m.text, inv.mustNotContain)),
  );

  if (violations.length > 0) {
    const detail = violations
      .map((v) => `  ${inv.file}:${v.no}  ${v.text.trim().slice(0, 90)}`)
      .join("\n");
    throw new Error(
      `[wiring-invariant] 공용 경로를 우회한 줄 ${violations.length}건 ` +
        `(기대: ${String(inv.mustContain)})\n${detail}`,
    );
  }
}
