/**
 * **렌더 경로에서 라이브 저장소를 읽는 자리**를 소스에서 파생 수집한다(하이드레이션 불일치 탐지).
 *
 * ─ 왜 필요한가 ─────────────────────────────────────────────────────────────
 * zustand v5 의 `useStore` 는 `useSyncExternalStore(subscribe, getState, **getInitialState**)` 로
 * 붙는다. React 는 **클라이언트 하이드레이션 렌더에서도 서버 스냅샷**(세 번째 인자)을 쓰므로,
 * **셀렉터로만 읽는 persist 소비는 원리적으로 불일치를 만들지 못한다.**
 *   ★단 그 세 번째 인자만으로는 **충분하지 않다.** 바닐라 `createStore` 의 `initialState` 는
 *   initializer 반환값이고, `persist` 는 그 안에서 **동기 재수화**를 끝낸다. 안전한 진짜 이유는
 *   `zustand/middleware` 가 `api.getInitialState = () => configResult` 로 **다시 덮어쓰기** 때문이다
 *   (독립 리뷰가 이 구분을 짚었다 — 필요조건을 충분조건처럼 적고 있었다).
 *   → `lib/hydration/__tests__/zustand-server-snapshot.contract.test.tsx` 가 **persist 픽스처로** 잠근다.
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

export type ReadKind = "getState" | "localStorage" | "store-method";
export type RenderVia = "component-body" | "useState-initializer" | "useMemo" | "useSyncExternalStore";

export type RenderPathRead = {
  file: string;
  line: number;
  kind: ReadKind;
  /** 렌더 중 실행되는 이유(어떤 훅 콜백 안인지) */
  via: RenderVia;
  text: string;
};

/** 렌더 중에 **실행되지 않는** 콜백을 만드는 훅·API. 이 안에 있으면 안전하다. */
const DEFERRED_HOOKS = new Set([
  "useEffect", "useLayoutEffect", "useCallback", "useInsertionEffect", "useImperativeHandle",
  "setTimeout", "setInterval", "requestAnimationFrame", "queueMicrotask", "then", "catch", "finally",
  "addEventListener", "subscribe",
]);
/** 렌더 중에 **실행되는** 콜백. */
const RENDER_HOOKS: Record<string, RenderVia> = {
  useMemo: "useMemo",
  useState: "useState-initializer",
  useSyncExternalStore: "useSyncExternalStore",
};
/**
 * **즉시 실행되는 콜백**을 받는 배열/객체 API — 렌더 안에서 쓰이면 그 콜백도 렌더 중에 돈다.
 * ★이걸 "알 수 없는 고차함수"로 버리면 `{rows.map((r) => …getState()…)}` 가 통째로 위음성이 된다
 *   (독립 리뷰 실측: `InputResolveModal.tsx` 의 진짜 자리가 정확히 이 사각에 숨어 있었다).
 */
const TRANSPARENT_CALLBACKS = new Set([
  "map", "filter", "flatMap", "reduce", "forEach", "some", "every", "find", "findIndex", "sort", "flat",
]);
/** 컴포넌트를 감싸기만 하는 래퍼 — 안쪽 함수는 여전히 컴포넌트 본문이다. */
const COMPONENT_WRAPPERS = new Set(["memo", "forwardRef", "observer"]);

/**
 * 스토어 메서드 중 **상태를 바꾸는 것**(뮤테이션)은 이 검사의 대상이 아니다.
 * 하이드레이션 불일치는 *읽은 값이 렌더에 실린* 결과이고, 뮤테이션은 값을 돌려주지 않는다.
 * (렌더 중 뮤테이션 호출은 **다른 결함 클래스**다 — `projects/new/page.tsx` 의
 *  `useState(() => { clearProject(); … })` 가 실례다. 이 파일이 그것까지 잠근다고 쓰지 않는다.)
 */
const MUTATION_PREFIX =
  /^(set|update|clear|mark|add|revert|remove|reset|delete|toggle|save|push|consume|sync|trigger|apply|start|stop|cancel|record|register|init|load|refresh|schedule|enqueue|run)/;

