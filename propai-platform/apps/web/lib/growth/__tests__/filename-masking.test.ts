// @vitest-environment jsdom
/**
 * ★**`filename` 도 마스킹을 거치는가** — 형제 `message`·`stack` 과 같은 처리인가.
 *
 * 왜(2026-08-27 독립 적대 리뷰 실측): `ErrorEvent.filename` 은 **인라인 스크립트 오류에서
 * 문서 URL 전체**가 된다(헤드리스 브라우저로 실측). 그리고 이 앱은 **지번을 쿼리에** 싣는다 —
 * `components/operations/LandScheduleClient.tsx:460`
 * `router.push(\`/${'${'}rl${'}'}/registry-analysis?addr=${'${'}encodeURIComponent(jibun)${'}'}\`)`.
 *
 * 그런데 `event-collector` 의 같은 객체 리터럴에서 `message: maskString(…)` ·
 * `stack: maskString(…)` 인데 **`filename` 만 생것**이었다 — 프론트 `ADDRESS_RE` 방어를
 * **유일하게 우회하는 필드**였다. `app/layout.tsx` 는 매 페이지 `<head>` 에 인라인 스크립트를
 * 2개 실으므로 그 컨텍스트의 오류는 실재한다.
 *
 * ★두 모집단을 같은 실행에서 가른다: **주소가 든 URL 은 지워지고 · 평범한 청크 경로는 남는다**
 * (한쪽만 보면 "전부 지운다"는 구현도 통과한다 — 그건 진단 불가라는 다른 결함이다).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  flush,
  initEventCollector,
  teardownEventCollector,
} from "@/lib/growth/event-collector";

let sent: string[] = [];

beforeEach(() => {
  sent = [];
  vi.stubGlobal("navigator", { ...globalThis.navigator, sendBeacon: undefined });
  // ★*"그래서 이 층을 못 태운다"* 는 **오추론**이다 — **비동기로는 읽을 수 있다**
  //   (`__tests__/_read-blob.ts` · `transport-sendbeacon.test.ts`). 그 오추론이 부채를 만들었다.
  vi.stubGlobal("fetch", ((_u: string, init?: RequestInit) => {
    sent.push(String(init?.body ?? ""));
    return Promise.resolve({ ok: true } as Response);
  }) as unknown as typeof fetch);
  flush();
  sent.length = 0;
  initEventCollector();
});
afterEach(() => {
  teardownEventCollector();
  vi.unstubAllGlobals();
});

function fireErrorWith(filename: string): void {
  window.dispatchEvent(
    new ErrorEvent("error", {
      message: "boom",
      filename,
      lineno: 1,
      colno: 2,
      error: new Error("boom"),
    }),
  );
  flush();
}

function lastFilename(): string | null {
  const events = sent.flatMap(
    (b) => (JSON.parse(b) as { events: Array<Record<string, unknown>> }).events,
  );
  const ev = events.find((e) => e.event_type === "js_error");
  expect(ev, "js_error 가 전송되지 않았다 — 이 테스트는 무엇도 잠그지 못한다").toBeTruthy();
  return (ev!.payload as Record<string, unknown>).filename as string | null;
}

describe("★filename 도 형제와 같은 마스킹을 거친다", () => {
  it("문서 URL 쿼리의 지번이 지워진다", () => {
    fireErrorWith("https://4t8t.net/ko/registry-analysis?addr=서울 강남구 테헤란로 152");
    const f = lastFilename();
    expect(f, "지번이 그대로 실렸다 — 프론트 ADDRESS_RE 를 우회한다").not.toContain("테헤란로 152");
  });

  it("★음성 대조군 — 평범한 청크 경로는 **그대로 남는다**(진단 가능해야 한다)", () => {
    const path = "https://4t8t.net/_next/static/chunks/main-abc123.js";
    fireErrorWith(path);
    expect(lastFilename(), "정상 경로까지 지웠다 — 어느 파일에서 났는지 알 수 없다").toBe(path);
  });

  it("null 이면 null 그대로(위양성 방지)", () => {
    fireErrorWith("");
    expect(lastFilename()).toBeNull();
  });
});
