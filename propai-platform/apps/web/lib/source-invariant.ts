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
  //   되돌렸을 때를 대비한 **회귀 백스톱**이다. 저장소 최장 정당 주석은 13줄이라 여유 3.08배(R3 재실측 — 12줄이라 적었던 것 정정).
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
 *
 * ★변이검증 생존 판정(다음 사람이 다시 판정하지 않게). **합이 맞는지 세어라** — 한 번은
 *   "12건"이라 적었는데 내역 합이 13이었다:
 *   · 타입 필드 삭제 — vitest 는 타입을 지우고 돌리므로 생존이 당연하다. **추정이 아니라
 *     실측**했다: `minFiles` 를 지우면 `tsc --noEmit` 이 TS2353 1건 + TS2339 2건을 낸다
 *     (= type-check 게이트가 지는 몫).
 *   · `importClosure` 의 **오류 메시지 문구** — 던지는 **조건**은 픽스처로 잠겨 있다
 *     (`source-invariant.backdrop.test.ts` 의 throw 3종). 한때 "조건도 전부 CAUGHT"라고
 *     적었으나 **거짓이었고**(무력화해도 초록이었다) 그래서 픽스처를 넣었다. 문구 자체는
 *     사용자 산출물이 아니라 개발자 진단이라 계약이 아니다.
 *   ★생존 0 이 목표가 아니라 **설명 못 하는 생존을 남기지 않는 것**이 목표다.
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
 * 주석을 **줄 수를 보존한 채** 지운다(JSX 주석 + 줄 끝 `//`).
 *
 * ★★최상위 블록 주석(`/* … *\/`)은 **일부러 벗기지 않는다**. R1 에서 "주석 안 백드롭을
 *   집계한다(위양성)"는 지적을 받고 스트립을 넣었다가 **수백 파일 규모의 실코드를 삼키는
 *   맹점**을 만들었다(스코프에 따라 404~576파일·6,890~11,258줄 — R2 가 보고한 474/9,882 는
 *   R3 가 재현하지 못했다. ★나는 그 숫자를 **재실측 없이 옮겨 적었다**. 결론(맹점 실재)은
 *   주입 실증으로 확증됐지만 수치는 근거가 없었다). 원인: 이 저장소에는 `//` 주석 안의 `/*`(`// /auction/* 는 …`)와
 *   문자열 안의 `/*`(`accept="…,image/*"`)가 흔한데, 그게 블록 주석 시작으로 잡혀 다음 `*\/`
 *   까지 통째로 공백이 됐다. 실제로 `AuctionMonitorPanel`(지도 시드!)에 z-50 백드롭을 주입해도
 *   계약이 초록이었다 — **봉합 전에는 잡던 위반을 못 잡게** 됐다.
 * ★그리고 고치려던 위양성은 **실저장소에 0건**이었다(832파일 대조에서 달라진 2건이 모두
 *   테스트 픽스처). 없는 결함을 고치려다 실재하는 맹점을 만든 것이라 되돌린다.
 * ★같은 파일 위쪽 `stripJsxComments` 가 "44,444자를 통째로 삼켰다"고 스스로 박제한 사고의
 *   **직계 재발**이다. 다시 넣으려면 ①줄주석 제거 **뒤에** ②문자열을 건너뛰는 스캔으로
 *   ③span 상한 throw 까지 갖춰야 한다.
 * ★소비처는 **수집 개수 하한**을 함께 단언해 통째 주석 처리가 초록으로 지나가지 않게 한다
 *   (rule 2). 다만 그 하한은 "사라짐"만 잡고 "안 보임"은 못 잡는다(위 맹점이 그래서 통과했다).
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
  const src = stripComments(source);
  const hits: BackdropHit[] = [];
  for (const v of classNameValues(src)) {
    if (!v.literal) continue;
    const classes = v.raw.replace(/\s+/g, " ").trim();
    if (!HAS_CLASS(classes, "fixed") || !HAS_CLASS(classes, "inset-0")) continue;
    if (HAS_CLASS(classes, "pointer-events-none")) continue;
    const zs = Array.from(classes.matchAll(Z_UTIL)).map((z) => Number(z[1]));
    hits.push({ file, classes, zs });
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
