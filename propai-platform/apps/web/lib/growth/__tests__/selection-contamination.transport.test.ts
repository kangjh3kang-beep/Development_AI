/**
 * ★전송 층 — `surface` 축이 **실제 전송 본문에** 실리는가.
 *
 * 왜 별도 파일인가: 같은 파일에서 `trackEvent` 를 목으로 갈아 끼우면 **collector 자체가
 * 검증 대상에서 빠진다**(스텁이 검증 대상 층을 우회하는 전형 — 규율 §3). 여기서는
 * 목 없이 진짜 collector 를 태우고, 네트워크 경계만 가로채 본문을 읽는다.
 *
 * ★`surface` 는 호출부가 아니라 collector 가 채운다. 그 줄이 사라져도 백엔드는
 *   `ev.surface or "web"` 폴백 때문에 **오늘은 같은 값**을 쓴다 — 그래서 백엔드 테스트로는
 *   못 잡는다. 프론트가 축을 잃는 순간을 잡는 것은 이 단언뿐이다.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import type { SelectionIntegrity } from "@/lib/selection-integrity";

import { flush } from "../event-collector";
import {
  SELECTION_CONTAMINATION_SERVICE,
  trackSelectionContamination,
} from "../selection-contamination";

const MULTI_REGION: SelectionIntegrity = {
  verdict: "multi_region",
  regionGroups: ["충청북도 제천시 금성면 성내리 산 7-1", "충청북도 제천시 모산동 123-1"],
  malformedRows: [],
  spreadKm: 15.94,
};

afterEach(() => {
  vi.unstubAllGlobals();
  flush(); // 링버퍼를 비워 다음 테스트로 새지 않게 한다
});

describe("★전송 — 관측이 collector 를 지나 본문에 실린다", () => {
  it("event_type·surface·service 가 전송 본문에 그대로 있다", () => {
    const sent: string[] = [];
    // sendBeacon 을 **없는 것으로** 만들어 fetch 폴백을 강제한다(Blob 은 동기로 못 읽는다).
    // ★단 *"그래서 이 층을 못 태운다"* 는 **오추론**이다 — **비동기로는 읽을 수 있다**
    //   (`__tests__/_read-blob.ts` · `transport-sendbeacon.test.ts` 참조). 그 오추론이 실제로 부채를 만들었다.
    vi.stubGlobal("navigator", { ...globalThis.navigator, sendBeacon: undefined });
    vi.stubGlobal("fetch", ((_url: string, init?: RequestInit) => {
      sent.push(String(init?.body ?? ""));
      return Promise.resolve({ ok: true } as Response);
    }) as unknown as typeof fetch);

    flush(); // 선행 테스트 잔재 제거
    sent.length = 0;

    expect(trackSelectionContamination(MULTI_REGION, "/ko/precheck")).toBe(true);
    flush();

    // 공허 진리 가드 — 전송이 아예 없었으면 아래 단언은 무의미하다(규율 §A-2).
    expect(sent.length, "전송이 일어나지 않았다").toBe(1);

    const body = JSON.parse(sent[0]) as { events: Array<Record<string, unknown>> };
    expect(body.events.length).toBeGreaterThanOrEqual(1);
    const ev = body.events.find(
      (e) => e.event_type === "selection_contamination_observation",
    );
    expect(ev, "관측 이벤트가 본문에 없다 — 샘플링에 걸렸거나 타입이 바뀌었다").toBeTruthy();
    expect(ev!.surface).toBe("web");
    expect(ev!.service).toBe(SELECTION_CONTAMINATION_SERVICE);
    expect((ev!.payload as Record<string, unknown>).verdict).toBe("multi_region");
    expect((ev!.payload as Record<string, unknown>).region_groups).toBe(2);
  });
});
