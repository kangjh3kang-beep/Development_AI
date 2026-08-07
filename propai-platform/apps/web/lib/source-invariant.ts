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

import ts from "typescript";

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
 * ── 블록 주석 제거의 이력 (왜 네 번 고쳤는가) ────────────────────────────────
 *
 * 이 락들은 `line.includes(mustContain)` 이라 **주석이 조건을 대신 충족시킨다**.
 * 그래서 검사 전에 주석을 지워야 하는데, 그 "지우기"가 네 번 뚫렸다:
 *
 *   ① `{/* … *\/}` 정규식만       → 평범한 `/* … *\/` 로 관통 (실배선 락 24개 노출)
 *   ② 손수 짠 따옴표 스캐너        → **정규식 리터럴**이 상태를 오염(R1)
 *   ③ AST `forEachChild` 순회      → **구두점 토큰 미방문**으로 닫는 괄호 앞 주석 생존(R2)
 *   ④ **트리비아 간극 전수 주사**  → 현재(누락도 오인도 구조적으로 불가)
 *
 * ★매번 처방이 **목록을 한 칸 늘렸다**. ③은 "판정을 파서에게 넘긴다"고 선언해 놓고
 *   파서에게 *묻지* 않고 노드를 돌며 주워 담은 것이라 특히 뼈아프다.
 *   그래서 ④는 형태를 세지 않고 **누락이 구조적으로 불가능한 열거**로 갔고,
 *   그것이 참인지를 **오라클 등가 테스트**로 잠갔다(형태가 아니라 등가성을 잠근다).
 */
/** `.tsx` 만 JSX 로 읽는다 — `.ts` 를 TSX 로 읽으면 `<T>x`(레거시 타입 단언)와 `<T,>` 제네릭이 JSX 로 오독돼 그 뒤 토큰 위치가 어긋난다(R2 실증, 현 트리 미발화). */
function scriptKindOf(fileName: string): ts.ScriptKind {
  return /\.tsx$/.test(fileName) ? ts.ScriptKind.TSX : ts.ScriptKind.TS;
}

/** 파일의 모든 **리프 토큰**을 등장 순서로. `getChildren` 은 `forEachChild` 와 달리 `}` `)` 같은 구두점 토큰까지 준다(R2 가 잡아낸 미탐의 원인이 정확히 그 차이였다). */
function leafTokens(sf: ts.SourceFile): ts.Node[] {
  const out: ts.Node[] = [];
  const walk = (n: ts.Node): void => {
    // ★JSDoc(`/** … */`)은 트리비아가 아니라 **노드**로 파싱된다 — 간극에 없다.
    //   내려가지 않고 통째로 하나의 단위로 다룬다(미탐 67건의 원인이었다).
    if (ts.isJSDoc(n)) {
      out.push(n);
      return;
    }
    const kids = n.getChildren(sf);
    if (kids.length === 0) {
      out.push(n);
      return;
    }
    for (const k of kids) walk(k);
  };
  walk(sf);
  return out;
}

/**
 * 소스에서 **블록 주석 구간**을 전부 찾는다.
 *
 * ★이 함수의 유일한 설계 목표는 **누락이 구조적으로 불가능한 것**이다. 이 결함은
 *   세 번 연속 "내가 안 떠올린 형태"로 뚫렸고, 매번 처방이 목록을 한 칸 늘렸다:
 *
 *     ① `{/* … *\/}` 정규식        → 평범한 `/* … *\/` 로 관통
 *     ② 손수 짠 따옴표 스캐너      → **정규식 리터럴**이 상태를 오염시켜 관통
 *     ③ AST `forEachChild` 순회    → **구두점 토큰을 방문하지 않아** 닫는 괄호 앞
 *                                    자기 줄 주석이 전부 생존(미탐 230건·81파일)
 *     ④ 스캐너 단독 열거           → 파서 문맥이 없어 **정규식 리터럴을 주석으로 오인**
 *                                    (= 정상 코드를 삼키는 거짓 초록). 실측으로 기각
 *
 *   ③ 이 특히 뼈아프다 — "판정을 파서에게 넘긴다"고 선언해 놓고, **파서에게 "이 파일의
 *   주석을 다 달라"고 묻지 않고 노드를 돌며 주워 담았다.** 방향은 옳았고 실행이 모자랐다.
 *
 * ★그래서 **간극 전수 주사**를 쓴다. 주석은 오직 **토큰과 토큰 사이(트리비아)**에만
 *   존재할 수 있다. 그러니 리프 토큰을 순서대로 늘어놓고 **모든 간극**을 훑으면
 *   "안 들른 자리"가 원리적으로 없다. 간극에는 공백과 주석밖에 없으므로 그 안에서는
 *   단순 주사로 충분하다 — 문자열·템플릿·정규식은 애초에 **토큰이라 간극이 아니다.**
 *
 *   `ts.createScanner` 단독은 안 된다(시도했다가 실측으로 기각): 파서 문맥이 없어
 *   `/[/*]/` 같은 **정규식 리터럴을 주석으로 오인**해 정상 코드를 삼킨다(= 거짓 초록).
 *   JSX children 의 `/* … *\/` 도 같은 이유로 오인하는데, 간극 방식은 그것이 `JsxText`
 *   **토큰**이라 자동으로 제외된다 — 예외 처리를 적을 필요가 없다.
 */
