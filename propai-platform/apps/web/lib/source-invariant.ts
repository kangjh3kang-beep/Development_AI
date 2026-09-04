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
import { existsSync, readFileSync, statSync } from "node:fs";
import { dirname, relative, resolve } from "node:path";

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
 * ── 블록 주석 제거의 이력 (왜 네 번 고쳤는가) ────────────────────────────────
 *
 * 이 락들은 `line.includes(mustContain)` 이라 **주석이 조건을 대신 충족시킨다**.
 * 그래서 검사 전에 주석을 지워야 하는데, 그 "지우기"가 네 번 뚫렸다:
 *
 *   ① `{/* … *\/}` 정규식만       → 평범한 `/* … *\/` 로 관통 (실배선 락 24개 노출)
 *   ② 손수 짠 따옴표 스캐너        → **정규식 리터럴**이 상태를 오염(R1)
 *   ③ AST `forEachChild` 순회      → **구두점 토큰 미방문**으로 닫는 괄호 앞 주석 생존(R2)
 *   ④ 트리비아 간극 전수 주사      → **블록 주석은 막혔다**(R3: 44개 적대 구문 프로브 +
 *                                   873파일에서 미탐 0·오탐 0). 그런데 같은 함수의
 *                                   **다른 절반**인 줄 주석이 `://` 예외로 열려 있었다
 *   ⑤ **줄 주석도 같은 간극 경로**  → 현재. `stripLineComment` 정규식을 삭제했다
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
 *                                    자기 줄 주석이 전부 생존. R3 재실측(873파일):
 *                                    오라클 대비 미탐 **2,301건/311파일(35.6%)**,
 *                                    그중 "자기 줄 평범 주석"만 **109건/50파일**
 *                                    (R2 가 인용한 230/81 은 어느 정의로도 재현 안 됨)
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
  // ★`parseDiagnostics` 는 TS **비공개 필드**다(공개 타입에 없다). 버전이 올라가 사라지면
  //   `undefined && …` 로 **검사가 조용히 증발**한다 — 없애겠다던 "조용한 미탐"으로 복귀다.
  //   그래서 부재 자체를 실패로 만든다.
  const diagnostics = (sf as unknown as { parseDiagnostics?: readonly unknown[] }).parseDiagnostics;
  // ★이 분기는 **오늘 도달 불가**다(TS 5.9 에 필드가 있다) — 변이로 지워도 아무 테스트가
  //   죽지 않는다. 가짜 잠금을 만들지 않고 도달 불가임을 적어 둔다(규율 B: 설명할 수 있는
  //   생존은 코드에 적는다). 미래에 필드가 사라지면 **여기서 시끄럽게** 실패한다.
  if (diagnostics === undefined) {
    throw new Error(
      "[wiring-invariant] TS 의 parseDiagnostics 가 사라졌다(비공개 API). " +
        "파스 실패를 못 잡으면 락이 거짓 초록이 되므로 중단한다 — 대체 경로를 찾아라.",
    );
  }
  if (diagnostics.length > 0) {
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
        // ★2026-08-07(R3) — 줄 주석도 **여기서 범위로 잡는다**(종전엔 건너뛰기만 했다).
        //   줄 주석은 `stripLineComment` 의 손수 정규식이 따로 처리했는데, 그 안의
        //   `://` 예외(`(^|[^:])//`)가 **다섯 번째 관통구**였다: `X://needle` 로 쓰면
        //   `:` 앞이라 주석으로 안 보고, 주석 속 needle 이 `mustContain` 을 충족시킨다.
        //   TS 에서 `:` 직후 줄바꿈은 타입 주석·삼항 else·객체 속성 어디서나 합법이라
        //   실제 락 2개를 tsc·eslint 클린 상태로 초록으로 만들 수 있었다(R3 실증).
        //   간극 기반으로 옮기면 그 예외가 **필요 없어진다** — 문자열 안의 `//`(URL)는
        //   토큰이라 애초에 간극에 없다.
        const nl = src.indexOf("\n", i);
        const end = nl === -1 || nl >= to ? to : nl;
        out.push([i, end]);
        i = end;
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
    cursor = tok.end;
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

/** 다른 소스 스캐너가 **주석에 뚫리지 않도록** 같은 스트립을 쓰게 공개한다. */
export const __stripCommentsForScan = stripBlockComments;

/** 테스트가 구현과 **다른 메커니즘**으로 같은 답이 나오는지 대조할 수 있게 공개한다. */
export const __blockCommentRangesForOracle = blockCommentRanges;

/** 주석은 이미 파일 수준에서 전부 지워졌으므로 여기서는 줄을 그대로 본다. */
function includes(line: string, needle: string | RegExp): boolean {
  return typeof needle === "string" ? line.includes(needle) : needle.test(line);
}

/* ────────────────────────────────────────────────────────────────────────────
 * 층위(z) 감시용 소스 파생 도구 — 2026-08-07 추가.
 *
 * ★왜 공용화하나: 층위 사다리 계약(`__tests__/layer-ladder.contract.test.tsx`)이
 *   "지도와 공존하는 화면의 모달"을 **하드코딩 목록**이 아니라 임포트 그래프에서
 *   **파생**하는데, 그 파생에 두 구멍이 있었다(자기 지적 → 실측 확인):
 *     ① 임포트를 **1단계만** 따라가고, 게다가 `@/...` 별칭만 봤다. 이 저장소는
 *        같은 폴더 컴포넌트를 `./X` 로 부르므로 **상대 임포트가 통째로 안 보였다**.
 *        실제 누락 1건 — MarketInsightsWorkspaceClient → `@/…/OrchestratorPanel`
 *        → `./InputResolveModal`(z-50). 지도(SatongMapShell)와 같은 화면인데
 *        본문 sticky(600)·지도 오버레이(≤500) 아래로 깔려 있었다.
 *     ② 백드롭을 `className="…"` **리터럴만** 봤다. 삼항·`cn()`·템플릿으로 조립한
 *        className 은 정규식 밖이었다.
 *   두 도구 모두 여기 두어 다른 층위 검사도 같은 눈을 쓰게 한다.
 *
 * ★변이검증(2026-08-08 재실행 — **저장소 도구로**):
 *   `python3 scripts/mutate_changed.py --base origin/main --tests <계약·파서·불변식 테스트 3개>`
 *   → 15변이 · **생존 7**.
 *   ※정정: 한때 "저장소 도구는 `.py` 전용이라 이 PR 에 한 건도 안 돈다"고 적었고 그때는
 *     사실이었으나, **다른 세션이 #586 에서 TS·vitest 지원을 넣어** 더는 참이 아니다.
 *     임시 어댑터는 버리고 본체로 돌렸다 — 이제 다음 사람이 같은 명령으로 **재현**할 수 있다.
 * ★생존 7건은 전부 **문자열**이고 설명된다:
 *   · `importClosure` 오류 메시지 6건 — 던지는 **조건**은 픽스처로 잠겨 있다
 *     (`source-invariant.backdrop.test.ts` 의 throw 3종). 문구는 사용자 산출물이 아니라
 *     개발자 진단이라 계약이 아니다.
 *   · `InputResolveModal` 의 **주석** 1건 — 주석은 동작이 아니다(도구가 문자열로 집었을 뿐).
 *   ※도구가 **TS 타입 선언을 아예 변이 대상에서 뺀다**(런타임에 사라지므로 vitest 로는 원리적으로
 *     못 잡는다) — 종전에 내가 "타입 필드 생존은 tsc 게이트의 몫"이라 분류한 것과 같은 판단이
 *     이제 도구에 내장돼 있다.
 *   ★"설명 못 하는 생존 0" 은 **그 실행 시점 코드에 대한 주장**이다. 코드를 고친 뒤에는
 *     다시 돌려 분류하기 전까지 그 문장을 재사용하지 마라(한 번 그렇게 해서 틀렸다).
 * ──────────────────────────────────────────────────────────────────────────── */

/** 한 개의 리터럴 `className` 에서 읽어낸 백드롭 후보. */
export type BackdropHit = {
  /** apps/web 기준 상대 경로(수집기가 채운다). */
  file: string;
  /** 그 className 문자열(판정 근거를 그대로 보고하기 위함). */
  classes: string;
  /** 그 안에서 읽어낸 z 값들(변이 prefix `md:z-50` 포함). 없으면 빈 배열. */
  zs: number[];
};

/**
 * 백드롭 수집 전 주석을 지운다 — **같은 파일의 `stripBlockComments`(TS 파서)를 그대로 쓴다.**
 *
 * ★내력: 2026-08-07 에 내가 정규식으로 블록 주석을 지웠다가 **수백 파일의 실코드를 삼키는
 *   맹점**을 만들었다(줄주석 안의 `/*`·문자열 안의 `image/*` 를 블록 시작으로 오인).
 *   지도 시드인 `AuctionMonitorPanel` 에 z-50 백드롭을 주입해도 계약이 초록이었다.
 *   그래서 되돌리고 "다시 넣으려면 ①줄주석 뒤에 ②문자열을 건너뛰는 스캔으로 ③상한 throw
 *   까지 갖춰야 한다"고 적어 두었다.
 * ★그 조건을 **다른 세션이 #584 에서 TS 파서로 충족**시켰다(간극 주사 — 문자열·템플릿·정규식은
 *   애초에 토큰이라 간극이 아니므로 오인 여지가 없고, 파스 실패는 시끄럽게 던진다).
 *   그래서 손수 정규식을 버리고 그쪽에 합류한다 — 같은 판정을 두 메커니즘으로 하지 않는다.
 */
function stripComments(src: string): string {
  return stripBlockComments(src, "backdrop-scan.tsx");
}

/**
 * **문자열 리터럴** `className` 값만 뽑는다 — `="…"` 와 `={"…"}` 두 형태.
 *
 * ★종전엔 `={…}` 표현식을 중괄호 균형으로 파싱했는데, 수집 범위를 리터럴 전용으로 줄이면서
 *   그 25줄이 통째로 **죽은 코드**가 됐다(변이검증이 적발: `else if (ch === "{")` 를 무력화해도
 *   전부 초록 = 아무도 그 경로를 쓰지 않는다). 남겨두면 다음 사람이 "표현식도 본다"고 오해한다.
 * ★표현식은 자연히 걸러진다 — `className={cn(…)}` 는 `=` 뒤가 따옴표가 아니라 매치되지 않는다.
 *   템플릿(백틱)도 일부러 제외한다: 보간이 있으면 리터럴이 아니고, 없으면 굳이 쓸 이유가 없다.
 */
function literalClassNames(src: string): string[] {
  // ★`[^\\]` 를 쓰지 않는다 — 백슬래시를 품은 리터럴(`after:content-['\2014']`)에서 매치가
  //   통째로 실패해 **리터럴인데 못 보는** 형태가 생긴다(독립 검증이 적발·저장소 현황 0건이나
  //   축소 전 파서는 정상 처리했으므로 순손실이었다). 이스케이프는 `\\.` 로 건너뛴다.
  return Array.from(src.matchAll(/className\s*=\s*\{?\s*(["'])((?:\\.|(?!\1)[^\\])*)\1/g)).map(
    (m) => m[2],
  );
}

const HAS_CLASS = (t: string, cls: string) =>
  new RegExp(`(?:^|\\s)${cls}(?:\\s|$)`).test(t);

const Z_UTIL = /(?:^|\s)(?:[\w-]+:)*z-\[?(\d+)\]?(?=\s|$)/g;

/**
 * 소스에서 **모달 백드롭**(`fixed` + `inset-0`)인 className 을 모은다.
 *
 * ★★범위(2026-08-07 R3 판정으로 **줄였다** — 이게 이 도구의 핵심 결정이다):
 *   **통짜 문자열 리터럴 className 만** 본다. 삼항·`cn()`·템플릿으로 조립한 것은 보지 않는다.
 *
 *   R1~R2 에서 비리터럴 파서를 만들었다가 **3라운드 연속 위양성**을 생산했다(삼항 갈래 병합 →
 *   갈래 분리 → 이번엔 `cn("fixed inset-0", c ? "a" : "b", "z-[800]")` 같은 **준수 코드가
 *   CI 를 깨뜨림`). 그리고 실측하니 그 90줄이 지키는 대상은 **전 저장소에 단 1건**이고
 *   그마저 계약을 지키고 있었다(`CadBimIntegrationPanel` z-[9990]).
 *   지도 공존 폐포의 백드롭 **8건은 전부 리터럴**이라, 리터럴 전용으로 줄여도 **감시 8/8 유지**다.
 *   → 지키는 게 1건(준수)인데 위양성을 계속 만드는 코드는 **순손실**이라 걷어낸다.
 *
 * ★`pointer-events-none` 은 제외한다 — 클릭을 받지 않는 **배경 장식**이지 모달 백드롭이 아니다
 *   (실측 2건: Auth·PasswordRecovery 의 `pointer-events-none fixed inset-0 -z-10`). 위반으로
 *   신고하면 정상 코드를 막는다(rule 6).
 * ★인라인 `style={{ zIndex }}` 도 보지 않는다 — R2 에서 창(窓) 휴리스틱으로 읽었다가
 *   **양방향으로 틀렸다**(제목 속성·자식 텍스트의 "zIndex: 800" 을 z 로 오인 / `style` 이
 *   className **앞**에 오면 준수 코드를 위반으로 신고). 모달 층위는 이 저장소에서 전부
 *   클래스로 표기되므로(폐포 8/8), 클래스 표기를 계약으로 삼는다.
 * ★못 보는 형태는 계약 테스트의 `it.todo` 에 부채로 드러낸다 — 조용히 넘기지 않는다.
 */
export function collectBackdrops(source: string, file = ""): BackdropHit[] {
  const hits: BackdropHit[] = [];
  for (const raw of literalClassNames(stripComments(source))) {
    const classes = raw.replace(/\s+/g, " ").trim();
    if (!HAS_CLASS(classes, "fixed") || !HAS_CLASS(classes, "inset-0")) continue;
    if (HAS_CLASS(classes, "pointer-events-none")) continue;
    hits.push({
      file,
      classes,
      zs: Array.from(classes.matchAll(Z_UTIL)).map((z) => Number(z[1])),
    });
  }
  return hits;
}

/**
 * 임포트 지정자 → apps/web 기준 상대 경로. 별칭(`@/…`)과 **상대(`./`·`../`)** 를 모두
 * 푼다. 확장자·index 파일까지 시도하고, 저장소 밖(패키지)이면 null.
 */
export function resolveModuleSpec(fromFile: string, spec: string): string | null {
  let base: string;
  if (spec.startsWith("@/")) base = spec.slice(2);
  else if (spec.startsWith("./") || spec.startsWith("../"))
    base = relative(process.cwd(), resolve(dirname(resolve(process.cwd(), fromFile)), spec));
  else return null;
  for (const cand of [
    `${base}.tsx`,
    `${base}.ts`,
    `${base}/index.tsx`,
    `${base}/index.ts`,
  ]) {
    const abs = resolve(process.cwd(), cand);
    if (existsSync(abs) && statSync(abs).isFile()) return cand;
  }
  // ★R1 은 여기를 "등가 변이라 안 잠긴다"고 적었는데 **틀렸다**(R2 지적) — 같은 PR 이 추가한
  //   해석기 픽스처("존재하지 않는 경로는 null")가 `undefined` 로 바꾸면 실패한다. 봉합 뒤
  //   갱신하지 않은 주석이 다음 사람을 오도할 뻔했다.
  return null;
}

/** `importClosure` 가 **반드시** 받아야 하는 공허진리 방지 선언. */
export type ClosureExpectation = {
  /**
   * 최소 파일 수 — **필수**. ★**성긴 붕괴 하한**이다. 배선 회귀를 이걸로 잡으려 하지 마라.
   *
   * 두 번 틀렸다: 초판은 "정상 157 의 절반"이라며 80 을 썼고(회귀 다수 통과), 그다음엔
   * 회귀값을 잘못 실측해 130 을 썼다(실제 최대 회귀값 143 이 통과). 그래서 150 까지 올렸더니
   * 이번엔 **정상 제품 변경이 관통**했다 — 지도 공존 화면 15개 중 하나가 지도를 그만 쓰면
   * 폐포가 122~155 로 줄어드는데(3개는 즉시 실패·1개는 여유 0), 그중 143 은 **회귀 A 와 정확히
   * 같은 값**이라 이 지표로는 두 사건이 **원리적으로 구분되지 않는다**(R3 실증).
   *
   * ★그래서 축을 바꾼다. 회귀는 `mustInclude`(경로 형태별)와 `minDepth` 가 진다 —
   *   실측으로 확인했다: `minFiles: 1` 로 낮추고 상대 임포트 해석을 제거해도
   *   `mustInclude` 가 단독으로 잡는다. 이 하한은 "폐포가 통째로 무너졌다"만 본다.
   */
  minFiles: number;
  /**
   * 최소 최대깊이 — **필수**. 개수 하한만으로는 "깊이에서 자르기"를 못 잡는다
   * (실측: 깊이 2 절단 140 · 깊이 3 절단 155 — 개수로는 정상과 구분되지 않는다).
   * 이 PR 이 고친 결함 "1단계만 봤다"의 한 칸 옆 버전이 그대로 재발하는 자리다.
   * ※깊이 4 인 파일은 실측 2건뿐이라, 앱 구조가 정상적으로 얕아지면 이 가드가 먼저 운다 —
   *   오류 메시지가 그 가능성을 함께 말하게 해 두었다(도구 고장으로 오도하지 않도록).
   */
  minDepth: number;
  /**
   * 반드시 폐포에 들어와야 하는 파일들 — **필수**. 해석기의 **분기마다** 하나씩 넣어야
   * 목록형이 아니라 경로형 잠금이 된다(`./`·`../`·확장자·index 별로).
   */
  mustInclude: string[];
};

/**
 * 진입 파일들에서 시작해 **정적·동적 임포트를 끝까지** 따라간 전이 폐포를 돌려준다
 * (진입 파일 포함). 저장소 안(별칭·상대)만 따라가므로 node_modules 로 새지 않는다.
 *
 * ★`expect` 는 **필수 인자**다 — 이 파일의 `assertWiredThrough` 가 `minMatches` 를 필수로
 *   받아 공허진리를 구조적으로 막는 것과 같은 설계다. 초판은 그 강제 없이 호출자의 느슨한
 *   단언에 맡겼고, 그중 하나가 실제로 공허했다(독립 검증 M4·H2).
 */
export function importClosure(entries: string[], expect: ClosureExpectation): string[] {
  const seen = new Set(entries);
  const depth = new Map(entries.map((e) => [e, 0]));
  const queue = [...entries];
  while (queue.length) {
    const rel = queue.shift()!;
    // ★읽기 실패를 **삼키지 않는다**. 초판은 try/catch 로 `continue` 했는데 두 가지가 나빴다:
    //   ① 폐포가 조용히 줄어든다 = 감시 대상이 사라지는데 초록 — 이 도구가 막으려는 바로 그 실패.
    //   ② 변이검증에서 이 catch 가 `rel` 미정의(ReferenceError)까지 삼켜 **큐가 안 줄어드는
    //      무한 루프**가 됐다(실측: 변이 하나가 vitest 를 영원히 멈춰 세웠다).
    //   진입은 walk() 로 실재를 확인했고 확장은 resolveModuleSpec 이 existsSync 로 거른다 —
    //   그래도 못 읽으면 그건 알아야 할 사건이므로 그대로 던진다.
    const src = readFileSync(resolve(process.cwd(), rel), "utf8");
    for (const m of src.matchAll(/(?:from\s+|import\()\s*["'`]([^"'`]+)["'`]/g)) {
      const next = resolveModuleSpec(rel, m[1]);
      if (!next || seen.has(next)) continue;
      seen.add(next);
      depth.set(next, depth.get(rel)! + 1);
      queue.push(next);
    }
  }
  const maxDepth = Math.max(...depth.values());
  if (seen.size < expect.minFiles)
    throw new Error(
      `[import-closure] 폐포 ${seen.size}파일 < 최소 ${expect.minFiles} — 경로 해석이 통째로 ` +
        "깨졌거나(감시 대상이 조용히 사라진다), 지도 공존 화면이 정상적으로 줄었다. " +
        "후자면 기대값을 낮춰라 — 도구 고장으로 오도하지 말 것.",
    );
  if (maxDepth < expect.minDepth)
    throw new Error(
      `[import-closure] 최대깊이 ${maxDepth} < 최소 ${expect.minDepth} — 임포트를 끝까지 ` +
        "따라가지 못하고 있거나(깊은 곳의 모달이 감시망 밖), 앱 임포트 체인이 정상적으로 " +
        "얕아졌다. 후자면 기대값을 낮춰라 — 도구 고장으로 오도하지 말 것.",
    );
  for (const f of expect.mustInclude)
    if (!seen.has(f))
      throw new Error(
        `[import-closure] ${f} 가 폐포에 없다 — 그 파일에 닿는 임포트 형태(상대·확장자·index)의 ` +
          "해석이 깨졌거나, 그 파일을 끌어오던 지도 공존 화면이 정상적으로 사라졌다. " +
          "후자면 기대 목록을 갱신하라 — 도구 고장으로 오도하지 말 것.",
      );
  return [...seen];
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
