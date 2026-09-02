/**
 * ★플래그 값이 **조용히 잘렸다** — 17키 중 4키만 그리고 **버린 몫을 말하지 않았다.**
 *
 * 【무엇이 있었나 · 라이브 실측 2026-09-02 `/growth/heal-log?limit=200`】
 *
 *     growth_capture(worker) 17키 · 보임 4 · ★조용히 버림 12
 *     growth_capture(api)    17키 · 보임 4 · ★조용히 버림 13
 *
 * 그리고 **무엇이 보이는지가 「키 이름의 철자 길이」로 정해지고 있었다** — Postgres `jsonb`
 * 가 삽입 순서를 버리고 (키 길이, 바이트순)으로 정렬하기 때문이다. 그래서
 * `lost_total`·`loss_rate_pct`·`queue_depth` 같은 **유실 신호가 통째로 안 보였다.**
 *
 * 【이 파일이 갈라 두는 네 모집단】
 *   ① 17키(jsonb 왕복본)   → 진단 키가 **전부 보인다**            (원래 결함의 부활을 막는다)
 *   ② 4키                  → 출력 **무변** · `외` 없음            (과잉 교정을 막는다)
 *   ③ 상한 초과            → 잘리고 **`외 N종` 을 말한다**        (상한이 다시 조용해지는 것을 막는다)
 *   ④ 액션 params 5키      → 4개 + `외 1종`                       (형제 소비처의 침묵을 막는다)
 *
 * ★픽스처는 **저장소를 왕복한 값**을 재현한다(리터럴 dict 를 그리지 않는다). 동료 세션이
 * 오늘 정확히 이 축에서 값을 치렀다 — 렌더 락이 **Python dict(삽입 순서)** 를 태워서
 * "고쳤다"고 선언한 것이 저장 계층을 통과하며 무효화됐다.
 * → 자문: ***"내 락이 태우는 값이 저장소를 왕복한 값인가, 그 전의 값인가?"***
 *
 * ★그리고 **그 정렬 모델 자체도 검증 대상이다** — 모델이 틀리면 이 파일 전체가 틀린 전제
 * 위에 선다. 그래서 모델을 **라이브 관측 앞 8키**와 대조하는 단언을 따로 둔다.
 */
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";

const getMock = vi.fn();
vi.mock("@/lib/api-client", () => ({
  apiClient: { get: (...a: unknown[]) => getMock(...a), post: vi.fn() },
  ApiClientError: class extends Error { status = 500 },
}));
vi.mock("@/lib/use-is-admin", () => ({ useIsAdmin: () => true }));

import { GrowthDashboard, summarizeParams } from "../GrowthDashboard";

/**
 * Postgres `jsonb` 의 키 정렬을 재현한다 — **(키 길이, 바이트순)**.
 * 삽입 순서를 일부러 무너뜨려, 리터럴 dict 로는 절대 안 잡히는 것이 잡히게 한다.
 */
function asJsonb<T extends Record<string, unknown>>(o: T): T {
  const enc = new TextEncoder();
  const cmp = (a: string, b: string) => {
    if (a.length !== b.length) return a.length - b.length;
    const A = enc.encode(a), B = enc.encode(b);
    for (let i = 0; i < Math.min(A.length, B.length); i++) if (A[i] !== B[i]) return A[i] - B[i];
    return 0;
  };
  const out: Record<string, unknown> = {};
  for (const k of Object.keys(o).sort(cmp)) out[k] = o[k];
  return out as T;
}

/** 라이브 `growth_capture` 17키. ★삽입 순서를 **진단 키가 앞에 오도록** 일부러 써 둔다 — */
/*  그러면 `asJsonb` 가 그것을 뒤로 밀어내므로, 왕복을 안 거치는 픽스처와 결과가 갈린다.  */
const CAPTURE_RAW = {
  queue_depth: 7, lost_total: 3, loss_rate_pct: 1.5, producer_build_id: "abc12345",
  at: "2026-09-02T13:12:35Z", flushed: 120, requeued: 4, max_queue: 500,
  flush_limit: 200, counter_scope: "api", flush_failures: 2, max_flush_retry: 3,
  dropped_overflow: 0, cancelled_requeued: 1, dropped_after_retry: 0,
  consecutive_failures: 0, max_sustained_per_sec: 12,
};
const CAPTURE = asJsonb(CAPTURE_RAW);

