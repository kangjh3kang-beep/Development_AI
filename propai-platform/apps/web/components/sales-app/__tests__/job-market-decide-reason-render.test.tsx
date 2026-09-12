/**
 * ★★**렌더 락** — 멤버십 보류 사유가 **승인자의 화면까지** 도달하는가.
 *
 * 【왜 · 2026-09-08 적대 리뷰 M2】
 * 서버는 `membership_linked: boolean` 하나만 줬고 **여섯 상황이 같은 `false`** 였다.
 * 그리고 화면은 **그 boolean 마저 읽지 않고 버렸다**:
 *
 *     .then(() => loadApps())          ← 응답을 통째로 폐기
 *
 * 그래서 승인자는 «승인은 됐는데 조직도엔 아무도 없다» 를 **원인 없이** 마주쳤다.
 * 라이브 현장 대부분이 조직도 미시드라 그게 **기본 경로**였다.
 *
 * 【이 락이 형제 락과 다른 것】
 * `lib/sales-app/__tests__/membership-reason.test.ts` 는 **매핑 함수**를 태운다.
 * 그것만으로는 **컴포넌트가 그 함수를 안 부르거나 결과를 안 그려도** 초록이다 —
 * 저장소가 여러 번 데인 «호출을 잠그면 효과는 안 잠긴다» 그 자리다.
 * ⇒ 여기서는 **실제로 수락 버튼을 눌러** 사유 문구가 DOM 에 나타나는지 본다.
 *
 * 【두 모집단】보류(`ORG_NOT_SEEDED`)는 **문구가 뜨고**, 정상 연결(`LINKED`)은 **안 뜬다.**
 * 하나만 단언하면 «항상 띄운다»/«절대 안 띄운다» 와 구별되지 않는다.
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

import JobMarketPanel from "../JobMarketPanel";

const ME = { id: "u-author", name: "작성자", email: "author@example.com" };
const POST = {
  id: "p-1",
  kind: "hire",
  title: "분양 상담원 모집",
  body: "",
  region: "서울",
  author_user_id: ME.id,
  status: "open",
};
const APPLICATION = {
  id: "app-1",
  post_id: POST.id,
  applicant_user_id: "u-applicant",
  applicant_name: "지원자",
  applicant_email: "a@example.com",
  status: "applied",
  message: "",
};

function wireGet() {
  getMock.mockImplementation((url: string) => {
    if (url === "/auth/me") return Promise.resolve(ME);
    if (url.startsWith("/market/posts?")) return Promise.resolve({ items: [POST], count: 1 });
    if (url.includes("/applications")) return Promise.resolve({ items: [APPLICATION], count: 1 });
    return Promise.reject(new Error(`목킹되지 않은 GET: ${url}`));
  });
}

/** 목록 → 상세로 들어가 신청자 행이 그려질 때까지. */
async function openApplications() {
  render(<JobMarketPanel />);
  const card = await screen.findByText(POST.title);
  fireEvent.click(card);
  return screen.findByText("수락");
}

beforeEach(() => {
  getMock.mockReset();
  postMock.mockReset();
  wireGet();
});

describe("수락 결과의 «사유» 가 화면에 도달하는가", () => {
  it("대조군 — 신청자 목록과 수락 버튼이 실제로 그려진다", async () => {
    // ★공허 진리 가드. 이게 없으면 아래 «문구가 뜬다» 가 «버튼을 못 눌렀다» 와 구별되지 않는다.
    const accept = await openApplications();
    expect(accept).toBeTruthy();
  });

  it("★조직도 미시드 보류면 **조치를 안내하는 문구**가 뜬다", async () => {
    postMock.mockResolvedValue({
      id: APPLICATION.id,
      status: "accepted",
      membership_linked: false,
      membership_reason: "ORG_NOT_SEEDED",
    });

    fireEvent.click(await openApplications());

    await waitFor(() => {
      expect(screen.getByText(/조직도.*다시 승인/)).toBeTruthy();
    });
  });

  it("★★반대편 모집단 — 정상 연결되면 **아무 문구도 안 뜬다**", async () => {
    postMock.mockResolvedValue({
      id: APPLICATION.id,
      status: "accepted",
      membership_linked: true,
      membership_reason: "LINKED",
    });

    fireEvent.click(await openApplications());

    await waitFor(() => expect(postMock).toHaveBeenCalled());
    expect(screen.queryByText(/다시 승인/)).toBeNull();
  });

  it("★서버가 모르는 사유를 줘도 **침묵하지 않는다**(무진단이 종전 결함이다)", async () => {
    postMock.mockResolvedValue({
      id: APPLICATION.id,
      status: "accepted",
      membership_linked: false,
      membership_reason: "SOMETHING_SERVER_ADDED",
    });

    fireEvent.click(await openApplications());

    await waitFor(() => {
      expect(screen.getByText(/SOMETHING_SERVER_ADDED/)).toBeTruthy();
    });
  });
});
