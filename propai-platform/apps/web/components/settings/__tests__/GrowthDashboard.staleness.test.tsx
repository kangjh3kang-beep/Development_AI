/**
 * ★**화면이 인사이트의 나이를 말하는가** — 「낡은 가득 찬 화면」이 건강해 보이지 않게.
 *
 * 【무엇이 있었나 · 라이브 실측 2026-09-05】
 * `status=open` critical **10건이 전부 2026-08-24 이전**(12일 전)인데, 화면은
 * `fmtDate(created_at)` 로 **절대 시각만** 그렸다. 상대 나이도, 「낡음」 표시도 없었다.
 * ★조사하던 세션이 그 목록을 보고 **「살아 있는 신호」로 읽고 우선순위를 세웠다** —
 *   이 락은 그 오독을 막는다. **결함의 1차 피해자가 그 세션 자신이었다.**
 *
 * 【형제】같은 파일의 **effectors 탭**은 `hours_since`·`state`·「최장 침묵 N시간」을 이미 그린다.
 *   insights 탭에만 없었다. 재발명하지 않고 같은 태도를 옮긴다.
 *
 * 【이 파일이 잠그는 것】
 * · 나이가 **실제로 렌더**된다(이름이 아니라 값)
 * · 절대 시각이 **사라지지 않는다**(대체가 아니라 **합성**)
 * · **두 모집단** — 방금 것과 오래된 것이 **다른 문자열**을 낸다
 * · 목록이 비지 않았는데 **요약이 없으면 실패**
 * ★**임계를 단언하지 않는다** — 이 PR 은 「며칠이면 낡음」을 정하지 않는다(그건 내가 정한 수다).
 */
