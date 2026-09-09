/**
 * ★승인자 패널 — **렌더**를 태운다(R2 리뷰 J-4).
 *
 * 【왜】 앞 판은 이 컴포넌트를 **렌더하는 테스트가 0건**이었다. 403 처리 · `membership_reason`
 * 표시 · decide 왕복이 전부 소스 문자열 grep 으로만 «잠겨» 있었고, 리뷰어가 decide 경로를
 * `/deciiide` 로 깨자 **17건 전부 초록**이었다(`::VERDICT=SURVIVED`).
 *
 * 형제 패널(`DiscoverSitesPanel`)에는 같은 라운드에 경로를 `toBe` 로 못 박아 놓고
 * **이쪽에는 안 걸었다** — 「지적된 자리만 고친다」의 재발이다. **2개 중 1개.**
 *
 * 【잠그는 것 — 전부 두 모집단】
 * ① 403(승인자 아님) → **아무것도 안 그린다** / 권한 있으면 목록을 그린다
 * ② 수락 시 **정확한 경로**로 POST 하고 body 에 `approve` 를 싣는다
 * ③ `membership_linked:false` → **사유를 사람 말로** 띄운다 / `true` → 조용하다
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const getMock = vi.fn();
const postMock = vi.fn();

vi.mock("@/lib/api-client", async (orig) => {
  const actual = await (orig as () => Promise<Record<string, unknown>>)();
  return {
    ...actual,
    apiClient: {
      ...(actual.apiClient as object),
      get: (...a: unknown[]) => getMock(...a),
      post: (...a: unknown[]) => postMock(...a),
    },
  };
});

import JoinRequestsPanel from "../JoinRequestsPanel";

const SITE = "site-1";
const ROW = {
  request_id: "req-1",
  user_id: "u-1",
  name: "지원자",
  email: "a@example.com",
  message: "합류 희망합니다",
  status: "pending",
  created_at: "2026-09-09T00:00:00Z",
};

beforeEach(() => {
  getMock.mockReset();
  postMock.mockReset();
  getMock.mockResolvedValue({ items: [ROW], count: 1 });
});

describe("JoinRequestsPanel — 렌더", () => {
  it("★신청 목록을 **그 엔드포인트에서** 읽는다(경로 축)", async () => {
    render(<JoinRequestsPanel siteId={SITE} />);
    await screen.findByText("지원자");
    expect(getMock).toHaveBeenCalledWith(`/sales/sites/${SITE}/join-requests`);
  });

  it("★★승인 권한이 없으면(403) **아무것도 안 그린다** — 오류로 보여 주지 않는다", async () => {
    const err = Object.assign(new Error("forbidden"), { status: 403 });
    getMock.mockRejectedValue(err);
    const { container } = render(<JoinRequestsPanel siteId={SITE} />);
    await waitFor(() => expect(container.textContent).toBe(""));
  });

  it("★★반대편 모집단 — 권한이 있으면 신청자를 그린다", async () => {
    render(<JoinRequestsPanel siteId={SITE} />);
    expect(await screen.findByText("지원자")).toBeTruthy();
    expect(screen.getByText("수락")).toBeTruthy();
    expect(screen.getByText("거절")).toBeTruthy();
  });

  it("★★수락이 **정확한 경로**로 나가고 `approve` 를 싣는다", async () => {
    postMock.mockResolvedValue({ membership_linked: true, membership_reason: "LINKED" });
    render(<JoinRequestsPanel siteId={SITE} />);
    fireEvent.click(await screen.findByText("수락"));

    await waitFor(() => expect(postMock).toHaveBeenCalled());
    // ★경로를 `toBe` 로 못 박는다 — 앞 판은 이 단언이 없어 오타 변이가 생존했다.
    expect(postMock.mock.calls[0][0]).toBe("/sales/join-requests/req-1/decide");
    expect(postMock.mock.calls[0][1]).toMatchObject({ body: { approve: true } });
  });

  it("★거절도 같은 경로에 `approve:false` 로", async () => {
    postMock.mockResolvedValue({ membership_linked: false, membership_reason: "DECLINED" });
    render(<JoinRequestsPanel siteId={SITE} />);
    fireEvent.click(await screen.findByText("거절"));

    await waitFor(() => expect(postMock).toHaveBeenCalled());
    expect(postMock.mock.calls[0][0]).toBe("/sales/join-requests/req-1/decide");
    expect(postMock.mock.calls[0][1]).toMatchObject({ body: { approve: false } });
  });

  it("★★승인했는데 멤버십이 안 붙으면 **왜인지 말한다**", async () => {
    postMock.mockResolvedValue({
      membership_linked: false,
      membership_reason: "ORG_NOT_SEEDED",
    });
    render(<JoinRequestsPanel siteId={SITE} />);
    fireEvent.click(await screen.findByText("수락"));

    // 공용 모듈(`membership-reason`)이 옮긴 사람 말이 화면에 나온다.
    await waitFor(() => expect(screen.getByText(/조직도.*다시 승인/)).toBeTruthy());
  });

  it("★★반대편 — 정상 연결이면 **아무 경고도 안 뜬다**", async () => {
    postMock.mockResolvedValue({ membership_linked: true, membership_reason: "LINKED" });
    render(<JoinRequestsPanel siteId={SITE} />);
    fireEvent.click(await screen.findByText("수락"));

    await waitFor(() => expect(postMock).toHaveBeenCalled());
    expect(screen.queryByText(/다시 승인/)).toBeNull();
  });

  it("대기열이 비면 **그 사실을 말한다**(빈 화면은 진단 불가다)", async () => {
    getMock.mockResolvedValue({ items: [], count: 0 });
    render(<JoinRequestsPanel siteId={SITE} />);
    expect(await screen.findByText(/대기 중인 등록신청이 없습니다/)).toBeTruthy();
  });
});