function calleeName(call: ts.CallExpression): string {
  const e = call.expression;
  if (ts.isIdentifier(e)) return e.text;
  if (ts.isPropertyAccessExpression(e)) return e.name.text;
  return "";
}
/**
 * `X.getState()` — X 가 식별자면 전부 본다.
 * ★`^use[A-Z]\w*Store$` 로 좁혔다가 별칭(`useProjectContext.getState()`)을 놓쳤다(리뷰 실측).
 *   `getState()` 는 zustand 관용구라 넓게 잡아도 위양성이 사실상 없다.
 */
function isStoreGetState(node: ts.CallExpression): boolean {
  const e = node.expression;
  return ts.isPropertyAccessExpression(e) && e.name.text === "getState" && ts.isIdentifier(e.expression);
}
const STORAGE_ROOT = /^(window\.)?(localStorage|sessionStorage)$/;
/** `localStorage.getItem(...)` · `localStorage.length` · `localStorage["k"]` 전부 읽기다. */
function isStorageRead(node: ts.Node): boolean {
  if (ts.isPropertyAccessExpression(node)) {
    if (!STORAGE_ROOT.test(node.expression.getText())) return false;
    return node.name.text !== "setItem" && node.name.text !== "removeItem" && node.name.text !== "clear";
  }
  if (ts.isElementAccessExpression(node)) return STORAGE_ROOT.test(node.expression.getText());
  return false;
}

function findEnclosingFunction(n: ts.Node): ts.Node | undefined {
  let p: ts.Node | undefined = n.parent;
  while (p) {
    if (ts.isArrowFunction(p) || ts.isFunctionExpression(p) || ts.isFunctionDeclaration(p) || ts.isMethodDeclaration(p)) return p;
    p = p.parent;
  }
  return undefined;
}
/** 대문자로 시작하는 이름 = React 컴포넌트 관례. 익명 `export default function` 도 컴포넌트로 본다. */
function isLikelyComponent(fn: ts.Node): boolean {
  if (ts.isFunctionDeclaration(fn)) {
    if (fn.name) return /^[A-Z]/.test(fn.name.text);
    return !!fn.modifiers?.some((m) => m.kind === ts.SyntaxKind.DefaultKeyword);
  }
  const p = fn.parent;
  if (p && ts.isVariableDeclaration(p) && ts.isIdentifier(p.name)) return /^[A-Z]/.test(p.name.text);
  if (p && ts.isExportAssignment(p)) return true;
  return false;
}
/** 이 함수 노드에 붙은 이름(지역 헬퍼 오염 전파용). */
function functionName(fn: ts.Node): string | null {
  if (ts.isFunctionDeclaration(fn) && fn.name) return fn.name.text;
  const p = fn.parent;
  if (p && ts.isVariableDeclaration(p) && ts.isIdentifier(p.name)) return p.name.text;
  return null;
}

/**
 * 이 노드가 렌더 중에 실행되는가를 **조상 체인을 실제로 올라가며** 판정한다.
 * ★초판은 `while` 안의 모든 경로가 첫 회에 return 해 **한 번도 상승하지 않았다**(독립 리뷰 실측).
 *   그래서 `.map` 콜백·중첩 화살표가 통째로 위음성이었고, eslint `prefer-const` 가 그 사실을
 *   기계로 신고하고 있었다 — **린트 결함과 논리 결함이 같은 한 줄이었다.**
 */
function renderPhase(node: ts.Node): RenderVia | null {
  let cur: ts.Node = node;
  for (let depth = 0; depth < 32; depth += 1) {
    const fn = findEnclosingFunction(cur);
    if (!fn) return null; // 모듈 스코프
    const parent = fn.parent;
    if (parent && ts.isCallExpression(parent)) {
      const name = calleeName(parent);
      if (DEFERRED_HOOKS.has(name)) return null;
      if (name in RENDER_HOOKS) return RENDER_HOOKS[name];
      if (TRANSPARENT_CALLBACKS.has(name)) { cur = parent; continue; } // ★계속 상승한다
      if (COMPONENT_WRAPPERS.has(name)) return "component-body";
      return null; // 알 수 없는 고차함수 — 보수적으로 제외(위양성 방지)
    }
    if (isLikelyComponent(fn)) return "component-body";
    return null; // 지역/모듈 헬퍼 — 오염 전파(아래 2차 통과)가 대신 처리한다
  }
  return null;
}

