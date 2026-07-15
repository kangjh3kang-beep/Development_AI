import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { KakaoCallbackWorkspaceClient } from "@/components/auth/KakaoCallbackWorkspaceClient";
import { apiClient } from "@/lib/api-client";

const { pushMock, replaceMock } = vi.hoisted(() => ({
  pushMock: vi.fn(),
  replaceMock: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: pushMock,
    replace: replaceMock,
  }),
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
  apiClient: {
    post: vi.fn(),
  },
}));

describe("KakaoCallbackWorkspaceClient", () => {
  beforeEach(() => {
    window.localStorage.clear();
    window.sessionStorage.clear();
    pushMock.mockReset();
    replaceMock.mockReset();
    vi.mocked(apiClient.post).mockReset();
  });

  it("exchanges the Kakao code(+state), stores tokens, and enables dashboard entry", async () => {
    // 로그인 시작 시 보관한 state와 콜백 state가 일치 → 정상 교환.
    window.sessionStorage.setItem("kakao_oauth_state", "st-abc");
    vi.mocked(apiClient.post).mockResolvedValue({
      access_token: "kakao-access-001",
      refresh_token: "kakao-refresh-001",
      expires_in: 3600,
    });

    render(
      <KakaoCallbackWorkspaceClient
        locale="en"
        code="kakao-code-123"
        state="st-abc"
        redirectUri="https://propai.ai/auth/kakao/callback"
      />,
    );

    await waitFor(() => {
      expect(apiClient.post).toHaveBeenCalledWith(
        "/auth/kakao/callback",
        expect.objectContaining({
          useMock: false,
          body: {
            code: "kakao-code-123",
            state: "st-abc",
            redirect_uri: "https://propai.ai/auth/kakao/callback",
          },
        }),
      );
    });

    expect(
      await screen.findByText("You're signed in"),
    ).toBeInTheDocument();
    expect(window.localStorage.getItem("propai_access_token")).toBe(
      "kakao-access-001",
    );
    // 성공 후 보관 state 제거(재사용 방지).
    expect(window.sessionStorage.getItem("kakao_oauth_state")).toBeNull();
  });

  it("blocks the exchange on state mismatch (CSRF/session-fixation)", async () => {
    // 보관 state와 콜백 state 불일치 → 교환하지 않고 보안 오류 표시.
    window.sessionStorage.setItem("kakao_oauth_state", "st-legit");

    render(
      <KakaoCallbackWorkspaceClient
        locale="en"
        code="attacker-code"
        state="st-forged"
        redirectUri={null}
      />,
    );

    await waitFor(() => {
      expect(
        screen.getByText("Security check failed. Please start the login over."),
      ).toBeInTheDocument();
    });
    expect(apiClient.post).not.toHaveBeenCalled();
  });

  it("surfaces a parameter error when the callback payload is incomplete", async () => {
    render(
      <KakaoCallbackWorkspaceClient
        locale="en"
        code={null}
        state={null}
        redirectUri={null}
      />,
    );

    expect(
      screen.getByText("The sign-in info is invalid. Please start over."),
    ).toBeInTheDocument();
    expect(apiClient.post).not.toHaveBeenCalled();
  });
});
