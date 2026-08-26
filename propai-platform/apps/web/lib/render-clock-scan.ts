/**
 * 렌더 중 실행되는 **비결정 시각 호출** 탐지 — AST 기반.
 *
 * ## 무엇을 막는가
 *
 * 컴포넌트 본문에서 `new Date()` / `Date.now()` 를 부르고 그 값을 화면에 그리면 **두 가지**가 생긴다:
 *  1. **거짓 근거** — 라벨이 *"마지막 업데이트"* 라고 말하는데 값은 **화면을 그린 순간**이다.
 *  2. **하이드레이션 불일치**(React #418) — 서버 렌더 시각 ≠ 클라이언트 하이드레이트 시각이라
 *     같은 자리의 텍스트가 갈린다.
 *
 * ★로컬 프로덕션 빌드 변이로 확정했다(2026-08-25): `ProjectsOverviewClient` 의 그 한 줄만
 *   상수로 고정하니 `/ko/projects` 의 #418 이 **1 → 0**, 같은 배치의 양성 대조군 2 라우트는 1 유지.
 *   ★그리고 이 결함은 **저장 상태와 무관**하다 — localStorage 가 비어 있어도 재현된다
 *   (persist 파생 조건부 렌더가 원인인 다른 라우트와 **다른 축**이다).
 *
 * ## ★왜 정규식이 아니라 AST 인가
 *
 * 정규식 스윕(`^  const … = … new Date()`)은 **2칸 대입문만** 본다. 실측으로 그 방식은
 * 같은 형태 **3건을 놓쳤다**(`DeskAppraisalReportClient` · `TaxPanel` · `SreDashboardClient`).
 * 또 *"들여쓰기 2칸 = 컴포넌트 본문"* 은 **모듈 스코프 함수 본문**과 구별되지 않아 위양성을 낸다.
 * 여기서는 감싸는 함수 경계를 AST 로 올라가며 **콜백·핸들러·effect 를 제외**한다.
 *
 * ## 판정 한계(정직 표기)
 *
 * - `함수본문` 은 **판정 불가**로 둔다. 그 함수가 JSX 에서 불리면 렌더 중이지만, 간접 호출까지
 *   추적하지 않는다. 이 락은 그 부류를 **잠그지 않는다**(위양성으로 정상 코드를 막지 않기 위해).
 * - 그러므로 이 스캐너의 결과는 **하한**이다. 0건이 "없음"을 뜻하지 않는다.
 */
import ts from "typescript";

export type ClockPhase =
  /** 컴포넌트 본문(JSX 를 반환하는 함수) — 렌더 중 확정 */
  | "component-body"
  /** 배열 콜백(map/filter/…) — 렌더 중 확정(JSX 조립 경로) */
  | "array-callback";

export interface ClockHit {
  file: string;
  line: number;
  kind: "new Date()" | "Date.now()";
  phase: ClockPhase;
}

function clockKind(n: ts.Node): ClockHit["kind"] | null {
  if (
    ts.isNewExpression(n) &&
    n.expression.getText() === "Date" &&
    (!n.arguments || n.arguments.length === 0)
  ) {
    return "new Date()";
  }
  if (ts.isCallExpression(n) && n.expression.getText() === "Date.now") return "Date.now()";
  return null;
}

/** 인자로 넘겨지는 콜백의 호출자 이름 — 렌더 중이 아닌 부류를 가려낸다. */
/**
 * **렌더 이후**에 실행되는 콜백의 호출자 — 여기 안의 시각 호출은 하이드레이션과 무관하다.
 *
 * ★`useMemo` 는 **일부러 빼 놓았다.** 그것은 **렌더 중 실행**되므로 서버와 클라이언트가
 *   각각 부르고, 결과가 화면에 닿으면 똑같이 불일치를 만든다. `useCallback` 은 함수를 만들 뿐
 *   본문을 실행하지 않으므로 여기 남는다.
 */
const DEFERRED = /^(useEffect|useLayoutEffect|useCallback|setTimeout|setInterval|requestAnimationFrame|queueMicrotask)$/;
/** 렌더 중 실행되는 훅 콜백 — `useMemo` 는 렌더 단계다. */
const RENDER_HOOK = /^useMemo$/;
const ARRAY_CB = /\.(map|filter|forEach|reduce|sort|find|some|every)$/;

