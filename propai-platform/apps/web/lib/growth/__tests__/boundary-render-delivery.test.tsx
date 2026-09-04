/**
 * ★**경계를 실제로 렌더해서** 오류가 서버까지 나가는지 본다 — 소스 검사가 못 보는 층.
 *
 * 왜 별도 파일인가(독립 리뷰 적발 · 2026-08-27): 형제 `error-boundary-report-wiring.test.ts` 는
 * **소스 문자열**만 본다. 그래서 아래 변이가 **락 9건 전부를 통과했다** —
 *
 *     if (String(1) === "2") reportBoundaryError("…", error);   // 死코드
 *     import { trackEvent as trackEventAlias } from "@/lib/growth/event-collector";
 *     trackEventAlias("js_error", { … });                        // 별칭 우회
 *
 * 즉 그 경계는 **PR 이전 상태 그대로**인데 전부 초록이었다. 경계 컴포넌트를 **임포트·렌더하는
 * 테스트가 0건**이라 그 층은 어떤 변이든 자동 생존이었다.
 * ★「변이 N/N CAUGHT」를 말하기 전에 **몇 개 층에 넣었는지**를 먼저 물어야 한다.
 *
 * 이 파일은 네트워크 경계만 가로채고 **목을 쓰지 않는다** — 진짜 collector 를 태운다.
 */
import { render } from "@testing-library/react";
import React, { type ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import GlobalError from "@/app/global-error";
import DashboardError from "@/app/[locale]/(dashboard)/error";
import { MapErrorBoundary } from "@/components/common/MapShell";
import { HubErrorBoundary } from "@/components/projects/HubErrorBoundary";
import { flush } from "@/lib/growth/event-collector";

type Sent = { url: string; body: string };
let sent: Sent[] = [];

function captureSends(): void {
  sent = [];
  vi.stubGlobal("navigator", { ...globalThis.navigator, sendBeacon: undefined });
  // ★*"그래서 이 층을 못 태운다"* 는 **오추론**이다 — **비동기로는 읽을 수 있다**
  //   (`__tests__/_read-blob.ts` · `transport-sendbeacon.test.ts`). 그 오추론이 부채를 만들었다.
  vi.stubGlobal("fetch", ((u: string, init?: RequestInit) => {
    sent.push({ url: String(u), body: String(init?.body ?? "") });
    return Promise.resolve({ ok: true } as Response);
  }) as unknown as typeof fetch);
}

/** 모든 전송 본문에서 이벤트를 펼친다. */
function events(): Array<Record<string, unknown>> {
  return sent.flatMap((s) => {
    try {
      return (JSON.parse(s.body) as { events: Array<Record<string, unknown>> }).events;
    } catch {
      return [];
    }
  });
}
const scopes = () =>
  events().map((e) => (e.payload as Record<string, unknown> | null)?.scope).filter(Boolean);

/** 렌더 중 throw 하는 자식 — 클래스 경계를 **실제로 발화**시킨다. */
function Boom(): ReactNode {
  throw new Error("boundary-boom");
}

beforeEach(() => {
  flush(); // 선행 테스트 잔재 제거
  captureSends();
  // 경계가 콘솔에 찍는 것은 이 테스트의 관심사가 아니다.
  vi.spyOn(console, "error").mockImplementation(() => {});
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("★경계를 렌더하면 오류가 실제로 서버로 나간다", () => {
  it("global-error — 수집기가 없는 문서에서도 나간다", () => {
    render(
      <GlobalError error={Object.assign(new Error("g-boom"), { digest: "dg" })} reset={() => {}} />,
    );
    expect(sent.length, "전송이 일어나지 않았다 — 배달 구동자가 없다").toBeGreaterThan(0);
    expect(scopes()).toContain("global-error");

    const ev = events().find(
      (e) => (e.payload as Record<string, unknown>)?.scope === "global-error",
    )!;
    const payload = ev.payload as Record<string, unknown>;
    // ★payload 필드를 못 박는다 — `message` 는 장식이 아니라 analyzer 군집의 **해시 입력**이다
    //   (`normalize_stack` 이 메시지 전문을 sha1 한다). 빠지면 전 경계 오류가 한 군집으로 붕괴한다.
    expect(payload.message, "message 가 실리지 않았다 — 군집이 붕괴한다").toBe("g-boom");
    expect(payload.digest, "digest 가 실리지 않았다").toBe("dg");
    expect(ev.severity, "severity 가 error 가 아니다 — 성장루프 필터 입력이다").toBe("error");
    expect(ev.event_type).toBe("js_error");
    // ★상대경로로 새면 프론트 오리진 404 가 된다(collector 주석이 경고한 회귀).
    expect(sent[0].url).toContain("/api/v1/growth/events");
  });

  it("라우트 경계(dashboard/error.tsx) — 렌더하면 나간다", () => {
    render(<DashboardError error={new Error("d-boom")} reset={() => {}} />);
    expect(scopes()).toContain("dashboard-error");
  });

  it("★클래스 경계 MapErrorBoundary — 오류를 **가두지만** 보고는 나간다", () => {
    render(
      <MapErrorBoundary>
        <Boom />
      </MapErrorBoundary>,
    );
    expect(
      scopes(),
      "지도 경계가 오류를 가두기만 하고 보고하지 않는다 — 상위 error.tsx 는 이것을 볼 수 없다",
    ).toContain("map-shell");
  });

  it("★클래스 경계 HubErrorBoundary — console.error 말고 서버로 나간다", () => {
    render(
      <HubErrorBoundary>
        <Boom />
      </HubErrorBoundary>,
    );
    expect(scopes(), "허브 경계가 console.error 로만 남긴다 — 성장루프는 0건").toContain(
      "projects-hub",
    );
  });

  it("★음성 대조군 — 경계가 발화하지 않으면 아무것도 안 나간다(위양성 방지)", () => {
    render(
      <HubErrorBoundary>
        <div>정상</div>
      </HubErrorBoundary>,
    );
    expect(scopes(), "오류가 없는데 보고가 나갔다 — 이 락은 무엇이든 초록으로 만든다").toEqual([]);
  });
});
