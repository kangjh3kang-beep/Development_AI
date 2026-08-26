/**
 * **렌더 경로에서 라이브 저장소를 읽는 자리**를 소스에서 파생 수집한다(하이드레이션 불일치 탐지).
 *
 * ─ 왜 필요한가 ─────────────────────────────────────────────────────────────
 * zustand v5 의 `useStore` 는 `useSyncExternalStore(subscribe, getState, **getInitialState**)` 로
 * 붙는다. React 는 **클라이언트 하이드레이션 렌더에서도 서버 스냅샷**(세 번째 인자)을 쓰므로,
 * **셀렉터로만 읽는 persist 소비는 원리적으로 불일치를 만들지 못한다.**
 *   → `apps/web/lib/__tests__/zustand-hydration-snapshot.contract.test.tsx` 가 이 전제를 잠근다.
 *
 * 불일치는 그 스냅샷을 **우회**할 때만 난다. 우회 경로는 셋이다:
 *   ① `useXStore.getState()` 를 **렌더 중** 호출(= 라이브 상태)
 *   ② 스토어가 노출한 **메서드**(`stageCompletion()` 등)를 렌더 중 호출 — 내부에서 `get()` 을 쓴다
 *   ③ 렌더 중 `localStorage` 직접 읽기
 * ★①은 `useState` **지연 초기값**과 `useMemo` 콜백을 포함한다 — 둘 다 **렌더 중에 실행**된다.
 *   반대로 `useEffect`·`useCallback`·이벤트 핸들러 본문은 렌더 중에 실행되지 않아 안전하다.
 *
 * ─ 실증(2026-08-26) ────────────────────────────────────────────────────────
 * `GlobalAddressSearch` 의 `useState(() => … getState().siteAnalysis?.parcels …)` 가
 * 서버 `[]`(배지 "대기") / 클라 77필지(배지 "77필지") 를 그려 라이브에서 **React #418**
 * (`args[]=text`)이 났다. `/ko/regulations`·`/ko/permits` 각 1건 · `/ko/mypage/profile` 0건.
 * ★그 직전 PR(#850)은 **같은 컴포넌트 트리의 다른 것**(드롭다운 노드 유무)을 고쳤고,
 *   예측(배포 후 0)이 **반증**됐다 — 셀렉터 읽기였기 때문이다. **분류가 곧 처방을 가른다.**
 *
 * ★이 수집기는 **목록형이 아니라 파생형**이다. 새 파일·새 컴포넌트가 같은 패턴을 쓰면
 *   허용목록에 없는 한 자동으로 걸린다.
 */
import ts from "typescript";

export type RenderPathRead = {
  file: string;
  line: number;
  kind: "getState" | "localStorage" | "store-method";
  /** 렌더 중 실행되는 이유(어떤 훅 콜백 안인지) */
  via: "component-body" | "useState-initializer" | "useMemo" | "useSyncExternalStore";
  text: string;
};

/** 렌더 중에 **실행되지 않는** 콜백을 만드는 훅·API. 이 안에 있으면 안전하다. */
const DEFERRED_HOOKS = new Set([
  "useEffect", "useLayoutEffect", "useCallback", "useInsertionEffect", "useImperativeHandle",
  "setTimeout", "setInterval", "requestAnimationFrame", "queueMicrotask", "then", "catch", "finally",
]);
/**
 * 스토어 메서드 중 **상태를 바꾸는 것**(뮤테이션)은 이 검사의 대상이 아니다.
 * 하이드레이션 불일치는 *읽은 값이 렌더에 실린* 결과이고, 뮤테이션은 값을 돌려주지 않는다.
 * (렌더 중 뮤테이션 호출은 **다른 결함 클래스**다 — `projects/new/page.tsx` 의
 *  `useState(() => { clearProject(); … })` 가 실례다. 이 파일이 그것까지 잠근다고 쓰지 않는다.)
 */
const MUTATION_PREFIX =
  /^(set|update|clear|mark|add|revert|remove|reset|delete|toggle|save|push|consume|sync|trigger|apply|start|stop|cancel|record|register|init|load|refresh|schedule|enqueue|run)/;