/** 렌더 중 실행이 **확정**되는 경우만 phase 를 돌려준다. 판정 불가·비렌더는 null. */
function renderPhase(node: ts.Node, sf: ts.SourceFile): ClockPhase | null {
  let cur: ts.Node | undefined = node.parent;
  while (cur) {
    if (
      ts.isFunctionDeclaration(cur) ||
      ts.isFunctionExpression(cur) ||
      ts.isArrowFunction(cur) ||
      ts.isMethodDeclaration(cur)
    ) {
      const p = cur.parent;
      if (p && ts.isCallExpression(p) && p.arguments.includes(cur as ts.Expression)) {
        const callee = p.expression.getText();
        // ★변이 생존을 코드에 적어 둔다(점수 부풀리기 방지): 이 줄을 무력화해도 테스트는 통과한다.
        //   `useEffect` 류는 아래 폴백("그 밖의 콜백 → null")이 **같은 답**을 주기 때문이다 —
        //   즉 여기는 **이중 가드**이고 그 생존은 구멍이 아니다.
        //   그럼에도 이 목록을 남기는 이유: 폴백이 나중에 "콜백도 잡는다"로 바뀌면 이 줄이 유일한
        //   방어가 된다. `useMemo` 를 여기서 뺀 것이 그 목록에 실질을 준다(아래 RENDER_HOOK).
        if (DEFERRED.test(callee)) return null;
        if (RENDER_HOOK.test(callee)) return "component-body";
        if (ARRAY_CB.test(callee)) return "array-callback";
        return null; // 그 밖의 콜백(핸들러 등)
      }
      // onClick={() => …} 같은 JSX 속성 안의 함수는 이벤트 시점이라 렌더 중이 아니다.
      if (p && (ts.isJsxAttribute(p) || ts.isJsxExpression(p))) return null;
      const txt = cur.getText(sf);
      const returnsJsx = /return\s*\(?\s*</.test(txt) || /=>\s*\(?\s*</.test(txt);
      return returnsJsx ? "component-body" : null; // 판정 불가는 잠그지 않는다
    }
    cur = cur.parent;
  }
  return null; // 모듈 스코프
}

/** 한 파일에서 렌더 중 시각 호출을 모은다. */
export function scanRenderClocks(file: string, source: string): ClockHit[] {
  const sf = ts.createSourceFile(file, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const out: ClockHit[] = [];
  const visit = (n: ts.Node): void => {
    const kind = clockKind(n);
    if (kind) {
      const phase = renderPhase(n, sf);
      if (phase) {
        out.push({ file, line: sf.getLineAndCharacterOfPosition(n.getStart(sf)).line + 1, kind, phase });
      }
    }
    ts.forEachChild(n, visit);
  };
  visit(sf);
  return out;
}

/**
 * ★래칫 **판정** — 스캔 결과 중 등재부에 없는 파일들.
 *
 * 순수 함수로 꺼내 둔 이유: 테스트에서 이 판정을 `scanAll()` 결과로만 태우면
 * **현재 미등재가 0건이라 단언이 공허한 참**이 된다(변이 검증에서 실제로 생존했다 —
 * `unlisted` 를 빈 배열로 갈아 끼워도 통과했다). 합성 입력으로 **판정 자체**를 태운다.
 */
export function unlistedFiles(
  hits: ReadonlyArray<Pick<ClockHit, "file">>,
  ratchet: Readonly<Record<string, string>>,
): string[] {
  return [...new Set(hits.map((h) => h.file).filter((f) => !(f in ratchet)))].sort();
}

/** 래칫에 적혀 있는데 소스에서 사라진 항목 — 목록이 낡지 않게 한다. */
export function staleRatchetEntries(
  hits: ReadonlyArray<Pick<ClockHit, "file">>,
  ratchet: Readonly<Record<string, string>>,
): string[] {
  const present = new Set(hits.map((h) => h.file));
  return Object.keys(ratchet).filter((f) => !present.has(f)).sort();
}
