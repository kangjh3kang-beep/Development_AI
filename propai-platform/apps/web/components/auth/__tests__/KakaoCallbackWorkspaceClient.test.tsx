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
    pushMock.mockReset();
    replaceMock.mockReset();
    vi.mocked(apiClient.post).mockReset();
  });

  it("exchanges the Kakao code, stores tokens, and enables dashboard entry", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({
      access_token: "kakao-access-001",
      refresh_token: "kakao-refresh-001",
      expires_in: 3600,
    });

    render(
      <KakaoCallbackWorkspaceClient
        locale="en"
        code="kakao-code-123"
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
            redirect_uri: "https://propai.ai/auth/kakao/callback",
          },
        }),
      );
    });

    expect(
      await screen.findByText("Welcome back. Taking you to the dashboard."),
    ).toBeInTheDocument();
    expect(window.localStorage.getItem("propai_access_token")).toBe(
      "kakao-access-001",
    );
    expect(window.localStorage.getItem("propai_refresh_token")).toBe(
      "kakao-refresh-001",
    );
  });

  it("surfaces a parameter error when the callback payload is incomplete", async () => {
    render(
      <KakaoCallbackWorkspaceClient
        locale="en"
        code={null}
        redirectUri={null}
      />,
    );

    expect(
      screen.getByText("The sign-in info is invalid. Please start over."),
    ).toBeInTheDocument();
    expect(apiClient.post).not.toHaveBeenCalled();
  });
});
