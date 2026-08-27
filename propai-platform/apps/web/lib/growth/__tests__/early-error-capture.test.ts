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

import { earlyErrorBootstrap, EARLY_ERROR_CAP } from "@/lib/growth/early-error-bootstrap";
import { drainEarlyErrors, type EarlyCapturedError } from "@/lib/growth/event-collector";

type EarlyStore = { buf: EarlyCapturedError[]; closed: boolean };
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
    const types = bodies.flatMap((t) => {
      try {
        const j = JSON.parse(t) as { events?: { event_type?: string }[] };
        return (j.events ?? []).map((e) => e.event_type ?? "");
      } catch { return []; }
    });
    expect(types.length, "전제 — 아무것도 안 나갔으면 아래 단언이 공허하다").toBeGreaterThan(0);
    expect(types, "두 이름이 다 나와야 한다 — 한쪽만 나오면 군집이 갈린다").toEqual(
      expect.arrayContaining(["js_error", "promise_rejection"]),
    );
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
  });
});