/**
 * 이 식별자가 **재수화 게이트 뒤**에 있는가 — `hydrated && f()` · `hydrated ? f() : x`.
 * ★가드를 못 보면 안전한 코드를 위반으로 신고하게 된다(위양성도 결함이다 — 저장소 §A-6).
 */
function isBehindHydrationGate(node: ts.Node, gateNames: Set<string>): boolean {
  const named = (n: ts.Node): boolean => ts.isIdentifier(n) && gateNames.has(n.text);
  /**
   * `&&` 사슬의 **왼쪽 어딘가**에 게이트가 있으면 오른쪽은 게이트 뒤다.
   * ★`hydrated && !isDone(id) && stageCompletion(id) === "partial"` 은
   *   `((hydrated && !isDone) && (…))` 로 파싱돼 왼쪽이 **식별자 하나가 아니다** —
   *   그걸 못 보면 이미 고쳐 둔 코드를 위반으로 신고한다(독립 리뷰가 짚은 위양성 클래스).
   */
  const leftHasGate = (n: ts.Node): boolean => {
    if (named(n)) return true;
    if (ts.isBinaryExpression(n) && n.operatorToken.kind === ts.SyntaxKind.AmpersandAmpersandToken) {
      return leftHasGate(n.left) || leftHasGate(n.right);
    }
    return false;
  };
  let cur: ts.Node | undefined = node;
  while (cur) {
    const p: ts.Node | undefined = cur.parent;
    if (!p) break;
    if (ts.isBinaryExpression(p) && p.operatorToken.kind === ts.SyntaxKind.AmpersandAmpersandToken && p.right === cur && leftHasGate(p.left)) return true;
    if (ts.isConditionalExpression(p) && named(p.condition) && p.whenTrue === cur) return true;
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
      let neg = false;
      const scan = (e: ts.Node): void => {
        if (ts.isPrefixUnaryExpression(e) && e.operator === ts.SyntaxKind.ExclamationToken
            && ts.isIdentifier(e.operand) && gateNames.has(e.operand.text)) neg = true;
        ts.forEachChild(e, scan);
      };
      scan(n.expression);
      // ★`!a && !hydrated` 처럼 **조건이 결합**되면 다른 분기에서 게이트가 빠진다 —
      //   그때는 "전체 게이트"로 보지 않는다(부분 게이트는 잡아야 한다).
      const simple = ts.isPrefixUnaryExpression(n.expression)
        || (ts.isBinaryExpression(n.expression) && n.expression.operatorToken.kind === ts.SyntaxKind.BarBarToken);
      if (neg && simple && n.thenStatement) found = true;
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
  //   ①`useHydrated()` 게이트 변수  ②스토어 셀렉터로 꺼낸 **메서드** 변수
  const gateNames = new Set<string>();
  const storeMethodNames = new Set<string>();
  const collect = (n: ts.Node): void => {
    if (ts.isVariableDeclaration(n) && n.initializer && ts.isCallExpression(n.initializer)) {
      const call = n.initializer;
      const callee = call.expression;
      const isStoreHook = ts.isIdentifier(callee) && /^use[A-Z]\w*Store$/.test(callee.text);
      if (ts.isIdentifier(n.name)) {
        if (ts.isIdentifier(callee) && callee.text === "useHydrated") gateNames.add(n.name.text);
        if (isStoreHook && call.arguments.length === 1) {
          const arg = call.arguments[0];
          if (ts.isArrowFunction(arg) && ts.isPropertyAccessExpression(arg.body) && !MUTATION_PREFIX.test(n.name.text)) {
            storeMethodNames.add(n.name.text);
          }
        }
      }
      /**
       * ★**구조분해**로 꺼낸 메서드 — `const { feasibilityCompleteness } = useXStore();`
       *   2026-08-27 독립 리뷰가 이 사각을 실증했다: 같은 결함을 구조분해로 되살렸더니
       *   래칫이 **SURVIVED** 였다. `get()` 은 **어떻게 꺼냈든** 라이브를 읽으므로 결함은 동일하다.
       *   그리고 이 형태는 이 저장소의 **지배적 스타일**이다(`} = useFeasibilityV2Store();` 등).
       */
      if (isStoreHook && call.arguments.length === 0 && ts.isObjectBindingPattern(n.name)) {
        for (const el of n.name.elements) {
          if (ts.isIdentifier(el.name) && !MUTATION_PREFIX.test(el.name.text)) storeMethodNames.add(el.name.text);
        }
      }
    }
    ts.forEachChild(n, collect);
  };
  collect(sf);
  const wholeComponentGated = gateNames.size > 0 && hasEarlyHydrationReturn(sf, gateNames);

  /** 이 노드 자체가 라이브 읽기인가. */
  const readKindOf = (n: ts.Node): ReadKind | null => {
    if (ts.isCallExpression(n)) {
      if (isStoreGetState(n)) return "getState";
      if (ts.isIdentifier(n.expression) && storeMethodNames.has(n.expression.text)) return "store-method";
    }
    if (isStorageRead(n)) return "localStorage";
    return null;
  };

  // ── 2차 통과: **오염 전파** ──
  //   지역/모듈 헬퍼가 라이브 상태를 읽으면, 그 헬퍼를 렌더 중에 부르는 것도 라이브 읽기다.
  //   ★이걸 안 하면 `const f = () => …getState(); … {rows.map(() => f())}` 가 통째로 위음성이다
  //     (독립 리뷰가 `InputResolveModal.tsx` 에서 실제 사례를 찾아냈다).
  const fnBodies = new Map<string, ts.Node>();
  const mapFns = (n: ts.Node): void => {
    if (ts.isArrowFunction(n) || ts.isFunctionExpression(n) || ts.isFunctionDeclaration(n)) {
      const name = functionName(n);
      if (name) fnBodies.set(name, n);
    }
    ts.forEachChild(n, mapFns);
  };
  mapFns(sf);
  const tainted = new Set<string>();
  for (let round = 0; round < 8; round += 1) {
    let grew = false;
    for (const [name, body] of fnBodies) {
      if (tainted.has(name)) continue;
      let hit = false;
      const walk = (n: ts.Node): void => {
        if (hit) return;
        // ★게이트가 **헬퍼 안**에 있으면 그 헬퍼는 오염이 아니다.
        //   `const isDone = (id) => hydrated && (… stageCompletion(id) …)` 이 실례다 —
        //   이걸 빼먹으면 이미 고쳐 둔 `LifecycleProgressRail` 을 위반으로 신고한다(위양성도 결함).
        if ((readKindOf(n) || (ts.isCallExpression(n) && ts.isIdentifier(n.expression) && tainted.has(n.expression.text)))
            && !isBehindHydrationGate(n, gateNames)) { hit = true; return; }
        ts.forEachChild(n, walk);
      };
      walk(body);
      if (hit) { tainted.add(name); grew = true; }
    }
    if (!grew) break;
  }
  // 오염된 헬퍼가 곧 컴포넌트면 전파 대상이 아니다(그 자신이 아래에서 직접 잡힌다).
  for (const [name, body] of fnBodies) if (isLikelyComponent(body)) tainted.delete(name);

  const push = (n: ts.Node, kind: ReadKind): void => {
    const via = renderPhase(n);
    if (!via || wholeComponentGated || isBehindHydrationGate(n, gateNames)) return;
    out.push({
      file, kind, via,
      line: sf.getLineAndCharacterOfPosition(n.getStart(sf)).line + 1,
      text: n.getText(sf).replace(/\s+/g, " ").slice(0, 120),
    });
  };

  const seen = new Set<number>();
  const visit = (n: ts.Node): void => {
    const kind = readKindOf(n);
    if (kind && !seen.has(n.getStart(sf))) { seen.add(n.getStart(sf)); push(n, kind); }
    else if (ts.isCallExpression(n) && ts.isIdentifier(n.expression) && tainted.has(n.expression.text)
             && !seen.has(n.getStart(sf))) {
      seen.add(n.getStart(sf));
      push(n, "getState"); // 오염된 헬퍼 호출 = 라이브 읽기(간접)
    }
    ts.forEachChild(n, visit);
  };
  visit(sf);
  return out;
}
