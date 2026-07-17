import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ProfileClient } from "@/components/mypage/ProfileClient";
import { apiClient } from "@/lib/api-client";

vi.mock("next/navigation", () => ({
  usePathname: () => "/ko/mypage/profile",
}));

vi.mock("@/lib/api-client", () => ({
  ApiClientError: class ApiClientError extends Error {
    status: number;
    payload: unknown;
    constructor(message: string, status: number, payload: unknown) {
      super(message);
      this.status = status;
      this.payload = payload;
    }
  },
  apiV1BaseUrl: () => "http://test/api/v1",
  apiClient: { get: vi.fn(), post: vi.fn(), patch: vi.fn() },
}));

describe("ProfileClient", () => {
  beforeEach(() => {
    vi.mocked(apiClient.get).mockReset();
    vi.mocked(apiClient.patch).mockReset();
  });

  it("이름·전화 수정을 PATCH /auth/me로 보낸다(이메일은 읽기전용)", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({
      name: "강재희",
      email: "user@example.com",
      phone: null,
      email_verified: true,
    });
    vi.mocked(apiClient.patch).mockResolvedValue({
      name: "강개발",
      email: "user@example.com",
      phone: "010-1234-5678",
      email_verified: true,
    });

    render(<ProfileClient locale="ko" />);
    const nameInput = await screen.findByLabelText("이름");
    await userEvent.clear(nameInput);
    await userEvent.type(nameInput, "강개발");
    await userEvent.type(screen.getByLabelText(/휴대전화/), "010-1234-5678");
    await userEvent.click(screen.getByRole("button", { name: "저장" }));

    await waitFor(() => {
      expect(apiClient.patch).toHaveBeenCalledWith(
        "/auth/me",
        expect.objectContaining({
          body: { name: "강개발", phone: "010-1234-5678" },
          useMock: false,
        }),
      );
    });
    expect(await screen.findByText("프로필이 저장되었습니다.")).toBeInTheDocument();
    expect(screen.getByLabelText(/이메일/)).toBeDisabled();
  });

  it("로드 실패를 '미인증' 허위 단정 없이 오류로 표시한다(거짓 성공 위장 방지)", async () => {
    vi.mocked(apiClient.get).mockRejectedValue(new Error("boom"));
    render(<ProfileClient locale="ko" />);
    expect(await screen.findByText(/프로필 정보를 불러오지 못했습니다/)).toBeInTheDocument();
    // 로드 실패 시 인증 상태 문구(인증/미인증)를 아예 표기하지 않는다.
    expect(screen.queryByText(/이메일 인증이 아직 완료되지 않았습니다/)).toBeNull();
    expect(screen.queryByText("인증 완료된 이메일입니다.")).toBeNull();
  });
});
