/**
 * 설정 화면의 **웹훅 관리가 실제 서버와 이야기하는가.**
 *
 * ★배경(실측 2026-08-27): 이 패널은 `MOCK_WEBHOOKS` 를 렌더했다. 목록·등록·토글·삭제가
 * **전부 로컬 state 조작**이라, 사용자가 웹훅을 등록하면 화면은 성공했다고 말하고
 * **서버에는 아무 일도 일어나지 않았다.** 백엔드는 `/api/v1/webhooks` CRUD 7라우트가
 * **완비**돼 있었다 — 미배선이었고, 미배선보다 나쁘다(거짓말이다).
 *
 * ★그리고 목업은 **없는 필드를 지어냈다**: `last_delivery_status`·`last_delivered_at`·`active`.
 * 실제 계약은 `is_active` 이고 전송 이력은 별도 경로다. 지어낸 것을 화면에 만들지 않는다.
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { get, post, put, del } = vi.hoisted(() => ({
  get: vi.fn(), post: vi.fn(), put: vi.fn(), del: vi.fn(),
}));

// ★`vi.mock` 은 파일 최상단으로 **호이스팅**된다 — 팩토리 밖 변수를 참조하면
//   "Cannot access before initialization" 으로 죽는다(첫 실행에서 그랬다).
//   `vi.fn()` 은 `vi.hoisted` 로 올리고, 에러 클래스는 **팩토리 안에서** 만든다.
vi.mock("@/lib/api-client", () => {
  class ApiClientError extends Error {
    status: number;
    payload: unknown;
    constructor(message: string, status: number, payload: unknown) {
      super(message);
      this.status = status;
      this.payload = payload;
    }
  }
  return {
    ApiClientError,
    apiClient: {
      get: (...a: unknown[]) => get(...a),
      post: (...a: unknown[]) => post(...a),
      put: (...a: unknown[]) => put(...a),
      delete: (...a: unknown[]) => del(...a),
    },
  };
});

import { ApiClientError as FakeApiError } from "@/lib/api-client";
import { WebhookManagementPanel } from "@/components/settings/WebhookManagementPanel";

/** ★백엔드 계약(`WebhookResponse`) **그대로** — 스텁이 실제보다 좁으면 그 필드를 쓰는 코드가
 *  테스트에서만 터진다(스텁도 계약이다). */
const ROW = {
  id: "11111111-1111-1111-1111-111111111111",
  tenant_id: "22222222-2222-2222-2222-222222222222",
  url: "https://hooks.example.com/propai",
  events: ["project.created"],
  is_active: true,
  description: "운영 알림",
  created_at: "2026-08-01T00:00:00Z",
  updated_at: "2026-08-01T00:00:00Z",
};

beforeEach(() => {
  get.mockReset();
  post.mockReset();
  put.mockReset();
  del.mockReset();
  get.mockResolvedValue([ROW]);
});

describe("웹훅 관리 — 서버가 진실이다", () => {
  it("★목록을 **서버에서** 가져온다(목업이 아니다)", async () => {
    render(<WebhookManagementPanel />);
    await waitFor(() => expect(get).toHaveBeenCalled());
    expect(get.mock.calls[0][0]).toBe("/webhooks");
    expect(await screen.findByText(ROW.url)).toBeTruthy();
  });

  it("★두 모집단 — 서버가 준 것만 그린다(지어낸 행이 없다)", async () => {
    // 서버가 빈 배열이면 화면도 비어야 한다. 목업이면 이 단언이 깨진다.
    get.mockResolvedValue([]);
    const { container } = render(<WebhookManagementPanel />);
    await waitFor(() => expect(get).toHaveBeenCalled());
    expect(container.textContent).not.toContain("example.com/hooks/propai"); // 옛 목업 URL
    expect(container.textContent).not.toContain("hooks.example.com"); // 이번 픽스처 URL
  });

  it("★배열을 직접 받는다 — `{webhooks: []}` 래퍼를 가정하지 않는다", async () => {
    // 목업 시절 타입은 래퍼였다. 래퍼를 주면 화면이 비어야 정상(계약이 배열이므로).
    get.mockResolvedValue({ webhooks: [ROW] } as unknown as typeof ROW[]);
    const { container } = render(<WebhookManagementPanel />);
    await waitFor(() => expect(get).toHaveBeenCalled());
    expect(container.textContent).not.toContain(ROW.url);
  });

  it("등록이 **POST 를 실제로 보낸다**", async () => {
    post.mockResolvedValue({ ...ROW, id: "new", url: "https://new.example.com/h" });
    const user = userEvent.setup();
    render(<WebhookManagementPanel />);
    await waitFor(() => expect(get).toHaveBeenCalled());

    await user.click(screen.getByRole("button", { name: /웹훅 추가|추가/ }));
    const input = await screen.findByPlaceholderText(/https:\/\//i);
    await user.type(input, "https://new.example.com/h");
    // 이벤트 선택은 <label> 이 아니라 토글 <button> 이다(마크업 실측).
    await user.click(screen.getByRole("button", { name: "프로젝트 생성" }));
    await user.click(screen.getByRole("button", { name: /등록/ }));

    await waitFor(() => expect(post).toHaveBeenCalled());
    expect(post.mock.calls[0][0]).toBe("/webhooks");
    expect(post.mock.calls[0][1]).toMatchObject({
      body: { url: "https://new.example.com/h", events: ["project.created"] },
    });
  });

  it("★서버가 거부하면 화면도 바뀌지 않는다(낙관적 갱신 금지)", async () => {
    put.mockRejectedValue(new FakeApiError("nope", 403, { detail: "권한 없음" }));
    const user = userEvent.setup();
    render(<WebhookManagementPanel />);
    expect(await screen.findByText("활성")).toBeTruthy();

    // 토글 버튼의 이름은 현재 상태 문구다("활성" | "비활성") — 마크업 실측.
    const toggle = screen.getByRole("button", { name: "활성" });
    await user.click(toggle);
    await waitFor(() => expect(put).toHaveBeenCalled());

    // 실패했으므로 상태는 그대로 '활성' 이어야 한다.
    expect(screen.getByText("활성")).toBeTruthy();
    expect(await screen.findByText(/권한/)).toBeTruthy();
  });

  it("★오류를 삼키지 않는다 — 무엇이 막혔는지 화면이 말한다", async () => {
    get.mockRejectedValue(new FakeApiError("boom", 500, {}));
    render(<WebhookManagementPanel />);
    expect(await screen.findByText(/불러오지 못했습니다|HTTP 500/)).toBeTruthy();
  });
});