function blockCommentRanges(src: string, fileName: string): Array<[number, number]> {
  const sf = ts.createSourceFile(
    fileName,
    src,
    ts.ScriptTarget.Latest,
    /* setParentNodes */ true,
    scriptKindOf(fileName),
  );

  // ★파스가 깨지면 **조용히 덜 지운다**(= 거짓 초록). 조용한 미탐 대신 시끄럽게 실패한다.
  const diagnostics = (sf as unknown as { parseDiagnostics?: readonly unknown[] }).parseDiagnostics;
  if (diagnostics && diagnostics.length > 0) {
    throw new Error(
      `[wiring-invariant] ${fileName} 파싱에 실패했다(진단 ${diagnostics.length}건). ` +
        "주석 제거가 불완전해 락이 거짓 초록이 될 수 있어 중단한다.",
    );
  }

  const out: Array<[number, number]> = [];
  /** 간극(트리비아)에서 블록 주석을 집는다. 여기엔 공백과 주석만 있어 오인 여지가 없다. */
  const scanGap = (from: number, to: number): void => {
    let i = from;
    while (i < to) {
      const ch = src[i];
      // ★줄 주석 안의 `/*` 를 블록 시작으로 오인하면 **정상 코드를 삼킨다**(거짓 초록).
      //   실측: `// 라이브 모드 /api/*는 RBAC 게이트` 같은 줄이 9개 파일에서 오탐을 냈다.
      //   간극에는 공백·줄주석·블록주석만 있으므로 셋을 그대로 구분하면 끝난다.
      if (ch === "/" && src[i + 1] === "/") {
        const nl = src.indexOf("\n", i);
        i = nl === -1 || nl >= to ? to : nl + 1;
        continue;
      }
      if (ch === "/" && src[i + 1] === "*") {
        const close = src.indexOf("*/", i + 2);
        const end = close === -1 ? to : Math.min(close + 2, to);
        out.push([i, end]);
        i = end;
        continue;
      }
      i += 1;
    }
  };

  let cursor = 0;
  for (const tok of leafTokens(sf)) {
    const start = tok.getStart(sf);
    scanGap(cursor, start); // 토큰 앞 트리비아 = 간극
    // JSDoc 은 노드지만 의미상 주석이다 — 통째로 지운다.
    if (ts.isJSDoc(tok)) out.push([start, tok.end]);
    cursor = Math.max(cursor, tok.end);
  }
  scanGap(cursor, src.length); // 마지막 토큰 뒤(EOF 토큰이 있어 보통 비지만 안전망)
  return out;
}

/** 블록 주석을 **줄 수를 보존한 채**(개행만 남기고) 지운다. */
function stripBlockComments(src: string, fileName: string): string {
  const ranges = blockCommentRanges(src, fileName);
  if (ranges.length === 0) return src;

  // 뒤에서부터 치환해 앞쪽 오프셋이 밀리지 않게 한다.
  ranges.sort((a, b) => b[0] - a[0]);
  let out = src;
  for (const [pos, end] of ranges) {
    out = out.slice(0, pos) + out.slice(pos, end).replace(/[^\n]/g, " ") + out.slice(end);
  }
  return out;
}

/** 테스트가 구현과 **다른 메커니즘**으로 같은 답이 나오는지 대조할 수 있게 공개한다. */
export const __blockCommentRangesForOracle = blockCommentRanges;

function assertJsxCommentSpanLimit(src: string): void {
  // ★2026-08-07(R2) — 이 함수는 이제 **지우지 않는다. 검사만 한다.**
  //   스트립은 `stripBlockComments` 한 곳으로 모았다(순서가 load-bearing 이 되는 것을
  //   없애고, JSX 스트립이 남긴 빈 `{ }` 가 파스 오류를 만드는 경로도 함께 제거).
  //   남은 역할은 **정규식이 코드를 삼킨 흔적을 잡는 회귀 백스톱** 하나다:
  //   비정상적으로 긴 JSX 주석 매치는 "정규식이 폭주해 코드를 먹었다"의 신호다.
  //   저장소 최장 정당 주석은 12줄이라 상한 40 은 여유 3.2배.
  for (const m of src.matchAll(/\{\/\*(?:(?!\*\/)[\s\S])*\*\/\s*\}/g)) {
    const span = (m[0].match(/\n/g) || []).length;
    if (span > 40) {
      throw new Error(
        `[wiring-invariant] JSX 주석이 ${span}줄이다(상한 40). ` +
          "주석을 쪼개거나, 정규식을 되돌린 게 아닌지 확인하라(코드를 삼켰을 수 있다).",
      );
    }
  }
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
  // ★2026-08-07(R2) — 스트립은 **한 곳**에서만 한다. 종전에는 JSX 스트립을 먼저 돌리고
  //   블록 스트립을 뒤에 돌렸는데, ①어느 쪽이 먼저인지가 load-bearing 이 되어 순서
  //   자체가 결함원이 됐고 ②JSX 스트립이 남긴 빈 `{ }` 가 **실제로 2개 파일에서 파스
  //   오류를 유발**했다(원본은 진단 0건인데 스트립 후 3건·8건). 스캐너 열거는 JSX 주석도
  //   똑같이 트리비아로 보므로 전처리가 필요 없다 — 순서 문제를 없애서 없앤다.
  //   `stripJsxComments` 는 이제 **폭주 백스톱 전용**이다(지우지 않고 검사만).
  assertJsxCommentSpanLimit(raw);
  const src = stripBlockComments(raw, inv.file);
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