/** 음성 대조군 — 라이브 `threshold.fallback_warn_pct` 와 같은 4키. */
const SMALL = asJsonb({ value: 12, cap_pct: 30, previous: 10, proposed: 15 });

const flag = (key: string, scope: string, value: Record<string, unknown>) => ({
  key, scope, value, ttl_expires_at: null, updated_by: "test", updated_at: "2026-09-02T13:00:00Z",
});

beforeEach(() => {
  getMock.mockReset();
  getMock.mockImplementation((url: string) =>
    typeof url === "string" && url.includes("/growth/heal-log")
      ? Promise.resolve({
          actions: [],
          active_flags: [flag("growth_capture", "api", CAPTURE), flag("threshold.fallback_warn_pct", "global", SMALL)],
          total: 2,
        })
      : Promise.resolve({ items: [], total: 0, actionable_counts: {} }));
});

describe("★모델 검증 — jsonb 정렬 재현이 라이브와 같은가", () => {
  it("라이브 관측 앞 8키와 일치한다(모델이 틀리면 이 파일 전체가 틀린 전제 위에 선다)", () => {
    // 2026-09-02 라이브 `/growth/heal-log` 실측 — scope=api·worker 둘 다 동일했다.
    const LIVE_FIRST_8 = ["at", "flushed", "requeued", "max_queue", "lost_total", "flush_limit", "queue_depth", "counter_scope"];
    expect(Object.keys(CAPTURE).slice(0, 8)).toEqual(LIVE_FIRST_8);
  });

  it("★왕복이 실제로 순서를 바꾼다(픽스처가 공허하지 않다)", () => {
    // 이 단언이 깨지면 asJsonb 가 아무 일도 안 하고 있다는 뜻 = 픽스처가 결함을 재현 못 함.
    expect(Object.keys(CAPTURE)).not.toEqual(Object.keys(CAPTURE_RAW));
    expect(Object.keys(CAPTURE_RAW)[0]).toBe("queue_depth");   // 내가 앞에 뒀는데
    expect(Object.keys(CAPTURE)[0]).toBe("at");                // 저장을 통과하면 밀려난다
  });
});

