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
  /**
   * z 를 **소스만으로 판정할 수 있는가**. false = 판정불가(변수로 조립한 z ·
   * 같은 요소의 인라인 `style={{ zIndex }}`). ★판정불가를 위반과 섞으면 정상 코드를
   * 막는다 — 이 저장소가 zoning 커버리지에서 쓰는 "갭 vs 판정불가" 구분과 같은 처방이다.
   */
  resolvable: boolean;
};

/**
 * 주석을 **줄 수를 보존한 채** 지운다(JSX 주석 + 블록 주석 + 줄 끝 `//`).
 *
 * ★블록 주석(`/* … *\/`)도 벗긴다 — 초판은 "JSX 안에서는 `{/* *\/}` 형태여야 하므로
 *   불필요"라고 적었는데 **방향이 반대**였다(독립 검증 L1). 컴포넌트 위 JSDoc 예시나
 *   주석 처리된 컴포넌트 전체가 그대로 집계돼 **없는 백드롭을 신고**한다(위양성).
 * ★그래도 소스 검사인 이상 완전면역은 아니므로, 소비처는 **수집 개수 하한**을 함께
 *   단언해 통째 주석 처리가 초록으로 지나가지 않게 해야 한다(rule 2 — 공허 진리 가드).
 */
function stripComments(src: string): string {
  return stripJsxComments(src)
    .replace(/\/\*(?:(?!\*\/)[\s\S])*\*\//g, (m) => m.replace(/[^\n]/g, " "))
    .split("\n")
    .map((l) => stripLineComment(l))
    .join("\n");
}

/**
 * `className` 속성의 값을 잘라낸다. `="…"` 는 그대로, `={…}` 는 **중괄호 균형**으로
 * 끝을 찾는다(문자열 안의 괄호는 세지 않는다).
 */
function classNameValues(src: string): { raw: string; literal: boolean; end: number }[] {
  const out: { raw: string; literal: boolean; end: number }[] = [];
  const re = /className\s*=\s*/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(src))) {
    const i = m.index + m[0].length;
    const ch = src[i];
    if (ch === '"' || ch === "'") {
      const end = src.indexOf(ch, i + 1);
      if (end < 0) continue;
      out.push({ raw: src.slice(i + 1, end), literal: true, end });
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
      out.push({ raw: src.slice(i + 1, j), literal: false, end: j });
      re.lastIndex = j;
    }
  }
  return out;
}

const HAS_CLASS = (t: string, cls: string) =>
  new RegExp(`(?:^|\\s)${cls}(?:\\s|$)`).test(t);