/** 렌더 중에 **실행되는** 콜백. */
const RENDER_HOOKS: Record<string, RenderPathRead["via"]> = {
  useMemo: "useMemo",
  useState: "useState-initializer",
  useSyncExternalStore: "useSyncExternalStore",
};

function isStoreGetState(node: ts.CallExpression): boolean {
  const e = node.expression;
  if (!ts.isPropertyAccessExpression(e) || e.name.text !== "getState") return false;
  const base = e.expression;
  return ts.isIdentifier(base) && /^use[A-Z]\w*Store$/.test(base.text);
}
function isLocalStorageRead(node: ts.CallExpression): boolean {
  const e = node.expression;
  if (!ts.isPropertyAccessExpression(e)) return false;
  if (e.name.text !== "getItem") return false;
  const t = e.expression.getText();
  return /(^|\.)localStorage$/.test(t) || /sessionStorage$/.test(t);
}

/**
 * 이 호출이 렌더 중에 실행되는가를 **조상 체인**으로 판정한다.
 * 가장 가까운 함수 경계부터 위로 올라가며, 그 함수가 무엇의 인자인지 본다.
 * - `useEffect`/`useCallback`/… 의 인자 → 안전(null)
 * - `useMemo`/`useState`/`useSyncExternalStore` 의 인자 → 렌더 중
 * - 아무 호출의 인자도 아니고 컴포넌트 함수까지 올라가면 → 컴포넌트 본문(렌더 중)
 * - 그 외(일반 함수 선언·중첩 함수) → 안전(호출 시점을 알 수 없으므로 보수적으로 제외)
 */
function renderPhase(node: ts.Node): RenderPathRead["via"] | null {
  let cur: ts.Node | undefined = node;
  while (cur) {
    const fn = findEnclosingFunction(cur);
    if (!fn) return null;
    const parent = fn.parent;
    if (parent && ts.isCallExpression(parent)) {
      const callee = parent.expression;
      const name = ts.isIdentifier(callee) ? callee.text
        : ts.isPropertyAccessExpression(callee) ? callee.name.text : "";
      if (DEFERRED_HOOKS.has(name)) return null;
      if (name in RENDER_HOOKS) return RENDER_HOOKS[name];
      return null; // 알 수 없는 고차함수 — 보수적으로 제외(위양성 방지)
    }
    // 함수가 어떤 호출의 인자가 아니다 → 컴포넌트/일반 함수 선언
    if (isLikelyComponent(fn)) return "component-body";
    return null;
  }
  return null;
}
function findEnclosingFunction(n: ts.Node): ts.Node | undefined {
  let p: ts.Node | undefined = n.parent;
  while (p) {
    if (ts.isArrowFunction(p) || ts.isFunctionExpression(p) || ts.isFunctionDeclaration(p) || ts.isMethodDeclaration(p)) return p;
    p = p.parent;
  }
  return undefined;
}
/** 대문자로 시작하는 이름 = React 컴포넌트 관례. */
function isLikelyComponent(fn: ts.Node): boolean {
  if (ts.isFunctionDeclaration(fn) && fn.name) return /^[A-Z]/.test(fn.name.text);
  const p = fn.parent;
  if (p && ts.isVariableDeclaration(p) && ts.isIdentifier(p.name)) return /^[A-Z]/.test(p.name.text);
  return false;
}

/**
 * 이 식별자가 **재수화 게이트 뒤**에 있는가 — `hydrated && f()` · `hydrated ? f() : x`.
 * `useHydrated()` 로 만든 변수 이름 집합을 받아 조상 체인에서 그 가드를 찾는다.
 * ★가드를 못 보면 안전한 코드를 위반으로 신고하게 된다(위양성도 결함이다 — 저장소 §A-6).
 */