describe("summarizeParams — 네 모집단", () => {
  it("① 17키: 진단 키가 **전부** 출력에 있다(종전엔 앞 4키만이었다)", () => {
    const out = summarizeParams(CAPTURE, 40);
    for (const k of ["lost_total", "loss_rate_pct", "queue_depth", "dropped_overflow", "consecutive_failures"]) {
      expect(out, `★${k} 가 화면에서 사라졌다`).toContain(k);
    }
    // 공허 진리 가드 — 대상이 실제로 17키인가(0키를 «전부 보인다»로 읽지 않게)
    expect(Object.keys(CAPTURE).length).toBe(17);
    expect(out).not.toContain("외 ");   // 상한 미만이므로 버릴 게 없다
  });

  it("② 4키: 출력 무변 · 절단을 **말하지 않는다**(과잉 교정 금지)", () => {
    const out = summarizeParams(SMALL, 40);
    expect(out).not.toContain("외 ");
    // 두 모집단이 갈리는지 — ①은 길고 ②는 짧아야 한다(같은 값이면 배선을 끊어도 통과한다)
    expect(out.length).toBeLessThan(summarizeParams(CAPTURE, 40).length);
  });

  it("③ 상한 초과: 잘리고 **`외 N종`** 을 말하며, N 이 실제 버린 수와 일치한다", () => {
    const CAP = 5;
    const out = summarizeParams(CAPTURE, CAP);
    // ★기대값을 상수로 못 박지 않고 **입력에서 파생**시킨다(자기지시 기대값 금지).
    const expected = Object.values(CAPTURE).filter((v) => v !== null && v !== undefined).length - CAP;
    expect(expected).toBeGreaterThan(0);          // 이 케이스가 실제로 절단을 만드는가
    expect(out).toContain(`외 ${expected}종`);
  });

  it("④ 액션 params 5키: 기본 상한 4 + `외 1종`(형제 소비처도 침묵하지 않는다)", () => {
    const out = summarizeParams({ a: 1, b: 2, c: 3, d: 4, e: 5 });
    expect(out).toContain("외 1종");
    expect(summarizeParams({ a: 1, b: 2, c: 3, d: 4 })).not.toContain("외 ");
  });

  /**
   * ★이 케이스는 처음에 **변이 생존**을 냈다. `not.toContain("외 ")` 만 보고 있었는데,
   * 필터를 무력화해도 4키 입력에서는 `rest` 가 0 이라 그 단언이 **여전히 참**이었다.
   * → **음성만 보지 말고 출력 자체를 못 박는다**(null 이 화면에 실리는 것을 직접 잡는다).
   */
  it("★null 은 출력에도 분모에도 안 들어간다 — 빈 칸을 「감춘 것」으로 세면 거짓말이 된다", () => {
    // 상한(4)보다 **표시 가능한 키가 많은** 입력이라야 필터 유무가 결과를 가른다.
    const out = summarizeParams({ a: 1, b: null, c: undefined, d: 2, e: 3, f: 4 });
    expect(out, "★null 이 화면에 실렸다").not.toContain("null");
    expect(out, "★undefined 가 화면에 실렸다").not.toContain("undefined");
    expect(out).not.toContain("외 ");          // 표시 가능한 4키가 상한과 같으므로 버릴 게 없다
    expect(out).toBe("a 1 · d 2 · e 3 · f 4"); // ★출력을 못 박는다(음성 단언만으로는 안 잠긴다)
  });
});

/**
 * ★플래그 카드는 **조건부 렌더**다 — 기본 탭이 `insights` 라 `HealSection` 이 아예 없다.
 * 그 상태를 만들지 않고 단언하면 «대상이 0개라 위반 0» 인 **공허한 초록**이 된다.
 * (실제로 이 파일 첫 실행에서 그렇게 실패했다 — 상태를 안 만들었기 때문이다.)
 */
async function openHealTab() {
  render(<GrowthDashboard />);
  fireEvent.click(await screen.findByText("자가치유 현황"));
  await waitFor(() => expect(getMock.mock.calls.some((c) => String(c[0]).includes("/growth/heal-log"))).toBe(true));
}

describe("★배선 — 화면이 실제로 그 상한으로 그리는가", () => {
  it("렌더 결과에 `lost_total` 이 **보인다**(유닛 락만으로는 배선이 안 잠긴다)", async () => {
    await openHealTab();
    // 공허 진리 가드 — 플래그 카드 자체가 그려졌는가(대상 존재를 먼저 단언한다)
    await screen.findByText(/2건 적용 중/);
    const body = document.body.textContent ?? "";
    expect(body, "★lost_total 이 화면에서 사라졌다 — 배선이 끊겼다").toContain("lost_total");
    expect(body, "★loss_rate_pct 가 화면에서 사라졌다").toContain("loss_rate_pct");
    expect(body).toContain("queue_depth");
  });

  it("★음성 대조군: 4키 플래그는 그려지되 절단 문구가 **없다**", async () => {
    await openHealTab();
    await screen.findByText(/2건 적용 중/);
    const body = document.body.textContent ?? "";
    expect(body).toContain("cap_pct");
    // ★두 모집단이 같은 실행에서 갈린다: 17키는 다 보이고, 4키에는 「외 N종」이 안 붙는다.
    expect(body).not.toContain("외 ");
  });
});