import { render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const getMock = vi.fn();
vi.mock("@/lib/api-client", () => ({
  apiClient: { get: (...a: unknown[]) => getMock(...a), post: vi.fn() },
  ApiClientError: class extends Error { status = 500 },
}));
vi.mock("@/lib/use-is-admin", () => ({ useIsAdmin: () => true }));

import { GrowthDashboard, fmtAge } from "../GrowthDashboard";

const NOW = Date.parse("2026-09-05T12:00:00Z");
const OLD_ISO = "2026-08-24T12:00:00Z";   // 12일 전
const FRESH_ISO = "2026-09-05T11:30:00Z"; // 30분 전

function insight(id: string, created_at: string) {
  return {
    id, insight_type: "error_cluster", severity: "critical", status: "open",
    window_start: null, window_end: null, metrics_json: {},
    narrative: `n${id}`, recommended_action: "none", created_at,
  };
}

function mountWith(items: ReturnType<typeof insight>[]) {
  getMock.mockImplementation((path: string) => {
    if (typeof path === "string" && path.includes("/growth/insights")) {
      return Promise.resolve({ items, total: items.length, actionable_counts: { critical: items.length, warn: 0, info: 0 } });
    }
    return Promise.resolve({});
  });
  render(<GrowthDashboard />);
}

describe("fmtAge — 순수함수(시각을 인자로 받아 고정한다)", () => {
  it("★두 모집단이 다른 문자열을 낸다 — 같은 값이면 나이를 안 보는 구현도 통과한다", () => {
    const old = fmtAge(OLD_ISO, NOW);
    const fresh = fmtAge(FRESH_ISO, NOW);
    expect(old).toBe("12일 전");
    expect(fresh).toBe("30분 전");
    expect(old).not.toBe(fresh);
  });

  it("★모르는 것을 지어내지 않는다 — null·잘못된 값·미래 시각은 말하지 않는다", () => {
    expect(fmtAge(null, NOW)).toBeNull();
    expect(fmtAge("not-a-date", NOW)).toBeNull();
    // 미래 시각을 "방금"으로 위장하면 「모름」이 유효값을 입는다.
    expect(fmtAge("2026-09-06T00:00:00Z", NOW)).toBeNull();
  });

  it("경계 — 분·시간·일이 각각 자기 단위로 넘어간다", () => {
    expect(fmtAge(new Date(NOW - 30 * 1000).toISOString(), NOW)).toBe("방금");
    expect(fmtAge(new Date(NOW - 60 * 1000).toISOString(), NOW)).toBe("1분 전");
    expect(fmtAge(new Date(NOW - 60 * 60 * 1000).toISOString(), NOW)).toBe("1시간 전");
    expect(fmtAge(new Date(NOW - 24 * 60 * 60 * 1000).toISOString(), NOW)).toBe("1일 전");
  });
});

describe("인사이트 목록이 나이를 말한다", () => {
  // ★`shouldAdvanceTime` 없이 fake timer 를 켜면 `findBy*` 의 폴링이 멈춰 **타임아웃까지 기다린다**
  //   (실측: 이 파일 초판이 그래서 120초를 쓰고 4건 실패했다). 시각은 고정하되 타이머는 흐르게 둔다.
  beforeEach(() => {
    getMock.mockReset();
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.setSystemTime(NOW);
  });
  afterEach(() => { vi.useRealTimers(); });

  it("★★낡은 카드에 나이가 **실제로 실린다** — 그리고 절대 시각이 남는다(합성)", async () => {
    mountWith([insight("1", OLD_ISO)]);
    // 공허 진리 가드 — 단언 앞에 대상 존재를 먼저 확정한다.
    const ages = await screen.findAllByTestId("insight-age");
    expect(ages.length).toBe(1);
    expect(ages[0].textContent).toContain("12일 전");
    // ★대체가 아니라 합성 — 절대 시각을 지우면 이 단언이 죽는다.
    const line = ages[0].parentElement!;
    expect(line.textContent).toMatch(/\d{2}\. ?\d{1,2}\. ?\d{1,2}/);
  });

  it("★두 모집단을 같은 실행에서 — 낡은 것과 새 것이 다른 나이를 낸다", async () => {
    mountWith([insight("1", OLD_ISO), insight("2", FRESH_ISO)]);
    const ages = await screen.findAllByTestId("insight-age");
    expect(ages.length).toBe(2);
    const texts = ages.map((e) => e.textContent ?? "");
    expect(texts.some((t) => t.includes("12일 전"))).toBe(true);
    expect(texts.some((t) => t.includes("30분 전"))).toBe(true);
    // ★핵심 — 두 줄이 실제로 다르다. 나이를 안 보는 구현이면 같아진다.
    expect(texts[0]).not.toBe(texts[1]);
  });

  it("★★요약이 「이 화면이 언제 것인지」를 말한다 — 가장 최근 것 기준", async () => {
    mountWith([insight("1", OLD_ISO), insight("2", FRESH_ISO)]);
    const sum = await screen.findByTestId("insights-newest-age");
    // 가장 **최근** 것이어야 한다 — 가장 오래된 것을 쓰면 화면이 실제보다 낡아 보인다.
    expect(sum.textContent).toContain("30분 전");
    expect(sum.textContent).not.toContain("12일 전");
  });

  it("★대조군(음성) — 목록이 비면 요약도 나이도 뜨지 않는다", async () => {
    mountWith([]);
    // ★공허 진리 가드 — 대시보드 자체는 렌더됐는가.
    //   ★초판은 "인사이트 목록" 을 앵커로 썼는데 **그 카드가 조건부 렌더**라 목록이 비면 없다
    //     (대조군이 대상 부재로 죽는다). 항상 있는 탭 버튼을 앵커로 쓴다.
    await waitFor(() => expect(screen.getByRole("button", { name: "성장 인사이트" })).toBeTruthy());
    expect(screen.queryByTestId("insights-newest-age")).toBeNull();
    expect(screen.queryAllByTestId("insight-age").length).toBe(0);
  });

  // ★부채 — 이 락은 나이 **표시**를 잠글 뿐 **계산의 정확성**(시간대·서머타임·서버시계 편차)은
  //   잠그지 않는다. `fmtAge` 는 UTC ISO 를 받아 밀리초 차이만 보므로 로컬 시간대와 무관하지만,
  //   서버가 미래 시각을 보내는 경우(시계 편차)는 null 로만 접고 **경고하지 않는다.**
  it.todo("★부채: 서버 시계가 앞선 경우를 「모름」이 아니라 「시계 편차」로 구별한다");
});
