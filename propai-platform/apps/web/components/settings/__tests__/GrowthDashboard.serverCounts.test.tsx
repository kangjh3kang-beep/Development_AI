/**
 * ★집계는 **서버가 준 값**이어야 한다 — 이 페이지(`limit`)를 세면 안 된다.
 *
 * 【무엇이 있었나 · 라이브 실측 2026-08-26】
 * 화면이 `?sort=severity&limit=200` 으로 받아 **그 200행을 세고** 있었다. 라이브 분포가
 * `critical 79 · warn 476 · info 2,544` 라 200행은 `critical 79 + warn 121` 로 채워지고
 * **`info` 는 0행** 온다. 그래서 요약 카드가 warn 을 **476이 아니라 121** 로 보여 줬다
 * (**74% 과소계상**). 즉 **페이지 크기가 집계를 결정**했다 — 집계가 아니라 표본이었다.
 *
 * 【이 테스트가 잡는 것】
 * ①서버 집계를 쓰는가(탐지) ②서버 값이 없으면 폴백하는가(특이도) ③`status=open` 을 실제로
 * 보내는가(배선) ④절단을 **말하는가**(종전엔 침묵했다).
 *
 * ★두 모집단이 갈리게 짰다 — 픽스처의 `items` 와 `actionable_counts` 를 **다른 값**으로 둔다.
 *   같은 값이면 어느 쪽을 읽든 통과해 **배선을 지워도 초록**이 된다.
 */
