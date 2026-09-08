/**
 * ★「등록 안 된 현장」 패널 — **렌더**를 태운다.
 *
 * 【왜 · 2026-09-09 Stage 2】
 * 종전 현장 리스트의 빈 상태는 이렇게 끝났다:
 *
 * > 소속된 현장이 없습니다. **현장 관리자가 조직도에 추가하면** 여기에 표시됩니다.
 *
 * 사용자가 할 수 있는 일이 **없었다**. 신청은 «공고» 를 대상으로만 가능했으므로
 * (`market.apply_post`), 공고를 안 올린 현장에는 «들어가고 싶다» 를 말할 방법이 아예 없었다.
 *
 * 【이 락이 잠그는 것 — 전부 두 모집단】
 * ① 이미 멤버인 현장은 **안 보이고**, 아닌 현장은 **보인다**
 * ② `pending` 은 **대기 배지**, `none` 은 **신청 버튼**(두 값이 다른 행동을 뜻한다)
 * ③ 신청을 누르면 **실제로 POST 가 나가고**, 그 카드가 대기 상태로 바뀐다
 * ④ 서버가 `already_member` 를 주면 **낙관적 pending 을 지어내지 않고** 목록에서 뺀다
 *
 * ★④가 없으면 «서버 응답을 안 읽고 pending 으로 칠하는» 구현이 통과한다 —
 *   저장소가 여러 번 데인 «응답을 버리는» 형태다.
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

import DiscoverSitesPanel, {
  DISCOVER_RELATIONS,
  selectJoinable,
  type DiscoverSite,
} from "../DiscoverSitesPanel";

const SITES: DiscoverSite[] = [
  { site_id: "s-active", site_name: "이미소속현장", status: "PREP", membership: "active" },
  { site_id: "s-pending", site_name: "신청중현장", status: "PREP", membership: "pending" },
  { site_id: "s-open", site_name: "신청가능현장", status: "OPEN", membership: "none" },
];

beforeEach(() => {
  getMock.mockReset();
  postMock.mockReset();
  getMock.mockResolvedValue(SITES);
});

describe("selectJoinable — 무엇을 보여줄지의 계약", () => {
  it("★이미 멤버인 현장은 빼고, 나머지는 남긴다(두 모집단)", () => {
    const out = selectJoinable(SITES);
    expect(out.map((s) => s.site_id)).toEqual(["s-pending", "s-open"]);
    // 반대편도 단언 — 「전부 뺀다」/「전부 남긴다」와 구별한다.
    expect(out.some((s) => s.membership === "active")).toBe(false);
    expect(out.length).toBeGreaterThan(0);
  });

  it("관계 어휘가 셋이다 — 하나로 뭉개면 화면이 무엇을 보여줄지 정할 수 없다", () => {
    expect([...DISCOVER_RELATIONS].sort()).toEqual(["active", "none", "pending"]);
  });
});

describe("DiscoverSitesPanel — 렌더", () => {
  it("★발견 목록을 **그 엔드포인트에서** 읽는다(경로 축 — 아무도 안 보던 자리)", async () => {
    render(<DiscoverSitesPanel />);
    await screen.findByText("신청가능현장");
    expect(getMock).toHaveBeenCalledWith("/sales/sites/discover");
  });

  it("★신청 가능한 현장에는 **신청 버튼**, 대기 중에는 **대기 배지**", async () => {
    render(<DiscoverSitesPanel />);
    expect(await screen.findByText("신청가능현장")).toBeTruthy();
    expect(screen.getByText("신청중현장")).toBeTruthy();
    // 두 값이 서로 다른 것을 그린다.
    expect(screen.getByText("등록신청")).toBeTruthy();
    expect(screen.getByText("승인 대기")).toBeTruthy();
  });

  it("★★이미 멤버인 현장은 **안 그린다**(위쪽 「내 현장」이 그 자리다)", async () => {
    render(<DiscoverSitesPanel />);
    await screen.findByText("신청가능현장");
    expect(screen.queryByText("이미소속현장")).toBeNull();
  });

  it("★신청을 누르면 **실제로 POST 가 나가고** 그 카드가 대기로 바뀐다", async () => {
    postMock.mockResolvedValue({ status: "pending", already_member: false });
    render(<DiscoverSitesPanel />);
    fireEvent.click(await screen.findByText("등록신청"));

    await waitFor(() => expect(postMock).toHaveBeenCalled());
    // ★★경로를 **정확히** 못 박는다(적대 리뷰 B-8). 앞 판은 `toContain("s-open")` 뿐이라
    //   경로가 통째로 깨져도(`join-requests-TYPO`) site id 만 들어 있으면 통과했다
    //   — 주석은 «무엇을 넘겼는가를 본다» 고 선언했는데 코드가 그 면역을 안 갖고 있었다.
    expect(postMock.mock.calls[0][0]).toBe("/sales/sites/s-open/join-requests");
    // 버튼이 사라지고 대기 배지가 둘이 된다(원래 1 + 방금 1).
    await waitFor(() => expect(screen.queryByText("등록신청")).toBeNull());
    expect(screen.getAllByText("승인 대기").length).toBe(2);
  });

  it("★★서버가 `already_member` 를 주면 **pending 을 지어내지 않고** 목록에서 뺀다", async () => {
    postMock.mockResolvedValue({ status: null, already_member: true });
    render(<DiscoverSitesPanel />);
    fireEvent.click(await screen.findByText("등록신청"));

    await waitFor(() => expect(screen.queryByText("신청가능현장")).toBeNull());
    // 낙관적으로 칠했다면 대기 배지가 2개가 됐을 것이다.
    expect(screen.getAllByText("승인 대기").length).toBe(1);
  });

  it("모두 소속이면 **그 사실을 말한다**(빈 화면은 진단 불가다)", async () => {
    getMock.mockResolvedValue([SITES[0]]);
    render(<DiscoverSitesPanel />);
    expect(await screen.findByText(/신청할 수 있는 현장이 없습니다/)).toBeTruthy();
  });

  it("조회 실패도 **말을 한다** — 침묵은 「현장이 없다」와 구별되지 않는다", async () => {
    getMock.mockRejectedValue(new Error("boom"));
    render(<DiscoverSitesPanel />);
    expect(await screen.findByText(/불러오지 못했습니다/)).toBeTruthy();
  });
});
