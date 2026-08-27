// @vitest-environment jsdom
/**
 * **초기 렌더 오류 조기 포착**의 계약.
 *
 * ★왜(2026-08-27 라이브 실측): 전역 오류 수집기는 `useGrowthEvents` 의 **`useEffect`** 에서
 *   등록돼 하이드레이션 커밋 **이후**에 붙는다. 같은 타임라인에서 재니
 *     `Minified React error #418` = **237ms** / `addEventListener("error")` = **307ms**
 *   — **오류가 등록보다 70ms 먼저 났다.** 그래서 성장루프 analyzer 가 `js_error` 를 볼 준비를
 *   갖추고 있는데도 라이브에서 `js_error` 는 **0건**이었다(beacon 본문 가로채기로 확인.
 *   대조군 `api_call` 28건은 실림 — **수집기의 일부만 살아 있었다**).
 *
 * ★이 파일은 부트스트랩을 **문자열로 검사하지 않는다.** 실제로 **실행**해서 오류를 던져 보고
 *   버퍼에 담기는지 본다 — 소스 검사는 주석·문자열에 뚫리고, 무엇보다 *"스크립트가 있다"* 는
 *   *"그 스크립트가 오류를 잡는다"* 와 **다른 명제**다.
 */
import type * as TS from "typescript";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { earlyErrorBootstrap, EARLY_ERROR_CAP, EARLY_MESSAGE_CAP } from "@/lib/growth/early-error-bootstrap";
import { drainEarlyErrors, type EarlyCapturedError } from "@/lib/growth/event-collector";

type EarlyStore = { buf: EarlyCapturedError[]; closed: boolean };
type Ev = { event_type?: string; payload?: { message?: string; early?: boolean; tMs?: number } };
const store = (): EarlyStore | undefined =>
  (window as unknown as { __propaiEarly?: EarlyStore }).__propaiEarly;

/** 부트스트랩을 **실제로 실행**한다(문서 파싱 시점 인라인 스크립트와 같은 효과). */
function runBootstrap(): void {
  new Function(earlyErrorBootstrap)();
}
/** jsdom 에서 `window.onerror` 경로를 태운다. */
function fireError(message: string): void {
  window.dispatchEvent(
    new ErrorEvent("error", { message, filename: "x.js", lineno: 1, colno: 2, error: new Error(message) }),
  );
}

beforeEach(() => {
  delete (window as unknown as { __propaiEarly?: EarlyStore }).__propaiEarly;
});

describe("부트스트랩 — 등록보다 먼저 난 오류를 담는다", () => {
  it("★실행하면 오류를 **실제로** 잡는다(문자열 검사가 아니라 동작)", () => {
    runBootstrap();
    fireError("Minified React error #418");
    const buf = store()?.buf ?? [];
    expect(buf).toHaveLength(1);
    expect(buf[0].m).toContain("#418");
    expect(buf[0].k).toBe("error");
    expect(buf[0].f).toBe("x.js");
  });

  it("★음성 대조군 — 부트스트랩을 **안 돌리면** 아무것도 안 담긴다(이 검사가 공허하지 않다)", () => {
    fireError("Minified React error #418");
    expect(store()).toBeUndefined();
  });

  it("★상한이 있다 — 오류 폭주가 메모리를 먹지 않는다", () => {
    runBootstrap();
    for (let i = 0; i < EARLY_ERROR_CAP + 15; i += 1) fireError(`boom ${i}`);
    expect(store()?.buf).toHaveLength(EARLY_ERROR_CAP);
  });

  it("★멱등 — 두 번 실행돼도 store 가 갈리지 않는다(갈리면 **조용한 손실**)", () => {
    // 독립 리뷰 실측: 가드가 없으면 두 번째 실행이 store 를 갈아 치우고, 첫 store 의 리스너가
    // 담은 것을 drain 이 **못 본다** — 이중 전송이 아니라 **손실**이다.
    runBootstrap();
    const first = store();
    fireError("before-second-run");
    runBootstrap();
    expect(store(), "두 번째 실행이 store 를 갈아 치웠다").toBe(first);
    expect(store()?.buf.map((e) => e.m)).toEqual(["before-second-run"]);
  });

  it("★메시지에도 상한이 있다 — 건수만 잠그면 **한 건이** 메모리를 먹는다", () => {
    runBootstrap();
    fireError("x".repeat(500_000));
    const m = store()?.buf[0].m ?? "";
    expect(m.length, "메시지가 안 잘렸다 — 20건 × 500KB 는 10MB 다").toBe(EARLY_MESSAGE_CAP);
  });

  it("★리스너 **본문**도 격리돼 있다 — 바깥 try 는 등록만 감싼다", () => {
    // 리스너 안에서 예외가 나면(예: 전역 부재) 그 오류가 페이지로 새어 나가면 안 된다.
    runBootstrap();
    const orig = performance.now;
    performance.now = () => { throw new Error("no clock"); };
    expect(() => fireError("boom")).not.toThrow();
    performance.now = orig;
  });

  it("unhandledrejection 도 담는다", () => {
    runBootstrap();
    // jsdom 은 PromiseRejectionEvent 를 안 주므로 같은 형태의 이벤트를 만든다.
    const ev = new Event("unhandledrejection") as Event & { reason?: unknown };
    ev.reason = new Error("rejected!");
    window.dispatchEvent(ev);
    const buf = store()?.buf ?? [];
    expect(buf).toHaveLength(1);
    expect(buf[0].k).toBe("rejection");
    expect(buf[0].m).toBe("rejected!");
  });
});