/** 표현식 텍스트를 **런타임에 가능한 클래스 조합**으로 펼친다(삼항 갈래별). */
function classVariants(expr: string, literal: boolean): string[] {
  const normalize = (t: string) =>
    // ★템플릿 보간(`${big ? "z-[800]" : "z-50"}`)은 조각 하나로 들어오므로, 따옴표·`${`·중괄호를
    //   공백으로 바꿔 **클래스 토큰을 공백으로 분리**한다. 빼먹으면 `"z-50"` 이 따옴표에 붙어
    //   z 정규식(앞이 공백)에 안 걸려 **조용히 z 없음**이 된다(실측으로 적발).
    t.replace(/\$\{|[`"'{}]/g, " ").replace(/\s+/g, " ").trim();

  if (literal) return [normalize(expr)];

  // ★삼항은 **갈래를 합치지 않는다**. 합치면 배타적인 두 상태가 한 덩어리가 되어
  //   `open ? "fixed inset-0 z-[800]" : "hidden z-10"` 의 z-10 이 백드롭 위반으로 신고된다
  //   (독립 검증 H4 실증 — 정상 코드를 막는 가드 위양성). 갈래별로 펼쳐, **그 갈래 자체가
  //   백드롭일 때만** z 를 따진다.
  // ★단 `?`·`:` 는 **따옴표 밖에서만** 갈래 경계다. 문자열을 쪼개면 템플릿 안의 보간
  //   (`` `fixed inset-0 ${big ? "z-[800]" : "z-50"}` ``)이 통째로 잘려 백드롭 자체를
  //   못 알아본다(실측으로 적발 — 이 변경의 첫 판이 그랬다). 템플릿 한 덩이는 한 조각이다.
  // ★`:` 는 **`?` 를 본 뒤에만** 경계다. 안 그러면 객체 리터럴 `{ "fixed inset-0 …": open }` 의
  //   콜론이 갈래를 쪼갠다.
  const chunks: { text: string; seg: number }[] = [];
  let seg = 0;
  let sawTernary = false;
  const QUOTED = /(["'`])((?:\\.|(?!\1)[^\\])*)\1/y;
  for (let i = 0; i < expr.length; i++) {
    const c = expr[i];
    if (c === '"' || c === "'" || c === "`") {
      QUOTED.lastIndex = i;
      const m = QUOTED.exec(expr);
      if (m) {
        chunks.push({ text: m[2], seg });
        i = QUOTED.lastIndex - 1;
        continue;
      }
    } else if (c === "?") {
      sawTernary = true;
      seg++;
    } else if (c === ":" && sawTernary) seg++;
  }
  if (!sawTernary) return [normalize(chunks.map((c) => c.text).join(" "))];

  const base = chunks.filter((c) => c.seg === 0).map((c) => c.text).join(" ");
  const branchSegs = [...new Set(chunks.filter((c) => c.seg > 0).map((c) => c.seg))];
  if (!branchSegs.length) return [normalize(base)];
  return branchSegs.map((s) =>
    normalize(`${base} ${chunks.filter((c) => c.seg === s).map((c) => c.text).join(" ")}`),
  );
}

const Z_UTIL = /(?:^|\s)(?:[\w-]+:)*z-\[?(\d+)\]?(?=\s|$)/g;

/**
 * 소스에서 **모달 백드롭**(`fixed` + `inset-0`)인 className 을 전부 모은다.
 *
 * ★`pointer-events-none` 이 붙은 것은 제외한다 — 클릭을 받지 않는 **배경 장식**이지
 *   모달 백드롭이 아니다(실측 2건: AuthWorkspaceClient·PasswordRecoveryClient 의
 *   `pointer-events-none fixed inset-0 -z-10`). 이걸 위반으로 신고하면 정상 코드를
 *   막는다 — 이 저장소가 이미 두 번 데인 **가드 위양성**(rule 6)이다.
 *
 * ★★정직한 커버리지 경계(독립 검증 H3 지적 — "면역을 거짓 주장하지 마라"):
 *   문자열 조각이 **표현식 안에 리터럴로** 있어야 보인다. `className={BACKDROP_CLS}` 처럼
 *   상수·변수·props 로 조립하면 조각이 없으므로 **아무것도 못 본다**(종전 정규식과 동일).
 *   그 경계는 계약 테스트의 `it.todo` 에 부채로 남겼다.
 * ★z 를 못 읽었을 때 `resolvable` 이 false 면 그것은 **위반이 아니라 판정불가**다
 *   (변수 z·인라인 `style={{zIndex}}`). 소비처가 둘을 갈라 보고해야 한다 —
 *   "갭 vs 판정불가"를 섞으면 정상 코드가 위반으로 신고된다.
 */
export function collectBackdrops(source: string, file = ""): BackdropHit[] {
  const src = stripComments(source);
  const hits: BackdropHit[] = [];
  for (const v of classNameValues(src)) {
    const variants = classVariants(v.raw, v.literal).filter(
      (c) => HAS_CLASS(c, "fixed") && HAS_CLASS(c, "inset-0") && !HAS_CLASS(c, "pointer-events-none"),
    );
    if (!variants.length) continue;
    const zs = variants.flatMap((c) => Array.from(c.matchAll(Z_UTIL)).map((z) => Number(z[1])));
    // ★z 를 못 읽었을 때만 "정말 소스로 판정 불가한가"를 따진다.
    //   ①비리터럴이면 z 가 변수로 조립됐을 수 있다 ②같은 요소가 인라인 `style={{ zIndex }}`
    //   로 층위를 줄 수 있다(이 저장소의 실제 관용 — SATONG_UI_Z 는 인라인으로 흘린다).
    //   창(窓)은 같은 태그 안으로 제한한다 — 다음 여는 태그(`<`)를 만나면 멈춘다.
    const tail = src.slice(v.end, v.end + 400).split("<")[0];
    const resolvable = zs.length > 0 || (v.literal && !/\bzIndex\b/.test(tail));
    hits.push({ file, literal: v.literal, classes: variants.join(" | "), zs, resolvable });
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
  // ★이 `return null` 은 변이로 잠기지 않는다(실측): 호출부가 `if (!next)` 로 보므로
  //   null 이든 undefined 든 동작이 같은 **등가 변이**다. 위 두 return 경로(패키지 · 해석 성공)가
  //   실제 판정을 지고, 그건 잠겨 있다.
  return null;
}

/** `importClosure` 가 **반드시** 받아야 하는 공허진리 방지 선언. */
export type ClosureExpectation = {
  /**
   * 최소 파일 수 — **필수**. ★하한은 "정상값의 절반"이 아니라 **회귀 상태의 값보다 위**여야
   * 한다. 초판은 실측 157 의 절반인 80 을 썼는데, 이 도구가 막겠다고 선언한 회귀
   * (별칭 전용·1단계 = 구판)의 폐포가 **99파일**이라 그 하한으로는 구판으로 되돌려도
   * 통과한다(독립 검증 H2 실증). 즉 하한을 정할 때 **회귀 쪽 값을 실측**해야 한다.
   */
  minFiles: number;
  /**
   * 최소 최대깊이 — **필수**. 개수 하한만으로는 "깊이 2 에서 자르기"를 못 잡는다
   * (독립 검증 H1 실증: 깊이 2·3 절단이 둘 다 SURVIVED). 이 PR 이 고친 결함
   * "1단계만 봤다"의 한 칸 옆 버전이 그대로 재발하는 자리다.
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
      `[import-closure] 폐포 ${seen.size}파일 < 최소 ${expect.minFiles} — 경로 해석이 깨지면 ` +
        "감시 대상이 조용히 사라지고 위반이 0 이 된다.",
    );
  if (maxDepth < expect.minDepth)
    throw new Error(
      `[import-closure] 최대깊이 ${maxDepth} < 최소 ${expect.minDepth} — 임포트를 끝까지 ` +
        "따라가지 못하고 있다(깊은 곳의 모달이 감시망 밖).",
    );
  for (const f of expect.mustInclude)
    if (!seen.has(f))
      throw new Error(
        `[import-closure] ${f} 가 폐포에 없다 — 그 파일에 닿는 임포트 형태(상대·확장자·index)의 ` +
          "해석이 깨졌다.",
      );
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
