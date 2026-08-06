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
 * ──────────────────────────────────────────────────────────────────────────── */

/** 한 개의 `className` 속성에서 읽어낸 백드롭 후보. */
export type BackdropHit = {
  /** apps/web 기준 상대 경로(수집기가 채운다). */
  file: string;
  /** className 이 통짜 문자열이었으면 true. false = 삼항·`cn()`·템플릿 조립. */
  literal: boolean;
  /** 표현식 안 문자열 조각을 이어붙인 클래스 후보(판정 근거를 그대로 보고하기 위함). */
  classes: string;
  /** 그 안에서 읽어낸 z 값들. 조건부면 여러 개이고, 하나도 없으면 빈 배열. */
  zs: number[];
};

/**
 * 주석을 **줄 수를 보존한 채** 지운다(JSX 주석 + 줄 끝 `//`).
 *
 * ★정직한 경계: 최상위 블록 주석(`/* … *\/`)은 벗기지 않는다. JSX 본문 안에서는
 *   블록 주석이 문법상 `{/* … *\/}` 형태여야 하므로 실제 "렌더를 주석 처리하는"
 *   변이는 위 두 형태로 나타난다. 그래도 소스 검사인 이상 완전면역은 아니므로,
 *   소비처는 **수집 개수 하한**을 함께 단언해 통째 주석 처리가 초록으로 지나가지
 *   않게 해야 한다(rule 2 — 공허 진리 가드).
 */
function stripComments(src: string): string {
  return stripJsxComments(src)
    .split("\n")
    .map((l) => stripLineComment(l))
    .join("\n");
}

/**
 * `className` 속성의 값을 잘라낸다. `="…"` 는 그대로, `={…}` 는 **중괄호 균형**으로
 * 끝을 찾는다(문자열 안의 괄호는 세지 않는다).
 */
function classNameValues(src: string): { raw: string; literal: boolean }[] {
  const out: { raw: string; literal: boolean }[] = [];
  const re = /className\s*=\s*/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(src))) {
    const i = m.index + m[0].length;
    const ch = src[i];
    if (ch === '"' || ch === "'") {
      const end = src.indexOf(ch, i + 1);
      if (end < 0) continue;
      out.push({ raw: src.slice(i + 1, end), literal: true });
      re.lastIndex = end;
    } else if (ch === "{") {
      let depth = 0;
      let quote: string | null = null;
      let j = i;
      for (; j < src.length; j++) {
        const c = src[j];
        if (quote) {
          if (c === "\\") j++;
          else if (c === quote) quote = null;
          continue;
        }
        if (c === '"' || c === "'" || c === "`") quote = c;
        else if (c === "{") depth++;
        else if (c === "}" && --depth === 0) break;
      }
      out.push({ raw: src.slice(i + 1, j), literal: false });
      re.lastIndex = j;
    }
  }
  return out;
}

/** 표현식 안의 문자열/템플릿 조각만 모은다(삼항·`cn()` 인자 등). */
function stringChunks(expr: string): string[] {
  const chunks: string[] = [];
  const re = /(["'`])((?:\\.|(?!\1)[^\\])*)\1/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(expr))) chunks.push(m[2]);
  return chunks;
}

const HAS_CLASS = (t: string, cls: string) =>
  new RegExp(`(?:^|\\s)${cls}(?:\\s|$)`).test(t);

/**
 * 소스에서 **모달 백드롭**(`fixed` + `inset-0`)인 className 을 전부 모은다.
 *
 * ★`pointer-events-none` 이 붙은 것은 제외한다 — 클릭을 받지 않는 **배경 장식**이지
 *   모달 백드롭이 아니다(실측 2건: AuthWorkspaceClient·PasswordRecoveryClient 의
 *   `pointer-events-none fixed inset-0 -z-10`). 이걸 위반으로 신고하면 정상 코드를
 *   막는다 — 이 저장소가 이미 두 번 데인 **가드 위양성**(rule 6)이다.
 */
export function collectBackdrops(source: string, file = ""): BackdropHit[] {
  const src = stripComments(source);
  const hits: BackdropHit[] = [];
  for (const v of classNameValues(src)) {
    const classes = (v.literal ? [v.raw] : stringChunks(v.raw))
      .join(" ")
      // ★템플릿 안의 보간(`${big ? "z-[800]" : "z-50"}`)은 조각 하나로 들어오므로, 따옴표·
      //   `${`·중괄호를 공백으로 바꿔 **클래스 토큰을 공백으로 분리**한다. 이걸 빼먹으면
      //   `"z-50"` 이 따옴표에 붙어 z 정규식(앞이 공백)에 걸리지 않고 **조용히 z 없음**이
      //   되어, 삼항으로 낮은 z 를 숨기는 형태가 그대로 통과한다(실측으로 적발).
      .replace(/\$\{|[`"'{}]/g, " ")
      .replace(/\s+/g, " ")
      .trim();
    if (!HAS_CLASS(classes, "fixed") || !HAS_CLASS(classes, "inset-0")) continue;
    if (HAS_CLASS(classes, "pointer-events-none")) continue;
    const zs = Array.from(classes.matchAll(/(?:^|\s)z-\[?(\d+)\]?(?=\s|$)/g)).map((z) =>
      Number(z[1]),
    );
    hits.push({ file, literal: v.literal, classes, zs });
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
  return null;
}

/**
 * 진입 파일들에서 시작해 **정적·동적 임포트를 끝까지** 따라간 전이 폐포를 돌려준다
 * (진입 파일 포함). 저장소 안(별칭·상대)만 따라가므로 node_modules 로 새지 않는다.
 */
export function importClosure(entries: string[]): string[] {
  const seen = new Set(entries);
  const queue = [...entries];
  while (queue.length) {
    const rel = queue.shift()!;
    let src: string;
    try {
      src = readFileSync(resolve(process.cwd(), rel), "utf8");
    } catch {
      continue;
    }
    for (const m of src.matchAll(/(?:from\s+|import\()\s*["'`]([^"'`]+)["'`]/g)) {
      const next = resolveModuleSpec(rel, m[1]);
      if (!next || seen.has(next)) continue;
      seen.add(next);
      queue.push(next);
    }
  }
  return [...seen];
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