describe("drainEarlyErrors — 비우고 **닫는다**(이중 전송 차단)", () => {
  it("★두 모집단이 갈린다 — 첫 호출은 담긴 것을 주고, 그 뒤로는 **더 안 쌓인다**", () => {
    runBootstrap();
    fireError("first");
    const drained = drainEarlyErrors(window as never);
    expect(drained.map((e) => e.m)).toEqual(["first"]);

    // 닫힌 뒤의 오류는 정식 핸들러가 잡는다 — 여기 또 쌓이면 **같은 오류가 두 번** 전송된다.
    fireError("second");
    expect(store()?.buf).toEqual([]);
    expect(store()?.closed).toBe(true);
    expect(drainEarlyErrors(window as never)).toEqual([]);
  });

  it("부트스트랩이 안 돌았어도 안전하다(빈 배열)", () => {
    expect(drainEarlyErrors({} as never)).toEqual([]);
    expect(drainEarlyErrors({ __propaiEarly: { buf: null, closed: false } } as never)).toEqual([]);
  });
});

describe("배선 — 수집기가 그 버퍼를 실제로 비우고 `js_error` 로 내보낸다", () => {
  it("★`initEventCollector()` 가 조기 오류를 `js_error` 로 전송한다", async () => {
    vi.resetModules();
    const mod = await import("@/lib/growth/event-collector");
    runBootstrap();
    fireError("Minified React error #418");

    // ★전송 경로(sendBeacon)는 jsdom 에 없을 수 있다 — 그래서 **버퍼 상태**로 배선을 판정한다.
    //   "부른다"가 아니라 **"그래서 일어난 일"** 을 본다(§'락은 호출이 아니라 효과를 잠근다').
    expect(store()?.buf.length, "전제 — 비우기 전에 담겨 있어야 이 검사가 의미를 갖는다").toBe(1);
    mod.initEventCollector();
    expect(store()?.buf, "수집기가 조기 버퍼를 비우지 않았다 — 초기 오류가 영영 전송되지 않는다").toEqual([]);
    expect(store()?.closed, "닫지 않으면 같은 오류가 두 번 전송된다").toBe(true);

    // ★음성 대조군 — 정식 핸들러가 붙었으니 이후 오류는 **버퍼가 아니라** 그 경로로 간다.
    fireError("after-init");
    expect(store()?.buf).toEqual([]);
  });
});

