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
import { render, screen, waitFor } from "@testing-library/react";
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
    expect(screen.queryByText("465")).not.toBeNull();
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

  it("★특이도: 서버가 집계를 안 주면 폴백한다 — **그리고 무엇을 보여 주는지까지** 잠근다", async () => {
    // ★초판은 단언이 `queryByText("465")).toBeNull()` **하나뿐**이었다. 그 단언은
    //   아무것도 안 그려도·0을 그려도·빈 상태로 떨어져도 **통과**한다
    //   (저장소 §「음성 단언은 아무것도 잠그지 않는다」). 양성을 함께 못 박는다.
    // ★페이지 집계가 **구별 가능한 수**를 내도록 warn 을 3건으로 둔다(전역 픽스처는 1건이라
    //   "1" 이 화면 다른 곳과 충돌한다 — 대조가 흐려진다).
    const WARN3 = Array.from({ length: 3 }, (_, i) => ({
      id: `w${i}`, insight_type: "fallback_rate", severity: "warn", status: "open",
      window_start: null, window_end: null, metrics_json: {}, narrative: "w",
      recommended_action: "heal", created_at: "2026-08-26T00:00:00Z",
    }));
    getMock.mockImplementation((url: string) =>
      typeof url === "string" && url.includes("/growth/insights")
        ? Promise.resolve({ items: WARN3, total: 3083 })   // actionable_counts 없음
        : Promise.resolve({ actions: [], active_flags: [], total: 0 }));
    render(<GrowthDashboard />);
    await waitFor(() => expect(getMock).toHaveBeenCalled());

    // ①양성 — 폴백은 **페이지 집계**를 그린다(3건).
    await screen.findByText("3");
    // ②음성 — 서버 값은 아니다(두 모집단이 갈린다).
    expect(screen.queryByText("465")).toBeNull();
    // ③★**말하는가** — 침묵이 이 결함의 본체다. 폴백 화면이 정상 화면과 구별돼야 한다.
    await screen.findByText(/현재 목록/);
  });

  it("★대조군: 서버가 집계를 주면 그 고지는 **뜨지 않는다**(상시 문구면 무의미하다)", async () => {
    // 고지가 항상 떠 있으면 ③은 폴백을 증명하지 못한다 — 두 모집단으로 가른다.
    render(<GrowthDashboard />);   // beforeEach 의 기본 응답 = actionable_counts 있음
    await screen.findByText("465");
    expect(screen.queryByText(/현재 목록/)).toBeNull();
  });
});