function isBehindHydrationGate(node: ts.Node, gateNames: Set<string>): boolean {
  const named = (n: ts.Node): boolean => ts.isIdentifier(n) && gateNames.has(n.text);
  let cur: ts.Node | undefined = node;
  while (cur) {
    const p: ts.Node | undefined = cur.parent;
    if (!p) break;
    if (ts.isBinaryExpression(p) && p.operatorToken.kind === ts.SyntaxKind.AmpersandAmpersandToken && p.right === cur && named(p.left)) return true;
    if (ts.isConditionalExpression(p) && named(p.condition) && p.whenTrue === cur) return true;
    // `if (!hydrated) return …` 로 조기 반환하는 형태는 함수 전체가 게이트된다.
    cur = p;
  }
  return false;
}
/** 함수 본문 초입에 `if (!hydrated) return …` 형태의 조기 반환이 있는가. */
function hasEarlyHydrationReturn(sf: ts.SourceFile, gateNames: Set<string>): boolean {
  let found = false;
  const visit = (n: ts.Node): void => {
    if (found) return;
    if (ts.isIfStatement(n)) {
      const c = n.expression;
      const isNegGate = ts.isPrefixUnaryExpression(c) && c.operator === ts.SyntaxKind.ExclamationToken
        && ts.isIdentifier(c.operand) && gateNames.has(c.operand.text);
      const isNegGateInAnd = ts.isBinaryExpression(c) && c.operatorToken.kind === ts.SyntaxKind.BarBarToken
        && ts.isPrefixUnaryExpression(c.left) && ts.isIdentifier(c.left.operand) && gateNames.has(c.left.operand.text);
      if ((isNegGate || isNegGateInAnd) && n.thenStatement) found = true;
    }
    ts.forEachChild(n, visit);
  };
  visit(sf);
  return found;
}

/** 한 파일에서 렌더 경로의 라이브 저장소 읽기를 모두 수집한다. */
export function scanSource(file: string, source: string): RenderPathRead[] {
  const sf = ts.createSourceFile(file, source, ts.ScriptTarget.ES2022, true, ts.ScriptKind.TSX);
  const out: RenderPathRead[] = [];

  // ── 1차 통과: 이름 수집 ──
  //   ①`useHydrated()` 로 만든 게이트 변수  ②스토어 셀렉터로 꺼낸 **메서드** 변수
  const gateNames = new Set<string>();
  const storeMethodNames = new Set<string>();
  const collect = (n: ts.Node): void => {
    if (ts.isVariableDeclaration(n) && ts.isIdentifier(n.name) && n.initializer && ts.isCallExpression(n.initializer)) {
      const call = n.initializer;
      const callee = call.expression;
      if (ts.isIdentifier(callee) && callee.text === "useHydrated") gateNames.add(n.name.text);
      // `const stageCompletion = useXStore((s) => s.stageCompletion);`
      if (ts.isIdentifier(callee) && /^use[A-Z]\w*Store$/.test(callee.text) && call.arguments.length === 1) {
        const arg = call.arguments[0];
        if (ts.isArrowFunction(arg) && ts.isPropertyAccessExpression(arg.body)
            && !MUTATION_PREFIX.test(n.name.text)) {
          storeMethodNames.add(n.name.text);
        }
      }
    }
    ts.forEachChild(n, collect);
  };
  collect(sf);
  const wholeComponentGated = gateNames.size > 0 && hasEarlyHydrationReturn(sf, gateNames);

  const visit = (n: ts.Node): void => {
    if (ts.isCallExpression(n)) {
      // ②스토어가 노출한 메서드를 렌더 중 호출 — 내부에서 `get()`(라이브 상태)을 읽는다.
      //   2026-08-13 `LifecycleProgressRail` 사고가 이 형태였다.
      if (ts.isIdentifier(n.expression) && storeMethodNames.has(n.expression.text)) {
        const via = renderPhase(n);
        if (via && !wholeComponentGated && !isBehindHydrationGate(n, gateNames)) {
          out.push({ file, kind: "store-method", via,
            line: sf.getLineAndCharacterOfPosition(n.getStart(sf)).line + 1,
            text: n.getText(sf).slice(0, 120) });
        }
      }
      const kind = isStoreGetState(n) ? "getState" : isLocalStorageRead(n) ? "localStorage" : null;
      if (kind) {
        const via = renderPhase(n);
        if (via && !wholeComponentGated && !isBehindHydrationGate(n, gateNames)) {
          out.push({
            file, kind, via,
            line: sf.getLineAndCharacterOfPosition(n.getStart(sf)).line + 1,
            text: n.getText(sf).slice(0, 120),
          });
        }
      }
    }
    ts.forEachChild(n, visit);
  };
  visit(sf);
  return out;
}