describe("이벤트 타입 — 형제와 **같은 이름**을 쓴다(군집이 갈리지 않게)", () => {
  /**
   * ★`handleWindowError`=`js_error` / `handleRejection`=`promise_rejection` 이고 **둘 다** 백엔드
   *   화이트리스트에 있다. 조기 포착이라고 한 이름으로 몰아 보내면 같은 사건이 두 이름으로 쌓여
   *   analyzer 의 `error_cluster` 군집이 갈린다(§29 *"없는 걸 만드는 것과 있는 걸 안 쓰는 것은
   *   처방이 다르다"*).
   */
  it("★두 모집단이 갈린다 — error 는 js_error, rejection 은 promise_rejection", async () => {
    // ★`vi.spyOn(mod, "trackEvent")` 은 ESM export 라 안 먹는다 — **전송 본문**을 직접 잡는다
    //   ("부른다"가 아니라 **"그래서 나간 것"** 을 본다).
    vi.resetModules();
    /**
     * ★전송 경로를 **fetch 폴백**으로 몬다(그것도 실제 코드 경로다).
     *   `sendBeacon` 경로는 **Blob** 을 넘기는데 jsdom 의 Blob 에는 `.text()` 가 없다 —
     *   두 번 헛짚었고, 두 번 다 아래 「전제」 가드가 조용한 0 을 막았다.
     */
    const bodies: string[] = [];
    Object.defineProperty(navigator, "sendBeacon", { configurable: true, value: () => false });
    const origFetch = globalThis.fetch;
    globalThis.fetch = ((_u: string, init?: RequestInit) => {
      if (typeof init?.body === "string") bodies.push(init.body);
      return Promise.resolve(new Response("{}"));
    }) as typeof fetch;
    const mod = await import("@/lib/growth/event-collector");

    runBootstrap();
    fireError("boom");
    const ev = new Event("unhandledrejection") as Event & { reason?: unknown };
    ev.reason = new Error("rejected!");
    window.dispatchEvent(ev);
    mod.initEventCollector();
    mod.flush();

    globalThis.fetch = origFetch;
    /**
     * ★**집합 소속이 아니라 대응을 건다**(독립 리뷰 MAJOR-1 실측): `arrayContaining` 만 쓰면
     *   매핑을 **뒤집어도** 통과한다 — 뒤집힌 상태에서 초기 JS 오류는 `promise_rejection` 으로
     *   적재되고, analyzer 의 `_analyze_error_cluster` 는 `js_error/api_error` 만 조회하므로
     *   **이 PR 이 고치려는 증상(js_error 0건)이 그대로 재발**한다.
     */
    const evs = bodies.flatMap((t) => {
      try { return (JSON.parse(t) as { events?: Ev[] }).events ?? []; } catch { return []; }
    });
    expect(evs.length, "전제 — 아무것도 안 나갔으면 아래 단언이 공허하다").toBeGreaterThan(0);
    const byMsg = (m: string) => evs.find((e) => e.payload?.message === m)?.event_type;
    expect(byMsg("boom"), "error 는 js_error 로 가야 한다").toBe("js_error");
    expect(byMsg("rejected!"), "rejection 은 promise_rejection 으로 가야 한다").toBe("promise_rejection");

    // ★`payload.early` 는 **라이브 확증 절차가 근거로 삼는 필드**다(계획서 §3) — 잠그지 않으면
    //   그 절차가 영원히 아무것도 못 찾는다. `tMs` 는 "얼마나 앞섰나" 를 남긴다.
    const one = evs.find((x) => x.payload?.message === "boom");
    expect(one?.payload?.early, "early 플래그가 빠지면 조기 포착분을 구별할 수 없다").toBe(true);
    expect(typeof one?.payload?.tMs, "tMs 가 없으면 얼마나 앞섰는지 못 남긴다").toBe("number");
  });
});

describe("★빌드 안전 — 조각을 `+` 로 이으면 빌드가 잘라 버린다", () => {
  /**
   * ★실측(2026-08-27 · 로컬 프로덕션 빌드에서 **라이브와 바이트 동일하게 재현**):
   *   백틱 조각을 `+` 로 이었더니 `.next/server/pages/404.html` 산출물이
   *     `if(B.length<20window.addEventListener(...m:C(e.message,8000s:(e.error&&...`
   *   — **각 조각이 `${…}` 보간 직후에서 끊기고 보간 없는 조각은 통째로 사라졌다.**
   *   라이브에서 `window.__propaiEarly` 가 `undefined` 였고 `js_error` 가 0건이었다.
   *
   * ★이 검사는 **대리 변수가 아니라 원인**을 잠근다 — 그 형태를 쓰면 빌드가 부순다.
   *   ★한계: *"왜 SWC 가 그렇게 접는가"* 는 규명하지 못했다(추정). 그러므로
   *   **배포 후 라이브에서 `window.__propaiEarly` 존재를 확인**하는 절차를 계획서에 남긴다.
   */
  it("초기화식이 **단일 템플릿 리터럴**이다(연결 금지)", async () => {
    const ts = (await import("typescript")).default;
    const { readFileSync } = await import("node:fs");
    const src = readFileSync("lib/growth/early-error-bootstrap.ts", "utf8");
    const sf = ts.createSourceFile("b.ts", src, ts.ScriptTarget.ES2022, true);

    let init: TS.Expression | undefined;
    const visit = (n: TS.Node): void => {
      if (ts.isVariableDeclaration(n) && ts.isIdentifier(n.name) && n.name.text === "earlyErrorBootstrap") init = n.initializer;
      ts.forEachChild(n, visit);
    };
    visit(sf);
    expect(init, "선언을 못 찾았다 — 이 검사가 공허하다").toBeTruthy();
    // 양성: 템플릿 리터럴이어야 하고, 음성: `+` 연결(BinaryExpression)이면 안 된다.
    expect(
      init && (ts.isTemplateExpression(init) || ts.isNoSubstitutionTemplateLiteral(init)),
      "백틱 조각을 `+` 로 잇지 마라 — 빌드가 `${…}` 직후를 버린다(실측)",
    ).toBe(true);
    expect(init && ts.isBinaryExpression(init)).toBe(false);
  });

  it("★형제 `themeBootstrap` 도 같은 형태다(양성 대조군 — 이 규칙이 이 저장소의 관행이다)", async () => {
    const ts = (await import("typescript")).default;
    const { readFileSync } = await import("node:fs");
    const sf = ts.createSourceFile("l.tsx", readFileSync("app/layout.tsx", "utf8"), ts.ScriptTarget.ES2022, true, ts.ScriptKind.TSX);
    let ok = false;
    const visit = (n: TS.Node): void => {
      if (ts.isVariableDeclaration(n) && ts.isIdentifier(n.name) && n.name.text === "themeBootstrap" && n.initializer) {
        ok = ts.isTemplateExpression(n.initializer) || ts.isNoSubstitutionTemplateLiteral(n.initializer);
      }
      ts.forEachChild(n, visit);
    };
    visit(sf);
    expect(ok, "대조군이 죽었다 — themeBootstrap 을 못 찾았거나 형태가 다르다").toBe(true);
  });
});

