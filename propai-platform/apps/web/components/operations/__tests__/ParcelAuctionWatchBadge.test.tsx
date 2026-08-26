/**
 * ★사용자 신고 회귀 잠금(2026-08-25) — *"해당 필지(프로젝트)의 경·공매 현황 모니터링과
 * 연동도 안 되고 있다"*.
 *
 * ## 연동은 되어 있었다 — 보이지 않았을 뿐이다
 *
 * `GET /auction/watchlist` 는 호출마다 `sync_landschedule_targets()` 로 **토지조서 필지를
 * 자동 등록**하고, 매칭은 PNU 직접 → 주소 부분 → 폴리곤 순으로 돈다. 토지조서·종합분석
 * 화면에도 `공·경매` 지도 레이어가 배선돼 있다. 그런데:
 *  · 그 레이어는 **기본 꺼짐**(`SatongMapShell`: `new Set(["cadastre"])`)
 *  · 매칭 **결과**는 전용 `/auction` 페이지에서만 보인다
 *  · 등기·토지조서 화면에는 *"이 필지가 경매에 나왔는가"* 를 말하는 것이 **아무것도 없었다**
 *
 * ## ★이 파일이 잠그는 것 — "0건"을 뭉뚱그리지 않는다
 *
 * 침묵·0 은 여기서 **네 가지 다른 사실**이고 처방이 전부 다르다:
 *  ① 확인 중  ② 조회 실패  ③ 감시는 도는데 매칭 없음  ④ 필지 자체가 없음
 * 하나로 뭉치면 *"연동이 안 된다"* 는 오해가 그대로 재생산된다 — 그게 이 신고의 출발점이다.
 * 그래서 **네 상태가 서로 다른 문구를 내는지**를 각각 단언한다(전수 일치는 '둘 다 없음'과
 * 구별하지 못한다 — 대표 문구 존재도 함께 못 박는다).
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ParcelAuctionWatchBadge, countForProject } from "@/components/operations/ParcelAuctionWatchBadge";
import { apiClient } from "@/lib/api-client";

// ★스텁은 **계약을 좁히지 않는다**(§33). 첫 판은 `children`·`href` 만 넘기고
//   `data-testid`·`className` 을 **버려서**, 링크는 렌더되는데 testid 가 없어
//   "요소를 못 찾음"으로 실패했다 — 코드가 아니라 **스텁이 만든 실패**였다.
//   실측으로 확인했다(단독 실행은 통과 · DOM 을 찍어 보니 `<a href>` 는 있는데 testid 만 없음).
vi.mock("next/link", () => ({
  default: ({ children, href, ...rest }: { children: ReactNode; href: string } & Record<string, unknown>) => (
    <a href={href} {...rest}>{children}</a>
  ),
}));

vi.mock("@/lib/api-client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api-client")>();
  return { ...actual, apiClient: { ...actual.apiClient, get: vi.fn() } };
});

const PID = "prj-osan";

function wrap(ui: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return <QueryClientProvider client={qc}>{ui}</QueryClientProvider>;
}

const get = apiClient.get as unknown as ReturnType<typeof vi.fn>;

describe("필지 경·공매 배지 — 네 상태를 각각 다르게 말한다", () => {
  // ★목 상태를 **매 케이스마다** 초기화한다. 안 하면 앞 케이스의
  //   `mockReturnValue(영원히 pending)` / `mockRejectedValue` 가 남아 뒤 케이스가
  //   **타임아웃으로 실패**한다(실측: 단독 실행은 통과, 묶어 돌리면 두 건 실패).
  //   정리는 본문 끝이 아니라 훅에 둔다 — 실패하면 본문 끝에 도달하지 못한다.
  beforeEach(() => { get.mockReset(); });
  afterEach(() => { get.mockReset(); });

  it("④ 필지가 없으면 **감시 대상이 없다는 사실**을 말한다(0건이 아니다)", () => {
    get.mockReturnValue(new Promise(() => {}));
    render(wrap(<ParcelAuctionWatchBadge projectId={PID} parcelCount={0} />));
    expect(screen.getByTestId("auction-watch-empty-parcels")).toBeTruthy();
  });

  it("① 확인 중에는 **0으로 보이지 않는다**", () => {
    get.mockReturnValue(new Promise(() => {}));
    render(wrap(<ParcelAuctionWatchBadge projectId={PID} parcelCount={77} />));
    const el = screen.getByTestId("auction-watch-loading");
    expect(el.textContent ?? "").toContain("확인 중");
    // ★대조군: 이 상태에서 '매칭 없음' 문구가 같이 뜨면 안 된다(상태가 뭉친 것).
    expect(screen.queryByTestId("auction-watch-none")).toBeNull();
  });

  it("② 조회 실패는 **0건이 아니다** — 모르는 것을 없는 것으로 말하지 않는다", async () => {
    get.mockRejectedValue(new Error("boom"));
    render(wrap(<ParcelAuctionWatchBadge projectId={PID} parcelCount={77} />));
    const el = await waitFor(() => screen.getByTestId("auction-watch-error"));
    expect(el.textContent ?? "").toContain("확인하지 못했");
    expect(screen.queryByTestId("auction-watch-none")).toBeNull();
    expect(screen.queryByTestId("auction-watch-hit")).toBeNull();
  });

  it("③ 매칭이 없으면 **감시가 돌고 있다는 사실**을 함께 말한다", async () => {
    get.mockResolvedValue({ projects: [{ project_id: "other", items: [{ item_no: "x" }] }] });
    render(wrap(<ParcelAuctionWatchBadge projectId={PID} parcelCount={77} />));
    const el = await waitFor(() => screen.getByTestId("auction-watch-none"));
    const t = el.textContent ?? "";
    expect(t).toContain("자동 감시");        // ★"연동이 안 된다"는 오해를 여기서 끊는다
    expect(t).toContain("77");               // 감시 중인 필지 수를 말한다
  });

  it("★매칭이 있으면 건수와 링크를 준다", async () => {
    get.mockResolvedValue({
      projects: [{ project_id: PID, items: [{ item_no: "a" }, { item_no: "b" }] }],
    });
    render(wrap(<ParcelAuctionWatchBadge projectId={PID} parcelCount={77} locale="ko" />));
    const el = await waitFor(() => screen.getByTestId("auction-watch-hit"));
    expect(el.textContent ?? "").toContain("2");
    expect((el as HTMLAnchorElement).getAttribute("href")).toBe("/ko/auction");
  });

  it("★특이도 — 다른 프로젝트의 물건을 내 것으로 세지 않는다", () => {
    const data = {
      projects: [
        { project_id: "other", items: [{ item_no: "x" }, { item_no: "y" }, { item_no: "z" }] },
        { project_id: PID, items: [{ item_no: "a" }] },
      ],
    };
    // 순수 함수로 직접 — 렌더를 거치지 않아도 계수 규칙이 잠긴다.
    expect(countForProject(data, PID)).toBe(1);
    expect(countForProject(data, "other")).toBe(3);
    expect(countForProject(data, "없는프로젝트")).toBe(0);
    expect(countForProject(undefined, PID)).toBe(0);
  });
});