import { render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";

const getMock = vi.fn();
vi.mock("@/lib/api-client", () => ({
  apiClient: { get: (...a: unknown[]) => getMock(...a), post: vi.fn() },
  ApiClientError: class extends Error { status = 500 },
}));
vi.mock("@/lib/use-is-admin", () => ({ useIsAdmin: () => true }));

import { GrowthDashboard } from "../GrowthDashboard";

/** items 는 2건뿐인데 서버 집계는 465 — **두 모집단이 다르다.** */
const RES = {
  items: [
    { id: "1", insight_type: "fallback_rate", severity: "warn", status: "open",
      window_start: null, window_end: null, metrics_json: {}, narrative: "a",
      recommended_action: "heal", created_at: "2026-08-26T00:00:00Z" },
    { id: "2", insight_type: "error_cluster", severity: "critical", status: "open",
      window_start: null, window_end: null, metrics_json: {}, narrative: "b",
      recommended_action: "none", created_at: "2026-08-26T00:00:00Z" },
  ],
  total: 3083,
  actionable_counts: { critical: 74, warn: 465, info: 2000 },
};

/**
 * ★**어느 카드인지**까지 본다 — `findByText("3")` 은 화면 어딘가에 "3" 이 있으면 통과한다.
 *   독립 리뷰 실측: 폴백이 값을 엉뚱한 severity 에 귀속해도(`severityCounts.critical += 1`)
 *   그 단언은 **5건 전부 통과**했다(변이 SURVIVED). 대상을 안 태운 것이다.
 */
function cardValue(label: string): string {
  const title = screen.getByText(`${label} · 열린 인사이트`);
  const card = title.closest(".cc-panel");
  expect(card, `${label} 카드를 찾지 못했다 — 이 단언은 공허해진다`).not.toBeNull();
  return within(card as HTMLElement).getAllByText(/^\d+$/)[0].textContent ?? "";
}
/** 세 카드를 **한꺼번에** 못 박는다(하나만 보면 나머지 둘이 무잠금이다). */
function expectCards(critical: string, warn: string, info: string) {
  expect(cardValue("심각")).toBe(critical);
  expect(cardValue("주의")).toBe(warn);
  expect(cardValue("정보")).toBe(info);
}

beforeEach(() => {
  getMock.mockReset();
  getMock.mockImplementation((url: string) =>
    typeof url === "string" && url.includes("/growth/insights")
      ? Promise.resolve(RES)
      : Promise.resolve({ actions: [], active_flags: [], total: 0 }));
});

describe("GrowthDashboard — 집계는 서버 값", () => {
  it("★탐지: warn 을 **465**로 표시한다(페이지의 1건이 아니라)", async () => {
    render(<GrowthDashboard />);
    // 전제 도달 확인 — 조회가 실제로 일어났는가(공허한 통과 방지)
    await waitFor(() => expect(getMock).toHaveBeenCalled());
    await screen.findByText("465");
    // ★세 카드를 **전부** 못 박는다. 초판은 warn 하나만 봐서, 이 작업 계열의 존재 이유였던
    //   `info` 를 0 으로 되돌리는 변이(`serverCounts.info ?? 0` → `0`)가 **통과**했다
    //   (독립 리뷰 실측 · SURVIVED). PR 이 "가장 날카롭다"고 선언한 수치가 무잠금이었다.
    expectCards("74", "465", "2000");
  });

  it("★배선: 조회 URL 에 status=open 이 실린다", async () => {
    render(<GrowthDashboard />);
    await waitFor(() => expect(getMock).toHaveBeenCalled());
    const urls = getMock.mock.calls.map((c) => String(c[0]));
    const insightCall = urls.find((u) => u.includes("/growth/insights"));
    expect(insightCall).toBeDefined();
    expect(insightCall).toContain("status=open");
  });

  it("★절단을 말한다 — 종전엔 총계만 띄우고 침묵했다", async () => {
    render(<GrowthDashboard />);
    await waitFor(() => expect(getMock).toHaveBeenCalled());
    await screen.findByText(/나머지는 목록에 없습니다/);
  });

  it("★특이도: 서버가 집계를 안 주면 폴백한다 — **어느 카드에 얼마가** 그려지는지까지", async () => {
    // ★초판 단언은 `queryByText("465")).toBeNull()` **하나뿐**이라 아무것도 안 그려도 통과했다.
    //   그 뒤 `findByText("3")` 을 더했지만 **어느 카드인지 안 봐서** 값을 엉뚱한 severity 에
    //   귀속하는 변이가 여전히 통과했다(독립 리뷰 실측). 카드별로 못 박는다.
    // ★★픽스처를 **이질화**한다 — 폴백의 술어는 `status === "open"` **이면서 비조치 타입이
    //   아닌 것**이다. 균질하면 그 술어를 통째로 지워도(`openInsights` → `insights`) 통과한다.
    const mk = (id: string, severity: string, status: string, insight_type: string) => ({
      id, insight_type, severity, status,
      window_start: null, window_end: null, metrics_json: {}, narrative: "x",
      recommended_action: "heal", created_at: "2026-08-26T00:00:00Z",
    });
    const MIXED = [
      mk("w1", "warn", "open", "fallback_rate"),
      mk("w2", "warn", "open", "fallback_rate"),
      mk("w3", "warn", "open", "fallback_rate"),
      mk("w4", "warn", "acknowledged", "fallback_rate"),   // ★열림 아님 → 세면 안 된다
      mk("i1", "info", "open", "latency_baseline"),        // ★비조치 타입 → 세면 안 된다
      mk("i2", "info", "open", "latency_baseline"),
    ];
    getMock.mockImplementation((url: string) =>
      typeof url === "string" && url.includes("/growth/insights")
        ? Promise.resolve({ items: MIXED, total: 3083 })   // actionable_counts 없음
        : Promise.resolve({ actions: [], active_flags: [], total: 0 }));
    render(<GrowthDashboard />);
    await waitFor(() => expect(getMock).toHaveBeenCalled());
    await screen.findByText(/현재 목록/);

    // ①양성 — 술어를 통과한 것만 센다: warn 3(acknowledged 1 제외) · info 0(비조치 2 제외).
    expectCards("0", "3", "0");
    // ②음성 — 서버 값은 아니다(두 모집단이 갈린다).
    expect(screen.queryByText("465")).toBeNull();
    // ③★**말하는가** — 침묵이 이 결함의 본체다. 방향(과소)까지 본다.
    await screen.findByText(/실제보다 적습니다/);
  });

  it("★`{}` 는 폴백이 아니다 — 서버가 세었는데 조치 대상이 0 인 경우", async () => {
    // ★주석이 이 동작을 **주장**하는데 락이 없었다(독립 리뷰 실측: `Boolean(serverCounts)` 를
    //   `Object.keys(...).length > 0` 으로 바꾸는 변이가 SURVIVED — 화면이 서버 0 을 그리면서
    //   "현재 목록에서 셌습니다" 라고 **거짓말**하는 상태가 통과했다).
    // ★라이브에서 실제로 나온다: `status=open&insight_type=latency_baseline` → `actionable_counts: {}`.
    getMock.mockImplementation((url: string) =>
      typeof url === "string" && url.includes("/growth/insights")
        ? Promise.resolve({ items: RES.items, total: 2, actionable_counts: {} })
        : Promise.resolve({ actions: [], active_flags: [], total: 0 }));
    render(<GrowthDashboard />);
    await waitFor(() => expect(getMock).toHaveBeenCalled());
    expectCards("0", "0", "0");
    expect(screen.queryByText(/현재 목록/), "서버가 세었는데 폴백 고지가 떴다 — 화면이 거짓말한다").toBeNull();
  });

  it("★빈 목록에서는 고지를 띄우지 않는다 — 빈 상태 안내와 동시에 뜨면 모순이다", async () => {
    // 독립 리뷰 실측: 게이트가 `!countsFromServer` 뿐이라 목록이 0건이어도 고지가 렌더됐다.
    // 그러면 *"실제보다 적습니다"* 와 *"아직 …없습니다"* 가 한 화면에 함께 뜬다.
    getMock.mockImplementation((url: string) =>
      typeof url === "string" && url.includes("/growth/insights")
        ? Promise.resolve({ items: [], total: 0 })   // actionable_counts 없음 + 빈 목록
        : Promise.resolve({ actions: [], active_flags: [], total: 0 }));
    render(<GrowthDashboard />);
    await waitFor(() => expect(getMock).toHaveBeenCalled());
    await screen.findByText(/아직 수집·분석된 성장 인사이트가 없습니다/);
    expect(screen.queryByText(/현재 목록/), "빈 목록인데 폴백 고지가 떴다").toBeNull();
  });

  it("★대조군: 서버가 집계를 주면 그 고지는 **뜨지 않는다**(상시 문구면 무의미하다)", async () => {
    // 고지가 항상 떠 있으면 ③은 폴백을 증명하지 못한다 — 두 모집단으로 가른다.
    render(<GrowthDashboard />);   // beforeEach 의 기본 응답 = actionable_counts 있음
    await screen.findByText("465");
    expect(screen.queryByText(/현재 목록/)).toBeNull();
  });
});