describe("배선(소스) — 루트 layout 이 그 스크립트를 **실제로 렌더**한다", () => {
  /**
   * ★이 축이 없으면 "상수는 있는데 페이지에 안 실린" 상태가 **전부 초록**이다.
   *   런타임으로 태우고 싶지만 `app/layout.tsx` 는 CSS 를 import 해 vitest 에서 로드되지 않는다.
   *   그래서 **AST 로** 본다(정규식 아님 — 주석·문자열에 뚫리지 않는다).
   *   ★한계를 적어 둔다: 이것은 **계약이 코드에 남아 있는지**만 본다. 브라우저에서 실제로
   *     실행되는지는 **배포 후 라이브 HTML**에서 확인해야 한다(계획서 §3).
   */
  it("★`dangerouslySetInnerHTML` 로 `earlyErrorBootstrap` 을 렌더한다(theme 부트스트랩과 같은 방식)", async () => {
    const ts = (await import("typescript")).default;
    const { readFileSync } = await import("node:fs");
    const src = readFileSync("app/layout.tsx", "utf8");
    const sf = ts.createSourceFile("layout.tsx", src, ts.ScriptTarget.ES2022, true, ts.ScriptKind.TSX);

    /** `<script dangerouslySetInnerHTML={{ __html: X }} />` 의 X 식별자들을 모은다. */
    const injected: string[] = [];
    const visit = (n: TS.Node): void => {
      if (ts.isJsxSelfClosingElement(n) || ts.isJsxOpeningElement(n)) {
        const tag = n.tagName.getText(sf);
        for (const attr of n.attributes.properties) {
          if (!ts.isJsxAttribute(attr) || attr.name.getText(sf) !== "dangerouslySetInnerHTML") continue;
          const init = attr.initializer;
          if (!init || !ts.isJsxExpression(init) || !init.expression) continue;
          const obj = init.expression;
          if (!ts.isObjectLiteralExpression(obj)) continue;
          for (const prop of obj.properties) {
            if (ts.isPropertyAssignment(prop) && prop.name.getText(sf) === "__html" && ts.isIdentifier(prop.initializer)) {
              injected.push(`${tag}:${prop.initializer.text}`);
            }
          }
        }
      }
      ts.forEachChild(n, visit);
    };
    visit(sf);

    // ★양성 대조군을 **먼저** — theme 부트스트랩이 안 잡히면 이 수집기가 죽은 것이다.
    expect(injected, "수집기가 죽었다 — theme 부트스트랩조차 못 찾는다").toContain("script:themeBootstrap");
    expect(injected, "조기 오류 캡처가 layout 에서 렌더되지 않는다").toContain("script:earlyErrorBootstrap");

    /**
     * ★**이름만 보면 대리 변수다**(독립 리뷰 MAJOR-2 실측): layout 에서
     * `const earlyErrorBootstrap = "";` 로 바꿔도 위 단언은 통과하고 프로덕션 `<head>` 에는
     * **빈 `<script>`** 가 나간다. 런타임 락 8개는 자기가 import 한 상수를 태우므로 여전히 초록이다.
     * → 그 식별자가 **어느 모듈에서 import 되는지**까지 되짚는다.
     */
    const importedFrom = new Map<string, string>();
    for (const st of sf.statements) {
      if (!ts.isImportDeclaration(st) || !st.importClause?.namedBindings) continue;
      const nb = st.importClause.namedBindings;
      if (!ts.isNamedImports(nb)) continue;
      const from = (st.moduleSpecifier as TS.StringLiteral).text;
      for (const el of nb.elements) importedFrom.set(el.name.text, `${(el.propertyName ?? el.name).text}@${from}`);
    }
    expect(
      importedFrom.get("earlyErrorBootstrap"),
      "layout 이 넣는 것이 **그 모듈의 상수가 아니다** — 로컬 선언이면 빈 스크립트가 나갈 수 있다",
    ).toBe("earlyErrorBootstrap@@/lib/growth/early-error-bootstrap");
  });
});
