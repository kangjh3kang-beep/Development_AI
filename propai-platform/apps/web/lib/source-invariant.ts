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
/**
 * 파일 전체에서 **블록 주석 `/* … *\/`** 을 줄 수를 보존한 채 지운다.
 *
 * ★2026-08-06 실증한 **여섯 번째** 공허한 참 — 그리고 이 파일 역사상 가장 뼈아픈 것.
 *   R3~R6 네 라운드가 이 함수를 다듬었는데 **전부 `{/* … *\/}`(JSX 형태)만** 손봤다.
 *   그동안 TS/TSX 에서 가장 흔한 **평범한 `/* … *\/`** 는 한 번도 검토되지 않았다.
 *   실측(origin/main, `MarketInsightsWorkspaceClient.tsx:333`):
 *
 *     avmCaveat: payload.avm_caveat ?? …      → 락 초록 (정상)
 *     // avmCaveat: payload.avm_caveat ?? …   → 락 빨강 (기존 가드가 잡음)
 *     /* avmCaveat: payload.avm_caveat ?? … *\/  → ★락 초록 (배선이 끊겼는데 통과)
 *
 *   `CLAUDE.md` 규율 A-3 이 "렌더가 불가하면 이 헬퍼를 경유하라"고 지시하는데, 그
 *   헬퍼가 뚫려 있었다. 이 위에 배선 락 38개가 서 있었다.
 *
 * ★가드가 목록형이면 목록 밖 형태로 뚫린다 — 규율 A-4 가 골든에 대해 말한 것이
 *   **가드 자신에게도** 적용된다. 그래서 "JSX 주석"이 아니라 **블록 주석 일반**을 지운다.
 *
 * ★문자열 안의 `/*` 를 주석으로 오인하면 정상 코드를 삼켜 기준선이 깨진다(과도스코프는
 *   이 파일이 이미 두 번 데인 실패다). 그래서 정규식이 아니라 **따옴표 상태를 추적하는
 *   스캐너**로 짠다. 줄 주석(`//`)은 지우지 않고 **건너뛰기만** 한다 — 지우는 일은
 *   URL 예외를 아는 `stripLineComment` 의 몫이고, 여기서는 주석 안의 아포스트로피
 *   (`// don't`)가 따옴표 상태를 오염시키는 것만 막으면 된다.
 *
 * ★못 하는 것(면역을 주장하지 않는다 — 규율 C-11):
 *   ① **JSX 텍스트 노드의 아포스트로피** — `<p>don't</p>` 처럼 따옴표가 홀로 있으면
 *      그 지점부터 다음 따옴표까지를 문자열로 오인해, 그 사이의 블록 주석을 **안 지운다**.
 *      결과는 종전과 같은 미탐(거짓 초록)이지 새 오탐이 아니다 — 축소된 한계일 뿐.
 *   ② **정규식 리터럴 안의 `/*`** (`/[/*]/`) 는 주석 시작으로 오인될 수 있다. 저장소
 *      전수 실행으로 기준선이 깨지지 않음을 확인했고, 깨지면 **빨강**으로 드러난다
 *      (거짓 초록이 아니라 거짓 빨강 방향이라 안전한 실패다).
 */
function stripBlockComments(src: string): string {
  let out = "";
  let i = 0;
  let quote: '"' | "'" | "`" | null = null;

  while (i < src.length) {
    const c = src[i];

    if (quote) {
      if (c === "\\") {
        out += src.slice(i, i + 2);
        i += 2;
        continue;
      }
      if (c === quote) quote = null;
      out += c;
      i += 1;
      continue;
    }

    if (c === '"' || c === "'" || c === "`") {
      quote = c;
      out += c;
      i += 1;
      continue;
    }

    // 줄 주석은 그대로 두되 **따옴표 판정에서 제외**한다(아포스트로피 오염 방지).
    if (c === "/" && src[i + 1] === "/") {
      const nl = src.indexOf("\n", i);
      const stop = nl === -1 ? src.length : nl;
      out += src.slice(i, stop);
      i = stop;
      continue;
    }

    if (c === "/" && src[i + 1] === "*") {
      const end = src.indexOf("*/", i + 2);
      const stop = end === -1 ? src.length : end + 2;
      // 줄 번호를 보존해야 위반 위치를 정확히 보고할 수 있다 → 개행만 남긴다.
      out += src.slice(i, stop).replace(/[^\n]/g, " ");
      i = stop;
      continue;
    }

    out += c;
    i += 1;
  }

  return out;
}

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
  //   ★R6 리뷰(F-D) 정정 — R5 에서 닫는 쪽 `\s*` 를 "수용 조건만 넓히는 순손실"이라며
  //   지웠는데 **방향이 반대**였다. `\s*` 는 *제거* 범위를 넓히는 쪽이고, 그게 거짓 초록에
  //   안전하다: `{/* <DeadPanel /> */ }` 가 안 지워지면 그 주석이 `mustContain` 을 충족시켜
  //   **주석 처리된 JSX 위에서 락이 초록**이 된다(= R4 H-1 과 같은 계열).
  //   새 내부 클래스(`(?!\*\/)`)와 조합하면 첫 `*/` 에서 멈추므로 폭주도 없다 → 복원한다.
  const stripped = src.replace(/\{\/\*(?:(?!\*\/)[\s\S])*\*\/\s*\}/g, (m) =>
    m.replace(/[^\n]/g, " "),
  );
  // ★R6 리뷰(F-C) 정직 표기 — 이 가드가 **무엇을 잡고 무엇을 못 잡는지** 바로잡는다.
  //   새 내부 클래스가 첫 `*/` 를 넘지 못하므로 R4 형태의 **폭주는 구조적으로 불가능**하다
  //   (리뷰어 실측: 폭주 시도의 매치 span 이 전부 0줄). 따라서 이 조건이 성립하는 경우는
  //   사실상 **정당하게 긴 JSX 주석**뿐이고, 실질은 "주석 40줄 제한" 린트 + 정규식을
  //   되돌렸을 때를 대비한 **회귀 백스톱**이다. 저장소 최장 정당 주석은 12줄이라 여유 3.2배.
  for (const m of src.matchAll(/\{\/\*(?:(?!\*\/)[\s\S])*\*\/\s*\}/g)) {
    const span = (m[0].match(/\n/g) || []).length;
    if (span > 40) {
      throw new Error(
        `[wiring-invariant] JSX 주석이 ${span}줄이다(상한 40). ` +
          "주석을 쪼개거나, 정규식을 되돌린 게 아닌지 확인하라(코드를 삼켰을 수 있다).",
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
  // ★R4(H-1) — 줄 분할 **전에** 주석을 지운다. 줄 단위로는 여러 줄 주석을 못 벗긴다.
  // ★2026-08-06 — 순서가 중요하다. `stripJsxComments` 를 **먼저** 돌린다.
  //   그 안의 **40줄 폭주 백스톱**은 `{/* … */}` 매치를 세는데, 블록 스트립을 먼저 하면
  //   그 형태가 이미 공백이 되어 백스톱이 **한 건도 못 보는 공허한 검사**로 죽는다.
  //   (내가 지금 고치고 있는 바로 그 결함을 봉합 순서로 다시 만들 뻔했다.)
  const raw = readFileSync(resolve(process.cwd(), inv.file), "utf-8");
  const src = stripBlockComments(stripJsxComments(raw));
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
